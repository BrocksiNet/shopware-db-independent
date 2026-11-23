---
id: E1.10
type: Bug
template: bug_report.yml
title: "`LockValidator` uses `rowCount()` after a SELECT"
parent: E1
related: []
findings: [25]
status: draft
upstream: ""
---

## Shopware Version

trunk (code checked on `e9e18ef0e7b`, 2026-11-23)

## Affected area / extension

Platform(Default)

## Actual behaviour

`LockValidator::containsLockedEntities()` decides whether an entity is locked from the row count of a SELECT:

```php
$locked[$entityName] = $this->connection->createQueryBuilder()
    ->select('1')
    ->from(EntityDefinitionQueryHelper::escape($entityName))
    ->where('`id` IN (:ids) AND `locked` = 1')
    ->setParameter('ids', $primaryKeys, ArrayParameterType::BINARY)
    ->executeQuery()
    ->rowCount() > 0;
```

The PDO contract does not define `rowCount()` for a SELECT statement.
`pdo_mysql` happens to return the number of rows.
In a proof of concept `pdo_sqlite` returned a stale count from an earlier statement, so the validator reported entities as locked or unlocked incorrectly and 4 tests failed.
On MySQL and MariaDB the code works today.

## Expected behaviour

The check uses a result that is defined on every driver:

```php
->executeQuery()
->fetchOne() !== false
```

The result is the same on MySQL and MariaDB.

## How to reproduce

Found by reading the code, not run on trunk.
On MySQL and MariaDB there is no wrong result to reproduce; the code only relies on driver behaviour that the PDO documentation leaves open.

1. Write an entity of a lock aware definition (`isLockAware()`, with a `LockedField`), for example through a repository `update()`.
2. `PreWriteValidationEvent` reaches `LockValidator::preValidate()`, which runs the query above.
3. On a driver whose `rowCount()` after a SELECT does not return the number of selected rows the result of the check is wrong.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 25, `docs/24-sqlite-dal.md` ("Lock validator (4)", `rowCount()` of a SELECT; the PoC uses `fetchOne() !== false`).
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Write/Validation/LockValidator.php` lines 119 to 126, the only `rowCount()` in `src/Core/Framework/DataAbstractionLayer` (grep). The finding holds on trunk.
- Classified as bug in the findings table; on MySQL and MariaDB it is a latent defect, not a wrong result. Re-read before filing whether Improvement fits better.
- A test for it would need a second driver or a mocked `Result`; none was written.
