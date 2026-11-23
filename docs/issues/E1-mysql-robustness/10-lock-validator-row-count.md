---
id: E1.10
type: Improvement
template: technical_todo.yaml
title: "`LockValidator` uses `rowCount()` after a SELECT"
parent: E1
related: []
findings: [25]
status: checked
upstream: ""
---

## Technical TODO

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
`pdo_mysql` happens to return the number of rows, so the code works on MySQL and MariaDB today.
In a proof of concept `pdo_sqlite` returned a stale count from an earlier statement, so the validator reported entities as locked or unlocked incorrectly and 4 tests failed.

Proposed change:

```php
->executeQuery()
->fetchOne() !== false
```

The result is the same on MySQL and MariaDB.

Acceptance:

- `LockValidator` no longer calls `rowCount()` on a SELECT result.
- The existing lock validator tests pass on MySQL and MariaDB.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 25, `docs/24-sqlite-dal.md` ("Lock validator (4)", `rowCount()` of a SELECT; the PoC uses `fetchOne() !== false`).
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Write/Validation/LockValidator.php` lines 119 to 126, the only `rowCount()` in `src/Core/Framework/DataAbstractionLayer` (grep). The finding holds on trunk.
- Classified as bug in the findings table; typed here as Improvement (decided 2026-11-23) because MySQL and MariaDB give the right result today.
- A test for it would need a second driver or a mocked `Result`; none was written.
- Checked statically against trunk c6ef9571261 (2026-11-23).
