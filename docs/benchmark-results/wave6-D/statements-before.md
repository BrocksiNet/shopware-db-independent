| Scenario | Request ms PG | Request ms MariaDB | PG statements | MariaDB statements | PG DB ms | MariaDB DB ms |
|---|---:|---:|---:|---:|---:|---:|
| store API product listing with aggregations | 107 | 88 | 21 | 19 | 31 | 55 |
| admin API product search with aggregations | 72 | 76 | 17 | 14 | 16 | 62 |

### store API product listing with aggregations

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text, '-', '') as product` | 1 | 12.3 | - | - |
| `SELECT REPLACE(product.properties.id::text, '-', '') as properties.key, COUNT(product.id) as properties.count ` | 1 | 2.9 | - | - |
| `SELECT REPLACE(IFNULL(product.product_manufacturer_id, product.parent.product_manufacturer_id)::text, '-', '')` | 1 | 2.3 | - | - |
| `SELECT MAX(IFNULL(COALESCE((ROUND((ROUND(CAST((((jsonb_build_array(jsonb_path_query_first((product.cheapest_pr` | 1 | 2.1 | - | - |
| `SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_value(product.product_number) as product_numbe` | 1 | 1.6 | - | - |
| `-- manufacturer-aggregation::read SELECT REPLACE(product_manufacturer.id::text, '-', '') as product_manufactur` | 1 | 1.6 | - | - |
| `SELECT COUNT(*) FROM (SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_value(product.product_nu` | 1 | 1.5 | - | - |
| `SELECT MAX(IFNULL(product.rating_average, product.parent.rating_average)) as rating FROM product LEFT JOIN pro` | 1 | 1.4 | 1 | 7.1 |
| `dbal-plugin-loader SELECT name, base_class, CASE WHEN active AND installed_at IS NOT NULL THEN 1 ELSE 0 END AS` | 1 | 1.1 | - | - |
| `SELECT REPLACE(product_price.id::text, '-', '') as product_price.id, REPLACE(product_price.version_id::text, '` | 1 | 0.7 | - | - |
| `SELECT custom_entity.name, custom_entity.fields, custom_entity.flags FROM custom_entity LEFT JOIN app ON app.i` | 1 | 0.7 | - | - |
| `SELECT COALESCE(cfsr.entity_name, 'global') as entity_name, cf.name FROM custom_field cf LEFT JOIN custom_fiel` | 1 | 0.6 | - | - |
| `SET NAMES 'utf8'` | 1 | 0.6 | - | - |
| `SELECT REPLACE(sales_channel.id::text, '-', '') AS id, sales_channel.maintenance AS maintenance, COALESCE(sale` | 1 | 0.4 | 1 | 0.4 |

Unique statements: PostgreSQL 21, MariaDB 19, same text after normalisation 5.

### admin API product search with aggregations

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text, '-', '') as product` | 1 | 4.5 | - | - |
| `SELECT REPLACE(product.id::text, '-', '') as id, product.product_number, product.auto_increment FROM product L` | 1 | 2.9 | - | - |
| `SELECT REPLACE(product.product_manufacturer_id::text, '-', '') as by-manufacturer.key, COUNT(product.id) as by` | 1 | 1.9 | - | - |
| `SELECT custom_entity.name, custom_entity.fields, custom_entity.flags FROM custom_entity LEFT JOIN app ON app.i` | 1 | 1.2 | - | - |
| `SELECT key, value FROM app_config` | 1 | 0.7 | 1 | 0.4 |
| `SELECT REPLACE(product.tax_id::text, '-', '') as by-tax.key, COUNT(product.id) as by-tax.count FROM product WH` | 1 | 0.7 | - | - |
| `SELECT COUNT(*) FROM (SELECT REPLACE(product.id::text, '-', '') as id, product.product_number, product.auto_in` | 1 | 0.7 | - | - |
| `SELECT AVG(product.stock) as avg-stock FROM product WHERE (product.version_id = $1) AND (((product.stock >= $2` | 1 | 0.6 | 1 | 1.9 |
| `SELECT AVG(product.stock) as stats-stock.avg, MIN(product.stock) as stats-stock.min, MAX(product.stock) as sta` | 1 | 0.6 | 1 | 2.1 |
| `dbal-plugin-loader SELECT name, base_class, CASE WHEN active AND installed_at IS NOT NULL THEN 1 ELSE 0 END AS` | 1 | 0.6 | - | - |
| `SELECT last_updated_password_at, active FROM user WHERE id = $1` | 1 | 0.3 | 1 | 0.4 |
| `SELECT user.active, user.admin, role.privileges FROM user LEFT JOIN acl_user_role AS mapping ON mapping.user_i` | 1 | 0.3 | - | - |
| `SELECT REPLACE(product_price.id::text, '-', '') as product_price.id, REPLACE(product_price.version_id::text, '` | 1 | 0.2 | - | - |
| `SELECT name, type FROM custom_field WHERE active = 1` | 1 | 0.2 | - | - |

Unique statements: PostgreSQL 17, MariaDB 14, same text after normalisation 5.
