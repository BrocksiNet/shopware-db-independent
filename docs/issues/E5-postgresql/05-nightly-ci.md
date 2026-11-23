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
In a proof of concept the DAL integration suite (804 tests) passed on PostgreSQL and on MariaDB, and the `Content/Product/DataAbstractionLayer` suite (72 tests) passed on PostgreSQL.
The other integration suites were last measured with failures on PostgreSQL: Checkout 57, System 85 and Content/Product 54.
`CustomEntityTest` failed 9 of 12.
PHPUnit ran on PostgreSQL with a savepoint around every statement.
OpenSearch, replicas, `DATABASE_SSL_*` and the admin worker were not tested.

Technical TODO:

- [ ] Add a nightly workflow that installs Shopware on PostgreSQL and runs the DAL and integration suites.
- [ ] Run the migration schema comparison against MySQL in the same workflow.
- [ ] Triage the failing suites above, and either fix them or list them as known failures with an owner.
- [ ] Report the result in a place that the owners of the suites watch.
- [ ] Define the exit criterion: the full integration suite is green on PostgreSQL.
- [ ] Decide when, if ever, the run moves from nightly to pull requests.

## Research notes (not for upstream)

- Source: `docs/27-final-report.md` (phase 3 exit criterion, risks), `docs/24` (SQLite: 795 of 804 DAL tests pass, migrations are the blocker, optional).
- The migration schema check script reported 0 differences on the proof of concept.
- No code reference on trunk; this is CI work and depends on E5.01.
