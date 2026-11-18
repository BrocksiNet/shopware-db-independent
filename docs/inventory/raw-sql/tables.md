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
