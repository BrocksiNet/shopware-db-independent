# PostgreSQL performance: why the storefront is slower than on MariaDB

Source: wave 5, handoff A.
Status: intermediate state, the statement capture only; causes, fixes and before/after numbers follow in later commits.

## Method

- Stacks: the benchmark stacks `pg` (port 8102) and `mariadb` (port 8101) of `scripts/benchmark.sh`, snapshot of `instance/` at `bde8801404f`, databases `bench_pg` and `bench_mariadb` (catalog data set), warm object cache, non-persistent connections.
- Per scenario `scripts/capture-requests.py` warms the stack with 8 requests of the same scenario and then sends one request with a fresh ordinal (6000, sales channel 0, the same URL on both databases).
- PostgreSQL log: `ALTER DATABASE bench_pg SET log_min_duration_statement = 0`, so only that database logs.
  A statement is the sum of its `parse`, `bind` and `execute` durations, calls count the `execute` lines.
- MariaDB log: `log_output = TABLE`, `long_query_time = 0`, `slow_query_log = 1`, rows of `mysql.slow_log` with `db = 'bench_mariadb'`.
- `scripts/capture-statements.py` slices both logs by the request windows and joins the statements by their DAL comment tag (`product-listing-route::loading::read`) or, without a tag, by the SQL text with literals, `replace(x::text, '-', '')` and `lower(hex(x))` removed.
  Statements without a tag that look different on the two databases do not join and show `-`.
- The raw logs are 16 MB and 5 MB and not committed; the per statement result of each scenario is in `docs/benchmark-results/wave5-statements/*.json`.
- Logging every statement slows both sides, the request times here (one request each) are higher than the benchmark medians and are not benchmark results.
  The column "DB ms" is the sum of the statement times inside the database server, it does not contain network, driver or PHP time.
- Settings changed for the capture: `shared_buffers` 1 GB, `effective_cache_size` 3 GB, `work_mem` 16 MB, `maintenance_work_mem` 256 MB on PostgreSQL (`scripts/benchmark.sh settings`, restart), the per-database `log_min_duration_statement` (reset right after), the MariaDB slow log globals (reset right after).
  The list of what is reset at the end of the handoff is at the end of this document.

## Statement capture

Statement counts are almost equal on both databases (a difference of one per scenario, for the PostgreSQL count wrapper), so no extra statements (savepoints, per connection setup) explain the gap.
The time inside the PostgreSQL server is 2.3x to 6.5x the MariaDB time, and it is concentrated in a few statements.

| Scenario | Request ms PG | Request ms MariaDB | PG statements | MariaDB statements | PG DB ms | MariaDB DB ms |
|---|---:|---:|---:|---:|---:|---:|
| storefront home | 312 | 173 | 75 | 74 | 173 | 76 |
| storefront listing with filter | 299 | 94 | 65 | 64 | 188 | 29 |
| storefront search | 359 | 97 | 66 | 65 | 244 | 38 |
| storefront product detail | 383 | 115 | 83 | 82 | 223 | 44 |

Statements that did not join (untagged statements written differently on the two databases) cost, summed per scenario:

| Scenario | PostgreSQL only: calls / ms | MariaDB only: calls / ms |
|---|---:|---:|
| storefront home | 19 / 40 | 18 / 12 |
| storefront listing with filter | 14 / 51 | 13 / 5 |
| storefront search | 18 / 48 | 17 / 5 |
| storefront product detail | 25 / 68 | 24 / 11 |

The per-statement tables below show the 12 most expensive PostgreSQL statements of each scenario.

### storefront home

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 60.9 | 2 | 4.5 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 30.9 | - | - |
| `-- product-listing-route::loading::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(produ` | 1 | 8.8 | 1 | 7.4 |
| `SELECT LOWER(HEX(app_feature.app_id)) AS app_id, app.name AS app_name, app.active AS app_active, app.version A` | 1 | 7.4 | 1 | 0.9 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 2 | 7.1 | 2 | 9.3 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 4.3 | 1 | 5.0 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQU` | 1 | 3.7 | 1 | 5.1 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 3.3 | 1 | 2.9 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 2.9 | 1 | 1.0 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 2.5 | 3 | 3.5 |
| `SELECT COUNT(*) FROM (-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text,` | 1 | 2.1 | - | - |
| `-- product-listing-route::loading::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, produc` | 1 | 2.0 | 1 | 2.8 |

Unique statements: PostgreSQL 62, MariaDB 61, same text after normalisation 48.

### storefront listing with filter

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 81.4 | 2 | 2.6 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 46.1 | - | - |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 11.3 | 3 | 1.5 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 1 | 4.7 | 1 | 2.0 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 3.4 | 1 | 0.7 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 2.4 | 1 | 0.6 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 2.3 | 1 | 0.4 |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 2.3 | 1 | 0.4 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 2.0 | 3 | 2.4 |
| `SELECT custom_entity.name, custom_entity.fields, custom_entity.flags FROM custom_entity LEFT JOIN app ON app.i` | 1 | 1.8 | - | - |
| `-- footer-pagelet::shipping-methods::search-ids SELECT any_value(REPLACE(shipping_method.id::text, '-', '')) a` | 1 | 1.7 | 1 | 0.5 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQU` | 1 | 1.6 | 1 | 0.7 |

Unique statements: PostgreSQL 52, MariaDB 51, same text after normalisation 43.

### storefront search

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 73.5 | 2 | 2.5 |
| `-- search::detect-keywords SELECT keyword, IF (lower(keyword) COLLATE ucs_basic LIKE $1 OR lower(keyword) COLL` | 1 | 58.3 | 1 | 7.7 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 40.1 | - | - |
| `-- search-page::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text` | 1 | 10.2 | 1 | 2.5 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 9.1 | 3 | 1.4 |
| `-- search-page::search-ids SELECT ranked.id, ranked.product_number, ranked.auto_increment, ranked._score FROM ` | 2 | 6.7 | 2 | 1.4 |
| `-- search-page::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as options.key, COUNT(p` | 1 | 4.0 | 1 | 0.9 |
| `-- search-page::aggregation::manufacturer SELECT REPLACE(IFNULL(product.product_manufacturer_id, product.paren` | 1 | 3.9 | 1 | 1.3 |
| `-- search-page::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', '') as properties.key` | 1 | 3.9 | 1 | 0.9 |
| `-- search-page::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQUOTE(JSON_EXTRACT(pr` | 1 | 3.2 | 1 | 1.4 |
| `-- search-page::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, product.parent.rating_ave` | 1 | 2.6 | 1 | 0.9 |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 2.4 | 1 | 0.4 |

Unique statements: PostgreSQL 51, MariaDB 50, same text after normalisation 38.

### storefront product detail

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 77.3 | 2 | 3.1 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 30.7 | - | - |
| `SELECT REPLACE(product.id::text, '-', '') as id, REPLACE(child.id::text, '-', '') as child_id FROM product LEF` | 1 | 17.8 | - | - |
| `-- breadcrumb-builder::search-ids SELECT REPLACE(category.id::text, '-', '') as id, category.auto_increment FR` | 1 | 17.3 | 1 | 0.3 |
| `-- product-detail-route::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version` | 1 | 12.2 | 1 | 5.2 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 9.3 | 3 | 1.2 |
| `SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text, '-', '') as product` | 1 | 6.5 | - | - |
| `-- breadcrumb-builder::main-category::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(pr` | 1 | 4.2 | 1 | 1.6 |
| `SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_value(product.product_number) as product_numbe` | 1 | 3.1 | - | - |
| `-- product-detail-route::association::properties::read SELECT REPLACE(property_group_option.id::text, '-', '')` | 1 | 3.0 | 1 | 0.5 |
| `-- product-detail-route::association::mainCategories::read SELECT REPLACE(main_category.id::text, '-', '') as ` | 1 | 2.1 | 1 | 0.5 |
| `-- product-detail-route::find-best-variant::search-ids SELECT REPLACE(product.id::text, '-', '') as id, produc` | 1 | 2.0 | 1 | 0.4 |

Unique statements: PostgreSQL 69, MariaDB 68, same text after normalisation 49.

