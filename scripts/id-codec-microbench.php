<?php declare(strict_types=1);
// Micro cost of one id through the codec versus the hex string binding.
// usage: podman exec instance-web-1 php /var/www/html/../shopware-postsql/... or: php scripts/id-codec-microbench.php (needs the instance/ autoloader at /var/www/html/vendor)
require '/var/www/html/vendor/autoload.php';

use Shopware\Core\Framework\Adapter\Database\Dialect\IdBinding;
use Shopware\Core\Framework\Adapter\Database\PostgreSQL\IdCodecMiddleware;
use Shopware\Core\Framework\Uuid\Uuid;

$n = 500000;
$hex = Uuid::randomHex();
$bytes = (string) hex2bin($hex);
$uuid = substr($hex, 0, 8) . '-' . substr($hex, 8, 4) . '-' . substr($hex, 12, 4) . '-' . substr($hex, 16, 4) . '-' . substr($hex, 20);
IdBinding::useHexBinding(true);

$t = static function (string $label, callable $f) use ($n): void {
    $s = hrtime(true);
    for ($i = 0; $i < $n; ++$i) { $f(); }
    printf("%-46s %6.0f ns/op\n", $label, (hrtime(true) - $s) / $n);
};
$t('baseline loop', static fn () => null);
$t('before: fromHexToBytes + codec encode (param)', static fn () => IdCodecMiddleware::encode(Uuid::fromHexToBytes($hex), true));
$t('before: codec decode + fromBytesToHex (result)', static fn () => Uuid::fromBytesToHex(IdCodecMiddleware::decode($uuid)));
$t('after: IdBinding::value (hex, param)', static fn () => IdBinding::value($hex));
$t('after: IdBinding::toHex (uuid text, result)', static fn () => IdBinding::toHex($uuid));
$t('codec encode on a non id string (len != 16)', static fn () => IdCodecMiddleware::encode('some text value', false));
$t('codec decode on a non id string', static fn () => IdCodecMiddleware::decode('some text value'));
