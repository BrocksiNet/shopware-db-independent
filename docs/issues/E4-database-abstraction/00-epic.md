---
id: E4
type: Epic
template: epic.yaml
title: "Database abstraction groundwork: SQL dialect, id binding and neutral migrations"
parent: ""
related: [E1, E5]
findings: [7, 8, 15, 20, 21, 26]
status: checked
upstream: ""
---

## Problem we must solve

MySQL is wired into the whole core, not only into the DAL:

- About 460 files outside migrations use the connection, and a scan found MySQL-specific SQL in about 240 of the 446 files outside the DAL and migrations (upsert, JSON functions, group concat, quoting, case-insensitive compare).
- 715 id columns are `binary(16)`, and more than 300 files outside migrations convert ids between hex and bytes by hand.
- 919 migrations are MySQL DDL, and `CustomEntitySchemaUpdater` asks the connection platform for the schema diff SQL.
- Tests rely on MySQL details (`SET FOREIGN_KEY_CHECKS`, `0x...` literals, upper case `HEX(id)` compared case-insensitively, `DECIMAL` scale in strings).
- 55 percent of 3,747 store plugins contain raw SQL, and 1,389 have MySQL-only DDL in their migrations.

## WHY we need to solve it

Manual id conversion is a constant source of bugs, and raw MySQL in hundreds of files makes every SQL change harder to review and test.
Moving the MySQL specifics behind one service and one id binding is worth doing for MySQL alone, and it is the prerequisite for any second database (PostgreSQL, or SQLite for development and CI).

## Solution to the problem

- A `SqlDialect` service with the MySQL/MariaDB implementation only; MySQL-specific SQL in the core moves behind it (E4.01).
- Hex ids above the connection, bound to bytes in one place, with Rector rules for the migration of call sites and a deprecation of manual conversion (E4.02).
- A database-neutral migration API for new migrations; existing migrations keep running unchanged (E4.03).
- A fixed DDL platform for custom entity schema updates (E4.04).
- Portable SQL in tests (E4.05).
- A public dialect service for extensions and a `shopware-cli` check for MySQL-only SQL (E4.06).

## WHO benefits

Core developers (one place for SQL specifics and id handling), extension developers (portable SQL and migrations, early warnings from `shopware-cli`), Shopware (option for a second database at lower cost).

## Accessibility

Backend-only work required

## WHERE will we do it

Core platform: connection setup, DAL, every file with raw SQL, the migration system, `System/CustomEntity`, the test suites; `shopware-cli`.

## Out of scope

- Shipping a second database (a later PostgreSQL epic, after a go decision).
- Rewriting existing migrations.

## Acceptance criteria

- No MySQL-specific SQL in the core outside the MySQL dialect (checked by a static rule).
- No manual hex/bytes id conversion outside the binding and migrations; manual conversion is deprecated for extensions.
- New core migrations can be written with the neutral API.
- MySQL and MariaDB suites stay green; no measurable performance regression.

## Research notes (not for upstream)

- Trunk counts at `e9e18ef0e7b`: 463 non-migration files import `Doctrine\DBAL\Connection`, 919 core migrations; the PoC base had 446, 309 and 910 (`docs/04`, different scope).

- Source: `docs/core-findings.md` rows 7, 8, 15, 20, 21, 26; `docs/27-final-report.md` "Required core changes" rows 2, 3, 5, 8 and phases 1 and 2; `docs/28-plugin-sql-inventory.md` (plugin numbers).
- The PoC (`poc/db-independent`) has `SqlDialect` for MySQL, MariaDB, PostgreSQL and SQLite and `IdBinding` in 313 files, mostly rewritten with a Rector rule (`docs/15`, `docs/20`).
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Recount on trunk c6ef9571261 (2026-11-23), run in `src` of the checkout:
  - `grep -rl 'Doctrine\\DBAL\\Connection;' src --include='*.php' | grep -v '/Migration/' | wc -l` gives 463 (1425 with migrations).
  - `find src/Core/Migration -name 'Migration*.php' -path '*V6_*' | wc -l` gives 919.
  - `grep -rlE 'Uuid::fromHexToBytes|Uuid::fromBytesToHex|LOWER\(HEX|UNHEX\(|ArrayParameterType::BINARY|ParameterType::BINARY' src --include='*.php' | grep -v '/Migration/' | wc -l` gives 314.
  - `python3 docs/inventory/raw-sql/scan.py <trunk-checkout> <outdir>` gives 446 files in scope and 242 with an SQL-string construct (the base had 241).
  - The 715 `binary(16)` columns come from the installed schema (`information_schema.columns`, column type `binary(16)`), which cannot be recounted statically; not re-checked.
- Test claims verified in the trunk checkout: `SET FOREIGN_KEY_CHECKS` in 16 files under `tests`, `0x...` literals in e.g. `tests/integration/Core/Framework/DataAbstractionLayer/EntityExtensionReadTest.php:74`, `'250.0000'` in `EntityAggregatorTest.php:593`, `HEX(id) IN` in `TreeIndexerTest.php:284`.
