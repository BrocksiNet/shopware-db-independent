# Inventory summary (phase 1)

State: Shopware trunk at `ae0190f5892`, MariaDB schema as installed by the lane, PostgreSQL 18.7. Details and scripts are in `docs/inventory/`.

## Size of the problem

| Area | Number | Source |
|---|---|---|
| Tables / columns / foreign keys | 250 / 2,168 / 418 | `inventory/schema` |
| Triggers | 0 | `inventory/schema` |
| `BINARY(16)` columns | 715 (691 named `id` or `*_id`, 24 others) | `inventory/schema` |
| Composite foreign keys that include a version column | 63 | `inventory/schema` |
| JSON columns (`longtext` + `json_valid` check) | 220 | `inventory/schema` |
| Text columns with a case-insensitive collation (`utf8mb4_unicode_ci`) | 507 | `inventory/schema` |
| Generated columns | 15 | `inventory/schema` |
| Core migration classes | 910 | `src/Core/Migration` |
| PHP files outside DAL and migrations that use the connection | 446 | `inventory/raw-sql` |
| ... of those with MySQL-specific SQL | 241 | `inventory/raw-sql` |
| Files using binary uuid helpers (`Uuid::fromHexToBytes` etc.) | 212 | `inventory/raw-sql` |

## What we learned

1. **The schema is the easy part.** A script (`inventory/schema/mysql-to-pg-ddl.py`) translates the installed MariaDB schema from `information_schema` to PostgreSQL DDL. Applied to a scratch schema it produced 250 tables, 2,168 columns, 418 foreign keys, 715 `uuid` columns, 220 `jsonb` columns and 726 indexes without a failed statement. Replaying the 910 MySQL migrations on PostgreSQL is not needed for the proof of concept.
2. **The DAL has four clean seams.** Reader, searcher, aggregator and write gateway are interfaces wired in `DependencyInjection/data-abstraction-layer.php`. The MySQL-specific SQL sits in a known list of places (`inventory/dal/findings.md`), which a `SqlDialect` service can cover.
3. **Raw SQL outside the DAL is the large part.** 241 files, dominated by backtick quoting (1,434 hits in 135 files), `HEX()`/`UNHEX()` and the binary id helpers. Most of it is mechanical once ids and quoting go through one place.
4. **Ids are the widest change.** 715 columns and 212 PHP files assume 16 raw bytes. With native `uuid` the conversion has to move behind one id codec.
5. **Case sensitivity is a behaviour change, not a syntax change.** 507 columns compare case-insensitively on MySQL. On PostgreSQL this needs a nondeterministic ICU collation or `lower()` per query; unique indexes are affected too.
6. **The DTO pull request helps at the API edge only.** https://github.com/shopware/shopware/pull/17858 merges cleanly into trunk but keeps `Criteria` and the repository inside the route. The storage port is our addition. Symfony's Serializer is the right tool for row-to-DTO mapping; ObjectMapper does not coerce types (`inventory/dto/findings.md`).

## Consequences for the plan

- Phase 2 uses the schema translator instead of porting migrations, plus a driver-aware connection factory next to `MySQLFactory`.
- Phase 3 introduces `SqlDialect` and an id codec in the DAL first, then measures how far the installer and the storefront get on PostgreSQL.
- The DTO slice (newsletter recipient status) runs after the DAL reads work, on top of the merged DTO branch.

## Open questions

- Which queries rely on `ONLY_FULL_GROUP_BY` being switched off (`MySQLFactory.php:107`)?
- Does the retry logic survive PostgreSQL aborting the transaction after a failed statement?
- Nondeterministic collation or `lower()` for the 507 case-insensitive columns?
