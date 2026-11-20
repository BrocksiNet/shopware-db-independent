| Scenario | Request ms PG | Request ms MariaDB | PG statements | MariaDB statements | PG DB ms | MariaDB DB ms |
|---|---:|---:|---:|---:|---:|---:|
| storefront home | 134 | 125 | 75 | 73 | 38 | 43 |
| storefront listing with filter | 81 | 90 | 65 | 63 | 19 | 20 |
| storefront search | 153 | 99 | 66 | 64 | 77 | 36 |
| storefront product detail | 145 | 109 | 83 | 81 | 40 | 27 |

### storefront home

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- product-listing-route::loading::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(produ` | 1 | 5.4 | 1 | 4.1 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((((jsonb_b` | 1 | 4.1 | 1 | 2.9 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 2 | 4.0 | 2 | 6.3 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 2.8 | 1 | 3.1 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 2.4 | 1 | 2.1 |
| `SELECT COUNT(*) FROM (-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text,` | 1 | 1.8 | - | - |
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 1.7 | 2 | 1.7 |
| `-- product-listing-route::loading::aggregation::manufacturer SELECT REPLACE(IFNULL(product.product_manufacture` | 1 | 1.4 | 1 | 1.7 |
| `-- product-listing-route::loading::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, produc` | 1 | 1.3 | 1 | 1.4 |
| `-- product-listing-route::loading::aggregation::shipping-free-filter SELECT MAX(IFNULL(product.shipping_free, ` | 1 | 1.2 | 1 | 1.4 |
| `-- product-listing::property-filter::read SELECT REPLACE(property_group_option.id::text, '-', '') as property_` | 1 | 1.1 | 1 | 1.2 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 0.8 | 3 | 1.6 |
| `-- product-listing-route::loading::association::options::read SELECT REPLACE(property_group_option.id::text, '` | 1 | 0.6 | 1 | 0.3 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 0.6 | 1 | 1.1 |

Unique statements: PostgreSQL 62, MariaDB 60, same text after normalisation 46.

### storefront listing with filter

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 1.8 | 3 | 1.5 |
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 1.7 | 2 | 2.0 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 1 | 1.3 | 1 | 0.8 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 1.3 | 1 | 0.4 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 1.2 | 1 | 0.4 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((((jsonb_b` | 1 | 1.0 | 1 | 0.6 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 0.7 | 3 | 1.4 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 0.7 | 1 | 0.8 |
| `-- product-listing-route::loading::aggregation::manufacturer SELECT REPLACE(IFNULL(product.product_manufacture` | 1 | 0.7 | 1 | 0.4 |
| `-- product-listing-route::loading::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, produc` | 1 | 0.6 | 1 | 0.3 |
| `-- product-listing::property-filter::read SELECT REPLACE(property_group_option.id::text, '-', '') as property_` | 1 | 0.6 | 1 | 0.4 |
| `-- product-listing-route::loading::aggregation::shipping-free-filter SELECT MAX(IFNULL(product.shipping_free, ` | 1 | 0.5 | 1 | 0.2 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 0.4 | - | - |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 0.4 | 1 | 0.2 |

Unique statements: PostgreSQL 52, MariaDB 50, same text after normalisation 42.

### storefront search

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- search-page::search-ids SELECT ranked.id, ranked.product_number, ranked.auto_increment, ranked._score FROM ` | 2 | 8.6 | 2 | 1.2 |
| `-- search-page::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', '') as properties.key` | 1 | 8.5 | 1 | 0.7 |
| `-- search-page::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((((jsonb_build_array(jsonb_pa` | 1 | 7.9 | 1 | 1.0 |
| `-- search-page::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as options.key, COUNT(p` | 1 | 7.8 | 1 | 0.6 |
| `-- search-page::aggregation::manufacturer SELECT REPLACE(IFNULL(product.product_manufacturer_id, product.paren` | 1 | 7.5 | 1 | 0.9 |
| `-- search-page::aggregation::shipping-free-filter SELECT MAX(IFNULL(product.shipping_free, product.parent.ship` | 1 | 7.4 | 1 | 0.6 |
| `-- search-page::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, product.parent.rating_ave` | 1 | 7.1 | 1 | 0.7 |
| `-- search-page::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text` | 1 | 6.4 | 1 | 1.8 |
| `-- search::detect-keywords SELECT keyword, IF (d.k LIKE $1 OR d.k LIKE $2 OR d.k LIKE $3 OR d.k LIKE $4 OR d.k` | 1 | 5.3 | 1 | 13.1 |
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 1.6 | 2 | 1.8 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 0.8 | 3 | 1.6 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 0.6 | 3 | 1.2 |
| `-- product-listing::property-filter::read SELECT REPLACE(property_group_option.id::text, '-', '') as property_` | 1 | 0.5 | 1 | 0.3 |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 0.4 | 1 | 0.2 |

Unique statements: PostgreSQL 51, MariaDB 49, same text after normalisation 37.

### storefront product detail

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- product-detail-route::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version` | 1 | 8.2 | 1 | 2.8 |
| `SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text, '-', '') as product` | 1 | 5.4 | - | - |
| `-- breadcrumb-builder::main-category::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(pr` | 1 | 3.4 | 1 | 1.3 |
| `SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_value(product.product_number) as product_numbe` | 1 | 2.7 | - | - |
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 1.8 | 2 | 1.8 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 0.9 | 3 | 1.3 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 0.9 | 3 | 1.3 |
| `-- breadcrumb-extension::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.vers` | 2 | 0.8 | 2 | 0.4 |
| `-- product-detail-route::association::properties::read SELECT REPLACE(property_group_option.id::text, '-', '')` | 1 | 0.6 | 1 | 0.6 |
| `-- product-detail-route::find-best-variant::search-ids SELECT REPLACE(product.id::text, '-', '') as id, produc` | 1 | 0.6 | 1 | 0.7 |
| `SELECT REPLACE(property_group_option.id::text, '-', '') as property_group_option.id, REPLACE(property_group_op` | 1 | 0.6 | - | - |
| `SELECT COUNT(DISTINCT product_review.id) as review-count FROM product_review LEFT JOIN product product_review.` | 1 | 0.6 | 1 | 0.2 |
| `-- product-review-route::aggregation::customer-login-filter SELECT product_review.points as ratingMatrix.key, ` | 1 | 0.5 | 1 | 0.2 |
| `-- product-detail-route::association::mainCategories::read SELECT REPLACE(main_category.id::text, '-', '') as ` | 1 | 0.5 | 1 | 0.4 |

Unique statements: PostgreSQL 69, MariaDB 67, same text after normalisation 48.
