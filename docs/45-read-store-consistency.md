# Read Store: Consistency, Extensibility, Rebuild & O3/O4 Design

This document reports Wave 9 Handoff C ([`handoffs/wave9/C-consistency-and-extensibility.md`](../handoffs/wave9/C-consistency-and-extensibility.md)), evaluating how a read store stays fresh under real Shopware write paths, how plugins extend documents and filters, how blue/green rebuilds and store outages behave under load, and how two alternative sync topologies — **O3** (SQL publish-table copy worker) and **O4** (database-level CDC / triggers) — compare against direct application projection.

All measurements in this document were executed on `orm_spike` (5,000 products, MySQL 8.4 write DB) using `ReadStoreProjector`, `read-store:bench:lag` (R6), `read-store:bench:consistency` (`src/Core/Framework/ReadStore/Probe/ConsistencyProbeCommand.php`), and `read-store:load` (R5).

---

## 1. Write-to-Read Lag (R6): Sync vs. Queue vs. Engine Visibility

`ReadStoreProjector` supports two operating modes configured via `READ_STORE_PROJECTOR_MODE`:

- **`sync`**: projects inline at the end of `ProductIndexerEvent` / `ProductStockAlteredEvent` / referenced-entity listeners (inside the same PHP request as the write).
- **`queue`**: dispatches a deduplicated `ProjectProductsMessage` to Symfony Messenger's `async` transport (Doctrine DBAL `messenger_messages` table in this environment), consumed by `php bin/console messenger:consume async --sleep=0.05`.

### 1.1 `get()` Visibility Lag (`read-store:bench:lag`)

| Store | Mode | Writes | Missed | Lag p50 | Lag p95 | Lag max | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `store-sql-mysql` | `sync` | 50 | 0 | **0.4 ms** | 0.6 ms | 1.4 ms | Same-DB read-after-write |
| `store-sql-pgsql` | `sync` | 50 | 0 | **0.6 ms** | 0.9 ms | 1.5 ms | Cross-container PG write |
| `store-opensearch` | `sync` | 50 | 0 | **1.8 ms** | 3.1 ms | 11.2 ms | `GET /_doc/{id}` reads translog (realtime) |
| `store-mongodb` | `sync` | 50 | 0 | **0.7 ms** | 1.8 ms | 16.0 ms | Default `w:1` write concern |
| `store-valkey` | `sync` | 50 | 0 | **0.2 ms** | 0.3 ms | 0.8 ms | In-memory `HSET`/`SET` |
| `store-opensearch-valkey` | `sync` | 50 | 0 | **0.3 ms** | 0.5 ms | 1.2 ms | `get()` served by Valkey |
| `store-sql-mysql` | `queue` (`--sleep=0.05`) | 25 | 0 | **223.1 ms** | 284.1 ms | 318.4 ms | DBAL transport polling + worker build |
| `store-opensearch` | `queue` (`--sleep=0.05`) | 25 | 0 | **264.2 ms** | 507.8 ms | 800.1 ms | DBAL transport + bulk HTTP index |
| `store-mongodb` | `queue` (`--sleep=0.05`) | 25 | 0 | **157.5 ms** | 209.3 ms | 245.6 ms | DBAL transport + MongoDB bulkWrite |
| `store-valkey` | `queue` (`--sleep=0.05`) | 25 | 0 | **24.5 ms** | 190.0 ms | 263.2 ms | Fast write once picked up by worker |

**Operational note on `queue` mode:** Default Shopware `messenger:consume async` uses `--sleep=1` (1,000 ms poll interval on DBAL transport), which adds ~500 ms median / ~1,000 ms tail idle latency on top of the numbers above unless a push broker (Redis/Valkey Streams, RabbitMQ, or AMQP) or shorter `--sleep` is configured. Each R6 write also executed ~104–115 SQL statements on the write DB (Shopware's DAL + `ProductIndexer` + `SqlDocumentBuilder` single-product rebuild).

### 1.2 Engine-Specific Visibility Windows: OpenSearch `refresh_interval` & MongoDB Write Concern

A critical distinction for `store-opensearch` and `store-opensearch-valkey`:

- **Detail (`get()`, `GET /_doc/{id}`)** reads the OpenSearch translog directly → **realtime (p50 1.8 ms)** even with `refresh_interval: 1s`.
- **Listing / Search (`filter()` / `search()`, `POST /_search`)** queries the Lucene inverted index, which only exposes newly indexed documents after the next shard refresh (`index.refresh_interval = 1s`).

Measuring 10 `sync`-projected DAL writes while polling `OpenSearchStorage::filter()` on the updated `productNumber` (`read-store:bench:consistency --mode=os-refresh`):

| Path on `store-opensearch` (`sync` projector) | min | p50 | p95 / max |
|---|---:|---:|---:|
| `get()` (`GET /_doc/{id}`, translog) | — | **1.8 ms** | 3.1 ms / 11.2 ms |
| `filter()` (`POST /_search`, `refresh_interval=1s`) | 40.1 ms | **760.7 ms** | 794.9 ms |

Setting `refresh=wait_for` on every write eliminates this window for single admin edits, but destroys bulk indexing throughput (and hurts segment merge overhead under high write rates). For storefront search/listing, a ~0.5–1.0 s eventual visibility window is acceptable and identical to Shopware's existing O1 (`dal-opensearch`) behavior; for admin read-your-writes, the Admin API continues to read from MySQL directly.

For **MongoDB**, default `w: 1` acknowledges after primary RAM apply (p50 0.7 ms). In a replica set with `readPreference: secondaryPreferred`, reads can lag the primary by replication oplog latency (typically 5–50 ms) unless `w: majority` + primary read preference are used for write-after-read paths.

---

## 2. Consistency Miss Matrix (17 Scripted Write Probes)

`read-store:bench:consistency --mode=misses` executes 17 real write operations against MySQL (`orm_spike`) with `READ_STORE_PROJECTOR_STORES=sql-mysql READ_STORE_PROJECTOR_MODE=sync` and checks whether the read store reflects the mutation immediately.

### 2.1 Before vs. After Cheap Projector Fixes

In Handoff K, `ReadStoreProjectorSubscriber` subscribed only to `ProductIndexerEvent`, `ProductStockAlteredEvent`, and `product.deleted` — matching Shopware's existing Elasticsearch `ProductUpdater`. Running the 17 probes revealed **four real gaps that are cheap to close** and **three structural gaps that cannot be fixed cheaply inline**:

| # | Write path probed | Before C (K baseline) | After C fixes | Signal / Root cause |
|---:|---|---|---|---|
| 1 | DAL product name update (`product.repository`) | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` |
| 2 | Parent product update → child variant inherited field (`description`) | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` (indexer expands parent → children) |
| 3 | Variant price change → `cheapestPrice` + sibling variants | **PARTIAL** | **CAUGHT** | `ProductIndexer::update()` emits `[variant, parent]` without other siblings; C expands `parent_id IN (:ids)` (1 indexed SQL query) |
| 4 | DAL product price change | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` |
| 5 | Category assignment via DAL | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` |
| 6 | DAL product create + delete | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` + `product.deleted` |
| 7 | Non-default language (`de-DE`) translation update | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` |
| 8 | Stock API `StockStorage::alter()` (order placement / cancellation) | **CAUGHT** | **CAUGHT** | `ProductStockAlteredEvent` (dispatched by `StockStorage::alter()`) |
| 9 | Direct `ProductStockAlteredEvent` dispatch | **CAUGHT** | **CAUGHT** | `ProductStockAlteredEvent` |
| 10 | **Raw SQL `UPDATE product`** (plugin/ERP bypass) | **MISSED** | **MISSED** | No PHP/DAL event emitted (bypasses ORM completely) |
| 11 | Version merge (draft → live via `createVersion` + `merge`) | **CAUGHT** | **CAUGHT** | `ProductIndexerEvent` dispatched on merge |
| 12 | Referenced entity: **manufacturer rename** | **MISSED** | **CAUGHT** | Added `product_manufacturer[.translation].written` → lookup `product_manufacturer_id` + children |
| 13 | Referenced entity: category name rename | **CAUGHT** | **CAUGHT** | N/A — `ProductDocument` stores `categoryIds`/`categoryTree` only, not category names |
| 14 | Referenced entity: **property/option rename** | **MISSED** | **CAUGHT** | Added `property_group_option[.translation].written` → lookup `product_property` ∪ `product_option` |
| 15 | Referenced entity: **media path update** | **MISSED** | **CAUGHT** | Added `media[.translation].written` → lookup `product_media` |
| 16 | Referenced entity: **tax rate update** | **MISSED** | **MISSED** | `tax.written` touches up to 100% of catalog (150k rows); unsafe to fan out inline |
| 17 | Referenced entity: **currency factor update** | **MISSED** | **MISSED** | `currency.written` affects all multi-currency `priceGross`/`cheapestPrice`; needs queued rebuild |
| 18 | Referenced entity: rule condition update | **CAUGHT** | **CAUGHT** | Rule IDs evaluated live in `SalesChannelContext::getRuleIds()`; `cheapestPrice` already keyed by `ruleId` |

### 2.2 What Was Fixed Cheaply (~90 LOC in `ReadStoreProjectorSubscriber`)

Adding 4 lightweight listeners (gated behind `$this->projector->enabled()`, zero overhead when disabled) closed 4 of the 7 original gaps (all 452 unit tests pass):

1. **Sibling expansion on `ProductIndexerEvent`**: one indexed `SELECT id FROM product WHERE parent_id IN (:ids)` ensures that when a variant update changes group-level derived state, sibling variants are re-projected alongside `[variant, parent]`.
2. **`product_manufacturer.written` / `product_manufacturer_translation.written`**: resolves owning products + inheriting children (`WHERE product_manufacturer_id IN (:ids)`).
3. **`property_group_option.written` / `property_group_option_translation.written`**: resolves products from `product_property` and `product_option`.
4. **`media.written` / `media_translation.written`**: resolves products from `product_media`.

### 2.3 The Remaining 3 Structural Misses & Ecosystem Impact

1. **Raw SQL writes from plugins & ERPs (Probe #10 — highest risk):**
   Per [`docs/28-plugin-sql-inventory.md`](28-plugin-sql-inventory.md), **2,045 of 3,747 Shopware Store plugins (54.6%)** contain raw SQL statements, including direct `UPDATE product` / `INSERT INTO product_*` stock and price syncs in ERP connectors, bulk importers, and custom merchant scripts. Any write that bypasses DAL and `StockStorage::alter()` is invisible to an application-level projector.
   - *Mitigation options*: (a) **Reconciliation sweep** (periodic `updated_at > last_synced` or nightly blue/green rebuild, 1–2 minutes for 150k products), (b) **Explicit invalidation SDK** (`ReadStoreProjector::schedule($ids)` — same contract plugins already need for `EntityIndexerRegistry::index()` / OpenSearch today), or (c) **O4 DB-level CDC** (Section 6).
2. **Catalog-wide reference mutations (`tax.written`, `currency.written`, Probes #16–#17):**
   Updating a tax rate or currency exchange rate can invalidate every product in a 150k catalog. Fanning out 150k IDs synchronously would stall the Admin HTTP request for ~100 s.
   - *Recommended handling*: Subscribe to `tax.written` and `currency.written` only to enqueue an **async blue/green rebuild** (`Rebuilder::rebuild()`, ~70–100 s for 150k products) — or, for display prices in Shape (a), note that `ProductPriceCalculator` already recalculates currency/tax live at response time (Handoff R, Section 2), leaving only query-time price sorting/filtering on the pre-computed `priceGross`/`cheapestPrice` keys temporarily stale until the background rebuild swaps.

---

## 3. Extensibility Probe: `DocumentExtender` & Custom Fields

To verify Q5 (how plugins add custom attributes and filter on them without modifying core store adapters), we implemented `Probe/SamplePluginExtender` (`~30 LOC`, tagged `read_store.document_extender`), which attaches `extensions.samplePlugin = ['badge' => 'in-stock-plus'|'standard', 'tier' => 'gold'|'silver']` to every product batch, and wrote `customFields.sample_tag = 'featured-wave9'` onto a product.

Rebuilding and querying all four filterable stores via `read-store:bench:consistency --mode=extender`:

| Store | `extensions.samplePlugin.badge = 'in-stock-plus'` | `customFields.sample_tag = 'featured-wave9'` | Extra adapter code required? | Indexing behavior for arbitrary plugin fields |
|---|---:|---:|---|---|
| `array` (reference) | `total=2700` (5 returned) | `total=1` (`53eace96...`) | **None (0 LOC)** | In-memory scan |
| `sql-mysql` | `total=2700` (5 returned) | `total=1` (`53eace96...`) | **None (0 LOC)** | Unindexed `JSON_EXTRACT` full scan unless plugin adds a generated column + index |
| `opensearch` | `total=2700` (5 returned) | `total=1` (`53eace96...`) | **None (0 LOC)** | Dynamic mapping indexes automatically; **risk of mapping explosion** (`index.mapping.total_fields.limit = 1000`) if plugins write unbounded keys or dynamic maps |
| `mongodb` | `total=2700` (5 returned) | `total=1` (`53eace96...`) | **None (0 LOC)** | Wildcard index (`{"$**": 1}`) indexes all leaf paths automatically with no field-count limit; slightly higher write/disk cost |

### What a Plugin Developer Must Write

1. **Adding a computed or `EntityExtension`-backed field to the read store:**
   - Implement `DocumentExtender` (`name(): string`, `extend(array $documents): array` — batch-oriented, 1 SQL query per 500-product batch) and tag the service `read_store.document_extender` (~30 LOC).
   - If the plugin's own table changes independently of `product.written`, subscribe to its entity's written event and call `ReadStoreProjector::schedule($affectedProductIds)` (~15 LOC).
2. **Adding a Shopware Custom Field:**
   - **0 LOC** — `customFields` are already flattened per language into `ProductDocument` and queryable as `customFields.<key>` across all stores.
3. **What plugins CANNOT do through the generic read-store port:**
   - Arbitrary SQL `JOIN`s against custom plugin tables in `ProductListingCriteriaEvent` (`Criteria::addAssociation('myCustomTable')` + filtering on `myCustomTable.foo`). Those queries hit `CriteriaBridge::UnsupportedCriteria` and **automatically fall back to DAL** (Handoff R, Section 4).

---

## 4. Blue/Green Rebuild Under Concurrent Load & Store-Outage Fallback

### 4.1 Blue/Green Rebuild Under Concurrent Load (`c=4`, 12 s)

We ran `read-store:load --concurrency=4 --duration=12s` (mixed R1/R2/R3b) while triggering a full `read-store:rebuild` mid-run on `orm_spike` (5,000 products):

| Store | Rebuild time (under load) | Concurrent requests | Throughput | p50 / p95 | Errors | Swap mechanism & observation |
|---|---:|---:|---:|---:|---:|---|
| `store-sql-mysql` | 4.4 s | 2,633 | 191.8/s | 3.6 / 48.1 ms | **0** | Atomic `RENAME TABLE` + metadata lock queues swap behind active queries; zero failed reads |
| `store-opensearch` | 3.2 s | 4,506 | 373.6/s | 4.1 / 41.8 ms | **0** | Atomic `_aliases` swap + `indices.refresh` before swap; zero failed or partial reads |
| `store-mongodb` | 2.4 s | 5,226 | 433.4/s | 2.2 / 42.6 ms | **1** | **Race found:** `MongoDbStorage::swap()` updates pointer doc `rs_meta` and immediately calls `dropCollection($oldGen)`, killing 1 in-flight `aggregate` cursor (`collection dropped`) |

**Concrete production takeaway from the MongoDB race:** Any pointer-based store (`MongoDB`, `Valkey`, or pointer-table SQL) **must not drop the previous generation synchronously inside `swap()`**. Instead, `swap()` should either retain the previous generation for a grace window (`> max query timeout`, e.g. 60 s, or GC it at the start of the *next* rebuild) or retry once on `NamespaceNotFound` after refreshing the live pointer. Even OpenSearch benefits from delaying `indices.delete($old)` by a few seconds so long-running scroll/search requests finish cleanly.

### 4.2 Store-Outage Fallback Timing

`ReadStoreGateway` catches any `\Throwable` from the read store (connection refused, timeout, missing generation, `UnsupportedCriteria`) and transparently falls back to the decorated Shopware DAL route. Measuring `read-store:bench:consistency --mode=outage` (10 iterations each, `orm_spike`, simulated down/unavailable store):

| Route | Baseline DAL p50 | Fallback-on-outage p50 | Overhead | Fallbacks / Hits |
|---|---:|---:|---:|---:|
| `ProductDetailRoute` (`skipConfigurator+skipCmsPage`) | 10.55 ms | **10.35 ms** | **~0 ms** (-0.20 ms noise) | 10 / 0 |
| `ProductListingRoute` (category, 24 items) | 34.12 ms | **32.12 ms** | **~0 ms** (-1.99 ms noise) | 10 / 0 |

When a store fails fast (connection refused / circuit-breaker open), fallback adds **<0.5 ms** overhead and preserves 100% storefront availability. In production, a **circuit breaker** (e.g. open for 15–30 s after 3 consecutive TCP connect timeouts, with a 150–300 ms connect timeout on OpenSearch/MongoDB/Valkey clients) is mandatory so a blackholed/stalled read-store node does not add `connect_timeout` seconds to every single request before falling back to MySQL.

---

## 5. O3 Topology: SQL Publish Table → Copy Worker

Option **O3** separates document assembly from external store delivery:

1. **Step 1 (Transactional / SQL-local):** `ReadStoreProjector` builds `ProductDocument` and writes it to the SQL publish table (`sql-mysql`, same MySQL instance — or in the same transaction boundary as the write).
2. **Step 2 (Async Copy Worker):** A dumb copy worker streams JSON rows from `sql-mysql` (`mget` / `updated_at` watermark / outbox) into `opensearch`, `mongodb`, and/or `valkey` **without re-running `SqlDocumentBuilder` or touching the 15+ Shopware DAL tables**.

Measuring `read-store:bench:consistency --mode=o3-copy` on `orm_spike` (5,000 products, batch size 500):

| Copy path (`sql-mysql` → target) | Full 5k copy time | Copy throughput | Single-doc incremental copy p50 / p95 | Extrapolated 150k copy |
|---|---:|---:|---:|---:|
| `sql-mysql` → `opensearch` | 3.27 s | **1,529 docs/s** | **5.13 ms / 7.59 ms** | ~98 s |
| `sql-mysql` → `mongodb` | 2.33 s | **2,147 docs/s** | **1.72 ms / 2.59 ms** | ~70 s |
| `sql-mysql` → `valkey` | 0.51 s | **9,798 docs/s** | **0.95 ms / 1.45 ms** | ~15 s |

**O3 vs. Direct Projection trade-off:**
- **Wins of O3:**
  - If you run **two** external stores (e.g. `opensearch` + `valkey` in O1b, or `sql-mysql` fallback + `opensearch` primary), `SqlDocumentBuilder` runs **once** instead of once per store.
  - Rebuilding OpenSearch or Valkey after an outage/mapping change reads sequentially from one flat JSON table (**~0.1× the SQL complexity** and zero multi-table join pressure on `product_*`).
  - If the SQL publish row is written inside a transactional outbox / same-DB write, losing an external store (Valkey restart, OpenSearch crash) is trivially recoverable without rebuilding from DAL.
- **Costs of O3:**
  - Adds **1.58 GiB** of MySQL disk footprint at 150k products (Handoff S: `sql-mysql` = 1,576 MiB for full document + indexes; ~700 MiB if stored without secondary JSON indexes as a pure publish blob table).
  - Adds one extra hop of write-to-read lag (**1–8 ms** copy work + queue polling delay).
  - Does **not** by itself solve raw-SQL plugin writes (Probe #10), because Step 1 still relies on application events.

---

## 6. O4 Topology (Desk Research): Database-Level CDC & Trigger Changelogs

When raw SQL writes (`UPDATE product ...`) from plugins or external ERPs must be captured reliably without changing plugin code, projection must move below PHP into the database layer. Two battle-tested architectures exist in e-commerce:

### 6.1 Debezium MySQL Binlog CDC

- **How it works:** Debezium's MySQL connector ([Debezium MySQL Connector Docs](https://debezium.io/documentation/reference/stable/connectors/mysql.html)) reads the MySQL binary log (`binlog_format=ROW`, `binlog_row_image=FULL`, GTID enabled) as a logical replica and emits row-level change events per table to Kafka (or via Debezium Server directly to Redis Streams / NATS / RabbitMQ).
- **The fan-out / hydration trap for Shopware:** A Shopware `ProductDocument` aggregates **16+ tables** (`product`, `product_translation`, `product_price`, `product_category_tree`, `product_property`, `product_option`, `product_visibility`, `product_media`, `product_search_keyword`, `product_manufacturer`, `property_group_option`, `tax`, `currency`, `media`, ...). Maintaining materialized stream-stream joins across 16 tables in Flink/ksqlDB duplicates all of Shopware's inheritance rules (`parent_id` fallback, `CheapestPriceContainer`, language fallback chain, `DocumentExtender` plugin PHP hooks!) in a second language (Java/SQL).
- **Practical pattern ("CDC as a dirty-ID trigger"):** Instead of assembling documents in Kafka/Flink, use Debezium purely as a **reliable dirty-product-ID emitter**: watch `product`, `product_translation`, `product_price`, `product_visibility`, `product_category`, `product_property`, `product_media`, `product_manufacturer`, `media` → extract `product_id` (or resolve `manufacturer_id`/`media_id`) → deduplicate in a 100–500 ms tumbling window → push `ProjectProductsMessage($ids)` to PHP `SqlDocumentBuilder`.
- **Operational cost:** Requires MySQL binlog (`ROW` format, ~10–30% extra MySQL write I/O), a Debezium JVM service (512 MiB–2 GiB RAM), a broker (Kafka / Redis Streams / RabbitMQ), schema-history storage, and binlog retention monitoring. Overkill for small/mid self-hosted Shopware merchants; realistic for managed SaaS / Enterprise clusters where MySQL binlog is already enabled for replication.

### 6.2 Magento 2 `mview` (Database Triggers + Changelog Tables)

- **How it works:** Magento 2's `Magento_Framework_Mview` ([Adobe Commerce Indexer / Mview Architecture](https://developer.adobe.com/commerce/php/development/components/indexing/)) solves the exact same raw-SQL-plugin problem without external JVM/Kafka infrastructure:
  1. For each materialized view (e.g. `catalog_product_price`, `catalogsearch_fulltext`), Magento installs **`AFTER INSERT / UPDATE / DELETE` SQL triggers** on every subscribed source table (`catalog_product_entity`, `catalog_product_entity_decimal`, `cataloginventory_stock_status`, etc.).
  2. Each trigger appends the affected `entity_id` into an append-only changelog table (`*_cl`, with an auto-increment `version_id`).
  3. A cron/worker reads `WHERE version_id > last_processed_version_id`, deduplicates IDs, runs the PHP indexer/projector in batches, and advances the watermark.
- **Pros for Shopware:** Zero external infrastructure (runs on plain MySQL/MariaDB/PostgreSQL — works on every shared/self-hosted Shopware install), catches **100% of raw SQL plugin writes** (including `UPDATE product` and ERP imports), and naturally batches bursts (10,000 updates to 500 products collapse to 500 unique IDs).
- **Cons & Shopware-specific hazards:**
  1. **DDL/migration friction:** MySQL triggers cannot reference the same table recursively, require `SUPER` / `TRIGGER` / `LOG_BIN_TRUST_FUNCTION_CREATORS` privileges on managed RDS/Aurora/Cloud SQL instances, and historically cause lock contention and failed schema migrations (a well-known pain point in Magento 2 upgrades).
  2. **Write amplification & deadlocks:** Every `UPDATE product` (including Shopware's own `ProductIndexer` updating `cheapest_price_accessor`, `category_tree`, `available_stock`, and `OrderStockSubscriber` updating `stock`) fires the trigger and writes to `rs_product_cl`, adding lock contention on hot SKUs during flash sales.
  3. **Plugin tables still need registration:** A `DocumentExtender` reading a custom plugin table must declare its table in the trigger subscription list (just like Magento's `mview.xml`).

### 6.3 Comparison Summary (Application Projector vs. O3 vs. O4)

| Mechanism | Catches DAL + `StockStorage` | Catches Raw SQL plugins (doc 28: 54.6%) | Extra infra required | Typical visibility lag | Operational complexity |
|---|---|---|---|---|---|
| **App Projector (`sync` / `queue`) + C fixes** | Yes (14/14 DAL/event paths) | No (needs rebuild sweep) | None (uses Shopware Messenger) | 0.2–2 ms (`sync`) / 25–265 ms (`queue`) | **Low** |
| **O3 (SQL publish table + copy worker)** | Yes | No (needs rebuild sweep) | None (reuses MySQL + Messenger) | +1–8 ms copy step | **Low–Medium** (best when feeding ≥2 external stores) |
| **O4a: Magento-style DB triggers (`mview`)** | Yes | **Yes** | None (MySQL/PG triggers + `_cl` table) | Cron/worker interval (1–60 s) | **Medium–High** (RDS privileges, migration/deadlock risk) |
| **O4b: Debezium MySQL binlog → dirty-ID queue** | Yes | **Yes** | Debezium + broker + `ROW` binlog | ~0.2–2 s | **High** (SaaS / Enterprise only) |

---

## 7. Summary of Findings for Handoff C

1. **R6 lag is sub-millisecond in `sync` mode** (0.2–1.8 ms p50 across all 6 stores) and **25–265 ms p50 in `queue` mode** (`messenger:consume async --sleep=0.05`). OpenSearch `get()` is realtime (1.8 ms), whereas `filter()`/`search()` waits for `refresh_interval=1s` (**760.7 ms p50**).
2. **Application projection catches 14 / 17 scripted write paths** after adding ~90 LOC of cheap listeners (sibling expansion on `ProductIndexerEvent` + manufacturer, property/option, and media listeners). The 3 remaining misses are **raw SQL `UPDATE product`** (54.6% of store plugins contain raw SQL) and **catalog-wide `tax`/`currency` writes** (which must trigger an async blue/green rebuild, not inline fan-out).
3. **Extensibility works with 0 adapter changes:** `SamplePluginExtender` (`~30 LOC`) and native `customFields` rebuild and filter identically (`total=2700` and `total=1`) across `array`, `sql-mysql`, `opensearch`, and `mongodb`.
4. **Blue/green rebuild under concurrent `c=4` load** achieved **0 errors** on `sql-mysql` (2,633 reqs) and `opensearch` (4,506 reqs), and exposed a **real pointer-drop race on `mongodb`** (1 / 5,226 reqs failed with `collection dropped` because `swap()` dropped the old collection immediately while an `aggregate` cursor was in flight). Pointer-based stores must defer old-generation GC past max query timeout.
5. **Store-outage fallback adds ~0 ms overhead** on fast-failing stores (`10.35 ms` vs `10.55 ms` Detail; `32.12 ms` vs `34.12 ms` Listing); production deployments require a short connect timeout + circuit breaker.
6. **Practical consistency architecture:** Use the **application projector (`queue` mode) + C's referenced-entity listeners** for normal traffic, trigger **async blue/green rebuilds** for `tax`/`currency` writes and nightly reconciliation (catching raw-SQL plugin drift), add **O3** only if feeding multiple external read stores simultaneously, and reserve **O4 (Debezium dirty-ID trigger)** for Enterprise/SaaS deployments where raw-SQL plugin writes require sub-second consistency guarantees.
