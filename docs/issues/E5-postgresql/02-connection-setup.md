---
id: E5.02
type: Improvement
template: technical_todo.yaml
title: "Production connection setup for PostgreSQL: persistent connections, plan cache, replicas, TLS and poolers"
parent: E5
related: [E5.01]
findings: [11, 16, 42, 43, 44, 45]
status: draft
upstream: ""
---

## Technical TODO

Two costs on PostgreSQL come from the connection, not from the SQL.

Connecting: a PostgreSQL backend is a process.
In a proof of concept a PDO connect took 5.61 ms against 0.01 ms for a persistent connection, and the first comparison with the `ci` collation took 8.80 ms against 0.27 ms.
A request on a fresh connection therefore pays about 14 ms for connect and ICU setup.
A new backend costs about 36 ms plus connect (7.1 ms on PostgreSQL against 1.0 ms on MariaDB) in a separate measurement.

Planning: `pdo_pgsql` sets `PGSQL_ATTR_DISABLE_PREPARES`, so every statement is planned again.
A request ran 64 to 85 plans, which took 11.3 to 24.9 ms depending on the plan mode.
A per-connection cache that sends `PREPARE` once and `EXECUTE` afterwards removed 63 to 95 percent of the planning in generic plan mode and 38 to 82 percent in auto mode.
Request medians fell by 9 to 29 ms in generic mode, and responses were identical in 12 of 12 requests per scenario.

Technical TODO:

- [ ] Recommend `DATABASE_PERSISTENT_CONNECTION=1` for PostgreSQL in the PostgreSQL `.env` template and the hosting documentation.
- [ ] Add the plan cache as a connection middleware, switched on by `DATABASE_PLAN_CACHE=1`, active only with persistent connections.
- [ ] Keep `plan_cache_mode` at `auto`; `force_generic_plan` is an opt-in only.
- [ ] Bind booleans in the cache as `'1'` and `'0'`.
- [ ] Support `DATABASE_REPLICA_*` and `DATABASE_SSL_*` in `PostgreSQLFactory`, using the same variables as MySQL (`DATABASE_SSL_CA` maps to `sslmode=verify-full`, `DATABASE_SSL_DONT_VERIFY_SERVER_CERT` to `require`, `sslmode` in the URL wins).
- [ ] Route every write to the primary, including writes that return rows (`INSERT ... RETURNING` via `fetchOne()`/`executeQuery()`); DBAL's `PrimaryReadReplicaConnection` only switches on `executeStatement()`, `prepare()`, transactions, and savepoints.
- [ ] Document two supported setups: direct (`DATABASE_PERSISTENT_CONNECTION=1`, `DATABASE_PLAN_CACHE=1`, `max_connections` sized for php-fpm children × web nodes) and PgBouncer transaction mode (`DATABASE_PERSISTENT_CONNECTION=0`, no plan cache, PgBouncer ≥ 1.21 with `max_prepared_statements > 0`, `ignore_startup_parameters=extra_float_digits,options`).
- [ ] Document that a failed statement aborts the whole transaction on PostgreSQL (`25P02`), so code must not catch a database error and continue in the same transaction; wrap catch-and-retry paths in savepoints and reset/restart workers that leak an open transaction.

## Research notes (not for upstream)

- Findings: `docs/core-findings.md` rows 11, 16, and 42 to 45; `docs/22` (connection setup, plan cache), `docs/18` (backend cost), `docs/50` (production setup: replicas, TLS, OpenSearch, workers, PgBouncer), `docs/51` (canonical paired timings).
- Wave 10 E + D measured PgBouncer 1.26.1 (transaction mode, `max_prepared_statements=200`) end-to-end: 0 failures across 50+ measured storefront walks; total walk latency is **1.312×** direct persistent+plan-cache (`1,012` vs `771 ms`, 95 % CI `[1.128, 1.384]`), while direct PostgreSQL is **1.178×** MariaDB (`750` vs `637 ms`, 95 % CI `[1.088, 1.227]`) (`docs/51` 3f).
- PostgreSQL is about 1.25 times MariaDB on read-only OLTP work as a baseline (`docs/22`).
- With the cache, the remaining planning of the product detail statement is 7.4 ms (generic) or 13.3 ms (auto).
  This is why the 19 join detail read (finding 9) is not split.
- Trunk `e9e18ef0e7b`: `DATABASE_PERSISTENT_CONNECTION` already exists at `src/Core/Framework/Adapter/Database/MySQLFactory.php:125`.
  `DATABASE_PLAN_CACHE` does not exist, and there is no `.env` template entry for either variable.
  So finding 11 holds only for the template and the documentation, the flag is there.
- The plan cache class in the proof of concept is `PlanCacheMiddleware`.
- Related: E5.01 provides the PostgreSQL connection factory this builds on.
