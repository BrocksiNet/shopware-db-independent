# PostgreSQL hot spots

Source: wave 4, handoff A.
Measured on the shared benchmark stacks (`bench_pg`, php-fpm per database), three runs each, medians, noisy machine.
The final numbers come from the separate benchmark handoff.

## Summary

| Finding | Cause | Fix | Result |
|---|---|---|---|
| `search::detect-keywords` seq scan | `LIKE` on the nondeterministic collation `ci` cannot use an index | `SqlDialect::caseInsensitive()`, expression index with `gin_trgm_ops` | 9.6 ms to about 1 to 1.8 ms |
| `seo_url::replacement` 13 ms | `IN` of about 570 values on `ci` hashes through ICU on a seq scan | `lower(path_info) COLLATE ucs_basic` plus btree expression index | 13 ms to 1.3 ms |
| Deadlock on `product_keyword_dictionary` | REPLACE became delete-before-insert, rows locked in different order per worker | insert-or-ignore (`ON CONFLICT DO NOTHING`) plus `ksort` | 0 errors, 0.2 to 0.5 req/s up to about 8.5 req/s |
| `seo-url::resolve` 7 to 11 ms | first use of the ICU collator per connection | persistent connections (`DATABASE_PERSISTENT_CONNECTION=1`, already supported) | see latency table |

## Keyword search

`caseInsensitive($column)` returns the column as is on MySQL and MariaDB (their collation is already case-insensitive) and `lower(column) COLLATE ucs_basic` on PostgreSQL.
The collation is written unquoted, because the translator turns a double-quoted `"C"` into a string literal.
The PHP side lowercases the bound parameters with `mb_strtolower`.
The migration `Migration1795000000PostgreSqlCaseInsensitiveSearchIndexes` creates the indexes on PostgreSQL only, through the native PDO connection, and skips the trigram indexes if `pg_trgm` cannot be created.
`EXPLAIN` on `bench_pg` shows a `BitmapOr` over both trigram indexes instead of the seq scan.

Trade-off: the `ci` collation ignored accents (level 1), the lower-based match does not.
Keyword search on PostgreSQL is therefore case-insensitive but accent-sensitive.

## SEO URL replacement

The statement filters `seo_url.path_info IN (...)` on the nondeterministic column.
`EXPLAIN ANALYZE` showed a seq scan with ICU hashing per row.
With the `lower() COLLATE ucs_basic` expression the planner uses the btree index `(language_id, lower(path_info))`.

## Deadlock

`SearchKeywordUpdater::insertDictionary()` used REPLACE.
On PostgreSQL the rewriter turns that into delete-before-insert, so four parallel bulk requests locked overlapping dictionary rows in different orders.
Now the dictionary is sorted (`ksort`) and written with insert-or-ignore.
Reproduced with `scripts/benchmark-load.py` (bulk sync, 4 parallel): before 11 failures, after 0.

MySQL behaviour change: an existing dictionary row is no longer replaced, it is left as is.
The row only holds `keyword` and `reversed`, which are derived from the same key, so the content is identical.

## Connection setup

The first use of the `ci` collation in a new connection costs 7 to 11 ms (ICU collator open).
It showed up as `seo-url::resolve` (about 11.7 ms average per call, 15 calls over three requests, MariaDB about 0.2 ms).
Persistent connections remove it.

Median request latency on PostgreSQL (ms, ranges over three runs):

| Scenario | Before | Indexes and fixes | Plus persistent connections |
|---|---|---|---|
| search | 267 to 292 | 182 to 212 | 145 to 155 |
| product detail | 193 to 232 | 163 to 179 | 127 to 134 |
| home | 305 to 345 | 291 to 337 | 238 to 257 |
| listing | 188 to 240 | 208 to 218 | 150 to 218 |
| bulk sync | 372 to 428 | 322 to 338 | not measured |

## Next slowest statements (PostgreSQL, listing requests)

Server-side timings, average per request over three listing requests.

| Statement | PostgreSQL ms | Calls |
|---|---|---|
| `product-listing-route::loading::aggregation::options` | 6.1 | 5 |
| `seo_url::replacement` (after fix, includes cold connection) | 3.6 | 10 |
| `aggregation::price` | 2.9 | 5 |
| `search-ids` | 2.6 | 10 |
| `aggregation::properties` | 2.4 | 5 |
| `read` | 2.3 | 5 |

A per-statement MariaDB comparison was not obtained: the MariaDB slow-log capture returned only generic connection statements, so no MariaDB numbers are claimed here.
Open, not fixed: the aggregation statements (options, price, properties) and `search-ids` are plain joins and aggregates; a fix needs plan analysis per query and is not cheap.
