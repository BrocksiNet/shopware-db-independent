---
id: E5.02
type: Improvement
template: technical_todo.yaml
title: "Persistent connections and a plan cache for PostgreSQL"
parent: E5
related: [E5.01]
findings: [11, 16]
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
- [ ] Document that the cache does not work behind PgBouncer in transaction mode.
- [ ] Document the sizing of `max_connections` as php-fpm workers times web nodes.
- [ ] Measure PgBouncer 1.21 or newer with `max_prepared_statements`, which was not measured.

## Research notes (not for upstream)

- Findings: `docs/core-findings.md` rows 11 and 16; `docs/22` (connection setup, plan cache), `docs/18` (backend cost).
- PostgreSQL is about 1.25 times MariaDB on read-only OLTP work as a baseline (`docs/22`).
- With the cache, the remaining planning of the product detail statement is 7.4 ms (generic) or 13.3 ms (auto).
  This is why the 19 join detail read (finding 9) is not split.
- Trunk `e9e18ef0e7b`: `DATABASE_PERSISTENT_CONNECTION` already exists at `src/Core/Framework/Adapter/Database/MySQLFactory.php:125`.
  `DATABASE_PLAN_CACHE` does not exist, and there is no `.env` template entry for either variable.
  So finding 11 holds only for the template and the documentation, the flag is there.
- The plan cache class in the proof of concept is `PlanCacheMiddleware`.
- Related: E5.01 provides the PostgreSQL connection factory this builds on.
