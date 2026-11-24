# Read store adapters: MongoDB and Valkey

Handoff M of wave 9.
Both adapters and the composed `opensearch-valkey` (O1b) adapter live in `instance/src/Core/Framework/ReadStore/Adapter/` on the branch `poc/read-store` (milestone 2 alignment commit `19c2591`).
They are port validation targets, not recommendations.

## Capabilities

| Capability | MongoDB (`MongoDbStorage`) | Valkey (`ValkeyStorage`) |
|---|---|---|
| `Storage` (generations, store, get, mget) | yes | yes |
| `FilterAware` | yes | no, key-value only |
| `AggregationAware` | yes | no |
| `SearchAware` | yes | no |

Contract results (container `instance-web-1`, mongo 8.3.17, Valkey database 5): MongoDB 51 tests pass, Valkey 11 tests pass, none incomplete, none failed.

## Valkey mapping

Keys all start with the prefix `rs_store` and live in database 5 only.
`<prefix>:live` is the live pointer, `<prefix>:gens` the set of generations, `<prefix>:doc:<generation>:<id>` the JSON document and `<prefix>:ids:<generation>` the id set of a generation.
`store()` pipelines `SET` and `SADD` into the live and every pending generation, `mget()` is one `MGET`.
Clearing and dropping a generation walks the id set with `SSCAN` and `UNLINK`, nothing flushes a database.
`filter()`, `aggregate()` and `search()` do not exist, the composed store resolves ids in another engine and hydrates with `mget()`.

## MongoDB mapping

One database `rs_...`, one collection `rs_<generation>` per generation and `rs_meta` with the live pointer.
A stored document is `{_id, d, f, s}`.
`d` is the document as built and is what `get()` returns.
`f` holds the queryable fields with strings folded like `utf8mb4_unicode_ci` (case and accents), so equality, `Contains`, `Prefix` and grouping compare folded values and need no collation.
`s` holds the search keywords per language as `{k: folded keyword, r: ranking}` entries, because keywords are not safe field names.
The collection default collation is `en`, strength 1, used for sorting, string ranges and the min and max of a collapse.
Wildcard indexes on `f.$**` and `s.$**` are created when a generation is swapped live.

Every field goes through `FieldResolver`, so the price rounding rule of K (commit 69a048e7757) applies without own code.
Filters compile to truth sets: `Not` swaps the set that is wanted, unknown matches neither side, which keeps three-valued logic exact.
Presence of a value is tested with `$exists` plus `$ne: null`, because `{path: {$ne: null}}` alone is true below an empty array (an empty PHP array is a BSON array).
Aggregations run as one `$facet` pipeline without collation, hits as one pipeline with a `$facet` for the exact total.
`Terms` buckets of string fields are ordered and cut in PHP with an ICU primary collator, because the command runs without collation.

## Not answered, `NotSupportedByEngine`

- Nested and payload-only fields, and price rounding other than the currency rounding (from `FieldResolver`).
- Path segments that are empty, contain a dot, start with `$` or are all digits.
- `Contains` and `Prefix` needles with a NUL byte.
- Equality and ranges with a value type that does not match the field type in a way the reference defines (for example a string field compared with a number).
- Sorting by list fields, collapsing by list or custom fields.
- `Min` and `Max` on string fields, `Sum`, `Avg` and `Stats` on non-numeric fields, anything else of `Aggregation`.

The MongoDB `$text` index is not used: the DAL search matches keywords with the scoring of the reference evaluator, `$text` stems and scores differently, so using it would approximate.

## Composed store O1b (OpenSearch + Valkey)

`OpenSearchValkeyStorage` in `Adapter/OpenSearchValkey/` wraps the OpenSearch adapter of handoff O and the Valkey adapter.
It is registered as `read_store.storage.opensearch-valkey` with its own namespaces (indices `rs_ov_product_<generation>`, Valkey keys `rs_ov`), so it shares no data with the plain `opensearch` and `valkey` stores.
OpenSearch answers `filter()`, `search()` and `aggregate()`, the ids of the hits are hydrated from Valkey with one `MGET` in the order OpenSearch returned them.
Total, aggregations and scores come from OpenSearch unchanged.
Writes: `store()` writes the documents to Valkey first and the index second, `remove()` the index first and Valkey second, so a hit always finds its document.
A swap flips the index alias first and the Valkey pointer second.
In that short window a hit can name a document the live Valkey generation does not hold, the store then throws `NotSupportedByEngine` and the caller falls back to the DAL, it never drops or invents a document.
`get()`, `mget()` and `liveGeneration()` are answered by Valkey.
The OpenSearch adapter still returns the documents it holds in its own `_source`, the composed store ignores them, so the memory saving of an index without `_source` is not realised yet.
Contract result: 51 tests pass, 1 incomplete, 0 failed.
The incomplete test is inherited from the OpenSearch adapter (collapse sorted by `cheapestPrice` descending is not supported, the reference orders groups by the minimum).
One extra test proves the fallback for a hit without a document.

## Limitations

The addresses of MongoDB, Valkey and OpenSearch are fixed for the lane in `DependencyInjection/m.php` (`mongodb://instance-mongodb-1:27017`, `instance-valkey-1:6379`, namespaces `rs_readstore`, `rs_store`, `rs_ov`), which is fine for the PoC and has to read env variables for a product setup.

## Licensing

MongoDB Server since the releases after 16 October 2018 is under the Server Side Public License, earlier versions under AGPLv3: https://www.mongodb.com/legal/licensing/community-edition
Section 13 of the SSPL requires whoever offers the program as a service to publish the source of the whole service stack under the SSPL: https://www.mongodb.com/legal/licensing/server-side-public-license
Valkey is under the BSD 3-Clause license (file `COPYING` of the repository: https://raw.githubusercontent.com/valkey-io/valkey/unstable/COPYING), the project is described as BSD licensed and backed by the Linux Foundation: https://valkey.io/
Whether a hosting provider that offers Shopware on MongoDB falls under section 13 has to be checked with a lawyer, this document does not decide it.

## Operations

A shop operator has to run one more service (MongoDB 8 for `mongodb`, Valkey or Redis for `valkey`) and give the adapters their address.
In the lane the addresses are fixed in `DependencyInjection/m.php` (`mongodb://instance-mongodb-1:27017`, `instance-valkey-1:6379`), a product setup would read them from env.
MongoDB needs the `mongodb` PHP extension and `mongodb/mongodb`, Valkey the `redis` extension.
Rebuilds are blue/green: the new generation is a new collection or key set, the swap flips the pointer and drops the old one.
Valkey data is memory only unless persistence (RDB or AOF) is configured, a lost Valkey is rebuilt from the DAL.

## Timings, sizes and corpus (milestone 2)

All milestone 2 timings below are sanity runs (`other lanes stopped: no`, `APP_ENV=prod`, MySQL 8.4 write DB).
Canonical stopped-lanes timings belong to handoff F.

### `--verify` and 35-entry criteria corpus

| Store | `--verify` (`orm_spike`) | Criteria corpus (`rs_k_corpus`, 35 entries) |
|---|---|---|
| `store-mongodb` | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 28 match, 5 dal-defect, 2 fallback, 0 diff |
| `store-valkey` | S2, R4 OK; S1, S3, R3b, S5 unsupported (KV only) | 0 match, 0 dal-defect, 35 fallback, 0 diff |
| `store-opensearch-valkey` (O1b) | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 27 match, 5 dal-defect, 3 fallback, 0 diff |

### Rebuild and storage footprint

| Store | Dataset | R7 rebuild | Docs/s | Write-DB stmts | Footprint |
|---|---|---|---|---|---|
| `store-mongodb` | `orm_spike` (5k) | 2.0 s | 2,493 | 204 | WiredTiger compressed collection + wildcard indexes |
| `store-mongodb` | `read_store_large` (150k) | **71.6 s** | **2,095** | 6,004 | **351.6 MiB disk** (225.1 MiB WiredTiger storage + 126.5 MiB wildcard indexes; 1,180.6 MiB raw BSON) |
| `store-valkey` | `orm_spike` (5k) | 1.0 s | 4,832 | 204 | ~26 MiB RAM (DB 5) |
| `store-valkey` | `read_store_large` (150k) | **41.8 s** | **3,587** | 6,004 | **780.7 MiB RAM** delta (55.6 → 836.3 MiB, 150k docs + id set) |
| `store-opensearch-valkey` | `orm_spike` (5k) | 2.7 s | 1,874 | 204 | 13.8 MB OS disk + ~26 MiB Valkey RAM |
| `store-opensearch-valkey` | `read_store_large` (150k) | 120.1 s | 1,249 | 6,004 | **442.4 MB OS disk + 808.0 MiB Valkey RAM** (note: OS still keeps `_source` in the PoC) |

### Query timings (sanity run)

Cells: median / p95 in ms (write-DB statements in parentheses).
`orm_spike`: 5 warm-up, 50 iterations (host load ~6.6); `read_store_large`: 3 warm-up, 15–20 iterations (50 for `valkey`; host load 3.7–6.2).

| Store | Dataset | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|---|
| `store-mongodb` | `orm_spike` (5k) | 2.22 / 2.75 (0) | 0.27 / 0.44 (0) | 8.69 / 11.14 (0) | 25.15 / 31.76 (2) | 0.98 / 2.05 (0) |
| `store-mongodb` | `read_store_large` (150k) | 36.02 / 41.21 (0) | 0.35 / 0.65 (0) | 216.58 / 253.92 (0) | 809.61 / 947.51 (2) | 0.86 / 0.96 (0) |
| `store-valkey` | `orm_spike` (5k) | unsupported | 0.15 / 0.22 (0) | unsupported | unsupported | 0.66 / 0.91 (0) |
| `store-valkey` | `read_store_large` (150k) | unsupported | **0.14 / 0.26** (0) | unsupported | unsupported | **0.75 / 1.00** (0) |
| `store-opensearch-valkey` | `orm_spike` (5k) | 7.22 / 8.40 (0) | 0.15 / 0.18 (0) | 9.80 / 11.97 (0) | 26.79 / 36.98 (2) | 0.79 / 1.06 (0) |
| `store-opensearch-valkey` | `read_store_large` (150k) | **14.47 / 33.51** (0) | **0.18 / 0.20** (0) | **20.50 / 38.51** (0) | OOM on OS under shared-lane RAM pressure\* | **2.46 / 5.68** (0) |

\*On `read_store_large` with all 47 other lane containers running, Valkey (818 MiB RSS) + OpenSearch (4 GiB heap) triggered a container OOM kill during the Painless-scripted R3b run; `opensearch-valkey` R3b and R5 are measured with other lanes stopped in handoff F.

Short R5 sanity load for `store-mongodb` on `read_store_large` (15 s per level, 0 errors):

| Store | c | Throughput/s | p50 ms | p95 ms | R1 / R2 / R3b p50 ms | Write-DB stmts/req | `instance-mysql-1` CPU s |
|---|---|---|---|---|---|---|---|
| `store-mongodb` | 1 | 5.1 | 1.1 | 918.9 | 0.6 / 37.9 / 841.8 | 0.4 | 8.1 |
| `store-mongodb` | 8 | 19.4 | 32.9 | 2,046.7 | 0.5 / 40.4 / 1,838.9 | 0.4 | 77.6 |

Notice that even with MongoDB serving 100 % of product reads, `instance-mysql-1` still burned **77.6 CPU s** over 16.4 s at `c=8` solely because R3b invokes Shopware's SQL `ProductSearchBuilder` keyword interpreter (`product_search_keyword`) on the write database.

### Takeaways

- **MongoDB 8.3** is the strongest single-engine non-search document store: fastest rebuild among queryable stores (71.6 s), smallest disk footprint (351.6 MiB via WiredTiger compression), sub-millisecond `S2`/`R4` (0.35 / 0.86 ms), and 18–22× faster than MySQL/PostgreSQL JSON on `S3` (217 ms vs 3,896–4,852 ms), though still 14× slower than OpenSearch on `S3` (15.5 ms) and encumbered by SSPL licensing.
- **Valkey** sets the hydration floor at 150k products: `S2` **0.14 ms** and `R4` **0.75 ms** (32× and 16× faster than DAL), at a cost of ~5.2 KiB RAM per product (781 MiB for 150k products).
- **Composed O1b (`opensearch-valkey`)** gets the best of both worlds on every non-scripted scenario: OpenSearch latency for listings/facets (`S1` 14.5 ms, `S3` 20.5 ms) and Valkey latency for detail/mget hydration (`S2` 0.18 ms — 10.5× faster than standalone OpenSearch, 54× faster than O1; `R4` 2.46 ms — 3.4× faster than standalone OpenSearch, 6.3× faster than O1).
  Removing `_source` from the OpenSearch side (so documents live only once in Valkey) would cut OpenSearch index disk usage substantially, at the cost of replacing the Painless `_source.rs.k` scorer with native OpenSearch scoring.
