---
id: E4.01
type: Story
template: story.yaml
title: "SqlDialect service with the MySQL implementation"
parent: E4
related: [E4.02, E4.03, E4.06, E5.01]
findings: [8]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23318"
---

## User story

As a core developer, I would like MySQL-specific SQL to live behind one dialect service, so that I can review, test and change SQL specifics in one place.

## Acceptance criteria

- A `SqlDialect` interface exists with one implementation for MySQL and MariaDB, registered as a service.
- Dialect methods cover at least: identifier quoting, upsert, group concat, JSON extract, set, contains and length, id to text, case-insensitive equals and like, date format and date add, limited delete and update, `FOR UPDATE`, and the retry decision for a failed statement.
- MySQL-specific SQL in `EntityReader`, `EntitySearcher`, `EntityAggregator`, `EntityWriteGateway`, `MultiInsertQueryQueue` and the JSON field accessors is produced through the dialect.
- The remaining raw SQL in core services is moved behind the dialect step by step; a static rule reports MySQL-specific constructs outside the MySQL dialect and migrations.
- The SQL sent to MySQL and MariaDB stays the same as before, shown by the existing test suites and by a statement comparison on a sample of requests.
- No measurable performance regression.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 8; design in `docs/10`; plan in `docs/27` ("Required core changes" row 2, phase 1).
- Numbers in the proof of concept base (`docs/04`, `docs/10`): 446 files use the connection outside the DAL and migrations, 241 of them with MySQL SQL; backticks 1,434 in 135 raw-SQL files, `GROUP_CONCAT` 59 in 20 files, `JSON_*` 90 in 19 files, `LOWER(HEX())` 364 in 140 files, 507 case-insensitive columns.
- Trunk `e9e18ef0e7b`, counted by me with `grep`: 463 non-migration files import `Doctrine\DBAL\Connection;` (1425 with migrations).
  This does not match 446, which used a different scope; treat the counts as order of magnitude.
- Trunk has no dialect abstraction: `src/Core/Framework/Adapter/Database/` holds `MySQLFactory.php`, `ReplicaConnection.php` and `ReplicaConnectionResetter.php` only.
- The dialect spike moved reader group concat, JSON field accessor, write gateway JSON set and id types, and the `MultiInsertQueryQueue` upsert onto `SqlDialect`; 19 `SqlDialectTest` tests, DAL integration 801 tests (`docs/10`).
- Open questions from `docs/10`: boolean binding, case rule per column, `ONLY_FULL_GROUP_BY` (trunk's `MySQLFactory.php:107-109` removes it from the session `sql_mode`, see E1.02).
- The effort table of `docs/10` is an estimate and is not used here.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Recount on trunk c6ef9571261: 463 non-migration files import `Doctrine\DBAL\Connection;` (1425 with migrations), the raw-sql scan finds 242 of 446 in-scope files with SQL-string constructs (backticks 1,416 in 132 files, `GROUP_CONCAT` 60 in 20, `JSON_*` 86 in 19, `LOWER(HEX())` 387 in 142).
- Trunk c6ef9571261 still has no dialect abstraction (`grep -rli 'SqlDialect\|IdBinding' src` is empty); `src/Core/Framework/Adapter/Database/` holds the same three files; `MySQLFactory.php:107` removes `ONLY_FULL_GROUP_BY` (the cited 107-109 is now the one line 107 inside the `SET` command at 104-107).
- `EntityReader`, `EntitySearcher`, `EntityAggregator`, `EntityWriteGateway` (`Dbal/`) and `MultiInsertQueryQueue` (`Doctrine/`) exist on trunk.
