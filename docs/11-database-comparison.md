# Database comparison: MySQL, MariaDB, PostgreSQL, SQLite

What differs between the four databases for Shopware, what a shop owner or developer would gain, and how we measure it.
"Observed" means we hit it in the port (`docs/06-phase3-log.md`, `docs/09-test-run-on-postgresql.md`); the other rows are documented properties of the databases that we have not tested with Shopware yet.

## Differences that matter for Shopware

| Topic | MySQL 8 | MariaDB 10.11+ | PostgreSQL 18 | SQLite 3 | Source |
|---|---|---|---|---|---|
| Supported by Shopware today | yes | yes | no (this project) | no (this project) | Shopware docs |
| Identifier quoting | backticks | backticks | double quotes | double quotes (backticks accepted) | observed |
| Ids | `binary(16)` | `binary(16)` | native `uuid` (our choice) | `BLOB` or text, no uuid type | observed |
| Boolean | `TINYINT(1)`, `0` / `1` | same | real `boolean`, no implicit cast from integer | integer `0` / `1` | observed |
| JSON | native `JSON` type | `JSON` is an alias for `LONGTEXT` with a `json_valid` check | `jsonb` with operators and GIN indexes | JSON functions on text | observed (220 JSON columns) |
| Case-insensitive text | collation `utf8mb4_unicode_ci` | same | needs a nondeterministic ICU collation or `lower()` | `NOCASE` collation, ASCII only | observed (507 columns) |
| Upsert | `ON DUPLICATE KEY UPDATE` reacts to every unique key | same | `ON CONFLICT (target)` names one key | `ON CONFLICT (target)` | observed |
| `GROUP_CONCAT` | yes | yes | `string_agg` | `group_concat` | observed |
| Strict `GROUP BY` | configurable, Shopware turns `ONLY_FULL_GROUP_BY` off | configurable | always strict | lenient | observed |
| Failed statement inside a transaction | transaction stays usable | same | transaction aborted until rollback | statement rolled back, transaction usable | observed for PostgreSQL |
| DDL inside a transaction | implicit commit | implicit commit | transactional, can roll back | transactional | observed for PostgreSQL |
| `ALTER TABLE` | full | full | full | add, rename and drop column; changing a column means rebuilding the table | SQLite docs |
| Concurrency | row locks | row locks | row locks, MVCC | one writer at a time (readers in parallel with WAL) | database docs |
| `SELECT ... FOR UPDATE` | yes | yes | yes, not together with `GROUP BY` | no | observed for PostgreSQL |
| Foreign keys | always on | always on | always on | off unless `PRAGMA foreign_keys = ON` per connection | SQLite docs |
| Connections | thread per connection | thread per connection, thread pool available | process per connection, a pooler (PgBouncer) is common | in-process, no server | database docs |
| Full text search | `FULLTEXT` indexes | same | `tsvector` with ranking and language stemming | FTS5 extension | database docs |
| Extensions | few | some storage engines | many (`pgvector`, PostGIS, `pg_trgm`) | loadable extensions | database docs |
| Licence | GPL (Oracle) | GPL (MariaDB Foundation) | PostgreSQL licence (permissive) | public domain | database docs |

## Possible benefits, to be verified

These are reasons people choose each database.
None of them is measured for Shopware yet; the benchmark below is meant to confirm or reject them.

**PostgreSQL**

- `jsonb` with GIN indexes could make filtering on custom fields and JSON properties faster.
- Built-in full text search could replace the MySQL product search without Elasticsearch for small and medium shops.
- `pgvector` would allow semantic product search in the same database.
- Transactional DDL makes failed migrations roll back cleanly (we already rely on it in the migration check).
- It is the default database of many managed platforms and teams, and the licence is permissive.
- Costs: case-insensitive text needs a decision per column, connection pooling is needed for many PHP workers, VACUUM has to be monitored.

**SQLite**

- No database server: Shopware for local development, demos, workshops and CI with one file.
- Integration tests could run much faster (no network, database copied as a file); to be measured.
- Not for production shops: one writer at a time limits parallel checkouts and indexers.

**MySQL and MariaDB**

- The reference today: everything is tested on them and they need no translation.
- MySQL and MariaDB already differ (JSON type, some functions); a dialect per database makes that explicit instead of hoping both behave the same.

## Switch test

Question: how fast and how reliably can the same code be installed on another database?

For each of MySQL 8, MariaDB and PostgreSQL (SQLite once the spike gets that far):

1. Start an empty database container (or file).
2. Point `DATABASE_URL` at it, `bin/console system:install --basic-setup` (all migrations).
3. Load the same demo data (`framework:demodata` with a fixed size), run `dal:refresh:index`.
4. Smoke test: storefront home and listing, admin login, product write through the admin API, store API checkout.
5. Record the time of every step and every error.

Result: one table per database with times and pass/fail, repeatable with one script.

## Benchmark plan

Same machine, same container CPU and memory limits, same demo data, warm caches, several runs, median and p95.

| Measurement | How |
|---|---|
| Install with all migrations | time of `system:install` |
| Indexing | time of `dal:refresh:index` on the same data |
| Storefront | home, category listing with filters, search, product detail: latency under a fixed load |
| Store API | product listing with aggregations, cart, checkout |
| Admin API | product search with criteria and aggregations, bulk write through the sync API |
| Translator overhead | the same PostgreSQL queries with and without translation (time in the middleware per statement) |

Rules: the database settings are documented per run (buffer sizes, connection pooling); no database gets tuning the others do not get.
As long as PostgreSQL runs translated MySQL SQL, its numbers include the translator; the overhead row makes that visible.
