# Plan

## Two tracks

1. **Dialect track** (gets Shopware running): a platform abstraction under the
   DAL's `Dbal` layer and for raw SQL, with a MySQL and a PostgreSQL
   implementation.
2. **DTO track** (modern-code research): one vertical slice with a storage port
   and typed DTOs between route and database, so the route knows neither
   `Criteria` nor SQL.

## Phases

| # | Phase | Done when |
|---|---|---|
| 0 | Setup: lane `pg`, PostgreSQL container, web image with `pdo_pgsql` | MySQL lane runs, PostgreSQL reachable from the web container |
| 1 | Inventory: scripts classifying every SQL touchpoint by construct | Findings document with reproducible counts |
| 2 | Connection and schema: driver-aware connection factory; PostgreSQL schema without porting every migration (spike: convert an installed MySQL schema vs. generate from DAL definitions via `SchemaBuilder`) | Kernel boots against an empty-data PostgreSQL schema |
| 3 | DAL on PostgreSQL: one small entity first (read, search, aggregate, write), then translations, versioning, inheritance, JSON fields | DAL integration tests for those entities pass |
| 4 | Raw SQL by request path: `system:install`, indexers, cart, theme | Admin login and a storefront page render |
| 5 | DTO slice: evaluate Symfony ObjectMapper, Serializer and request-payload mapping against the generated DTOs of pull request 17858; build the newsletter slice with a storage port and two adapters | Same route runs on both databases with no SQL above the port |
| 6 | Measure: integration suite against PostgreSQL | Pass/fail report per area |
| 7 | Final report: required core changes, effort, breaking changes for extensions | Document plus working branch |

Every phase ends with a findings file in `docs/`.
