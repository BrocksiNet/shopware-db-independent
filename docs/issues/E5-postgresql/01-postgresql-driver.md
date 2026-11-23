---
id: E5.01
type: Story
template: story.yaml
title: "PostgreSQL dialect, connection factory and translator shim behind a flag"
parent: E5
related: [E4.01, E4.02, E4.03, E5.02, E5.05]
findings: [30]
status: draft
upstream: ""
---

## User story

As a merchant or hosting partner with a PostgreSQL standard, I would like to run Shopware on PostgreSQL as an experimental option, so that I can use my managed database.

## Acceptance criteria

- A flag selects the database, and MySQL and MariaDB stay the default.
- A PostgreSQL implementation of the dialect service (E4.01), a connection factory for PostgreSQL and a driver option are available.
- All core migrations run on PostgreSQL and produce the schema that MySQL gets, checked by a schema comparison script.
- A translator turns the MySQL statements of old migrations and of extensions into PostgreSQL SQL, rejects what it cannot map with a clear error, and is only active on PostgreSQL.
- A set of MySQL compatibility functions exists in the PostgreSQL schema for the functions the core and extensions call.
- A native `uuid` column type in a `CREATE TABLE` statement is mapped by the translator (see the note below), or the error names the supported alternative.
- The DAL integration suite passes on PostgreSQL.
- Not covered and documented as such: OpenSearch, read replicas, `DATABASE_SSL_*` options, the admin worker.

Result of a proof of concept, for scale:

- All 910 core migrations ran on PostgreSQL 18 with 0 schema differences against MySQL.
- 804 of 804 DAL integration tests passed on PostgreSQL and on MariaDB.
- The translator layer is about 3,450 lines, and the compatibility script defines 87 functions.
- The storefront was 1.13 to 1.46 times the MariaDB response time with persistent connections and the plan cache (E5.02), and up to 1.9 times with a new connection per request.
- Writes are about twice as slow: a bulk write took 520 ms against 264 ms on MariaDB, parallel writes ran at 3.89 against about 12.5 requests per second.

Translator gap: the translator of the proof of concept rejects a native `uuid` type in `CREATE TABLE` and maps only `BINARY(16)` to `uuid`.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 30 (found while creating probe tables, `docs/31` line 194).
  The translator exists only on the proof of concept branch (`poc/db-independent`, `Adapter/Database/PostgreSQL/`), so the finding has no counterpart in trunk code.
- Numbers: `docs/27-final-report.md`; migrations `docs/07`, install and translator `docs/17`.
- Trunk `e9e18ef0e7b`: only `MySQLFactory` exists as connection factory (`src/Core/Framework/Adapter/Database/MySQLFactory.php`, registered at `src/Core/Framework/DependencyInjection/services.php:303`).
- This story depends on E4.01 to E4.03 and on a go decision (epic E5).
- The PoC rejects the type with `AdapterException::unmappedColumnType`.
