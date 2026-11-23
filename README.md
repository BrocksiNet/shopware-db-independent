# Shopware database independent: research and proof of concept

Experiment: what has to change in the Shopware open source core so the database is exchangeable.
Targets: MySQL and MariaDB (supported today), PostgreSQL (first new target) and SQLite (third target, to prove the abstraction).
The goal is a Shopware that installs and runs on each of them from the same code, a measured comparison, and documentation of every finding on the way.

The project started as "Shopware on PostgreSQL" (repository `shopware-postgresql`, branch `poc/postgresql`), see `docs/02-decisions.md` for the rename.

## Scope

- Open source core only (`shopware/shopware`, trunk).
  No plugins, no commercial.
- Ids are stored as native `uuid` on PostgreSQL, not as `bytea`.
- Modern PHP: typed DTOs and a storage port between the API and the database.

## Layout

| Path | Content |
|---|---|
| `README.md` | This file |
| `docs/` | Plan, findings and decisions, numbered in the order they were written |
| `scripts/` | Checks and smoke tests (migrations on PostgreSQL, DTO slice) |
| `handoffs/` | Work packages for parallel sessions (not versioned) |
| `instance/` | The Shopware checkout, branch `poc/db-independent` (separate git repository, ignored here) |
| `review/` | Git worktrees of `instance/` for comparing branches and pull requests |

## Environment

The instance is the `sw-dev` lane `pg`: http://pg.localhost:8088 (admin: http://pg.localhost:8088/admin).

## Start reading

0. [docs/summary.md](docs/summary.md): findings and architecture after wave 5, with diagrams
0. [docs/core-findings.md](docs/core-findings.md): findings useful for the Shopware core, independent of PostgreSQL
0. [docs/27-final-report.md](docs/27-final-report.md): final report of the experiment after wave 7, [docs/28-plugin-sql-inventory.md](docs/28-plugin-sql-inventory.md) the plugin SQL scan
0. [docs/29-orm-alternatives.md](docs/29-orm-alternatives.md#conclusion): wave 8, replace the DAL with an ORM? Answer: keep the DAL and build DAL v2. Results in docs 30 to 33, all timings in [docs/34-orm-spike-final-timings.md](docs/34-orm-spike-final-timings.md), fair write comparison in [docs/35-orm-spike-fair-write.md](docs/35-orm-spike-fair-write.md), DAL v2 batched update on PostgreSQL in [docs/36-dal-v2-batched-update-postgresql.md](docs/36-dal-v2-batched-update-postgresql.md)
0. [docs/38-read-store-plan.md](docs/38-read-store-plan.md): wave 9 plan, a read-optimized store (SQL JSON, OpenSearch, MongoDB, Valkey) fed from the DAL, research and options
0. [docs/37-review-round-2.md](docs/37-review-round-2.md): review round 2, id codec cache, batched update semantics, corrected schema claim
1. [docs/00-plan.md](docs/00-plan.md)
2. [docs/02-decisions.md](docs/02-decisions.md)
3. [docs/10-architecture.md](docs/10-architecture.md): current state, target architecture and the change list
4. [docs/11-database-comparison.md](docs/11-database-comparison.md): differences between the databases, benchmark plan
5. [docs/09-test-run-on-postgresql.md](docs/09-test-run-on-postgresql.md): where the PostgreSQL port stands
