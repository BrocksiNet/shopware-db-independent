<?php
// Prints the SQL of the DBAL S1 query with its parameters as JSON (run inside instance-web-1 with the spike env).
// usage: php scripts/orm-spike-explain-s1.php > /tmp/s1.json   (copy to instance/ first, uses vendor/)
use Doctrine\DBAL\Connection;
use Shopware\Core\Framework\Adapter\Kernel\KernelFactory;
use Shopware\Core\Framework\OrmSpike\Dbal\DbalImplementation;
use Shopware\Core\Framework\OrmSpike\Harness\ParamsFactory;
use Shopware\Core\Framework\Plugin\KernelPluginLoader\StaticKernelPluginLoader;

$loader = require '/var/www/html/vendor/autoload.php';
$kernel = KernelFactory::create('prod', false, $loader, new StaticKernelPluginLoader($loader, null));
$kernel->boot();
$real = $kernel->getContainer()->get(Connection::class);

$spy = new class($real->getParams(), $real->getDriver(), $real->getConfiguration()) extends Connection {
    public array $log = [];
    public function fetchAllAssociative(string $query, array $params = [], array $types = []): array
    {
        $this->log[] = [$query, $params];
        return parent::fetchAllAssociative($query, $params, $types);
    }
};
$params = (new ParamsFactory($real))->create();
(new DbalImplementation($spy))->s1Listing($params);
echo json_encode($spy->log[0]);
