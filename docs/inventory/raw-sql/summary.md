# Raw SQL outside the DAL: MySQL-specific construct inventory

Generated with:

```
python3 -I scan.py <instance>      # writes raw-sql.csv, hits.tsv, tables.md, meta.json
python3 -I build_summary.py <instance>   # writes this file, verifies every example line
```

where `<instance>` = `<repo>/instance`, run from `docs/inventory/raw-sql/`. All numbers below come from these two scripts.

Scope rule (see `scan.py`): every `*.php` under `instance/src`, excluding any path containing `/Migration/` and `src/Core/Framework/DataAbstractionLayer/`; in scope if the file imports `Doctrine\DBAL\Connection` (`imports_connection`) or, without that import, calls an execute/fetch method, createQueryBuilder, MultiInsertQueryQueue or RetryableQuery/Transaction (`executes_sql_no_connection_import`). SQL constructs are matched only inside PHP string literals (comments and code are stripped first); PHP-side constructs only in code. Case-insensitive except where noted in (f). Test helpers that live under `src/` (for example `src/Core/Test`, `src/Elasticsearch/Test`) are included because they are under `src`.

Raw SQL vs QueryBuilder, per file: raw-SQL literal only 254, QueryBuilder only 37, both 21, neither (only execute/fetch calls with SQL held elsewhere, or helper classes) 134.

Totals note: `sql_constructs_total` sums all SQL-string constructs except `lower_hex` (a subset of `hex_fn`). `json_fn` counts every JSON_* call once; the per-function split is in its own table. The PHP-side binary-uuid helpers (`uuid_*`, `array_param_binary`) are reported separately in `raw-sql.csv` (`sql_plus_php_binary_total`) and are not part of the Top 30 ranking.

Scope numbers: excluded_dal=474, excluded_migration=982, in_scope=446, php_files_considered=5933, scope_executes_sql_no_connection_import=10, scope_imports_connection=436

### (a) Totals per construct

| construct | files | occurrences | kind |
|---|---:|---:|---|
| backtick_ident | 135 | 1434 | SQL string |
| hex_fn | 142 | 371 | SQL string |
| unhex_fn | 6 | 11 | SQL string |
| lower_hex | 140 | 364 | SQL string |
| json_fn | 19 | 90 | SQL string |
| json_arrow | 0 | 0 | SQL string |
| group_concat | 20 | 59 | SQL string |
| group_concat_separator | 17 | 51 | SQL string |
| on_dup_key | 10 | 12 | SQL string |
| replace_into | 3 | 3 | SQL string |
| insert_ignore | 3 | 3 | SQL string |
| ifnull | 12 | 63 | SQL string |
| if_fn | 10 | 10 | SQL string |
| limit_offset_comma | 0 | 0 | SQL string |
| date_format | 1 | 1 | SQL string |
| now_fn | 3 | 8 | SQL string |
| date_add | 0 | 0 | SQL string |
| date_sub | 1 | 1 | SQL string |
| interval_kw | 1 | 1 | SQL string |
| unix_timestamp | 0 | 0 | SQL string |
| concat_fn | 6 | 17 | SQL string |
| concat_ws | 0 | 0 | SQL string |
| find_in_set | 0 | 0 | SQL string |
| regexp | 0 | 0 | SQL string |
| match_against | 0 | 0 | SQL string |
| last_insert_id | 0 | 0 | SQL string |
| for_update | 6 | 11 | SQL string |
| skip_locked | 2 | 2 | SQL string |
| lock_in_share | 0 | 0 | SQL string |
| fk_checks | 1 | 4 | SQL string |
| at_at_var | 2 | 7 | SQL string |
| user_var | 1 | 2 | SQL string |
| information_schema | 1 | 1 | SQL string |
| show_stmt | 2 | 3 | SQL string |
| straight_join | 0 | 0 | SQL string |
| index_hint | 0 | 0 | SQL string |
| collate | 1 | 1 | SQL string |
| cast_unsigned | 1 | 1 | SQL string |
| cast_char_binary | 0 | 0 | SQL string |
| date_diff_fns | 2 | 2 | SQL string |
| field_fn | 0 | 0 | SQL string |
| substring_index | 0 | 0 | SQL string |
| rand_fn | 2 | 3 | SQL string |
| uuid_fn | 0 | 0 | SQL string |
| ddl_keywords | 2 | 4 | SQL string |
| multi_table_dml | 4 | 4 | SQL string |
| insert_set | 0 | 0 | SQL string |
| table_maint | 0 | 0 | SQL string |
| truncate | 3 | 3 | SQL string |
| sql_calc_found_rows | 0 | 0 | SQL string |
| null_safe_eq | 1 | 1 | SQL string |
| misc_fns | 2 | 6 | SQL string |
| div_mod_kw | 0 | 0 | SQL string |
| date_part_fns | 0 | 0 | SQL string |
| cast_datetime | 0 | 0 | SQL string |
| order_by_null | 4 | 24 | SQL string |
| values_fn | 2 | 3 | SQL string |
| uuid_fromHexToBytes | 187 | 496 | PHP-side binary-uuid |
| uuid_fromBytesToHex | 44 | 73 | PHP-side binary-uuid |
| uuid_randomBytes | 26 | 42 | PHP-side binary-uuid |
| array_param_binary | 89 | 162 | PHP-side binary-uuid |
| multi_insert_queue | 9 | 10 | metric (not MySQL-specific) |
| retryable | 41 | 76 | metric (not MySQL-specific) |
| qb_calls | 58 | 95 | metric (not MySQL-specific) |
| exec_calls | 326 | 830 | metric (not MySQL-specific) |
| raw_sql_literals | 275 | 630 | metric (not MySQL-specific) |

JSON functions found (inside `json_fn`):

| function | files | occurrences |
|---|---:|---:|
| JSON_ARRAY | 3 | 11 |
| JSON_ARRAYAGG | 8 | 8 |
| JSON_ARRAY_APPEND | 1 | 1 |
| JSON_CONTAINS | 2 | 3 |
| JSON_EXTRACT | 9 | 24 |
| JSON_LENGTH | 1 | 1 |
| JSON_OBJECT | 9 | 11 |
| JSON_OVERLAPS | 2 | 5 |
| JSON_QUOTE | 3 | 9 |
| JSON_REMOVE | 3 | 3 |
| JSON_SEARCH | 2 | 2 |
| JSON_SET | 1 | 1 |
| JSON_UNQUOTE | 5 | 11 |

Files with at least one SQL-string construct: 241 of 446 in scope.

### (b) Per area

| area | files in scope | files with SQL constructs | SQL constructs | raw SQL literals | QueryBuilder calls | exec calls |
|---|---:|---:|---:|---:|---:|---:|
| Core/Framework | 120 | 60 | 542 | 189 | 26 | 235 |
| Core/Content | 109 | 62 | 498 | 135 | 30 | 194 |
| Elasticsearch | 30 | 24 | 339 | 56 | 0 | 59 |
| Core/Checkout | 59 | 31 | 284 | 71 | 12 | 99 |
| Storefront | 25 | 19 | 242 | 37 | 3 | 43 |
| Core/System | 61 | 30 | 201 | 65 | 20 | 102 |
| Core/Maintenance | 8 | 2 | 46 | 29 | 3 | 43 |
| Administration | 7 | 3 | 33 | 6 | 1 | 8 |
| Core/Installer | 6 | 2 | 14 | 28 | 0 | 29 |
| Core/Service | 3 | 2 | 6 | 2 | 0 | 2 |
| Core/Test | 12 | 4 | 6 | 11 | 0 | 12 |
| Core/DevOps | 1 | 1 | 4 | 0 | 0 | 0 |
| Core | 2 | 1 | 2 | 1 | 0 | 2 |
| Core/Profiling | 3 | 0 | 0 | 0 | 0 | 2 |

### (b) Per area / sub-domain

| sub | files in scope | files with SQL constructs | SQL constructs | raw SQL literals | QueryBuilder calls | exec calls |
|---|---:|---:|---:|---:|---:|---:|
| Elasticsearch/Admin | 17 | 17 | 269 | 24 | 0 | 24 |
| Storefront/Framework | 9 | 8 | 162 | 11 | 2 | 15 |
| Core/Framework/App | 16 | 13 | 147 | 35 | 1 | 38 |
| Core/Content/Product | 29 | 21 | 123 | 46 | 11 | 72 |
| Core/Content/Media | 18 | 14 | 87 | 34 | 1 | 37 |
| Core/Content/Flow | 12 | 4 | 79 | 15 | 0 | 15 |
| Core/Framework/Adapter | 11 | 7 | 76 | 22 | 0 | 22 |
| Core/System/NumberRange | 2 | 2 | 67 | 8 | 0 | 11 |
| Core/Framework/Mcp | 10 | 6 | 62 | 19 | 0 | 17 |
| Core/Checkout/Customer | 12 | 8 | 59 | 11 | 2 | 15 |
| Core/Checkout/DocumentV2 | 6 | 5 | 58 | 6 | 1 | 8 |
| Storefront/Theme | 10 | 9 | 58 | 22 | 1 | 24 |
| Elasticsearch/Product | 4 | 3 | 57 | 12 | 0 | 12 |
| Core/Content/Newsletter | 2 | 2 | 52 | 7 | 0 | 7 |
| Core/Framework/Script | 2 | 2 | 51 | 2 | 0 | 2 |
| Core/Maintenance/System | 5 | 2 | 46 | 27 | 1 | 38 |
| Core/Checkout/Document | 11 | 4 | 41 | 12 | 0 | 13 |
| Core/Checkout/Cart | 5 | 5 | 40 | 10 | 1 | 11 |
| Core/Checkout/Shipping | 2 | 2 | 40 | 4 | 0 | 4 |
| Core/Framework/Webhook | 9 | 6 | 39 | 39 | 0 | 39 |
| Core/Content/Seo | 6 | 4 | 38 | 8 | 7 | 19 |
| Core/Checkout/Promotion | 6 | 4 | 36 | 20 | 4 | 32 |
| Core/Content/Sitemap | 4 | 3 | 36 | 1 | 1 | 7 |
| Core/Framework/Demodata | 11 | 11 | 36 | 29 | 0 | 28 |
| Core/Framework/Routing | 2 | 1 | 35 | 4 | 6 | 16 |
| Core/System/Snippet | 5 | 5 | 34 | 9 | 0 | 9 |
| Core/System/SalesChannel | 7 | 4 | 31 | 7 | 4 | 16 |
| Core/Framework/Increment | 1 | 1 | 30 | 3 | 2 | 5 |
| Core/Content/Category | 6 | 4 | 29 | 4 | 4 | 13 |
| Administration/Dashboard | 1 | 1 | 24 | 1 | 1 | 3 |
| Core/Content/Rule | 3 | 3 | 23 | 5 | 4 | 7 |
| Core/Framework/Api | 13 | 5 | 23 | 11 | 9 | 24 |
| Core/Content/Cms | 3 | 2 | 20 | 7 | 1 | 6 |
| Storefront/Mcp | 1 | 1 | 20 | 3 | 0 | 3 |
| Core/System/Tag | 1 | 1 | 14 | 0 | 5 | 4 |
| Core/System/SystemConfig | 4 | 2 | 13 | 5 | 2 | 9 |
| Core/Framework/Event | 1 | 1 | 12 | 1 | 0 | 1 |
| Core/System/StateMachine | 3 | 2 | 12 | 3 | 0 | 3 |
| Elasticsearch/Framework | 6 | 3 | 12 | 12 | 0 | 14 |
| Core/Framework/Plugin | 1 | 1 | 11 | 0 | 0 | 2 |
| Core/Installer/Configuration | 2 | 1 | 11 | 24 | 0 | 24 |
| Core/Checkout/Order | 2 | 2 | 9 | 1 | 2 | 5 |
| Administration/Controller | 2 | 1 | 8 | 3 | 0 | 3 |
| Core/System/CustomEntity | 4 | 2 | 8 | 13 | 0 | 14 |
| Core/Framework/Log | 3 | 2 | 7 | 5 | 0 | 6 |
| Core/System/Language | 3 | 2 | 7 | 3 | 1 | 7 |
| Core/Framework/Store | 4 | 1 | 6 | 5 | 0 | 5 |
| Core/Content/ImportExport | 6 | 1 | 5 | 3 | 1 | 6 |
| Core/DevOps/StaticAnalyze | 1 | 1 | 4 | 0 | 0 | 0 |
| Core/Framework/DependencyInjection | 21 | 1 | 4 | 1 | 0 | 1 |
| Core/Service/Subscriber | 1 | 1 | 4 | 1 | 0 | 1 |
| Core/System/CustomField | 2 | 1 | 4 | 5 | 0 | 5 |
| Core/Content/ProductExport | 3 | 1 | 3 | 1 | 0 | 1 |
| Core/Framework/Test | 9 | 2 | 3 | 9 | 2 | 15 |
| Core/Installer/Database | 3 | 1 | 3 | 2 | 0 | 3 |
| Core/System/Consent | 3 | 2 | 3 | 5 | 0 | 6 |
| Core/System/UsageData | 6 | 2 | 3 | 0 | 8 | 11 |
| Core/Test/(root) | 2 | 1 | 3 | 4 | 0 | 4 |
| Core/(root) | 2 | 1 | 2 | 1 | 0 | 2 |
| Core/Service/Requirement | 1 | 1 | 2 | 1 | 0 | 1 |
| Core/Test/Integration | 5 | 2 | 2 | 6 | 0 | 6 |
| Storefront/Test | 1 | 1 | 2 | 1 | 0 | 1 |
| Administration/Framework | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/Checkout/Payment | 7 | 1 | 1 | 7 | 2 | 11 |
| Core/Content/Mail | 2 | 1 | 1 | 1 | 0 | 1 |
| Core/Content/ProductStream | 1 | 1 | 1 | 2 | 0 | 2 |
| Core/Content/Test | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/System/Currency | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/System/Locale | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/System/Salutation | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/System/Tax | 1 | 1 | 1 | 1 | 0 | 1 |
| Core/System/User | 1 | 1 | 1 | 2 | 0 | 2 |
| Core/Test/PHPUnit | 1 | 1 | 1 | 1 | 0 | 2 |
| Elasticsearch/Test | 2 | 1 | 1 | 8 | 0 | 9 |
| Administration/DependencyInjection | 2 | 0 | 0 | 0 | 0 | 0 |
| Administration/Snippet | 1 | 0 | 0 | 1 | 0 | 1 |
| Core/Checkout/DependencyInjection | 8 | 0 | 0 | 0 | 0 | 0 |
| Core/Content/DependencyInjection | 13 | 0 | 0 | 0 | 0 | 0 |
| Core/Framework/(root) | 1 | 0 | 0 | 1 | 0 | 1 |
| Core/Framework/MessageQueue | 3 | 0 | 0 | 3 | 3 | 8 |
| Core/Framework/Sso | 1 | 0 | 0 | 0 | 3 | 5 |
| Core/Framework/Util | 1 | 0 | 0 | 0 | 0 | 0 |
| Core/Installer/Controller | 1 | 0 | 0 | 2 | 0 | 2 |
| Core/Maintenance/DependencyInjection | 1 | 0 | 0 | 0 | 0 | 0 |
| Core/Maintenance/Staging | 1 | 0 | 0 | 1 | 0 | 1 |
| Core/Maintenance/User | 1 | 0 | 0 | 1 | 2 | 4 |
| Core/Profiling/Controller | 1 | 0 | 0 | 0 | 0 | 2 |
| Core/Profiling/DependencyInjection | 1 | 0 | 0 | 0 | 0 | 0 |
| Core/Profiling/Doctrine | 1 | 0 | 0 | 0 | 0 | 0 |
| Core/Service/DependencyInjection | 1 | 0 | 0 | 0 | 0 | 0 |
| Core/System/DependencyInjection | 15 | 0 | 0 | 0 | 0 | 0 |
| Core/System/Integration | 1 | 0 | 0 | 1 | 0 | 1 |
| Core/Test/Stub | 4 | 0 | 0 | 0 | 0 | 0 |
| Elasticsearch/DependencyInjection | 1 | 0 | 0 | 0 | 0 | 0 |
| Storefront/DependencyInjection | 4 | 0 | 0 | 0 | 0 | 0 |

### (c) Top 30 files by SQL-string construct occurrences (`sql_constructs_total`; `lower_hex` is a subset of `hex_fn` and not added again)

| # | path | total | top constructs |
|---:|---|---:|---|
| 1 | src/Core/Framework/App/Feature/AppFeatureStorage.php | 90 | backtick_ident=87, lower_hex=3, hex_fn=3 |
| 2 | src/Storefront/Framework/SystemCheck/ProductListingReadinessCheck.php | 87 | backtick_ident=83, lower_hex=4, hex_fn=4 |
| 3 | src/Elasticsearch/Admin/Indexer/OrderAdminSearchIndexer.php | 74 | backtick_ident=27, lower_hex=19, hex_fn=19, group_concat=12, group_concat_separator=11 |
| 4 | src/Core/Content/Flow/Indexing/FlowPayloadUpdater.php | 56 | backtick_ident=50, lower_hex=6, hex_fn=6 |
| 5 | src/Elasticsearch/Admin/Indexer/ProductAdminSearchIndexer.php | 49 | lower_hex=14, hex_fn=14, group_concat=9, order_by_null=7, ifnull=6 |
| 6 | src/Elasticsearch/Product/ElasticsearchProductDefinition.php | 48 | ifnull=30, lower_hex=14, hex_fn=14, backtick_ident=2, json_fn=1 |
| 7 | src/Elasticsearch/Admin/Indexer/CustomerAdminSearchIndexer.php | 46 | order_by_null=12, group_concat_separator=12, group_concat=12, lower_hex=10, hex_fn=10 |
| 8 | src/Core/Content/Newsletter/DataAbstractionLayer/Indexing/CustomerNewsletterSalesChannelsUpdater.php | 45 | backtick_ident=36, json_fn=3, lower_hex=2, hex_fn=2, concat_fn=2 |
| 9 | src/Core/Checkout/DocumentV2/Service/ReferenceInvoiceLoader.php | 44 | backtick_ident=40, lower_hex=4, hex_fn=4 |
| 10 | src/Core/Framework/Script/Execution/ScriptLoader.php | 40 | backtick_ident=36, lower_hex=2, hex_fn=2, ifnull=1, if_fn=1 |
| 11 | src/Core/Maintenance/System/Service/ShopConfigurator.php | 40 | backtick_ident=33, now_fn=5, on_dup_key=1, if_fn=1 |
| 12 | src/Core/Checkout/Shipping/Validator/ShippingMethodValidator.php | 39 | backtick_ident=33, lower_hex=3, hex_fn=3, for_update=3 |
| 13 | src/Storefront/Framework/SystemCheck/Util/SalesChannelDomainProvider.php | 39 | backtick_ident=35, lower_hex=4, hex_fn=4 |
| 14 | src/Core/Framework/Routing/ApiRequestContextResolver.php | 35 | backtick_ident=34, lower_hex=1, hex_fn=1 |
| 15 | src/Core/System/NumberRange/ValueGenerator/NumberRangeValueGenerator.php | 34 | backtick_ident=31, lower_hex=3, hex_fn=3 |
| 16 | src/Storefront/Theme/ThemeRuntimeConfigStorage.php | 34 | backtick_ident=30, lower_hex=3, hex_fn=3, replace_into=1 |
| 17 | src/Core/System/NumberRange/ValueGenerator/Pattern/IncrementStorage/IncrementSqlStorage.php | 33 | backtick_ident=26, on_dup_key=3, user_var=2, lower_hex=1, if_fn=1 |
| 18 | src/Core/Content/Product/DataAbstractionLayer/StatesUpdater.php | 31 | backtick_ident=29, lower_hex=1, if_fn=1, hex_fn=1 |
| 19 | src/Core/Content/Seo/HreflangLoader.php | 31 | backtick_ident=31 |
| 20 | src/Core/Checkout/Cart/CartPersister.php | 30 | backtick_ident=29, on_dup_key=1 |
| 21 | src/Core/Checkout/Document/Aggregate/DocumentBaseConfig/DocumentBaseConfigValidator.php | 30 | backtick_ident=30 |
| 22 | src/Core/Content/Media/Subscriber/CustomFieldsUnusedMediaSubscriber.php | 30 | json_fn=24, concat_fn=6 |
| 23 | src/Core/Framework/Increment/MySQLIncrementer.php | 30 | backtick_ident=29, on_dup_key=1 |
| 24 | src/Core/Content/Product/DataAbstractionLayer/CheapestPriceUpdater.php | 27 | ifnull=12, lower_hex=10, hex_fn=10, backtick_ident=5 |
| 25 | src/Core/Framework/Adapter/Twig/EntityTemplateLoader.php | 25 | backtick_ident=25 |
| 26 | src/Administration/Dashboard/OrderAmountService.php | 24 | backtick_ident=20, ifnull=2, date_format=1, date_diff_fns=1 |
| 27 | src/Core/Checkout/Customer/Subscriber/CustomerMetaFieldSubscriber.php | 24 | backtick_ident=22, lower_hex=2, hex_fn=2 |
| 28 | src/Core/System/SalesChannel/Context/SalesChannelContextPersister.php | 21 | backtick_ident=19, replace_into=1, on_dup_key=1 |
| 29 | src/Storefront/Mcp/Tool/ThemeConfigTool.php | 20 | backtick_ident=18, lower_hex=2, hex_fn=2 |
| 30 | src/Core/Content/Category/DataAbstractionLayer/CategoryBreadcrumbUpdater.php | 19 | backtick_ident=12, lower_hex=4, hex_fn=4, values_fn=1, on_dup_key=1 |


### (d) Examples per construct (verified: each snippet was checked as a substring of the cited line)

**backtick_ident** (135 files, 1434 occurrences)

- `src/Storefront/Theme/Mail/MailThemeIdLoader.php:26`: `FROM `theme_sales_channel` WHERE `sales_channel_id` = :salesChannelId`
  - PostgreSQL: unquoted snake_case identifiers, or double quotes via `$connection->quoteIdentifier()`. PostgreSQL rejects backticks (verified: `syntax error at or near "`"`).
- `src/Core/Framework/Adapter/Storage/MySQLKeyValueStorage.php:43`: `REPLACE INTO `app_config` (`key`, `value`)`
  - PostgreSQL: same; `key`/`value` are not reserved in PostgreSQL, so unquoted works.

**hex_fn** (142 files, 371 occurrences)

- `src/Administration/Framework/App/ActiveAdminAppLoader.php:27`: `LOWER(HEX(app.integration_id)) as integrationId`
  - PostgreSQL: bytea column: `encode(app.integration_id, 'hex')`; native uuid column: `replace(app.integration_id::text, '-', '')` (both verified).
- `src/Core/Framework/Demodata/Generator/ProductGenerator.php:393`: `SELECT LOWER(HEX(id)) as id FROM sales_channel LIMIT 100`
  - PostgreSQL: same as above.

**lower_hex** (140 files, 364 occurrences)

- `src/Core/Framework/Demodata/Generator/ProductReviewGenerator.php:49`: `SELECT LOWER(HEX(id)) FROM sales_channel`
  - PostgreSQL: `encode(id,'hex')` already lower case; with uuid type `replace(id::text,'-','')`.

**unhex_fn** (6 files, 11 occurrences)

- `src/Core/Framework/Api/OAuth/RefreshTokenRepository.php:159`: `user_id = UNHEX(:userId)`
  - PostgreSQL: bytea: `decode(:userId,'hex')` (verified); uuid: `:userId::uuid` after re-inserting dashes.
- `src/Core/Installer/Configuration/ShopConfigurationService.php:134`: `VALUES (?, UNHEX(?))`
  - PostgreSQL: same.

**json_fn** (19 files, 90 occurrences)

- `src/Core/Checkout/Promotion/DataAbstractionLayer/PromotionExclusionUpdater.php:106`: `WHERE JSON_CONTAINS(promotion.exclusion_ids, JSON_ARRAY(:value)`
  - PostgreSQL: `promotion.exclusion_ids::jsonb @> jsonb_build_array(:value)` (the `@>` containment operator verified).
- `src/Core/Content/Media/Subscriber/CustomFieldsUnusedMediaSubscriber.php:65`: `JSON_UNQUOTE(JSON_EXTRACT(%1$s.custom_fields, CONCAT('$.', JSON_QUOTE(:field)))`
  - PostgreSQL: `custom_fields::jsonb ->> :field` (`#>>` path form verified).
- `src/Core/Content/Cms/Subscriber/UnusedMediaSubscriber.php:53`: `JSON_EXTRACT(slot_config, "$.*.sliderItems.value[*].mediaId")`
  - PostgreSQL: `jsonb_path_query_array(slot_config::jsonb, '$.*.sliderItems.value[*].mediaId')` (verified on sample data). Note the MySQL path is in double quotes, which PostgreSQL reads as an identifier.
- `src/Elasticsearch/Admin/Indexer/CategoryAdminSearchIndexer.php:148`: `JSON_ARRAYAGG(JSON_OBJECT(`
  - PostgreSQL: `jsonb_agg(jsonb_build_object(...))` (verified).

**group_concat** (20 files, 59 occurrences)

- `src/Core/Checkout/Document/Renderer/AbstractDocumentRenderer.php:47`: `GROUP_CONCAT(DISTINCT LOWER(HEX(id))) as ids`
  - PostgreSQL: `string_agg(DISTINCT encode(id,'hex'), ',')`; the separator is mandatory in PostgreSQL.
- `src/Elasticsearch/Admin/Indexer/MediaAdminSearchIndexer.php:203`: `GROUP_CONCAT(LOWER(HEX(tag.id)) ORDER BY NULL SEPARATOR ' ') as tagIds`
  - PostgreSQL: `string_agg(encode(tag.id,'hex'), ' ')` (`string_agg(DISTINCT x, ' ' ORDER BY x)` verified); drop `ORDER BY NULL`.

**group_concat_separator** (17 files, 51 occurrences)

- `src/Core/Content/Product/DataAbstractionLayer/ProductCategoryDenormalizer.php:116`: `GROUP_CONCAT(category.path SEPARATOR \'\')`
  - PostgreSQL: `string_agg(category.path, '')`.
- `src/Elasticsearch/Admin/Indexer/ShippingMethodAdminSearchIndexer.php:88`: `SEPARATOR " "`
  - PostgreSQL: second argument of `string_agg`; the double-quoted separator must become a single-quoted literal.

**order_by_null** (4 files, 24 occurrences)

- `src/Elasticsearch/Admin/Indexer/CustomerAdminSearchIndexer.php:220`: `GROUP_CONCAT(DISTINCT country_translation.name ORDER BY NULL SEPARATOR ' ') as country`
  - PostgreSQL: drop it; it only suppresses MySQL sorting inside GROUP_CONCAT.

**on_dup_key** (10 files, 12 occurrences)

- `src/Core/Checkout/Cart/CartPersister.php:113`: `ON DUPLICATE KEY UPDATE `payload` = :payload, `compressed` = :compressed`
  - PostgreSQL: ON CONFLICT (token) DO UPDATE SET payload = EXCLUDED.payload, ... (verified shape); needs the conflict target columns.
- `src/Core/Framework/App/DeletedApps/DeletedAppsGateway.php:36`: `ON DUPLICATE KEY UPDATE app_secret = VALUES(app_secret)`
  - PostgreSQL: ON CONFLICT (...) DO UPDATE SET app_secret = EXCLUDED.app_secret.

**values_fn** (2 files, 3 occurrences)

- `src/Core/Content/Category/DataAbstractionLayer/CategoryBreadcrumbUpdater.php:225`: `ON DUPLICATE KEY UPDATE `breadcrumb` = VALUES(`breadcrumb`)`
  - PostgreSQL: EXCLUDED.breadcrumb.

**replace_into** (3 files, 3 occurrences)

- `src/Core/Framework/Adapter/Storage/MySQLKeyValueStorage.php:43`: `REPLACE INTO `app_config` (`key`, `value`) VALUES (:key, :value)`
  - PostgreSQL: INSERT ... ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value.
- `src/Core/System/SalesChannel/Context/SalesChannelContextPersister.php:85`: `REPLACE INTO sales_channel_api_context`
  - PostgreSQL: INSERT ... ON CONFLICT (...) DO UPDATE SET <all columns>.

**insert_ignore** (3 files, 3 occurrences)

- `src/Storefront/Theme/DataAbstractionLayer/ThemeIndexer.php:89`: `INSERT IGNORE INTO theme_child (child_id, parent_id)`
  - PostgreSQL: INSERT ... ON CONFLICT DO NOTHING (verified).
- `src/Core/Framework/Mcp/McpToolsetSessionStorage.php:32`: `INSERT IGNORE INTO `mcp_toolset_session``
  - PostgreSQL: same.

**ifnull** (12 files, 63 occurrences)

- `src/Elasticsearch/Product/ElasticsearchProductDefinition.php:466`: `IFNULL(product_main.custom_search_keywords, product_parent.custom_search_keywords) AS customSearchKeywords`
  - PostgreSQL: COALESCE(...) (verified; `ifnull` does not exist in PostgreSQL).
- `src/Administration/Dashboard/OrderAmountService.php:39`: `IFNULL(CONVERT_TZ(`
  - PostgreSQL: COALESCE(...).

**if_fn** (10 files, 10 occurrences)

- `src/Core/Content/Product/DataAbstractionLayer/StatesUpdater.php:46`: `IF(`product_download`.`id` IS NOT NULL, 1, 0) as hasDownloads`
  - PostgreSQL: CASE WHEN ... THEN 1 ELSE 0 END (verified).
- `src/Core/Maintenance/System/Service/ShopConfigurator.php:158`: `SET factor = IF(iso_code = :newDefault, 1, factor * :fixFactor)`
  - PostgreSQL: CASE WHEN iso_code = :newDefault THEN 1 ELSE factor * :fixFactor END.

**date_format** (1 files, 1 occurrences)

- `src/Administration/Dashboard/OrderAmountService.php:46`: `DATE_FORMAT(' . $accessor . ', \'%Y-%m-%d\')`
  - PostgreSQL: to_char(x, 'YYYY-MM-DD') (verified); format tokens differ.

**now_fn** (3 files, 8 occurrences)

- `src/Core/Content/Product/Stock/StockStorage.php:56`: `updated_at = NOW()`
  - PostgreSQL: works unchanged (`now()` verified).
- `src/Core/Content/Category/DataAbstractionLayer/CategoryBreadcrumbUpdater.php:212`: `DATE(NOW())`
  - PostgreSQL: works unchanged.

**date_sub** (1 files, 1 occurrences)

- `src/Core/Framework/Demodata/PersonalData/CleanPersonalDataCommand.php:91`: `DATE_SUB(CURDATE(), INTERVAL :days DAY)`
  - PostgreSQL: CURRENT_DATE - make_interval(days => :days) (verified).

**interval_kw** (1 files, 1 occurrences)

- `src/Core/Framework/Demodata/PersonalData/CleanPersonalDataCommand.php:91`: `INTERVAL :days DAY`
  - PostgreSQL: make_interval(days => :days); PostgreSQL does not accept `INTERVAL :param DAY`.

**date_diff_fns** (2 files, 2 occurrences)

- `src/Administration/Dashboard/OrderAmountService.php:39`: `CONVERT_TZ(' . $accessor . ', :dbtimezone, :timezone)`
  - PostgreSQL: (x AT TIME ZONE :dbtimezone) AT TIME ZONE :timezone (verified with named zones); note MySQL accepts offsets such as '+00:00' here, PostgreSQL zone syntax differs.
- `src/Core/Framework/Demodata/PersonalData/CleanPersonalDataCommand.php:91`: `DATE_SUB(CURDATE()`
  - PostgreSQL: CURRENT_DATE.

**concat_fn** (6 files, 17 occurrences)

- `src/Storefront/Framework/Routing/DomainLoader.php:60`: `CONCAT(TRIM(TRAILING \'/\' FROM domain.url), \'/\') url`
  - PostgreSQL: runs unchanged in PostgreSQL, but PostgreSQL concat() skips NULL arguments (verified: concat('a',NULL,'b') = 'ab'); compare with MySQL behaviour per call site.
- `src/Core/Content/Media/Subscriber/CustomFieldsUnusedMediaSubscriber.php:65`: `CONCAT('$.', JSON_QUOTE(:field))`
  - PostgreSQL: builds a JSON path string; replace the whole expression with `->> :field`.

**for_update** (6 files, 11 occurrences)

- `src/Core/Framework/Api/OAuth/AuthCodeRepository.php:86`: `SELECT 1 FROM oauth_auth_code WHERE code_id = :codeId FOR UPDATE`
  - PostgreSQL: identical.
- `src/Core/Framework/Webhook/Outbox/WebhookOutboxStore.php:72`: `SELECT delivery_status FROM webhook_event_log WHERE id = :id FOR UPDATE`
  - PostgreSQL: identical.

**skip_locked** (2 files, 2 occurrences)

- `src/Core/Framework/Adapter/Cache/InvalidatorStorage/MySQLInvalidatorStorage.php:77`: `ORDER BY id FOR UPDATE SKIP LOCKED`
  - PostgreSQL: identical (syntax verified).
- `src/Core/Framework/Webhook/Outbox/StreamLockService.php:66`: `FOR UPDATE SKIP LOCKED`
  - PostgreSQL: identical.

**fk_checks** (1 files, 4 occurrences)

- `src/Core/System/CustomEntity/Schema/CustomEntitySchemaUpdater.php:69`: `SET FOREIGN_KEY_CHECKS = 0`
  - PostgreSQL: `SET session_replication_role = replica` (accepted by the container's role, verified; normally needs superuser) or deferrable constraints.

**at_at_var** (2 files, 7 occurrences)

- `src/Core/Framework/Adapter/Database/MySQLFactory.php:105`: `@@session.time_zone = \'+00:00\'`
  - PostgreSQL: `SET TIME ZONE 'UTC'` (verified).
- `src/Core/Framework/Adapter/Database/MySQLFactory.php:107`: `@@session.sql_mode = (SELECT REPLACE(@@sql_mode, \'ONLY_FULL_GROUP_BY\'`
  - PostgreSQL: no equivalent; PostgreSQL always enforces valid GROUP BY, so queries that relied on the removed mode must be fixed.

**user_var** (1 files, 2 occurrences)

- `src/Core/System/NumberRange/ValueGenerator/Pattern/IncrementStorage/IncrementSqlStorage.php:38`: ``last_value` = @nr' . $varname . ' := IF(`last_value`+1 > :value`
  - PostgreSQL: UPDATE ... SET last_value = ... RETURNING last_value (no user variables in PostgreSQL).

**information_schema** (1 files, 1 occurrences)

- `src/Core/Maintenance/System/Service/SetupDatabaseAdapter.php:69`: `->from('information_schema.SCHEMATA')`
  - PostgreSQL: information_schema.schemata exists in PostgreSQL; or pg_database / `$schemaManager->listDatabases()`.

**show_stmt** (2 files, 3 occurrences)

- `src/Core/Maintenance/System/Service/SetupDatabaseAdapter.php:46`: `fetchFirstColumn('SHOW TABLES')`
  - PostgreSQL: `$connection->createSchemaManager()->listTableNames()` or pg_catalog.pg_tables (query verified).

**collate** (1 files, 1 occurrences)

- `src/Core/Maintenance/System/Service/SetupDatabaseAdapter.php:28`: `CHARACTER SET `utf8mb4` COLLATE `utf8mb4_unicode_ci``
  - PostgreSQL: ENCODING/LC_COLLATE options of CREATE DATABASE; `utf8mb4_unicode_ci` has no PostgreSQL equivalent name (case-insensitive comparison needs citext or a nondeterministic ICU collation).

**cast_unsigned** (1 files, 1 occurrences)

- `src/Core/Framework/Adapter/Database/MySQLFactory.php:106`: `CAST(IF(@@group_concat_max_len > 320000, @@group_concat_max_len, 320000) AS UNSIGNED)`
  - PostgreSQL: no unsigned types; use bigint/integer. The statement itself is MySQL session setup and has no PostgreSQL counterpart.

**multi_table_dml** (4 files, 4 occurrences)

- `src/Core/Framework/Log/ScheduledTask/LogCleanupTaskHandler.php:49`: `DELETE ld FROM `log_entry` ld LEFT JOIN (`
  - PostgreSQL: DELETE FROM log_entry ld USING (...) x WHERE ... (shape verified); a LEFT JOIN anti-join becomes NOT EXISTS.
- `src/Core/Content/Product/Stock/StockStorage.php:104`: `UPDATE product`
  - PostgreSQL: UPDATE product SET ... FROM product parent WHERE ... (shape verified); the LEFT JOIN on line 105 needs a rewrite to a subquery.

**truncate** (3 files, 3 occurrences)

- `src/Elasticsearch/Framework/Command/ElasticsearchResetCommand.php:62`: `TRUNCATE elasticsearch_index_task`
  - PostgreSQL: identical; PostgreSQL also refuses to truncate a table referenced by foreign keys unless CASCADE is given.

**rand_fn** (2 files, 3 occurrences)

- `src/Core/Framework/Demodata/Generator/CustomFieldGenerator.php:221`: `ORDER BY rand() LIMIT %d`
  - PostgreSQL: ORDER BY random() (verified).

**null_safe_eq** (1 files, 1 occurrences)

- `src/Core/Content/Product/DataAbstractionLayer/ProductDescriptionTeaserIndexer.php:68`: `AND NOT (description <=> description_teaser)`
  - PostgreSQL: description IS DISTINCT FROM description_teaser (verified).

**misc_fns** (2 files, 6 occurrences)

- `src/Core/Content/Product/DataAbstractionLayer/VariantListingUpdater.php:59`: `SHA2(HEX(product.parent_id), 256)`
  - PostgreSQL: encode(sha256(convert_to(<hex string>,'UTF8')),'hex') (verified); the hashed input must be identical to keep display_group values stable.

**ddl_keywords** (2 files, 4 occurrences)

- `src/Core/Checkout/Cart/Command/CartMigrateCommand.php:95`: `cart.auto_increment > :lastId`
  - PostgreSQL: a column named auto_increment (not DDL); the schema decision for how it is generated is separate (PostgreSQL: identity column).

**uuid_fromHexToBytes** (187 files, 496 occurrences)

- `src/Storefront/Theme/Mail/MailThemeIdLoader.php:27`: `Uuid::fromHexToBytes($salesChannelId)`
  - PostgreSQL: if ids become native uuid, bind the hex/dashed string directly; if they stay bytea, keep the helper.

**uuid_fromBytesToHex** (44 files, 73 occurrences)

- `src/Administration/Controller/AdministrationController.php:417`: `array_map(Uuid::fromBytesToHex(...), $rows)`
  - PostgreSQL: not needed when the driver returns uuid as string.

**uuid_randomBytes** (26 files, 42 occurrences)

- `src/Core/Framework/Webhook/Outbox/WebhookOutboxStore.php:517`: `'id' => Uuid::randomBytes()`
  - PostgreSQL: generate a string uuid in PHP or let PostgreSQL 18 `uuidv7()` do it.

**array_param_binary** (89 files, 162 occurrences)

- `src/Core/Checkout/Customer/SalesChannel/MergeWishlistProductRoute.php:165`: `ArrayParameterType::BINARY`
  - PostgreSQL: with uuid columns use ArrayParameterType::STRING and cast `= ANY(:ids::uuid[])` style; with bytea the binary type stays.

**multi_insert_queue** (9 files, 10 occurrences)

- `src/Core/System/SystemConfig/SystemConfigService.php:263`: `new MultiInsertQueryQueue($this->connection, 100, false, true)`
  - PostgreSQL: class lives under the DAL path (excluded here) and emits INSERT IGNORE / ON DUPLICATE KEY; must be ported there once.

**retryable** (41 files, 76 occurrences)

- `src/Core/Content/Product/DataAbstractionLayer/VariantListingUpdater.php:57`: `new RetryableQuery(`
  - PostgreSQL: retries on deadlock/lock-wait exceptions; the exception classes it checks must cover PostgreSQL SQLSTATE 40P01/40001.

**qb_calls** (58 files, 95 occurrences)

- `src/Administration/Dashboard/OrderAmountService.php:33`: `$this->connection->createQueryBuilder()`
  - PostgreSQL: DBAL builder emits platform-specific quoting automatically, but the strings fed into it (see its select() above) are raw.

**Constructs with zero hits in scope** (the script found none; for the first eleven of them a plain-text grep over the same in-scope files, run without the string/comment filter, found no SQL either, only prose such as "against" in comments and a config key named `regexp`; the rest were checked by the script only): `json_arrow`, `limit_offset_comma`, `date_add`, `unix_timestamp`, `concat_ws`, `find_in_set`, `regexp`, `match_against`, `last_insert_id`, `lock_in_share`, `straight_join`, `index_hint`, `cast_char_binary`, `substring_index`, `insert_set`, `table_maint`, `sql_calc_found_rows`, `date_part_fns`, `cast_datetime`, `div_mod_kw`.


How PostgreSQL equivalents were checked: statements marked "verified" were run against the phase-0 PostgreSQL 18.7 container (`instance-postgres-1`, see `docs/03-environment.md`) with literal values only (SELECTs, plus a session-local TEMP table for the upsert/DELETE USING/UPDATE FROM shapes; nothing persisted). Equivalents without "verified" are standard PostgreSQL but were not executed. I did not run anything against MySQL/MariaDB, so statements about MySQL behaviour come from reading the PHP code only. `vendor/` is not installed in the checkout, so DBAL 4.4 API names mentioned below (constraint `~4.4.0` from `composer.json`) were not checked in the library source.

### (e) Classification

| construct | class | reasoning |
|---|---|---|
| `backtick_ident` | needs a dialect helper | 1434 hardcoded quotes in SQL text. DBAL's identifier quoting (`Connection::quoteIdentifier()`) emits the right quote per platform, but the strings are literals, so each must be rewritten once. Many are optional: unquoted lower-case snake_case works in both databases; quoting only matters for reserved words. Mechanical, high volume. |
| `hex_fn`, `lower_hex`, `unhex_fn`, `Uuid::fromHexToBytes`, `fromBytesToHex`, `randomBytes`, `ArrayParameterType::BINARY` | needs a dialect helper (decision-dependent) | All follow from the id storage decision. If ids become native `uuid`, `LOWER(HEX(id))` becomes `replace(id::text,'-','')` and the PHP binary helpers become no-ops; if they stay `bytea`, `encode(id,'hex')` / `decode(...,'hex')` apply. Not available as a DBAL platform call; one SQL helper that every query goes through is the sensible shape. 187 files call `Uuid::fromHexToBytes*`, 142 files use `HEX(` and 212 files use at least one of the four PHP-side binary helpers, so this is the biggest single surface. |
| `json_fn` (JSON_EXTRACT, JSON_UNQUOTE, JSON_CONTAINS, JSON_OVERLAPS, JSON_ARRAYAGG, JSON_OBJECT, ...) | needs a rewrite of the query | Different function set and semantics (jsonpath, `->>`, `@>`, `jsonb_agg`); JSON path strings, `JSON_UNQUOTE` wrapping and JSON_OVERLAPS have no 1:1 function. Only 19 files, so a manual port is feasible. Columns must also be `jsonb` or cast. |
| `group_concat`, `group_concat_separator`, `order_by_null` | needs a dialect helper | `string_agg(expr, sep)` is a mechanical map, but the separator argument is mandatory and DISTINCT/ORDER BY rules differ. 20 files. |
| `on_dup_key`, `values_fn`, `replace_into`, `insert_ignore` (and `MultiInsertQueryQueue`, which wraps them) | needs a rewrite of the query | `ON CONFLICT` needs the conflict target columns, which are not in the SQL today (they come from the schema's unique keys); `REPLACE INTO` has no single equivalent. 18 occurrences in 15 files plus the queue class in the excluded DAL path. |
| `ifnull`, `if_fn` | needs a rewrite of the query (mechanical) | `COALESCE` and `CASE WHEN` are standard SQL and also valid in MySQL, so they can be rewritten once into the portable form without any runtime helper. `ifnull`: 12 files, 63 occurrences; `if_fn`: 10 files, 10 occurrences. |
| `now_fn`, `for_update`, `skip_locked`, `truncate`, `information_schema`, `concat_fn` | portable (runs unchanged) | Identical or compatible syntax in PostgreSQL (`now()`, `FOR UPDATE SKIP LOCKED`, `TRUNCATE` verified). Caveat for `concat_fn`: PostgreSQL `concat()` skips NULL arguments (verified), so check each call. `TRUNCATE` needs CASCADE for FK-referenced tables. |
| `show_stmt` | portable via DBAL platform API | schema-manager table listing (`createSchemaManager()->listTableNames()` in DBAL 4) instead of `SHOW TABLES`. 3 hits in 2 files, one of them test infrastructure. |
| `date_format`, `date_sub`, `interval_kw`, `date_diff_fns` (CONVERT_TZ, CURDATE) | needs a dialect helper | `to_char`, `make_interval`, `AT TIME ZONE`, `CURRENT_DATE`. Only 2 files (5 occurrences); time-zone argument semantics differ. |
| `rand_fn`, `null_safe_eq`, `misc_fns` (SHA2) | needs a dialect helper | `random()`, `IS [NOT] DISTINCT FROM`, `sha256`. Few occurrences. |
| `multi_table_dml` | needs a rewrite of the query | `DELETE alias FROM ... JOIN` and `UPDATE ... JOIN` become `DELETE ... USING` / `UPDATE ... FROM`; LEFT JOIN semantics must be re-expressed. 4 files. |
| `at_at_var`, `fk_checks`, `collate`, `cast_unsigned`, `user_var`, `ddl_keywords` | needs a rewrite of the query (or removal) | Session setup in `MySQLFactory` (time zone, `group_concat_max_len`, dropping `ONLY_FULL_GROUP_BY`), FK-check toggling, `CREATE DATABASE ... COLLATE`, user variables for the number-range increment, and `auto_increment` columns have no direct counterpart. All in a handful of infrastructure files. The `ONLY_FULL_GROUP_BY` removal means MySQL-accepted GROUP BY queries exist that PostgreSQL will reject; the scan cannot find those. |
| `RetryableQuery` / `RetryableTransaction` | needs a dialect helper | 41 files use them. They are PHP wrappers around deadlock retries; they stay, but the exception classification must recognise PostgreSQL deadlock/serialization errors. |
| `qb_calls`, `exec_calls`, `raw_sql_literals` | metric only | Show where SQL is built; QueryBuilder output is only portable if the fragments passed in are. |

### (f) Regex limitations

Over-counting (verified while sampling):
- Matches are made inside any PHP string literal, not only SQL. Seen: `MD5()/SHA1()` in a PHPStan error message (`src/Core/DevOps/StaticAnalyze/PHPStan/Rules/NoLegacySqlHashFunctionRule.php:66`) counted under `misc_fns`; its backticks counted under `backtick_ident`. Earlier drafts of the patterns also hit prose ("version field (%s)", "rand(30-300)", "UUID (see ...)", a config key named `regexp`); those patterns were tightened, but similar prose in other strings can still match, in particular `IF(` and `FIELD(`-style keywords inside messages.
- `hex_fn` includes every `LOWER(HEX(`; `lower_hex` is its subset. Totals exclude `lower_hex`.
- `at_at_var` counts each `@@name` token, so one `MySQLFactory` statement yields several hits.
- `ddl_keywords` hits are columns named `auto_increment`, not DDL.
- `multi_table_dml` for UPDATE...JOIN spans lines and is reported at the line of the `UPDATE`.
- `interval_kw` and `date_diff_fns` can both fire on one expression (`DATE_SUB(CURDATE(), INTERVAL ...)`).
- Test and demodata code that lives under `src/` is counted.

Under-counting:
- SQL assembled across several string literals or with variables (`'... ' . $x . ' ...'`) is scanned fragment by fragment, so a construct split across two fragments is missed. One case is patched specially (`@nr` at the end of a fragment for user variables).
- SQL built by the DBAL QueryBuilder from non-literal values, constants, `sprintf` arguments or class constants is invisible; SQL stored in `.sql` files or non-PHP resources is not scanned.
- Heredoc/nowdoc handling is a simplified tokenizer: a malformed or unusual PHP construct could mis-split strings. Comments are removed with the same tokenizer; `#[` attributes are kept as code.
- `multi_table_dml` is case-sensitive (uppercase `DELETE`/`UPDATE`/`JOIN`), so lower-case multi-table DML is missed.
- Standard-SQL features that differ at runtime cannot be seen at all: GROUP BY on non-aggregated columns (MySQL mode is relaxed), implicit type coercions, case-insensitive default collation on string comparison, `LIKE` case folding, zero dates, silent truncation, integer division, boolean-as-int comparisons, `LIMIT` inside subqueries. The `collate` count therefore says nothing about how many comparisons rely on case-insensitive collation.
- `->`/`->>` JSON operators: pattern requires a quoted `$` path right after the arrow; none found, but a path passed as a bound parameter would be missed.
- Scope: only files matching the scope rule in the header are scanned. Files that execute SQL purely through other services (for example the DAL, excluded) are not in scope by design. `executes_sql_no_connection_import` relies on method names (`fetchOne`, `executeStatement`, `prepare`, ...), which can also match non-DBAL objects with the same method names.
- `raw_sql_literals` counts literals that begin with a SQL verb and contain a keyword or parameter; fragment strings (`' AND ...'`) are not counted, so it under-counts raw statements.
