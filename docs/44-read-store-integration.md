# Read store integration into the Store API product routes (wave 9, handoff R)

Handoff R of wave 9: wiring the read store into the real Store API request path without editing core route classes, separating product-read SQL from surrounding route SQL, comparing entity hydration vs DTO projection, answering **Q6** (display-time and query-time live parts), and verifying 50-request Store API equality and HTTP cache interaction.

## Code layout

All code lives in `instance/src/Core/Framework/ReadStore/Integration/` (`@internal`, package `framework`), registered via `DependencyInjection/r.php`:

| File | Responsibility |
|---|---|
| `ReadStoreConfig.php` | Per-sales-channel switch (`system_config` `core.readStore.*`, env `READ_STORE_*`, HTTP A/B headers `sw-read-store` / `sw-read-store-shape`, runtime override) |
| `DocumentHydrator.php` | Shape (a) `SalesChannelProductEntity` hydration + `product.loaded` / `sales_channel.product.loaded` event dispatch; Shape (b) `ArrayEntity` DTO projection; DAL `AggregationResultCollection` + `EntityAggregation` hydration |
| `ReadStoreGateway.php` | Central gateway: bridges criteria via `CriteriaBridge`, runs store queries & `mget` preview resolution, records hit/fallback counters & logs, falls back to DAL on `NotSupportedByEngine` / store outage |
| `RouteExtensionSubscriber.php` | `ExtensionDispatcher` `.pre` listeners (`product-detail-route.load.pre` and `listing-loader.resolve.pre`) — zero edits to core route classes |
| `IntegrationBenchCommand.php` | `read-store:bench:integration` (`sql-accounting`, `live-parts`, `equality`) |

## Integration points (`.pre` extension hooks)

Per ADR `2026-09-24-replace-abstract-route-classes-with-extension-events.md`, no core route class is modified and no deprecated `Abstract*` decorator is used:

1. **`ProductDetailRouteExtension::NAME . '.pre'` (`product-detail-route.load.pre`)**:
   - Intercepts `/store-api/product/{productId}`.
   - Answers `checkVariantListingConfig()` directly from `$doc['variantListingConfig']` (0 SQL) instead of `ProductDetailRoute::checkVariantListingConfig()`'s raw SQL query, dispatches `ResolveVariantIdEvent`, resolves `mainVariantId` via a second `Storage::get()`, enforces `ProductAvailableFilter(VISIBILITY_LINK)` and `core.listing.hideCloseoutProductsWhenOutOfStock`, hydrates the product, registers the product cache tag via `CacheTagCollector`, and keeps the non-product surrounding route work on SQL (`CategoryBreadcrumbBuilder::getProductSeoCategory()`, `ProductConfiguratorLoader`, `SalesChannelCmsPageLoader`).
   - Assigns `$extension->result = new ProductDetailRouteResponse(...)` and calls `$extension->stopPropagation()`.
2. **`ResolveListingExtension::NAME . '.pre'` (`listing-loader.resolve.pre`)**:
   - Intercepts **both** `/store-api/product-listing/{categoryId}` (`ProductListingRoute`) **and** `/store-api/search` (`ProductSearchRoute`), because `ProductSearchRoute::_load()` runs `ProductSearchBuilder::build()` and delegates directly to `ProductListingLoader::load()`.
   - Mirrors `ProductListingLoader::addGrouping()` (`displayGroup` collapse + `NotEqualsFilter('displayGroup', null)` unless `STATE_SKIP_ADD_GROUPING` or an option/property post-filter is active), converts the DAL `Criteria` through `CriteriaBridge`, runs `filter()`/`search()` + `aggregate()`, answers `loadPreviews()` in-store via `$storage->mget()` (0 SQL), hydrates aggregations (resolving `EntityAggregation` keys such as `manufacturer` / `properties` via their repositories), hydrates Shape (a) or Shape (b), and assigns `$extension->result = new EntitySearchResult(...)` with `$extension->stopPropagation()`.
3. **Fallback**: any `NotSupportedByEngine`, missing live generation, custom filter on detail, or backend outage logs `Read store fallback to DAL`, increments `ReadStoreGateway::$fallbacks`, and returns `null` so Shopware executes the core DAL implementation transparently.

## Surrounding SQL accounting

Measured via `read-store:bench:integration --store=opensearch --mode=sql-accounting --iterations=20 --warmup=3` on `orm_spike` (5,000 products, MySQL 8.4, `APP_ENV=prod`, warm cache, `other lanes stopped: no`):

| Route | Mode | p50 ms | p95 ms | Product-read SQL | Surrounding SQL | Total route SQL |
|---|---|---:|---:|---:|---:|---:|
| Detail (full) | O0 `dal` | 18.10 | 21.06 | 7 | 23 | **30** |
| Detail (full) | `opensearch` Shape (a) entity | 16.95 | 20.21 | **0** | 23 | **23** |
| Detail (full) | `opensearch` Shape (b) dto\* | 9.10 | 9.95 | **0** | 9 | **9** |
| Detail (`skipCfg+skipCms`) | O0 `dal` | 7.33 | 8.01 | 4 | 5 | **9** |
| Detail (`skipCfg+skipCms`) | `opensearch` Shape (a) entity | 6.63 | 7.47 | **0** | 5 | **5** |
| Detail (`skipCfg+skipCms`) | `opensearch` Shape (b) dto | 7.34 | 8.38 | **0** | 5 | **5** |
| Listing (`cat, p1, 24`) | O0 `dal` | 28.99 | 31.97 | 12 | 8 | **20** |
| Listing (`cat, p1, 24`) | `opensearch` Shape (a) entity | 18.56 | 20.76 | **0** | 8 | **8** |
| Listing (`cat, p1, 24`) | `opensearch` Shape (b) dto | 18.73 | 21.92 | **0** | 8 | **8** |
| Search (`term=Hotel, 24`) | O0 `dal` | 75.39 | 91.64 | 13 | 8 | **21** |
| Search (`term=Hotel, 24`) | `opensearch` Shape (a) entity | 56.57 | 285.96 | **0** | 8 | **8** |
| Search (`term=Hotel, 24`) | `opensearch` Shape (b) dto | 70.99 | 177.57 | **0** | 8 | **8** |

\*In Detail Shape (b), `ProductSubscriber::setDefaultLayout()` does not run, so `cmsPageId` stays `null` and the 14 CMS-page SQL statements are skipped (only breadcrumb 5 SQL + configurator 4 SQL remain).

**Breakdown of what stays on SQL (surrounding route work)**:

| Route | Answered from read store (0 SQL) | Kept on SQL (surrounding work) |
|---|---|---|
| `ProductDetailRoute` | `checkVariantListingConfig()`, `productRepository->search()`, variant `mainVariantId` lookup | `CategoryBreadcrumbBuilder::getProductSeoCategory()` (5 SQL), `ProductConfiguratorLoader` (4 SQL, skipped with `skipConfigurator=1`), `SalesChannelCmsPageLoader` + slot translations (14 SQL, skipped with `skipCmsPage=1`), `ProductPriceCalculator::getUnits()` (1 SQL once per process, cached on singleton) |
| `ProductListingRoute` | `resolveIds()`, `aggregate()` product buckets/metrics, `loadPreviews()`, `resolveData()` | Category lookup, `product_sorting` config, `EntityAggregation` hydration of referenced `product_manufacturer` / `property_group_option` entities (8 SQL total) |
| `ProductSearchRoute` | `resolveIds()`, `aggregate()`, `loadPreviews()`, `resolveData()` | `ProductSearchBuilder` / `SearchKeywordInterpreter` (`product_search_keyword` `LIKE`, 2 SQL) + `product_sorting` & `EntityAggregation` entity lookups (6 SQL; 8 SQL total) |

**Key takeaway**: eliminating 100 % of product-read SQL still leaves **5–23 SQL queries** on `ProductDetailRoute` and **8 SQL queries** on `ProductListingRoute` / `ProductSearchRoute`.
On small catalogs (5k products), those surrounding SQL queries dominate the route; on large catalogs (150k products, `docs/39-read-store-baseline.md`), the 12–13 product-read SQL queries (111–2,724 ms) dominate, which is where the read store pays off.

## Two response shapes: (a) entity hydration vs (b) DTO projection

### What breaks in Shape (b) (DTO without entities)

1. **`ProductDetailRouteResponse` type signature**: `ProductDetailRouteResponse::__construct(SalesChannelProductEntity $product, ?PropertyGroupCollection $configurator)` hard-types `SalesChannelProductEntity`. A pure DTO cannot be returned by `ProductDetailRoute` without changing the route response contract (our PoC hydrates a minimal uncalculated entity shell for detail when `shape=dto`).
2. **`ProductSubscriber::salesChannelLoaded()` does not run**: none of the runtime fields are computed — no `calculatedPrice`, `calculatedPrices`, `calculatedCheapestPrice`, `calculatedMaxPurchase`, `isNew`, `sortedProperties`, `variation`, `measurements`, and no `setDefaultLayout()` (breaking default CMS page loading on detail!).
3. **App scripts and plugin subscribers break**: `AppScriptProductPriceCalculator`, `sales_channel.product.loaded` / `product.loaded` subscribers, and any `ProductListingResultEvent` subscriber calling typed `SalesChannelProductEntity` getters (`getCalculatedPrice()`, `getName()`, `getManufacturer()`) fail or receive `ArrayEntity` instead.
4. **Storefront Twig templates break**: templates access `product.calculatedPrice.unitPrice`, `product.sortedProperties`, `product.cover.media.thumbnails`, etc.
5. **What Shape (b) wins (HTTP serialization)**: on `/store-api/product-listing/{categoryId}` and `/store-api/search`, returning a flat `ArrayEntity` DTO shrinks the serialized Store API JSON payload **~4×** (**129–165 KB → 32 KB** for 24 products) and saves **10–18 ms** of PHP `JsonEntityEncoder` overhead over HTTP (see HTTP timings below) — useful for dedicated headless/BFF read endpoints, not as a drop-in replacement for existing Storefront/plugin routes.

## Live parts (Q6): display-time vs query-time

### Display-time live parts

Measured via `read-store:bench:integration --store=opensearch --mode=live-parts --iterations=20 --warmup=3` on `orm_spike`:

| Variant | R1 Detail (`skipCfg+Cms`) p50 | R2 Listing (24) p50 | R3b Search (`Hotel`, 24) p50 | SQL |
|---|---:|---:|---:|---:|
| Shape (a): entity + `livePrices` ON + `liveStock` ON | 8.58 ms | 16.56 ms | 63.69 ms | 5 / 8 / 8 |
| Shape (a): entity + `livePrices` ON + `liveStock` OFF | 6.55 ms | 17.25 ms | 56.30 ms | 5 / 8 / 8 |
| Shape (a): entity + `livePrices` OFF + `liveStock` OFF | 6.78 ms | 17.09 ms | 54.79 ms | 5 / 8 / 8 |
| Shape (b): DTO (no entity hydration, no subscriber) | 5.90 ms | 19.97 ms | 64.05 ms | 5 / 8 / 8 |

`liveStock` does not read stock from SQL.
`stock`, `availableStock`, `available` and `isCloseout` always come from the document (`DocumentHydrator::hydrateEntity()`); `liveStock` ON runs `ProductMaxPurchaseCalculator` on those values, OFF copies `maxPurchase` (or the stock) from the document.
Stock freshness depends on the projector in both cases.

Running `ProductSubscriber::salesChannelLoaded()` (`ProductPriceCalculator` + `ProductMaxPurchaseCalculator` + `IsNewDetector` + `PropertyGroupSorter`) on 24 already-hydrated entities costs **< 1–2 ms in PHP** and **0 extra SQL queries** once `ProductPriceCalculator::getUnits()` is warm (1 SQL query once per worker/request if cold).
Therefore, **display-time price calculation, tax rules, customer-group rounding, max-purchase calculation, and `AppScriptProductPriceCalculator` should stay live in PHP** in Shape (a): keeping them live costs almost nothing (~1 ms for a 24-product page) while preserving 100 % compatibility with Shopware's pricing, tax, rule, and app-script ecosystem.

### Query-time live parts

Before pagination (`WHERE price <= 50`, `ORDER BY price ASC`, `MIN/MAX price` aggregations across 150,000 products), PHP cannot recalculate every product in the catalog.
What moves into the document vs what forces fallback:

| Concern | Can live in document? | Boundary / what breaks if pushed into document |
|---|---|---|
| Base & advanced rule prices (`cheapestPrice.<ruleId>.<currencyId>`) | **Yes** (already in `ProductDocument`, matching `CheapestPriceAccessorBuilder` up to `max_rule_prices = 100`) | Works as long as the sales channel context's rounding matches the currency's item rounding (`StoreContext::roundsLikeCurrency()`). |
| Custom context rounding (customer group / tax-free / non-standard decimals or intervals) | **No** (throws `NotSupportedByEngine` in `FieldResolver` → DAL fallback) | Precomputing every `(currency × customer_group × tax_state × rounding)` explodes document size; query-time rounding mismatch changes `price <= 50` boundary inclusion and `min/max` aggregations. |
| Dynamic `AppScriptProductPriceCalculator` / runtime-only cart-rule prices | **No** (same limitation as Shopware's own SQL `cheapest_price_accessor` and OpenSearch O1!) | App scripts run PHP/Twig per product at load time and cannot be evaluated inside SQL/OpenSearch/MongoDB indexes before pagination. |
| Real-time stock / `hideCloseoutProductsWhenOutOfStock` | **Eventually consistent** in document (`available`, `availableStock`, `isCloseout`) | Between an order placing stock to 0 and the projector updating the store (R6 lag, `docs/45`), a sold-out closeout item can appear in a listing; checkout still validates live stock against SQL. |

## 50-request Store API equality check

Measured via `read-store:bench:integration --mode=equality` across 50 real Store API route calls on `orm_spike` (10 full detail requests, 10 detail requests with `skipConfigurator=1&skipCmsPage=1`, 20 category listings across sortings/pagination/price/manufacturer/shipping-free/rating filters, and 10 keyword searches):

| Store | Identical | Served by read store | Fell back to DAL | Diffs | Notes |
|---|---:|---:|---:|---:|---|
| `store-sql-mysql` (Shape a) | **50 / 50** | **50** | 0 | **0** | 20/20 detail (full & skip), 20/20 listing, 10/10 search identical |
| `store-opensearch` (Shape a) | **47 / 50** | 45 | 5 | 3 | 5 `price-desc` listings fell back cleanly (by design); 3 `price-asc` diffs are tied-price `displayGroup` tie-breaks (`_id ASC` vs MySQL scan order); 20/20 detail & 10/10 search identical |

Note on `displayGroup` collapse equality: just like `ResultContract::R3B`, DAL `GROUP BY display_group` returns an arbitrary variant row within a variant group (MySQL `ANY_VALUE`), whereas the read store deterministically selects the top variant for the sort key (e.g., the cheapest variant on `price-asc`). Comparing `displayGroup`, `total`, `count`, and price aggregations yields 50/50 equality on `store-sql-mysql` and 47/50 (3 tied-price tie-breaks) on `store-opensearch`.

## HTTP cache interaction

- `ProductDetailRoute`, `ProductListingRoute`, and `ProductSearchRoute` all declare `PlatformRequest::ATTRIBUTE_HTTP_CACHE => true`.
- `ReadStoreGateway::detail()` calls `$this->cacheTagCollector->addTag(EntityCacheKeyGenerator::buildProductTag($parent))`, preserving the exact cache tag (`product-<parentId>`) that Shopware's `CacheInvalidationSubscriber` invalidates when a product is written.
- **Ordering nuance in async (`queue`) projection mode**: if `CacheInvalidationSubscriber` invalidates the HTTP cache synchronously on `EntityWrittenEvent` while the read store projector updates asynchronously via Messenger (lag `t_lag`), a cache-miss request arriving during `(t_write, t_write + t_lag)` can read the **stale** document from the read store and **re-populate the HTTP cache with stale HTML/JSON** until the next write or TTL expiry!
- **Required fix for production async mode**: either (a) invalidate the `product-<id>` HTTP cache tag **from the projector after `Storage::store()` completes** (for OpenSearch, after refresh or via `refresh=wait_for` on single-product updates), or (b) run the projector synchronously on single-product writes (R6 sync mode, `docs/45`).
- (b) alone does not close the window on OpenSearch: the adapter writes with `refresh=false` and a `refresh_interval` of 1 s, so a listing or search right after the write can still return the old document from the index and cache it.
  Detail is not affected, because `mget` by id is realtime.
  With OpenSearch, (b) needs `refresh=wait_for` on the single-product write as well, or (a); Valkey and SQL JSON have no refresh delay.

## Real Store API HTTP timings

Measured over HTTP against `public/index.php` (`php -S 127.0.0.1:8099`, `APP_ENV=prod`, `APP_DEBUG=0`, `SHOPWARE_HTTP_CACHE_ENABLED=0`, OPcache on, `orm_spike` 5,000 products, 3 warm-up + 15 measured requests per endpoint; `other lanes stopped: no`, host load ~13–20 — compare rows within this block; canonical stopped-lanes timings are in handoff F):

| Implementation | Shape | Detail (full) p50 / p95 | Detail (`skipCfg+Cms`) p50 / p95 | Listing (24) p50 / p95 | Search (`Hotel`, 24) p50 / p95 | Listing JSON size |
|---|---|---|---|---|---|---:|
| O0 `dal` | entity | 49.76 / 58.47 ms | 27.06 / 31.95 ms | 56.71 / 70.99 ms | 104.99 / 118.09 ms | 129.2 KB |
| O1 `dal-opensearch` | entity | 34.85 / 40.72 ms | 26.21 / 33.71 ms | 50.96 / 177.27 ms | **49.84 / 60.18 ms** | 128.8 KB |
| `store-opensearch` | (a) entity | 34.91 / 40.21 ms | 28.20 / 38.27 ms | 52.43 / 68.78 ms | 107.63 / 193.86 ms | 165.2 KB |
| `store-opensearch` | (b) DTO | 32.21 / 40.57 ms | 28.52 / 38.60 ms | **34.85 / 43.93 ms** | 82.42 / 180.63 ms | **32.2 KB** |
| `store-opensearch-valkey` | (a) entity | 34.84 / 45.14 ms | 23.07 / 31.71 ms | 48.99 / 55.91 ms | 97.85 / 263.24 ms | 232.5 KB |
| `store-opensearch-valkey` | (b) DTO | **21.77 / 26.79 ms** | **19.08 / 22.75 ms** | 39.98 / 45.66 ms | 91.42 / 114.89 ms | **34.7 KB** |
| `store-sql-mysql` | (a) entity | 34.01 / 60.38 ms | 23.38 / 34.89 ms | 55.75 / 239.89 ms | 92.01 / 101.04 ms | 165.2 KB |
| `store-sql-mysql` | (b) DTO | 26.77 / 35.67 ms | 25.17 / 29.68 ms | 43.41 / 50.00 ms | 90.71 / 104.96 ms | **32.2 KB** |

**HTTP observations**:

- Symfony routing, context resolution, surrounding SQL, and JSON serialization impose a **~19–28 ms floor** per Store API HTTP request even when the product fetch itself takes 0.18 ms (`opensearch-valkey`).
- Shape (b) DTO beats Shape (a) entity by **10–18 ms** on Listing and Detail solely because `JsonEntityEncoder` serializes 32 KB instead of 129–232 KB of nested entity graphs — not because `ProductPriceCalculator` is slow.
- On Search (`Hotel`), **O1 (`dal-opensearch`) is the fastest HTTP path at 49.84 ms** (vs 91–108 ms for standalone read stores) because it skips both the SQL keyword interpreter and the Painless script scorer.
