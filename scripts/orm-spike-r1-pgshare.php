<?php
// R1: planning versus execution time of every statement of one captured scenario on PostgreSQL.
// usage (inside instance-web-1, DATABASE_URL = pgsql orm_spike): php orm-spike-r1-pgshare.php <jsonl> [runs]
// prints one JSON line with the sum of the median planning and execution time over all statements.
use Doctrine\DBAL\ParameterType;
use Shopware\Core\Framework\Adapter\Database\PostgreSQL\IdCodecMiddleware;
use Shopware\Core\Framework\Adapter\Database\PostgreSQL\MySQLToPostgreSQLTranslator;
use Shopware\Core\Framework\Adapter\Database\PostgreSQLFactory;

require '/var/www/html/vendor/autoload.php';
$runs = (int) ($argv[2] ?? 5);
$pdo = PostgreSQLFactory::create()->getNativeConnection();
$translator = new MySQLToPostgreSQLTranslator();
$med = function (array $a) { sort($a); return $a[intdiv(count($a), 2)]; };
$sumPlan = $sumExec = 0.0;
$n = 0;
$rows = [];
$seen = false;
foreach (file($argv[1]) as $line) {
    $row = json_decode($line, true);
    if (isset($row['marker'])) {
        $seen = true; // statements before the scenario marker belong to the setup
        continue;
    }
    if (!isset($row['sql']) || !$seen) {
        continue;
    }
    $sql = preg_replace('/^(--[^\n]*\n)+/', '', $row['sql']);
    if (!preg_match('/^\s*(SELECT|WITH)\b/i', $sql)) {
        continue;
    }
    $translated = $translator->translate($sql)[0];
    $plans = $execs = [];
    for ($i = 0; $i < $runs; ++$i) {
        $st = $pdo->prepare('EXPLAIN (ANALYZE) ' . $translated);
        foreach ($row['params'] as $k => $p) {
            $v = is_array($p['v']) ? hex2bin($p['v']['hex']) : $p['v'];
            $type = constant(ParameterType::class . '::' . $p['t']);
            $st->bindValue($k, IdCodecMiddleware::encode($v, $type === ParameterType::BINARY), $type === ParameterType::INTEGER ? \PDO::PARAM_INT : \PDO::PARAM_STR);
        }
        $st->execute();
        $text = implode("\n", array_column($st->fetchAll(\PDO::FETCH_NUM), 0));
        preg_match('/Planning Time: ([\d.]+)/', $text, $m1);
        preg_match('/Execution Time: ([\d.]+)/', $text, $m2);
        $plans[] = (float) $m1[1];
        $execs[] = (float) $m2[1];
    }
    $sumPlan += $med($plans);
    $sumExec += $med($execs);
    ++$n;
}
echo json_encode(['file' => basename($argv[1]), 'statements' => $n, 'plan_ms' => round($sumPlan, 2), 'exec_ms' => round($sumExec, 2), 'plan_share' => round($sumPlan / max(1e-9, $sumPlan + $sumExec), 3)]), "\n";
