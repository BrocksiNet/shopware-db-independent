---
id: E3.01
type: Bug
template: bug_report.yml
title: "EntityWriteGateway misses the prefetched existence state for storage named primary keys"
parent: E3
related: [E3.04]
findings: [31]
status: reproduced
upstream: ""
---

## Shopware Version

trunk (checked on `e9e18ef0e7b`, 2026-11-23)

## Affected area / extension

Platform(Default)

## Actual behaviour

`EntityWriteGateway::getCurrentState()` decodes the primary key before it looks up the prefetched existence state in the `PrimaryKeyBag`:

```php
foreach ($primaryKey as $fieldName => $fieldValue) {
    $field = $definition->getField($fieldName);
    $decodedPrimaryKey[$fieldName] = $field ? $field->getSerializer()->decode($field, $fieldValue) : $fieldValue;
}
```

`WriteCommandExtractor::getPrimaryKey()` passes the key by storage name (`id`, `version_id`, `language_id`, `product_id`) with binary values.
`EntityDefinition::getField()` looks up by property name, so it returns `null` for every storage name that differs from the property name, and that value stays a 16 byte binary string.
`prefetch()` stores the state under property names with hex values, so the key built from the mixed hex and binary values never matches.

Every write of an entity with such a key column (every versioned entity, every translation, every mapping with a composite key) misses the prefetched state and runs its own `SELECT 1 ... WHERE ...` through `fetchFromDatabase()`.

Measured on a 50 product create and update: 248 of the 371 statements are these lookups on MySQL and MariaDB.

## Expected behaviour

The lookup decodes storage named keys the same way `getExistence()` already does (`getFields()->getByStorageName()`), hits the prefetched state and sends no extra query.
With the fix the same 50 product write runs 121 statements instead of 371 (60 ms instead of 88 ms on MySQL).

The property name lookup has to stay as well: `isTranslationChild()` calls `getExistence()` with `versionId`, a property name.

## How to reproduce

Unit test against `EntityWriteGateway`, which fails on trunk because `createQueryBuilder()` is called:

1. Definition with two primary key fields, `id` (`IdField('id', 'id')`) and `language_id` (`IdField('language_id', 'languageId')`).
2. `PrimaryKeyBag` with an existence state for `['id' => $hexId, 'languageId' => $hexLanguageId]` and `setPrefetchingCompleted(true)`, passed through `prefetchExistences()`.
3. Call `getExistence($definition, ['id' => <binary id>, 'language_id' => <binary language id>], [], new WriteCommandQueue())` with a `Connection` mock that expects `createQueryBuilder()` never to be called.

Fix:

```php
$field = $definition->getField($fieldName) ?? $definition->getFields()->getByStorageName($fieldName);
```

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- On trunk c6ef9571261 `EntityWriteGateway` lives at `Dbal/EntityWriteGateway.php`; `getCurrentState()` decode is at lines 652 to 656, unchanged, and no commit since ae0190f5892 touched the file.
- Branch `finding-31-write-gateway-decode` in the worktree `review/finding-31` (commit `76ec3f5d17a`, local): fix and the test `EntityWriteGatewayTest::testGetExistenceUsesPrefetchedStateForStorageNamedPrimaryKey`, red on trunk, green with the fix, php-cs-fixer clean, PHPStan not run.
- Statement counts: `docs/33-orm-spike-dal-v2.md`, lever W1a; measured on the spike branch (`orm-spike:bench` S4), not on trunk.
  Re-measure on trunk before filing.
- PostgreSQL in the PoC is not affected because its ids are hex above the connection.
