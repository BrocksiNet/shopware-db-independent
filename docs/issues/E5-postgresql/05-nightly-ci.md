---
id: E5.05
type: Task
template: technical_todo.yaml
title: "Nightly CI with the DAL and integration suites on PostgreSQL"
parent: E5
related: [E5.01]
findings: []
status: draft
upstream: ""
---

## Technical TODO

Support for a second database needs a regular test run.
In a proof of concept the DAL integration suite (804 tests) and `Content/Product/DataAbstractionLayer` (72 tests) passed on PostgreSQL and MariaDB.
In wave 10 C (`docs/49`), the five integration suites outside the DAL (`Core/Checkout`, `Core/System`, `Core/Content`, `Storefront`, `Core/Framework`, 8,072 tests total) were run against MariaDB as reference: PostgreSQL-only failures dropped from 386 to **90** (98.9 % pass rate outside 9 shared MariaDB failures): `Core/System` outside `CustomEntity` = **0**, `Storefront` = **1**, `Core/Checkout` = **15**, `Core/Framework` = **24**, `Core/Content` = **42**, and `Core/System/CustomEntity` = **8 of 12** (all runtime DDL gaps tracked in E4.04).
All 90 remaining failures are classified in `docs/49` (~2–3 developer-weeks outside E4.04).
PHPUnit ran on PostgreSQL with DDL savepoint wrapping (`DdlSavepointStatement`, which does not mask production DML failures inside transactions; catch-and-retry production sites were audited and wrapped in savepoints in `docs/49`).
OpenSearch, primary + streaming replica, `DATABASE_SSL_*`, PgBouncer, and messenger/scheduler workers were exercised end-to-end in wave 10 E (`docs/50`).

Technical TODO:

- [ ] Add a nightly workflow that installs Shopware on PostgreSQL and runs the DAL and integration suites (gate `DAL`, `Core/System` excl. `CustomEntity`, and `Storefront` first, as they are already at 0–1 PostgreSQL-only failures).
- [ ] Run the migration schema comparison against MySQL in the same workflow.
- [ ] Triage and close the remaining 90 classified PostgreSQL-only failures (outside E4.04 custom entity DDL), or track them with an owner.
- [ ] Report the result in a place that the owners of the suites watch.
- [ ] Define the exit criterion: the full integration suite is green on PostgreSQL.
- [ ] Decide when, if ever, the run moves from nightly to pull requests.

## Research notes (not for upstream)

- Source: `docs/27-final-report.md` (phase 3 exit criterion, risks), `docs/24` (SQLite: 795 of 804 DAL tests pass, migrations are the blocker, optional), `docs/49-postgresql-integration-suites.md` (wave 10 C suite run and classification), `docs/50-postgresql-production-setup.md` (wave 10 E production stack).
- The migration schema check script reported 0 differences on the proof of concept.
- No code reference on trunk; this is CI work and depends on E5.01.
