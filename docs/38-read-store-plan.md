# Read store: research and PoC plan (wave 9)

State: 2026-11-23, research before wave 9.
Question: can Shopware serve its hot reads from a read-optimized store that is fed from the DAL, with interchangeable engines (MySQL/MariaDB/PostgreSQL/SQLite JSON, OpenSearch, MongoDB, Valkey), while the SQL database stays the write model and the source of truth?
Goal, in the words of the archived prototype `shopware/storage` (README): "provide a read-optimized system for better scalability and performance and support different kinds of document storage engines like opensearch, mongodb, etc."

This doc holds the research and the plan.
The wave 9 PoC (docs 39 to 45) builds and measures it, and the conclusion section at the end is written by wave 9 F.

## Why this wave

Feedback on the experiment's results raised three points that wave 8 did not answer:

1. The DAL ties the database structure, the entity model, business data access and the public API contract together.
   A storage change becomes an API change.
   Wave 8 kept the DAL as the write and admin API (doc 29), but it did not ask whether the hot storefront reads need the DAL entity shape at all.
2. Shopware already had a prototype for a separate storage layer (`shopwareArchive/storage`, 2023 to 2024, archived).
   Nobody measured it against Shopware's real read cases.
3. The experiment's database work is about the write model.
   A read store could take load off the write database whatever engine that is, which matters more for scalability than PostgreSQL vs MySQL.

The goal of the wave is the same as for wave 8: find out with a measured PoC slice, not opinions.

## What Shopware has today (verified in `instance/`, trunk)

Read paths:

- Storefront product listing, search, suggest and detail go through the DAL.
  With OpenSearch enabled, `ElasticsearchEntitySearcher` decorates `EntitySearcherInterface`, but only for criteria with `Criteria::STATE_ELASTICSEARCH_AWARE` (`ElasticsearchHelper::allowSearch`), which `ProductListingLoader`, `ProductDetailRoute`, `ProductSearchRoute`, the suggest route and the product stream code set.
- OpenSearch returns ids, a total and aggregations only.
  `EntityRepository::_search()` then calls `$criteria->cloneForRead($ids)` and reads the full entities from SQL (`src/Core/Framework/DataAbstractionLayer/EntityRepository.php:289`).
  So every listing with OpenSearch is still a full DAL read with its joins on the write database: OpenSearch offloads filtering and aggregations, not hydration.
- SEO urls are already a materialized table (`seo_url`) read by raw SQL in `SeoResolver`.
- Caching is the HTTP cache (`CacheStore`, reverse proxy gateways for Varnish and Fastly) plus object caches (`CachedLanguageLoader`, `CachedSalesChannelContextFactory`, ...).

Write side and change signals:

- `EntityWrittenContainerEvent` after every DAL write, `EntityIndexerRegistry` runs the indexers sync or through the messenger `async` transport (`Context::USE_INDEXING_QUEUE`).
- `ProductIndexer` writes the denormalized product columns (`cheapest_price`, `category_tree`, `variant_listing_config`, `rating_average`, `available_stock`, the `*_ids` fields, ...) and then dispatches `ProductIndexerEvent`.
- The OpenSearch product index is fed from `ProductIndexerEvent` and `ProductStockAlteredEvent` (`src/Elasticsearch/Product/ProductUpdater.php`), not from the write event, so it sees the denormalized values.
- The document is built by raw SQL (`ElasticsearchProductDefinition::fetch()`), one index for all languages (ADR `2023-04-11-new-language-inheritance-mechanism-for-opensearch`), rebuilt blue/green with timestamped indices and an alias swap.
- No outbox or changelog table exists; `version_commit` is the versioning log.
- Writes that bypass the DAL (raw SQL in plugins, doc 28 counted them) emit no event and are missed by every event-based index today.

Pluggable storage pattern that already exists in core (the model for engine selection):

- `AbstractCartPersister` (SQL, Redis; `shopware.cart.storage.type`), `AbstractIncrementStorage` (SQL, Redis), `AbstractIncrementer` (MySQL, Redis, Array; per cluster), `AbstractInvalidatorStorage` (MySQL, Redis), `AbstractStockStorage` (replaceable, ADR `2023-05-15-stock-api`).
  Each is an abstract class with adapters picked by configuration and a compiler pass.

## The archived prototype `shopwareArchive/storage`

Checked in a local clone (HEAD `6d53fcf`, 2024-03-24, archived on GitHub):

- Capability interfaces: `Storage` (`setup`, `get`, `mget`, `store`, `remove`, `clear`, `destroy`), `FilterAware::filter(Criteria, StorageContext): Result`, `AggregationAware::aggregate(...)`, `SearchAware::search(...)`.
  An engine that cannot answer a query throws `NotSupportedByEngine`.
- Adapters: Array, MySQL (one table per collection, JSON columns, `JSON_VALUE`/`JSON_TABLE`, FULLTEXT), OpenSearch (translations through a script), MongoDB, Meilisearch; key-value only: Redis, DynamoDB, plus key variants of MySQL, MongoDB and Array.
- Schema: PHP attributes on typed `Document` classes (`#[Collection]`, `#[Field(type, translated, searchable)]`, `#[ListField]`, `#[ObjectField]`); translated values hold every language and are resolved against a language fallback list in `StorageContext` at read time.
- Shared abstract contract test suites (key-value, filter, aggregation, search) run against every adapter, one CI job per engine.
- Not covered: any Shopware integration, inheritance and variants, sales channels, prices per currency and rule, a write pipeline, consistency, benchmarks.
- Not installable on trunk: it requires PHP `~8.1 || ~8.2` and `doctrine/dbal ^3.6`; trunk requires PHP 8.2 to 8.5 and `doctrine/dbal ~4.4`.

Conclusion for wave 9: port the ideas (capability interfaces, `NotSupportedByEngine`, contract tests, translated values resolved at read time), not the package, and add what it never had: the Shopware product document, the pipeline from the DAL, and measurements.

## Patterns elsewhere (checked against the vendor docs)

- Spryker Publish and Synchronize (https://docs.spryker.com/docs/dg/dev/backend-development/data-manipulation/data-publishing/publish-and-synchronization): a listener builds the storefront data and saves it "to the spy_product_abstract_storage table, one row per store and locale", then sends a message to the `sync.storage.product` queue, which writes it to the key-value store (Redis or Valkey) and the search engine.
  The SQL publish table is the rebuildable source of the read store.
  A "direct synchronize" mode exists next to the queue.
- Magento mview (https://developer.adobe.com/commerce/php/development/components/indexing/): "Update on Save" reindexes right after the write; for "Update by Schedule" "the mechanism creates a record in the change log table using MYSQL triggers", processed by cron.
  Triggers also catch writes that bypass the application.
- commercetools Product Search (https://docs.commercetools.com/api/projects/product-search): the search returns product ids; for the data the docs say to "use Query ProductProjections with the returned Product IDs".
  That is the hybrid shape Shopware has today with OpenSearch, but the projection it reads is itself a read model, not the write tables.
- SEAL, the PHP search engine abstraction (`cmsig/seal` 0.12.19, 2026-10-15, on Packagist): adapters for OpenSearch, Elasticsearch, RediSearch, Meilisearch, Typesense, Loupe, Solr, Algolia and Memory.
  No MongoDB, PostgreSQL or MySQL adapter exists on Packagist.
  It is a search abstraction, not a document store, so it can at most back the search capability of one adapter.
- CDC from the binlog (Debezium) catches every write but emits rows, not aggregates, and needs Kafka Connect to run.
  Wave 9 does not build it; handoff C writes down what it would take.

## Architecture options

| | Option | Read path | Fed by | Notes |
|---|---|---|---|---|
| O0 | Today, DAL only | DAL on the write database | none | baseline |
| O1 | Today with OpenSearch | OpenSearch ids, then full DAL read | `ProductIndexerEvent`, raw SQL builder | baseline, hydration stays on SQL |
| O2 | Read store, events | full documents from the store, no DAL read | projector on `ProductIndexerEvent` / `EntityWrittenContainerEvent`, sync or queued | candidate |
| O3 | Read store with publish table | as O2 | projector writes documents to an SQL publish table, a sync step copies them to the target engine | Spryker shape; the SQL adapter of O2 is the publish table, so O3 is O2 plus a copy step |
| O4 | CDC | as O2 | binlog or triggers | desk research only (handoff C) |

Proposed target, to be confirmed or rejected by the PoC (O2, with O3 as a configuration of it):

```
            write model (unchanged)                         read model (new)
  Admin API / DAL writes ──> SQL database ──┐
                                            │ ProductIndexerEvent, EntityWrittenContainerEvent
                                            v
                                   Projector (sync | messenger)
                                            │ DocumentBuilder (DAL based, extensible by plugins)
                                            v
                         ReadStore port: Storage, FilterAware, AggregationAware, SearchAware
            ┌──────────────┬───────────────┬────────────┬──────────────┬──────────┐
          Array      SQL JSON (MySQL,   OpenSearch    MongoDB        Valkey
          (tests)    MariaDB, PG,                                   (key-value only)
                     SQLite; also the
                     publish table)
                                            ^
  Store API product routes ── ReadStoreGateway (criteria bridge, capability check, DAL fallback)
                              live parts stay live: rule prices, stock, availability
```

Principles:

- The write model stays as decided in wave 8: DAL plus `SqlDialect` on the four SQL engines.
- The read store is a cache with a schema: it can always be rebuilt from the write database, and losing it costs a rebuild, not data.
- The document is a public read contract of its own (typed, versioned), decoupled from the table layout; that answers point 1 of "Why this wave" for the storefront read side.
- Every engine declares its capabilities; what it cannot answer falls back to the DAL, counted and logged, never silently wrong.
- Plugins extend the document through the builder (an event or tagged extender), not through the store.

## What the PoC has to answer

| # | Question | Measured by |
|---|---|---|
| Q1 | Do full documents from a read store beat O0 and O1 on detail, listing and search, per engine, and by how much? | R1 to R3, R5 |
| Q2 | Document shape: one document per product with all languages, currencies and the price matrix resolved at read time, or one per product × sales channel × language, pre-resolved? | document size, R1 to R3, rebuild time |
| Q3 | Document builder: DAL based (plugin extensions included without extra work) or raw SQL (like OpenSearch today)? | build throughput (R7), extension probe |
| Q4 | Which DAL criteria (filters, sorting, aggregations, search) can each engine answer, and what falls back? | capability matrix from the contract suite and the Store API criteria corpus |
| Q5 | Consistency: lag from write to readable, sync vs queued, which writes are missed (raw SQL, stock changes, indexer-only writes, deletes, version merges)? | R6, miss probes |
| Q6 | What must stay live at read time (rule prices, customer group prices, stock, availability, cart rules) and what does that cost? | R1 to R3 with live parts on and off |
| Q7 | Does it scale: throughput and p95 under concurrency, the write database's load with and without the read store, a large catalogue | R5 on two dataset sizes |
| Q8 | Effort, API and extension story: how plugins and apps add fields, what changes for the Store API, BC | handoff F estimate |

Scenarios (the wave 8 harness and contract are reused, S1 to S3 results must equal the DAL result, see `docs/30-orm-spike-baseline.md`):

- R1 detail: S2 (one variant with inherited data).
- R2 listing: S1 (24 products of one category, page 2, total).
- R3 search: S3 (term, manufacturer filter, total, min/max price and manufacturer terms aggregations).
- R4 batch by id: `mget` of 24 ids (cross selling, wishlist, cart).
- R5 load: R1 to R3 mixed, 1, 8 and 32 concurrent clients, throughput, p95, and CPU of the write database container.
- R6 lag: write a product, poll until the read store returns the new value; sync and queued mode.
- R7 rebuild: full rebuild time, documents per second, store size per engine.

Datasets: `orm_spike` as in wave 8 (3,000 simple products, 400 parents with 4 variants) for correctness and comparison with docs 30 to 35, and `read_store_large` (100,000 simple products, 10,000 parents with 4 variants, same seed rules) for R5 and R7.

## Plan

Handoffs (work packages for parallel sessions, `handoffs/wave9/`):

| Handoff | Topic | Doc | Can run in parallel with |
|---|---|---|---|
| P | Branch, OpenSearch and MongoDB containers, `mongodb` PHP extension, large dataset, harness extension (R4 to R7, implementation ids per store), O0 and O1 baseline timings | `docs/39-read-store-baseline.md` | nothing until "branch ready", then K; S, O, M, R, C wait for "harness ready" |
| K | Port (capability interfaces, store criteria, `NotSupportedByEngine`), product document and its schema (Q2), DAL and SQL document builders (Q3), projector (sync and queued), rebuild command, Array adapter, contract test suite, DAL criteria bridge | `docs/40-read-store-port-and-document.md` | P after "branch ready"; everything else waits for "port ready" |
| S | SQL JSON adapter on MySQL, MariaDB, PostgreSQL and SQLite through `SqlDialect` (JSON columns, generated columns or expression indexes for filter fields), usable as publish table (O3) | `docs/41-read-store-sql.md` | O, M, R, C |
| O | OpenSearch adapter: own adapter vs reuse of the existing `CriteriaParser` vs SEAL, pick by the contract suite and timings | `docs/42-read-store-opensearch.md` | S, M, R, C |
| M | MongoDB adapter and Valkey key-value adapter | `docs/43-read-store-mongodb-valkey.md` | S, O, R, C |
| R | Read integration: `ReadStoreGateway` behind `ProductDetailRoute`, `ProductListingLoader` and `ProductSearchRoute` (flagged), document to `SalesChannelProductEntity` vs DTO response, live parts (Q6), fallback, Store API response equality | `docs/44-read-store-integration.md` | S, O, M, C |
| C | Consistency and extensibility: R6 lag, miss probes, plugin extension probe, rebuild blue/green, O3 copy step, CDC and trigger desk research (O4) | `docs/45-read-store-consistency.md` | S, O, M, R |
| F | One timing block with O0, O1 and every store, Q1 to Q8 answered, effort estimate, conclusion in this doc, `docs/summary.md`, issue drafts | this doc, "Conclusion" | nothing, runs alone and last |

Order: P alone until "branch ready"; then K; S, O, M, R and C together once K committed "port ready" and P committed "harness ready"; F alone at the end.

Out of scope: Meilisearch, DynamoDB, Typesense (the port must allow them, the PoC does not build them), CDC implementation, the admin search index, CMS and navigation documents (named as next candidates in F), production hardening.

## Conclusion

Written by wave 9 F.
