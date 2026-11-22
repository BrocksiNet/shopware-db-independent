# Plugin SQL inventory: how much MySQL-specific SQL do store plugins contain

## Question

Shopware 6 extensions run their own SQL through DBAL.
If core becomes database independent (MySQL, MariaDB, PostgreSQL, SQLite), how many store plugins would break or need the translator shim?
This document measures it on the public store plugin mirror.

## Method

The scanner is `scripts/plugin-sql-scan.py`.
It imports the tokenizer and the SQL and PHP regex lists from `docs/inventory/raw-sql/scan.py` and does not change them.
It runs over every PHP file of every plugin, skipping `vendor/`, `node_modules/`, `.git` and test directories, and files above 3 MB.
The tokenizer separates comments, string literals and code, so SQL-like words in comments are not counted.
A file counts as "touching the database" if it has a strict DBAL execute call, a QueryBuilder call, or a connection reference together with loose execute calls or SQL string literals.
Migration classes alone do not count, because many are empty.
Each SQL hit is classified as handled, partly handled or unhandled by the translator shim in `instance/src/Core/Framework/Adapter/Database/PostgreSQL/`.
The rule follows the shim sources:

- Handled: backticks, `<=>`, `0x` hex literals, double-quoted string literals, REGEXP, CAST AS UNSIGNED, GROUP_CONCAT SEPARATOR, most JSON functions, `@@foreign_key_checks` and similar, `ON DUPLICATE KEY`, `INSERT IGNORE`, `REPLACE INTO`, `INSERT ... SET`, `UPDATE ... JOIN`, `DELETE ... LIMIT`, multi-table DELETE, the functions in `mysql-compat.sql`, and the DDL rewrites (ENGINE, AUTO_INCREMENT, UNSIGNED, MODIFY/CHANGE, AFTER/FIRST, COLLATE utf8mb4).
- Partly handled: SHOW (only COLUMNS, INDEX, TABLES), information_schema (only columns and tables, only in the unquoted form), JSON functions without a compat function.
- No rule: everything else, for example `TIMESTAMPDIFF`, `DATEDIFF`, `YEAR()`, `FIND_IN_SET`, `FIELD`, user variables.

Hits of constructs that are also valid or nearly valid on PostgreSQL (NOW, CONCAT, FOR UPDATE, TRUNCATE, INTERVAL, `AS DATETIME)`) are tracked but do not count as MySQL-specific in the totals.
JSON_ARRAYAGG and JSON_VALUE count as native (PostgreSQL 17 and later).

Bucket priority, first match wins:

1. a: no PHP file.
2. b: no raw SQL, no `.sql` file, no direct mysqli use.
3. e: at least one hit without a shim rule.
4. d: at least one MySQL-only DDL marker (BINARY(16), ENGINE, CHARSET, COLLATE, UNSIGNED, AFTER, JSON CHECK and so on).
5. c: at least one construct the shim handles, or a binary uuid helper (`Uuid::fromHexToBytes` and friends).
6. c0: raw SQL, but no MySQL-specific construct found.

## Snapshot

The input is the mirror at commit `85ee954d70` of 2026-10-02, read only.
It holds 3,747 plugins (`plugins/shopware6/plugin`) and 625 apps (`plugins/shopware6/app`).
3,738 plugins have PHP files outside `vendor/`, with 105,802 PHP files scanned.
233 plugins bundle `vendor/` PHP (74,969 files, not scanned), 12 of them include doctrine.
6 plugins have encoded files (26 files, for example ionCube) that cannot be scanned.
1 file was above the size limit.
The scan found 40,258 SQL strings (1,980 plugins) and 17,808 DDL strings (1,472 plugins).
15,597 PHP files in 2,043 plugins touch the database with raw SQL or QueryBuilder.

### Apps are out of scope

The 625 apps contain 0 `.php` files and 0 `.sql` files, and all have a `manifest.xml`.
154 apps have `Resources/scripts` (807 script files); none contains SQL-like text.
No `INSERT INTO`, `DELETE FROM`, `CREATE TABLE` or `ON DUPLICATE KEY` appears in any app js, json, xml or twig file.
In the instance trunk only 2 of 35 `*Facade*.php` files reference DBAL (`SystemConfigFacade`, `SystemConfigFacadeHookFactory`, typed system config accessors), so app scripts get no raw SQL.
Apps are therefore not affected by the database engine.

## Buckets

| Bucket | Plugins | Share |
|---|---|---|
| a. no PHP (app-like) | 9 | 0.2 % |
| b. PHP, no raw SQL | 1,692 | 45.2 % |
| c0. raw SQL, no MySQL-specific construct found | 93 | 2.5 % |
| c. raw SQL, constructs the shim handles | 477 | 12.7 % |
| d. MySQL-only DDL, otherwise as c | 1,122 | 29.9 % |
| e. constructs without a shim rule | 354 | 9.4 % |

Details behind the buckets:

- b splits into 856 plugins that use only the DAL and 836 with neither DAL nor SQL.
- c: 46 of the 477 qualify only through binary uuid helpers, which is a "likely fine" call (see limits).
- d: 1,091 of 1,122 have migration classes, 31 do not (for example SwagAboCommerce, with legacy `Bootstrap/Database.php` DDL).
- e: 159 plugins have an unhandled information_schema use, 136 of the 354 have only information_schema or the update-join `;` problem.
- 2,045 plugins (54.6 %) contain raw SQL (c0, c, d, e together).
- 1,903 plugins have at least one MySQL-specific hit outside the weak set.

## Constructs

Plugins affected per construct.
A plugin counts once per construct, hits are all occurrences.

| Construct | Plugins | Share | Hits | Shim rule |
|---|---|---|---|---|
| backtick_ident | 1756 | 46.9 % | 215643 | shim |
| hex_fn | 632 | 16.9 % | 5961 | shim |
| lower_hex | 569 | 15.2 % | 5050 | shim |
| json_fn | 513 | 13.7 % | 3724 | partly |
| dq_string_literal | 423 | 11.3 % | 6423 | shim |
| unhex_fn | 337 | 9.0 % | 4747 | shim |
| now_fn | 271 | 7.2 % | 1994 | shim |
| show_stmt | 263 | 7.0 % | 663 | partly |
| information_schema | 258 | 6.9 % | 1068 | partly |
| multi_table_dml | 209 | 5.6 % | 508 | shim |
| insert_ignore | 205 | 5.5 % | 2612 | shim |
| on_dup_key | 152 | 4.1 % | 391 | shim |
| concat_fn | 122 | 3.3 % | 388 | shim |
| ifnull | 102 | 2.7 % | 519 | shim |
| fk_checks | 100 | 2.7 % | 556 | shim |
| if_fn | 97 | 2.6 % | 570 | shim |
| interval_kw | 91 | 2.4 % | 354 | shim |
| values_fn | 79 | 2.1 % | 666 | shim |
| date_diff_fns | 77 | 2.1 % | 731 | no rule |
| group_concat | 67 | 1.8 % | 155 | shim |
| date_sub | 65 | 1.7 % | 218 | shim |
| hex_literal_0x | 62 | 1.7 % | 81681 | shim |
| truncate | 56 | 1.5 % | 115 | shim |
| group_concat_separator | 45 | 1.2 % | 124 | shim |
| date_format | 41 | 1.1 % | 163 | shim |
| uuid_fn | 40 | 1.1 % | 68 | shim |
| misc_fns | 33 | 0.9 % | 167 | no rule |
| null_safe_eq | 32 | 0.9 % | 71 | shim |
| replace_into | 27 | 0.7 % | 45 | shim |
| cast_unsigned | 25 | 0.7 % | 54 | shim |
| user_var | 23 | 0.6 % | 123 | no rule |
| date_part_fns | 23 | 0.6 % | 192 | no rule |
| for_update | 22 | 0.6 % | 60 | shim |
| date_add | 20 | 0.5 % | 153 | shim |
| regexp | 18 | 0.5 % | 27 | shim |
| table_maint | 17 | 0.5 % | 45 | no rule |
| cast_char_binary | 16 | 0.4 % | 25 | no rule |
| at_at_var | 16 | 0.4 % | 43 | partly |
| substring_index | 12 | 0.3 % | 27 | shim |
| concat_ws | 12 | 0.3 % | 17 | shim |
| limit_offset_comma | 11 | 0.3 % | 26 | no rule |
| sql_calc_found_rows | 10 | 0.3 % | 44 | no rule |
| rand_fn | 10 | 0.3 % | 75 | shim |
| collate | 10 | 0.3 % | 34 | partly |
| insert_set | 8 | 0.2 % | 12 | shim |
| unix_timestamp | 7 | 0.2 % | 24 | no rule |
| field_fn | 6 | 0.2 % | 9 | no rule |
| find_in_set | 4 | 0.1 % | 5 | no rule |
| straight_join | 3 | 0.1 % | 4 | no rule |
| skip_locked | 2 | 0.1 % | 2 | shim |
| match_against | 2 | 0.1 % | 3 | no rule |
| div_mod_kw | 2 | 0.1 % | 10 | no rule |
| order_by_null | 1 | 0.0 % | 5 | shim |
| lock_in_share | 1 | 0.0 % | 1 | no rule |
| last_insert_id | 1 | 0.0 % | 2 | no rule |
| index_hint | 1 | 0.0 % | 2 | no rule |

Unhandled information_schema use, by view:

| View | Plugins |
|---|---|
| statistics | 81 |
| table_constraints | 71 |
| key_column_usage | 41 |
| quoted `information_schema`.`COLUMNS` | 16 |
| referential_constraints | 16 |
| quoted `information_schema`.`TABLES` | 10 |

JSON functions:

| Function | Plugins | Hits | Shim rule |
|---|---|---|---|
| JSON_EXTRACT | 216 | 1231 | shim |
| JSON_VALID | 204 | 660 | shim |
| JSON_REMOVE | 146 | 249 | shim |
| JSON_UNQUOTE | 132 | 691 | shim |
| JSON_SET | 81 | 169 | shim |
| JSON_CONTAINS_PATH | 46 | 81 | shim |
| JSON_ARRAY | 41 | 84 | shim |
| JSON_OBJECT | 38 | 189 | shim |
| JSON_CONTAINS | 24 | 62 | shim |
| JSON_OVERLAPS | 23 | 29 | no rule |
| JSON_LENGTH | 19 | 29 | shim |
| JSON_MERGE_PATCH | 14 | 31 | no rule |
| JSON_QUOTE | 13 | 30 | shim |
| JSON_TYPE | 12 | 25 | shim |

Binary uuid helpers (`Uuid::fromHexToBytes` and friends) are used by 980 plugins, all raw-SQL plugins.
`fromHexToBytes` appears 8,249 times in 757 plugins, `fromBytesToHex` 1,005 times in 288, `randomBytes` 2,206 times in 439, binary array parameters 1,911 times in 291.

Plugins by unhandled kind in bucket e (a plugin can have several):

| Kind | Plugins |
|---|---|
| information_schema (unquoted unsupported views) | 219 |
| date_diff_fns | 77 |
| json (no rule) | 77 |
| update_join_trailing_semicolon | 49 |
| information_schema, quoted | 26 |
| user_var | 23 |
| date_part_fns | 22 |
| misc_fns | 17 |
| table_maint | 17 |
| cast_char_binary | 16 |

## Top 30 plugins by MySQL-specific hits

Ranked by `mysql_specific_total`.
Backticks dominate most counts, so the table also shows the count without them.
DvsnShield is an outlier because of 80,553 `0x` hex literals.

| Rank | Plugin | MySQL-specific hits | Without backticks | Unhandled hits | Bucket |
|---|---|---|---|---|---|
| 1 | DvsnShield | 82158 | 80819 | 124 | e |
| 2 | P2LabStockly | 18178 | 2456 | 255 | e |
| 3 | SwagCommercial | 6825 | 670 | 24 | e |
| 4 | TonurJUNUX | 6770 | 1748 | 21 | e |
| 5 | PickwareErpStarter | 6437 | 510 | 78 | e |
| 6 | sc_AdminPowerToolsSearchMerchandising | 3041 | 233 | 5 | e |
| 7 | SwagB2bPlatform | 3003 | 740 | 50 | e |
| 8 | CogiIndividualBanner | 2484 | 123 | 17 | e |
| 9 | EmzConvertly | 1925 | 160 | 14 | e |
| 10 | CogiCommander | 1918 | 614 | 32 | e |
| 11 | CbaxModulAnalytics | 1764 | 385 | 46 | e |
| 12 | DvsnGiftRegistry | 1667 | 109 | 13 | e |
| 13 | Neon6Configurator | 1461 | 70 | 5 | e |
| 14 | NetiNextEasyCoupon | 1424 | 119 | 9 | e |
| 15 | SwagDigitalSalesRooms | 1362 | 569 | 1 | e |
| 16 | AcrisSearchCS | 1351 | 66 | 1 | e |
| 17 | AppflixDewaShop | 1346 | 45 | 0 | d |
| 18 | CogiTranslator | 1327 | 117 | 8 | e |
| 19 | PixelCanvasdesignersw6 | 1291 | 21 | 2 | e |
| 20 | FelOAIAssistantsManager | 1112 | 36 | 5 | e |
| 21 | LoyxxSW6SeoFaqManager | 1070 | 7 | 1 | e |
| 22 | ApplifactionDpdShipping | 1054 | 53 | 3 | e |
| 23 | SynGoogleShopping | 1047 | 183 | 23 | e |
| 24 | AcrisB2bCS | 1046 | 67 | 0 | d |
| 25 | CwkPostPurchaseUpsell | 1039 | 127 | 9 | e |
| 26 | P2LabStats | 1037 | 695 | 85 | e |
| 27 | DvsnProjectManager | 1003 | 62 | 5 | e |
| 28 | DreiscSeoPro | 989 | 257 | 2 | e |
| 29 | WotippsStatisticExpert | 980 | 101 | 63 | e |
| 30 | PixupWishlistSW6 | 911 | 87 | 46 | e |

## Migration DDL numbers

- 9,420 migration classes in 1,531 plugins.
- 8,979 classes with SQL in 1,508 plugins.
- 7,366 classes with DDL in 1,370 plugins.
- 7,505 classes with MySQL-only DDL in 1,389 plugins (higher than the DDL count because DDL fragments in strings are included).
- 386 classes with unhandled DML in 197 plugins.
- 17,808 DDL strings in 1,472 plugins, 9,064 files with DDL.

Of the 1,531 plugins with migration classes, 1,091 are in bucket d, 313 in e, 117 in c, 5 in c0, 5 in b.

| DDL marker | Plugins | Hits |
|---|---|---|
| ddl_binary16 | 1376 | 16720 |
| ddl_engine | 1364 | 5757 |
| ddl_charset | 1378 | 5942 |
| ddl_collate | 1355 | 7595 |
| ddl_auto_increment | 90 | 447 |
| ddl_unsigned | 181 | 826 |
| ddl_alter_modify_change | 321 | 1687 |
| ddl_on_update_ts | 17 | 40 |
| ddl_json_check | 202 | 631 |
| ddl_after_first | 492 | 2301 |
| ddl_backtick | 1496 | 297860 |
| ddl_inline_key | 127 | 488 |
| ddl_fulltext | 5 | 8 |
| ddl_drop_fk_index | 226 | 761 |
| ddl_mysql_types | 1372 | 17026 |

The DDL markers are what the DdlRewriter targets.
BINARY(16) ids (1,376 plugins) are the largest single item.
On PostgreSQL the shim maps them to uuid, which only works if plugin code and DAL agree on the id codec.

## Verified shim limits

These come from a scratch PostgreSQL 18.7 database (created and dropped, the `shopware` database was not touched).
72 whole statements sampled from real plugin SQL (30 bucket c, 30 bucket e files, 12 DDL) were run through the translator and rewriters, then prepared and executed in a rolled-back transaction.

- Statements without unhandled constructs: 38 of 48 ran.
- The 10 failures are mostly harness artifacts (text columns auto-created by the harness versus bytea, JSON on text, primary key stubs, an SQL fragment).
- DDL: 8 of 12 ran, the 4 failures need tables missing in the scratch database and are inconclusive.
- Real failures confirmed: `UPDATE ... JOIN` with a trailing `;` produces invalid SQL (`; FROM ...`), backtick-quoted `information_schema`.`COLUMNS` is not rewritten, `JSON_MERGE_PATCH` and `FIELD` are undefined, `information_schema.STATISTICS` does not exist.
- `information_schema.table_constraints` and `key_column_usage` run, but `table_schema` is `public` while `DATABASE()` returns the database name, so `TABLE_SCHEMA = DATABASE()` guards match no rows without error.
- Direct function probes on PostgreSQL 18.7 failed with 42883 for CURDATE, UTC_TIMESTAMP, DATEDIFF, YEAR, WEEKDAY, UNIX_TIMESTAMP, FIND_IN_SET, FIELD, JSON_OVERLAPS, JSON_MERGE_PATCH, LOCATE and INSTR.
- `TIMESTAMPDIFF` fails with a syntax error.
- JSON_ARRAYAGG, JSON_VALUE and MD5 work natively.
- Double-quoted literals and `0x` ids translate correctly (`like "x"` becomes `like 'x'`, `0x24ee...` becomes `'24ee...'::uuid`).

The update-join semicolon problem affects 49 plugins and is a shim bug, not a core issue.

## Hand checks

36 plugins were read by hand, independent of the scanner output.

- a, 3 of 3 correct: MolliePaymentsApp, mediameetsBannerApp, mediameetsCustomCssJsApp (0 PHP files, one manifest.xml each).
- b, 7 of 7 correct: SsikLibertyTheme, WebvDeactivateRegistration, CrehlerBaseLinkerShopsApi, ElioBatteryIncludedSearchExtension, CnkPlatformCustomFieldDetailPage, TabtenTemplateEnokiSW6, NenoCategoryH1 (grep found no raw SQL; two only import `Doctrine\DBAL\Connection` without queries).
- c0 and c, first pass 5 of 7 correct: ICTECHPromoCouponCart, ICTECHOdooShopwareConnector, CompraClearCommitDataSW6, BrandCrockSearchTrends, BrandCrockSubcategoryNav were right.
  UltraBreadcrumb and CoePaymentDueSw6 were wrong (the scanner missed `"..."` literals and `0x` hex).
  The scanner was fixed (new constructs `dq_string_literal`, `hex_literal_0x`) and both are now c.
- c, 6 of 6 correct: memoPostcodePlugin, ScaleflexCloudimage, LaudertFriendlyCaptcha, Dep24EnclosureReturnForm, AcrisOrderLineItemSortingCS, CbaxModulInstockExportAmazon.
- d, 6 of 6 correct: KzphChangelog, CodeComDynamicTabPlugin, NetiNextEasyCouponGenerator, DvsnAffiliateMlm, GshopDailyTotals (BINARY(16) DDL), SwagAboCommerce (legacy `INT(11) UNSIGNED AUTO_INCREMENT`).
- e, 7 checked, 6 confirmed and 1 corrected: BlueMediaShopwarePayment (quoted `information_schema`.`TABLES`), SwpProductOptionsSixDeepLink (TABLE_CONSTRAINTS), CwsProductAttachmentsPro and KommoraStorefrontStudio (STATISTICS), HatslogicSwAppAdminManager (`YEAR(created_at)`), SisiErrorMonitoring (`TIMESTAMPDIFF`).
  WtyGeoOptimizer: the `day(s)` prose hit was a false positive, but a real `WEEKDAY(` hit exists, so e stands.

Other false positives found and fixed in the scanner: `AS date` alias as cast, `auto_increment` as a column name, DDL fragments counted as DML, empty migration classes counted as SQL, a mysqli-only plugin in bucket b.

## Meaning for the deprecation path

- 45 % of plugins (bucket b) and 13 % more (c, c0) need no change or only what the shim already handles.
- 30 % (bucket d) differ only in migration DDL. A database-neutral migration API, or the DdlRewriter kept for migrations, covers them.
- 9.4 % (bucket e) use constructs without a shim rule, mostly information_schema (219 plugins), date functions (about 100) and JSON functions without a compat function (77).
- A public dialect service (a `SqlDialect` per database, usable by plugins) would give plugin authors a supported way to write `indexExists`, date difference and JSON overlap queries instead of the information_schema and function calls found here.
- `TABLE_SCHEMA = DATABASE()` guards on table_constraints, key_column_usage and statistics are the most common unhandled pattern, and they fail silently on PostgreSQL. A neutral schema inspection API would remove the need.
- Shim lifetime: 1,903 plugins use at least one MySQL-specific construct, so the shim needs to live as long as these plugins do. The data supports keeping it for several release cycles, with deprecation warnings, not removing it with the first release.
- A `shopware-cli` check can flag the constructs in the construct table (no-rule rows first) at extension validation time. The scanner regex list is a starting point.
- Fixing the update-join trailing semicolon, backtick-quoted information_schema, and adding compat functions for DATEDIFF, YEAR, FIND_IN_SET, FIELD, JSON_OVERLAPS and JSON_MERGE_PATCH would move a large share of bucket e into c without touching plugins.

## Limits of the method

- This is static regex matching on tokenized PHP. It reports presence of a construct, not whether a code path runs.
- SQL built by concatenation is only seen as fragments.
- SQL in non-PHP files other than `.sql` is not scanned. 33 plugins have `.sql` files.
- Test directories and `vendor/` are skipped.
- 6 plugins with encoded files cannot be scanned.
- String-level false positives from prose remain possible, for example MSSQL SQL in FirebearSapIntegration (`ISNULL`) lands in misc_fns.
- The binary uuid helper rule is a guess: whether uuid helpers alone are fine on PostgreSQL depends on the id codec and is not verified. 46 plugins in bucket c depend on it.
- Constructs hidden by harness errors in the empirical test were only verified through function probes.
- `json_arrow` (`->`, `->>`) had 0 hits.
- The 72 test statements were whole statements filtered from fragments, so the sample is biased toward complete queries.
- Counts are for the mirror snapshot and the store only, not private or customer plugins.
- Shares are shares of plugins, not of installations, and carry no weighting by popularity.
