---
id: E4.04
type: Improvement
template: technical_todo.yaml
title: "Fixed DDL platform for custom entity schema updates"
parent: E4
related: [E4.01, E4.03]
findings: [20]
status: draft
upstream: ""
---

## Technical TODO

`CustomEntitySchemaUpdater` builds the schema diff of custom entities with the DBAL schema manager and turns it into SQL with `$this->connection->getDatabasePlatform()->getAlterSchemaSQL(...)`.
The generated DDL therefore depends on the platform class of whatever connection is configured.
The same class also runs `SELECT @@FOREIGN_KEY_CHECKS` and `SET FOREIGN_KEY_CHECKS = 0` around the statements, which is MySQL syntax.

Technical TODO:

- [ ] Take the platform for the diff SQL from one method of the dialect (E4.01) instead of the connection, so that the DDL for custom entities is generated for a fixed, known platform on MySQL and MariaDB.
- [ ] Move the foreign key check handling behind the dialect as well.
- [ ] Keep the DDL for MySQL and MariaDB byte for byte as before; cover it with a test on a custom entity with each field type.
- [ ] Run the existing `CustomEntityTest` on MySQL and MariaDB.

In a proof of concept the platform was MySQL's for MySQL, MariaDB and SQLite and the MySQL 8.4 platform for PostgreSQL.
`CustomEntityTest` still failed 9 of 12 tests on PostgreSQL after that, for other reasons: a `double precision PRECISION` rendering, foreign keys that block drops, and leftover tables.
This issue only fixes the platform choice.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 20; the PoC change is `SqlDialect::schemaDdlPlatform()` (`docs/21`, "Wave 7" item 2).
- Trunk `e9e18ef0e7b`, `src/Core/System/CustomEntity/Schema/CustomEntitySchemaUpdater.php`:
  - line 64: `$this->getPlatform()->getAlterSchemaSQL($schemaManager->createComparator()->compareSchemas($baseSchema, $update))`.
  - lines 89-92: `getPlatform()` returns `$this->connection->getDatabasePlatform()`.
  - lines 68-69 and 79/86: `SELECT @@FOREIGN_KEY_CHECKS`, `SET FOREIGN_KEY_CHECKS = 0` and its reset.
  The finding holds on trunk.
- On MySQL and MariaDB the fix changes nothing, since the connection platform is already MySQL's; the issue is groundwork for a second database.
