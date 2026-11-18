<?php declare(strict_types=1);

/**
 * Copies all rows of an installed Shopware MariaDB into the PostgreSQL schema created by
 * docs/inventory/schema/mysql-to-pg-ddl.py. The PostgreSQL catalog drives the conversion:
 *
 *   uuid     <- BINARY(16), sent as 32 hex characters
 *   bytea    <- other binary / blob columns, sent as LOB
 *   boolean  <- TINYINT(1)
 *   jsonb    <- JSON text, sent unchanged
 *   generated columns are skipped, identity sequences are moved behind the copied maximum
 *
 * The target tables are truncated first, the whole copy runs in one transaction with foreign key
 * triggers disabled (session_replication_role = replica, needs a superuser).
 *
 * Usage inside the web container:
 *   php copy-data.php                 # MYSQL_URL (or DATABASE_URL) = MariaDB source, POSTGRES_URL = target
 *   php copy-data.php --schema=public
 */
$schema = 'public';
foreach (\array_slice($argv, 1) as $arg) {
    if (str_starts_with($arg, '--schema=')) {
        $schema = substr($arg, 9);
    }
}

function connect(string $url, string $driver): PDO
{
    $p = parse_url($url);
    if ($p === false || !isset($p['host'], $p['path'])) {
        throw new RuntimeException('Cannot parse database url for ' . $driver);
    }
    $dsn = sprintf('%s:host=%s;port=%d;dbname=%s', $driver, $p['host'], $p['port'] ?? ($driver === 'mysql' ? 3306 : 5432), ltrim($p['path'], '/'));
    if ($driver === 'mysql') {
        $dsn .= ';charset=utf8mb4';
    }

    return new PDO($dsn, rawurldecode($p['user'] ?? ''), rawurldecode($p['pass'] ?? ''), [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_STRINGIFY_FETCHES => true,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_NUM,
    ]);
}

function q(string $identifier): string
{
    return '"' . str_replace('"', '""', $identifier) . '"';
}

$mysql = connect((string) (getenv('MYSQL_URL') ?: getenv('DATABASE_URL')), 'mysql');
$mysql->exec("SET time_zone = '+00:00'");
$mysql->setAttribute(PDO::MYSQL_ATTR_USE_BUFFERED_QUERY, false);
$pg = connect((string) getenv('POSTGRES_URL'), 'pgsql');
$pg->exec("SET TIME ZONE 'UTC'");

$stmt = $pg->prepare(
    'SELECT table_name, column_name, data_type, is_identity
     FROM information_schema.columns
     WHERE table_schema = ? AND is_generated = \'NEVER\'
       AND table_name IN (SELECT table_name FROM information_schema.tables WHERE table_schema = ? AND table_type = \'BASE TABLE\')
     ORDER BY table_name, ordinal_position'
);
$stmt->execute([$schema, $schema]);
$tables = [];
foreach ($stmt->fetchAll() as [$table, $column, $type, $identity]) {
    $tables[$table][] = ['name' => $column, 'type' => $type, 'identity' => $identity === 'YES'];
}
if ($tables === []) {
    throw new RuntimeException('No tables in PostgreSQL schema ' . $schema);
}

$pg->beginTransaction();
$pg->exec('SET LOCAL session_replication_role = replica');
$pg->exec('SET LOCAL search_path TO ' . q($schema));
$pg->exec('TRUNCATE ' . implode(', ', array_map(q(...), array_keys($tables))) . ' RESTART IDENTITY');

$total = 0;
$copied = [];
foreach ($tables as $table => $columns) {
    $select = [];
    foreach ($columns as $column) {
        $name = '`' . $column['name'] . '`';
        $select[] = $column['type'] === 'uuid' ? 'LOWER(HEX(' . $name . '))' : $name;
    }
    $rows = $mysql->query('SELECT ' . implode(', ', $select) . ' FROM `' . $table . '`');

    $columnList = implode(', ', array_map(static fn (array $c): string => q($c['name']), $columns));
    $batchSize = max(1, min(500, intdiv(60000, \count($columns))));
    $count = 0;
    $batch = [];

    $flush = static function (array $batch) use ($pg, $table, $columns, $columnList): void {
        $rowPlaceholder = '(' . implode(', ', array_fill(0, \count($columns), '?')) . ')';
        $insert = $pg->prepare('INSERT INTO ' . q($table) . ' (' . $columnList . ') VALUES ' . implode(', ', array_fill(0, \count($batch), $rowPlaceholder)));
        $i = 0;
        foreach ($batch as $row) {
            foreach ($columns as $index => $column) {
                $value = $row[$index];
                ++$i;
                if ($value === null) {
                    $insert->bindValue($i, null, PDO::PARAM_NULL);
                } elseif ($column['type'] === 'bytea') {
                    $insert->bindValue($i, $value, PDO::PARAM_LOB);
                } elseif ($column['type'] === 'boolean') {
                    $insert->bindValue($i, $value !== '0', PDO::PARAM_BOOL);
                } else {
                    $insert->bindValue($i, $value, PDO::PARAM_STR);
                }
            }
        }

        try {
            $insert->execute();
        } catch (PDOException $e) {
            throw new RuntimeException('Insert into ' . $table . ' failed: ' . $e->getMessage(), 0, $e);
        }
    };

    while (($row = $rows->fetch()) !== false) {
        $batch[] = $row;
        ++$count;
        if (\count($batch) === $batchSize) {
            $flush($batch);
            $batch = [];
        }
    }
    if ($batch !== []) {
        $flush($batch);
    }
    $rows->closeCursor();

    foreach ($columns as $column) {
        if ($column['identity']) {
            $pg->exec(sprintf(
                'SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE((SELECT MAX(%s) FROM %s), 0) + 1, false)',
                $pg->quote(q($schema) . '.' . q($table)),
                $pg->quote($column['name']),
                q($column['name']),
                q($table)
            ));
        }
    }

    $copied[$table] = $count;
    $total += $count;
}

// Compare with what PostgreSQL holds before committing
$mismatch = [];
foreach ($copied as $table => $count) {
    $actual = (int) $pg->query('SELECT COUNT(*) FROM ' . q($table))->fetchColumn();
    if ($actual !== $count) {
        $mismatch[] = sprintf('%s: read %d, stored %d', $table, $count, $actual);
    }
}
if ($mismatch !== []) {
    $pg->rollBack();
    fwrite(\STDERR, "Row count mismatch, rolled back:\n" . implode("\n", $mismatch) . "\n");
    exit(1);
}

$pg->commit();

$filled = array_filter($copied);
arsort($filled);
printf("Copied %d rows into %d of %d tables in schema %s.\n", $total, \count($filled), \count($copied), $schema);
foreach (\array_slice($filled, 0, 10, true) as $table => $count) {
    printf("  %-40s %d\n", $table, $count);
}
