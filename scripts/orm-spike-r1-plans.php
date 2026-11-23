<?php
// R1 plan comparison: runs the main read statement of a captured JSONL file under the engine's explain mode.
// usage (inside instance-web-1, DATABASE_URL set to the orm_spike db): php orm-spike-r1-plans.php <engine> <jsonl> <rawout> [runs]
// prints one JSON line: engine, statement length, plan numbers (medians over runs).
use Doctrine\DBAL\DriverManager;
use Doctrine\DBAL\ParameterType;

require '/var/www/html/vendor/autoload.php';
[, $engine, $file, $raw] = $argv;
$runs = (int) ($argv[4] ?? 7);
// the same factories (translator, id codec, session setup) the DAL connection uses, so the statement is the one the engine receives
$conn = match ($engine) {
    'postgresql' => \Shopware\Core\Framework\Adapter\Database\PostgreSQLFactory::create(),
    'sqlite' => \Shopware\Core\Framework\Adapter\Database\SqliteFactory::create(),
    default => \Shopware\Core\Framework\Adapter\Database\MySQLFactory::create(),
};

$best = null;
foreach (file($file) as $line) {
    $row = json_decode($line, true);
    if (isset($row['sql']) && ($best === null || strlen($row['sql']) > strlen($best['sql']))) {
        $best = $row;
    }
}
$sql = $best['sql'];
$params = [];
$types = [];
foreach ($best['params'] as $k => $p) {
    $v = is_array($p['v']) ? hex2bin($p['v']['hex']) : $p['v'];
    $params[$k] = $v;
    $types[$k] = constant(ParameterType::class . '::' . $p['t']);
}

$prefix = match ($engine) {
    'postgresql' => 'EXPLAIN (ANALYZE, BUFFERS) ',
    'mysql' => 'EXPLAIN ANALYZE ',
    'mariadb' => 'ANALYZE FORMAT=JSON ',
    'sqlite' => 'EXPLAIN QUERY PLAN ',
};
$med = fn (array $a) => $a ? (function ($a) { sort($a); return $a[intdiv(count($a), 2)]; })($a) : null;
$out = ['engine' => $engine, 'sql_len' => strlen($sql), 'joins' => preg_match_all('/\bJOIN\b/', $sql), 'derived' => preg_match_all('/JOIN \(SELECT/', $sql)];
$plan = [];
$a = ['plan' => [], 'exec' => [], 'wall' => []];
for ($i = 0; $i < $runs; ++$i) {
    $t = hrtime(true);
    if ($engine === 'postgresql') {
        // the translator only handles statements that start with SELECT, so translate first and explain the result on the PDO connection
        $pdo ??= $conn->getNativeConnection();
        $translated ??= (new \Shopware\Core\Framework\Adapter\Database\PostgreSQL\MySQLToPostgreSQLTranslator())->translate($sql)[0];
        $st = $pdo->prepare($prefix . $translated);
        foreach ($params as $k => $v) {
            $st->bindValue($k, \Shopware\Core\Framework\Adapter\Database\PostgreSQL\IdCodecMiddleware::encode($v, $types[$k] === ParameterType::BINARY), $types[$k] === ParameterType::INTEGER ? \PDO::PARAM_INT : \PDO::PARAM_STR);
        }
        $st->execute();
        $rows = $st->fetchAll(\PDO::FETCH_NUM);
    } else {
        $rows = $conn->executeQuery($prefix . $sql, $params, $types)->fetchAllNumeric();
    }
    $a['wall'][] = (hrtime(true) - $t) / 1e6;
    $text = implode("\n", array_map(fn ($r) => implode(' | ', array_map('strval', $r)), $rows));
    if ($engine === 'postgresql') {
        preg_match('/Planning Time: ([\d.]+)/', $text, $m1);
        preg_match('/Execution Time: ([\d.]+)/', $text, $m2);
        $a['plan'][] = (float) $m1[1];
        $a['exec'][] = (float) $m2[1];
    } elseif ($engine === 'mysql') {
        preg_match('/actual time=[\d.]+\.\.([\d.]+)/', $text, $m);
        $a['exec'][] = (float) $m[1];
    } elseif ($engine === 'mariadb') {
        preg_match('/"query_optimization"[^}]*"r_total_time_ms":\s*([\d.]+)/', $text, $m1);
        preg_match('/"query_block"[^}]*?"r_total_time_ms":\s*([\d.]+)/s', $text, $m2);
        $a['plan'][] = (float) ($m1[1] ?? 0);
        $a['exec'][] = (float) ($m2[1] ?? 0);
    }
}
if ($engine === 'sqlite') {
    $a['exec'] = [];
    for ($i = 0; $i < $runs; ++$i) {
        $t = hrtime(true);
        $conn->executeQuery($sql, $params, $types)->fetchAllAssociative();
        $a['exec'][] = (hrtime(true) - $t) / 1e6;
    }
}
file_put_contents($raw, $text . "\n");
$out['plan_ms'] = $med($a['plan']) === null ? null : round($med($a['plan']), 3);
$out['exec_ms'] = round($med($a['exec']), 3);
$out['nodes'] = $engine === 'sqlite' ? count($rows) : (int) preg_match_all('/->|"table"\s*:/', $text);
$out['materialize'] = (int) preg_match_all('/Materializ|Subquery Scan|CTE Scan|Subquery|SUBQUERY|derived|"materialized_from_subquery"|MATERIALIZE/i', $text);
echo json_encode($out), "\n";
