# Shopware on PostgreSQL: research and proof of concept

Experiment: what has to change in the Shopware open source core so the database
is exchangeable, with PostgreSQL as the first target. The goal is a running
Shopware on PostgreSQL plus documentation of every finding on the way.

## Scope

- Open source core only (`shopware/shopware`, trunk). No plugins, no commercial.
- Ids are stored as native `uuid` on PostgreSQL, not as `bytea`.
- Modern PHP: typed DTOs and a storage port between the API and the database.

## Layout

| Path | Content |
|---|---|
| `README.md` | This file |
| `docs/` | Plan, findings and decisions, numbered in the order they were written |
| `instance/` | The Shopware checkout (separate git repository, ignored here) |
| `review/` | Git worktrees of `instance/` for comparing branches and pull requests |

## Environment

The instance is the `sw-dev` lane `pg`: http://pg.localhost:8088
(admin: http://pg.localhost:8088/admin).

## Start reading

1. [docs/00-plan.md](docs/00-plan.md)
2. [docs/01-initial-findings.md](docs/01-initial-findings.md)
3. [docs/02-decisions.md](docs/02-decisions.md)
