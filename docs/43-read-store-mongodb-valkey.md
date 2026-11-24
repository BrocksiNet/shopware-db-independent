# Read store adapters: MongoDB and Valkey

Handoff M of wave 9.
Both adapters live in `instance/src/Core/Framework/ReadStore/Adapter/` on the branch `poc/read-store`.
They are port validation targets, not recommendations.
Timings are pending milestone 2.

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

## Timings

Pending milestone 2.
