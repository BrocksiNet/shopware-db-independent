#!/bin/sh
# Applies the BinaryUuidToIdBindingRector to a copy of every non-migration source file with a binary uuid helper and prints the pattern counts before and after.
# usage: scripts/id-rector-coverage.sh   (needs the sw-dev container instance-web-1, writes only to /tmp)
set -e
cd "$(dirname "$0")/.."
WEB=${WEB_CONTAINER:-instance-web-1}
W=/tmp/id-rector-coverage
rm -rf $W && mkdir -p $W/before $W/after
(cd instance && grep -rlE 'Uuid::fromHexToBytes|Uuid::fromBytesToHex|ArrayParameterType::BINARY|LOWER\(HEX\(|UNHEX\(' src --include=*.php | grep -v -E '/Migration/|IdBinding.php|BinaryUuidToIdBindingRector.php' > $W/files.txt)
(cd instance && tar -cf - -T $W/files.txt) | tar -C $W/before -xf -
cat > $W/rector.php <<'PHP'
<?php declare(strict_types=1);
use Rector\Config\RectorConfig;
use Shopware\Core\DevOps\StaticAnalyze\Rector\BinaryUuidToIdBindingRector;
return RectorConfig::configure()
    ->withPaths(['/tmp/idcopy/src'])
    ->withImportNames(removeUnusedImports: true)
    ->withRules([BinaryUuidToIdBindingRector::class]);
PHP
podman exec $WEB sh -c 'rm -rf /tmp/idcopy && mkdir /tmp/idcopy'
tar -C $W/before -cf - src | podman exec -i $WEB tar -C /tmp/idcopy -xf -
podman cp $W/rector.php $WEB:/tmp/idcopy/rector.php
podman exec $WEB sh -c 'cd /tmp/idcopy && /var/www/html/vendor-bin/rector/vendor/bin/rector process --config rector.php --no-progress-bar --no-diffs --autoload-file /var/www/html/vendor/autoload.php 2>&1 | tail -3'
podman exec $WEB tar -C /tmp/idcopy -cf - src | tar -C $W/after -xf -
echo "== before"; python3 scripts/id-pattern-inventory.py $W/before | sed -n '1,/## migration/p' | grep -v '^## migration'
echo "== after"; python3 scripts/id-pattern-inventory.py $W/after | sed -n '1,/## migration/p' | grep -v '^## migration'
echo "files changed: $(diff -rq $W/before/src $W/after/src | wc -l)"
