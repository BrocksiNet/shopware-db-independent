# 47 O1a: full product document hydrated from OpenSearch `_source`

Wave 10, handoff A.
Question: doc 46 "What is not proven", point 1: is O1+ with `_source` hydration end to end as fast and as correct as wave 9 inferred?

## Answer

Proven for correctness, measured for speed on a shared VM (D repeats the timings in a quiet setup).
O1a serves every product read of listing and search from `_source` (detail keeps one SQL read for the breadcrumb's `mainCategories`), returns the same entities as the SQL read (50 of 50 requests identical, `--verify` S2 and R4 OK) and roughly doubles c=8 throughput against O1 at 5,000 products (905/s against 458/s) and adds 24 % at 150,000 products (442/s against 355/s).
MySQL CPU under c=8 drops by 82 % at 5,000 products and by 86 % at 150,000 products.
The price is a 2.4 times larger index (462 MB against 190 MB) and a 1.9 times longer `es:index` (170 s against 88 s) at 150,000 products.
Detail by id stays slower than Valkey: 2.9 ms against 0.09 ms for S2 and 9.9 ms against 0.6 ms for R4 at 5,000 products, because the bench's ids criteria runs an OpenSearch search before the `_mget`.
The projector cannot write the document alone: a partial `update` wipes the search fields of the product (see "Projector"), so it re-indexes the product through the Shopware indexer instead.

The OpenSearch OOM kills of 2026-11-24 did not recur: the run used the VM after the cleanup, with the other lanes running and about 1.5 to 1.9 GB of memory available.

## Design

### Where the document goes

One extra field in the existing product index: `rs_document`, mapped as `{"type": "object", "enabled": false}`.
OpenSearch keeps it in `_source` only: no inverted index, no doc values, no mapped sub-fields, so it adds no field count and cannot change query semantics.
The `_source` includes of the product index grow from `id, autoIncrement` to `id, autoIncrement, rs_document` (`ElasticsearchProductDefinition::getMapping()`).
`ElasticsearchProductDefinition::fetch()` fills it with wave 9's `SqlDocumentBuilder::build()`, the same builder with the same `DocumentExtender`s as every other read store (doc 40), so the document equals the projector's document by construction.
All of it sits behind `SHOPWARE_ES_SOURCE_DOCUMENT` (default `0`): with `0` the mapping, `_source` and `fetch()` are exactly O1.

Query fields, `displayGroup` collapsing, `postFilters`, aggregations, analyzers and word search are not touched: they still read the existing indexed fields.

### How the document reaches the route

`SalesChannelRepository::_search()` runs the search (OpenSearch returns ids), then `read(cloneForRead($ids))`, which calls `EntityReaderInterface::read()` and then dispatches the loaded events.
O1a keeps that flow and replaces only the SQL read:

1. `ElasticsearchEntitySearchHydrator` takes `rs_document` out of every hit's `_source` and puts it into a request-scoped `SourceDocumentBuffer` (reset by `kernel.reset`).
   It removes the field from the hit data, so the full document never lands in the `search` extension of the entities.
2. `SourceDocumentEntityReader` decorates `EntityReaderInterface`.
   For `SalesChannelProductDefinition`, the live version and an ids-only criteria it takes the documents from the buffer.
   Ids that are not in the buffer (a read without a search, for example detail by id) come from one `_mget` on the product alias with `_source_includes=rs_document`.
3. Wave 9's `DocumentHydrator` turns the documents into `SalesChannelProductEntity` objects (shape (a) of doc 44) through a new event-free method.
   `categories` and `tags` are read by id from the `categoryIds` and `tagIds` of the document, without a product query.
4. `SalesChannelRepository::read()` dispatches the loaded events on these entities as before, so live prices and purchase limits are computed at display time; stock and availability come from the document, as in wave 9.

Everything else goes to the inner SQL reader unchanged and is counted by reason: filters, sortings, aggregations, partial fields or a limit on the read criteria, a non-live version, associations the document does not hold, and ids without a document (the product indexer skips products without visibilities).

No change to `SalesChannelRepository`, `EntityRepository` or the DAL write path.

## Code

Branch `poc/wave10` in `instance/` (not pushed):

- `df32669d50c` `feat(elasticsearch): write full product document into _source and read it back (O1a)`:
  mapping, `_source` includes and `fetch()` in `ElasticsearchProductDefinition`, `SourceDocumentBuffer`, `SourceDocumentEntityReader`, hits to buffer in `ElasticsearchEntitySearchHydrator`, `DocumentHydrator::hydrateEntitiesWithoutEvents()`, `SourceDocumentReaderSwitch` and `read-store:bench:integration --store=o1a`.
- `1a19a6d4797` `fix(elasticsearch): read prices from _source, stamp entity names, consume buffered documents (O1a)`:
  the buffer handed documents of one request to the next iteration of a CLI loop, `prices` was read by SQL, and nested entities had no entity name.
- `4814f62bc31` `feat(elasticsearch): projector storage for the _source document and w10 composed store (O1a)`:
  `SourceDocumentStorage` (store key `opensearch-source`), the composed store `store-w10-opensearch-valkey` in wave 10 namespaces (`rs_w10_ov_`, Valkey `rs_w10_ov` in database 5), and a safer `read-store:bench:consistency --mode=misses` (it now aborts before any write when the probe products are not in the store, and takes the originals it restores from the database, not from the store).
- `b09147c26f9` `fix(elasticsearch): re-index products instead of partial _source updates in the O1a projector storage`.

PHPStan is clean and php-cs-fixer applied on every touched file.

## Results

All runs: `orm_spike` (5,000 products, 4,140 in the index) and `read_store_large` (150,000 products, 126,000 in the index), MySQL write model, `APP_ENV=prod`, HTTP cache off.
The product indexer skips products without a visibility and parents of variants without `displayParent` (`ElasticsearchProductDefinition::fetch()`), which is why fewer products are in the index; O1 and O1a skip the same products.
Other sw-dev lanes ran during every timing, so the absolute numbers are noisy; O1, O1a and the composed store ran back to back in one block each.

### Index size and rebuild time

`es:index --no-queue`, wall time and the `es-indexing` log line agree.

| Data set | O1 time | O1a time | O1 size | O1a size |
|---|---|---|---|---|
| `orm_spike` (4,140 products) | 2.3 s | 4.5 to 8 s | 6.9 MB | 16.3 MB |
| `read_store_large` (126,000 products) | 88 s | 170 s | 190 MB | 462 MB |

The document adds 272 MB at 150,000 products; the composed store needs 442 MB of OpenSearch plus 808 MiB of Valkey RAM for the same data, and its rebuild took 120.1 to 131.9 s (docs 38 and 43).
E6.03's "~454 MB OpenSearch index" holds for the O1a index as a whole.
Memory after the 150,000 build was about 1.8 GB available on the VM, disk 87 %.

### Statements per request

`read-store:bench:integration --store=o1a --mode=sql-accounting`, `orm_spike`, 10 iterations, real store-api routes:

| Route | O1 statements | O1a statements | Reader counters for O1a |
|---|---|---|---|
| Detail, full | 30 | 27 | `mget` 1, `document` 1, `fallback:association:mainCategories` 1 per request |
| Detail, `skipConfigurator` and `skipCms` | 9 | 7 | as above |
| Listing | 12 | 10 | `document` 1 per request |
| Search | 11 | 8 | `document` 1 per request |

The counters are per request (23 requests per route, 20 measured plus 3 warm-up).
On listing and search the reader served every product read from the document, with no fallback.
On detail the main read comes from one `_mget` (the route reads by id without a search), and one read falls back to SQL: the breadcrumb builder reads the product again with the `mainCategories` association, which the document does not hold.
The other statements are not product reads of the reader: sales channel context, CMS and configurator for the full detail page, SEO URLs and the categories that the reader loads by id from `categoryIds`.
A rerun with 20 iterations gave the same statement counts.

### Equality

- `read-store:bench:integration --store=o1a --mode=equality`: 50 of 50 requests identical, 46 served from the document, 4 fell back to the SQL read, 0 differences.
- `orm-spike:bench --impl=dal-opensearch --scenario=all --verify` with the O1a env: S2, S4, R3b and R4 OK; S1, S3 and S5 differ from the DAL exactly as O1 does (same first difference for S3 and S5).
  S1 differs on a sort tie at item 6, whose winner depends on the segment layout: after `_forcemerge?max_num_segments=1` on both indices O1 and O1a return the same id.
  R3b matches the DAL on O1a and differs on O1 (manufacturer aggregation 71 against 73) with both indices built from the same database; both hold 155 products of that manufacturer, and the aggregation is an OpenSearch aggregation that the reader never touches, so this is a search-side difference whose cause was not isolated here.
- Corpus (`read-store:bench:corpus`): not run, it compares a `StoreImplementation` with the DAL by ids and aggregations; O1a changes neither the query nor the ids, only the hydration, which equality and `--verify` cover.

### Projector

`SourceDocumentStorage` plugs into the wave 9 projector (`READ_STORE_PROJECTOR_STORES=opensearch-source`, `READ_STORE_PROJECTOR_MODE=sync`).
The first version wrote the projector's document with a partial `update` (`{"doc": {"rs_document": ...}}`).
That silently broke search: the product index keeps only `id`, `autoIncrement` and `rs_document` in `_source`, and OpenSearch rebuilds an updated document from `_source`, so the update dropped every search field.
After one probe run, 516 of 4,140 documents had no `active`, `visibilities` or `parentId` any more and fell out of every listing (S2 and R4 then failed with "not found or not visible"); `_mget` still returned their document, so the probes looked green.
The fixed storage calls `ElasticsearchIndexer::updateIds()` for the changed ids, which rebuilds the search fields and the document in one request; after a rebuilt index and a second probe run, 0 of 4,140 documents lack `active`.
This needs `SHOPWARE_ES_INDEXING_ENABLED=1`, as O1 itself does.
Core finding 46.

Doc 45 miss probes, `read-store:bench:consistency --mode=misses --store=opensearch-source` on `orm_spike`:

| | Caught | Missed |
|---|---|---|
| Shopware indexer only (projector off) | 1 to 5, 7 to 9, 18 | 6, 10 to 17 |
| Indexer plus projector | 1 to 5, 7 to 9, 12 to 15, 18 (13 of 18) | 6, 10, 11, 16, 17 |

10 (raw SQL), 16 (tax rate) and 17 (currency factor) are the same structural misses as doc 45.
6 (create) and 11 (version merge) miss because the probes create products without a visibility, which the product indexer does not index; the storefront cannot show such products either, and the reader falls back to SQL for ids without a document.
The probe rows of `orm_spike` that earlier runs changed were restored and checked (no `Probe` names or descriptions left).

### Timings

`orm-spike:bench --scenario=S2,S1,R3b,R4 --iterations=30`, median ms, statements in brackets.
S2 is the detail of one variant (R1), S1 the listing (R2), R3b the storefront search, R4 the `mget` of 24 products.

| Data set | Variant | S2 | S1 | R3b | R4 | MySQL CPU of the block |
|---|---|---|---|---|---|---|
| `orm_spike` | O1 | 7.59 (4) | 9.85 (2) | 13.88 (2) | 12.04 (4) | 275 ms |
| `orm_spike` | O1a | 2.93 (1) | 7.27 (0) | 12.00 (0) | 9.86 (1) | 40 ms |
| `orm_spike` | `store-w10-opensearch-valkey` | 0.09 (0) | 6.35 (0) | 23.76 (2) | 0.60 (0) | 407 ms |
| `read_store_large` | O1 | 12.67 (4) | 17.25 (2) | 32.98 (2) | 17.41 (4) | 615 ms |
| `read_store_large` | O1a | 4.71 (1) | 9.53 (0) | 28.39 (0) | 11.65 (1) | 77 ms |

`read-store:load --concurrency=8 --duration=20s` (mix R1 50 %, R2 30 %, R3b 20 %):

| Data set | Variant | Throughput | p50 / p95 | R1 p50 | R2 p50 | R3b p50 | Statements per request | MySQL CPU in 20 s |
|---|---|---|---|---|---|---|---|---|
| `orm_spike` | O1 | 458/s | 14.7 / 35.7 ms | 11.3 ms | 15.7 ms | 21.4 ms | 2.7 | 18.4 s |
| `orm_spike` | O1a | 905/s | 7.2 / 20.2 ms | 4.0 ms | 9.1 ms | 13.0 ms | 0.5 | 3.3 s |
| `orm_spike` | `store-w10-opensearch-valkey` | 543 to 581/s | 4.5 / 58 ms | 0.1 ms | 8.0 ms | 49 to 51 ms | 0.4 | 64 to 68 s |
| `read_store_large` | O1 | 355/s | 15.4 / 52.6 ms | 11.2 ms | 16.8 ms | 37.0 ms | 2.7 | 16.0 s |
| `read_store_large` | O1a | 442/s | 9.8 / 49.7 ms | 5.5 ms | 12.6 ms | 33.0 ms | 0.5 | 2.2 s |

The 0.5 statements per request of O1a are the categories of R1, loaded by id (1 statement per detail).
The composed store spends its MySQL CPU in R3b: all 4,688 statements of its run are R3b's 2 statements, from the SQL `ProductSearchBuilder` keyword lookup that the store runs before its own query, while O1 and O1a search through the OpenSearch search builder.
MySQL CPU over 20 idle seconds was 82 ms, so the other lanes did not distort these numbers.
The composed store was not built at 150,000 products: 808 MiB of Valkey (doc 43) against about 1.5 GB available would have risked the OOM kills of 2026-11-24.

### `_mget` against Valkey for detail

Through the whole bench path, a detail costs 2.9 ms (5,000) and 4.7 ms (150,000) on O1a against 0.09 to 0.18 ms on Valkey (doc 43 and above), and 24 products cost 9.9 to 11.7 ms against 0.6 to 2.5 ms.
Most of the O1a time is not the `_mget`: the bench adds `STATE_ELASTICSEARCH_AWARE` to its ids criteria, so the sales channel repository first runs an OpenSearch search (visibility and availability), then the reader takes the documents from the hits.
The store-api detail route does not search; its reader counter shows one `_mget` per request.
A raw `_mget` of one document from inside the OpenSearch container takes 2.4 ms median with `curl`, process start included.
For listing and search the difference disappears, because O1a takes the documents from the search hits and needs no second round trip (S1 7.27 ms on O1a against 6.35 ms on the composed store at 5,000 products).

## E6.03 estimate

The 4 to 7 person-weeks of doc 38 for `_source` hydration hold, at the upper half.
The PoC took about 800 changed lines in 4 commits for the happy path; what is left for core is mostly not code size:

- The write path: a `_source` document can only be written by a full re-index of the product (no partial update), so every listener that the projector adds (manufacturer, option, media, tax, currency) must feed `ElasticsearchIndexer::updateIds()`, and the tax and currency misses still need a design.
- Fallbacks by reason are needed and must stay counted: associations the document does not hold (`mainCategories`, CMS, cross-selling), non-live versions, products without a visibility.
- `mainCategories` (breadcrumb) belongs into the document, otherwise every detail page keeps one SQL product read.
- Reads by id that are `STATE_ELASTICSEARCH_AWARE` (like the bench's S2 and R4) pay a search plus the document; checking visibility on the document instead would close most of the gap to Valkey, which O1a does not do yet.
- Index size and rebuild time double; operators need that in the sizing guide, and custom fields drive the document size (doc 48).
- Tests: the PoC has none for the reader, the buffer and the storage.

## Commands for D

Helper `/tmp/wave10-a/env.sh <db>` (`orm_spike` or `read_store_large`) defines `a_console o1|o1a|plain <console args>` with separate cache directories and the index prefixes `rs_w10_o1_<db>_` and `rs_w10_o1a_<db>_`, `a_cpu_usec` (MySQL cgroup CPU) and `os <path>` (curl into OpenSearch).
The four indices `rs_w10_o1_orm_spike__product`, `rs_w10_o1a_orm_spike__product`, `rs_w10_o1_read_store_large__product` and `rs_w10_o1a_read_store_large__product` are kept for D; the composed store's index and Valkey keys were deleted and rebuild in 3.6 s on `orm_spike`.

```bash
cd /tmp && . /tmp/wave10-a/env.sh read_store_large   # or orm_spike
A_INDEXING=1 a_console o1a es:index --no-queue         # rebuild, also o1
a_console o1  orm-spike:bench --impl=dal-opensearch --scenario=S2,S1,R3b,R4 --iterations=30
a_console o1a orm-spike:bench --impl=dal-opensearch --scenario=S2,S1,R3b,R4 --iterations=30
a_console o1  read-store:load --impl=dal-opensearch --concurrency=8 --duration=20s
a_console o1a read-store:load --impl=dal-opensearch --concurrency=8 --duration=20s
a_console o1a read-store:bench:integration --store=o1a --mode=sql-accounting
a_console o1a read-store:bench:integration --store=o1a --mode=equality
a_console plain read-store:rebuild --store=w10-opensearch-valkey
a_console plain orm-spike:bench --impl=store-w10-opensearch-valkey --scenario=S2,S1,R3b,R4 --iterations=30
a_console plain read-store:load --impl=store-w10-opensearch-valkey --concurrency=8 --duration=20s
```

Wrap each run in `c0=$(a_cpu_usec); ...; c1=$(a_cpu_usec)` for the MySQL CPU in microseconds.
