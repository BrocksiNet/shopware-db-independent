# Shopware trunk schema inventory (MariaDB 10.11.16 install) and PostgreSQL 18 translation

Source of every number: `schema-stats.sh` (output saved in `stats-output.txt`), `mysql-to-pg-ddl.py` (output `generated-pg-schema.sql`), `pg-verify.sql` (output `pg-verify-output.txt`), plus the shell greps quoted inline.
Database: MariaDB `shopware` in `instance-database-1`, installed by `bin/console system:install`.
Source tree: `<repo>/instance` (trunk).

## a. Counts

| Item | Count | How |
|---|---:|---|
| Tables (BASE TABLE) | 250 | `information_schema.tables`; 0 views |
| Columns | 2168 | `information_schema.columns` |
| Indexes (distinct table + index name, incl. PK) | 726 | `information_schema.statistics`; all BTREE |
| of which PRIMARY / UNIQUE / non-unique | 250 / 97 / 379 | |
| Foreign keys | 418 | `referential_constraints` |
| Triggers | 0 | `information_schema.triggers` (the install runs without `BLUE_GREEN_DEPLOYMENT`, see section f) |
| Views | 0 | |
| Generated columns | 15 (4 STORED, 11 VIRTUAL) | `extra like '%GENERATED%'` |
| CHECK constraints (rows in `check_constraints`) | 376 | 374 contain `json_valid`, 2 are other |
| Distinct columns with a JSON_VALID check | 220 | MariaDB lists a column-level check and a named table-level `json.*` check separately (156 named `json.*`), so rows overcount; the count is the distinct (table, column) join |
| Fulltext indexes | 0 | |
| Columns with `ON UPDATE CURRENT_TIMESTAMP` | 1 | `sales_channel_api_context.updated_at` |
| AUTO_INCREMENT columns | 11 | see below |
| ENUM / SET columns | 0 | |

AUTO_INCREMENT columns (none of them is a uuid): `customer.auto_increment`, `order.auto_increment`, `category.auto_increment`, `product.auto_increment`, `cart.auto_increment` (bigint), `version_commit.auto_increment`, `version_commit_data.auto_increment`, `messenger_stats.id`, `messenger_messages.id`, `consent_log.id`, `webhook_delivery.id`.

The 2 non-JSON checks: `order.char_length.order.deep_link_code` = `char_length(deep_link_code) = 32`; `scheduled_task.check.scheduled_task.run_interval` = `run_interval >= 1`.

## b. Column types and proposed PostgreSQL types

The PostgreSQL column is what `mysql-to-pg-ddl.py` actually produced (read back with `format_type` from `pg_attribute`, joined per table/column), not a plan.

| MariaDB type | columns | PostgreSQL type (columns) |
|---|---:|---|
| `binary(16)` | 715 | `uuid` (715) |
| `datetime(3)` | 431 | `timestamp(3) without time zone` (431) |
| `varchar(255)` | 334 | `character varying(255)` (334) |
| `longtext` | 268 | `jsonb` (220), `text` (48) |
| `tinyint(1)` | 124 | `boolean` (124) |
| `int(11)` | 69 | `integer` (69) |
| `double` | 19 | `double precision` (19) |
| `varchar(64)` | 15 | `character varying(64)` (15) |
| `varchar(500)` | 14 | `character varying(500)` (14) |
| `varchar(50)` | 13 | `character varying(50)` (13) |
| `varchar(32)` | 13 | `character varying(32)` (13) |
| `mediumtext` | 12 | `text` (12) |
| `tinyint(1) unsigned` | 12 | `boolean` (12) |
| `varchar(100)` | 10 | `character varying(100)` (10) |
| `longblob` | 8 | `bytea` (8) |
| `datetime` | 8 | `timestamp(0) without time zone` (8) |
| `bigint(20) unsigned` | 7 | `bigint` (7) |
| `int(11) unsigned` | 7 | `bigint` (7) |
| `varchar(20)` | 7 | `character varying(20)` (7) |
| `varchar(1024)` | 6 | `character varying(1024)` (6) |
| `int(10) unsigned` | 6 | `bigint` (6) |
| `text` | 5 | `text` (5) |
| `varchar(2048)` | 5 | `character varying(2048)` (5) |
| `date` | 4 | `date` (4) |
| `bigint(20)` | 4 | `bigint` (4) |
| `decimal(10,3) unsigned` | 4 | `numeric(10,3)` (4) |
| `mediumblob` | 3 | `bytea` (3) |
| `int(8)` | 3 | `integer` (3) |
| `tinyint(4)` | 3 | `smallint` (3) |
| `varchar(512)` | 3 | `character varying(512)` (3) |
| `float` | 3 | `real` (3) |
| `varchar(750)` | 3 | `character varying(750)` (3) |
| `timestamp(6)` | 2 | `timestamp(6) without time zone` (2) |
| `varchar(254)` | 2 | `character varying(254)` (2) |
| `varchar(45)` | 2 | `character varying(45)` (2) |
| `varchar(80)` | 2 | `character varying(80)` (2) |
| `int(3)` | 2 | `integer` (2) |
| `smallint(6)` | 2 | `smallint` (2) |
| `varchar(70)` | 2 | `character varying(70)` (2) |
| `varchar(40)` | 2 | `character varying(40)` (2) |
| `int(5)` | 1 | `integer` (1) |
| `char(3)` | 1 | `character(3)` (1) |
| `decimal(10,3)` | 1 | `numeric(10,3)` (1) |
| `varchar(3)` | 1 | `character varying(3)` (1) |
| `varchar(5000)` | 1 | `character varying(5000)` (1) |
| `varchar(4096)` | 1 | `character varying(4096)` (1) |
| `double(10,3)` | 1 | `double precision` (1) |
| `char(32)` | 1 | `character(32)` (1) |
| `varchar(190)` | 1 | `character varying(190)` (1) |
| `varchar(127)` | 1 | `character varying(127)` (1) |
| `tinyint(3) unsigned` | 1 | `smallint` (1) |
| `decimal(11,4) unsigned` | 1 | `numeric(11,4)` (1) |
| `decimal(15,6) unsigned` | 1 | `numeric(15,6)` (1) |
| `int(1) unsigned` | 1 | `bigint` (1) |

### BINARY(16)

715 columns. By name: 691 are `id` or end in `_id` (primary keys, foreign keys, `version_id`, `*_version_id`), 24 are not:

| Columns | Count | What they are |
|---|---:|---|
| `product.deliveryTime, tax, manufacturer, cover, unit, media, prices, visibilities, properties, categories, translations, tags, crossSellings, featureSet, customFieldSets, canonicalProduct, cmsPage, mainCategories, openGraphMedia, guaranteeTermsMedia` | 20 | Inheritance marker columns, nullable `binary(16)`, camelCase names, created by `InheritanceUpdaterTrait::updateInheritance` (`src/Core/Framework/Migration/InheritanceUpdaterTrait.php:11-20`, e.g. `Migration1774345867AddProductOpenGraphFields.php:64`). `InheritanceUpdater.php:85-93` writes `IFNULL(...id...)` into them, i.e. they hold ids. No data in the install (0 products), so the content could not be checked. |
| `seo_url.foreign_key` | 1 | Generic foreign key to any entity id (part of unique index `uniq.seo_url.foreign_key`); not a real FK |
| `category_translation.internal_link` | 1 | `IdField` in `CategoryTranslationDefinition.php:67` |
| `webhook_delivery.partition_key`, `webhook_stream.partition_key` | 2 | Used in `WebhookOutboxStore.php:121,498,514` as a partition identifier; value format not verified (tables are empty), see open questions |

No BINARY(16) column holds a hash in this schema. All 715 were mapped to `uuid`. Hashes are stored elsewhere as `varchar` (`customer.hash`, `newsletter_recipient.hash`, `media.file_hash` generated `varchar(32)`, `payment_token.token` `char(32)`).
Other fixed binary defaults: 15 `*version_id` columns have `DEFAULT <live version>`. `information_schema.column_default` returns those 16 bytes mangled by the charset conversion (`'???jK¾K??u,4%'`), so the generator hard-codes `Defaults::LIVE_VERSION` (`src/Core/Defaults.php:20` = `0fa91ce3e96a4bc2be4bd9ce752c3425`) for every `binary(16)` default; it refuses to do so unless the column name ends in `version_id` (all 15 do).

### Other binary types

No `binary(n)` other than 16, no `varbinary`. BLOB columns (11, mapped to `bytea`):

| Column | Type |
|---|---|
| `app_script_condition.constraints`, `cart.payload`, `flow.payload`, `media.media_type`, `media.thumbnails_ro`, `media_folder_configuration.media_thumbnail_sizes_ro`, `rule.payload`, `webhook_event_log.serialized_webhook_message` | longblob (8) |
| `app.icon`, `app_flow_action.icon`, `plugin.icon` | mediumblob (3) |

`cart.payload`, `rule.payload`, `flow.payload`, `media.*_ro` hold PHP-serialised data, not JSON (not verified per column; classification by name, see open questions).

### JSON

MariaDB has no native JSON type: JSON is `longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin` plus `CHECK (json_valid(col))`. 220 columns carry the check: 218 with `utf8mb4_bin`, 2 with `utf8mb4_unicode_ci` (`mail_template_type.available_entities`, `product_stream_filter.parameters`). The 218 `utf8mb4_bin` columns are exactly the 218 `longtext`+`utf8mb4_bin` columns in the schema. Remaining `longtext` (268 total) = 48 plain text. All 220 mapped to `jsonb`; the 220 JSON_VALID checks are dropped (the type replaces them). Caveats of `jsonb` vs MariaDB text: key order is not preserved, duplicate keys collapse, number formatting is normalised (`1.0`, big ints), `\u0000` is rejected. If byte-exact round trip matters use `json` instead (no operators for indexing, but generated columns below work with `->>` on both).

### Booleans, dates, numbers

- `tinyint(1)` 124 and `tinyint(1) unsigned` 12 -> `boolean` (136; PG verify shows 136). Defaults 0/1 become `false`/`true`. `tinyint(4)` 3 and `tinyint(3) unsigned` 1 -> `smallint`; `product.active` is `tinyint(3) unsigned` and a nullable column, and `shipping_method_price.calculation` is `int(1) unsigned` -> `bigint`.
- Unsigned integers: `int(11) unsigned` 7, `int(10) unsigned` 6, `int(1) unsigned` 1 -> `bigint`; `bigint(20) unsigned` 7 -> `bigint` (loses range above 2^63-1; the install's uses are counters and auto-increment); `decimal(...) unsigned` 6 -> `numeric(p,s)` without the unsigned guarantee. PostgreSQL has no unsigned; add `CHECK (col >= 0)` if the unsigned guarantee is required (not generated).
- `datetime(3)` 431, `datetime` (no fraction) 8, `timestamp(6)` 2 (`migration.update`, `update_destructive`) -> `timestamp(n)` without time zone. Shopware writes UTC strings (`Defaults::STORAGE_DATE_TIME_FORMAT`), so no time zone conversion is wanted. `date` 4 -> `date`.
- `double` 19 + `double(10,3)` 1 -> `double precision`; `float` 3 -> `real`; `decimal(10,3) unsigned` 4, `decimal(10,3)` 1, `decimal(11,4) unsigned` 1, `decimal(15,6) unsigned` 1 -> `numeric(p,s)`.
- Display widths (`int(11)`, `int(8)`, `int(3)`) are ignored.

## c. Collations and case-insensitive behaviour

Character set: `utf8mb4` for all 725 string columns. Collation per column (`information_schema.columns`): `utf8mb4_unicode_ci` 507, `utf8mb4_bin` 218 (all of them JSON longtext). All 250 tables have table collation `utf8mb4_unicode_ci`. The database is created with that collation (`SetupDatabaseAdapter.php:28`), and `SchemaBuilder.php:170` sets `collate utf8mb4_unicode_ci` on generated tables.

`utf8mb4_unicode_ci` is case- and accent-insensitive (`a = A = ä`) and, being a PAD SPACE collation, ignores trailing spaces in comparisons. This applies to `=`, `LIKE`, `GROUP BY`, `DISTINCT` and to UNIQUE indexes. In PostgreSQL the default deterministic collations are case-sensitive, so:

- Unique indexes on strings below would accept `EUR` and `eur` at the same time. Real consequences: `user.email`, `user.username`, `currency.iso_code`, `locale.code`, `sales_channel.access_key`, `sales_channel_domain.url`, `product.product_number` (with version), `promotion.code`, `customer.hash` etc.
- Lookups by `WHERE email = :email` are case-insensitive today (not verified against application code for every query; `Storefront/Mcp/Tool/ThemeConfigTool.php:197` documents the same reliance for `sales_channel_translation.name`).
- Options:
  1. Nondeterministic ICU collation (`CREATE COLLATION ci (provider=icu, locale='und-u-ks-level1', deterministic=false)`) on the column. This is what the prototype does for all 507 columns. Equality, unique indexes and btree indexes work; PG 18 also supports `LIKE` on nondeterministic collations (checked: `'Abc' like 'aB%' collate ci` returned `t`). Differences verified on PG 18.7: `'a' = 'a '` is false under `ci` (MariaDB PAD SPACE treats them as equal), `'é' = 'e'` is true (accent-insensitive like unicode_ci). Smoke test in `pg-verify-output.txt`: inserting `EUR` then `eur` into `currency` raises `duplicate key value violates unique constraint "currency.uniq.currency.iso_code"`.
  2. `citext` extension: not installed in the scratch database, not tested; case-insensitive only (not accent-insensitive), no collation per column, not available on all managed services. Not prototyped.
  3. `lower(col)` expression indexes: needs every query rewritten to `lower(col) = lower(:v)`; the DAL builds SQL for equals filters, so this would need DAL changes. Not prototyped.
  Recommendation for the PoC: option 1 on all `utf8mb4_unicode_ci` string columns (done), revisit only columns where performance matters.

### Unique indexes that contain a string column (all collation `utf8mb4_unicode_ci`)

Lines also include unique indexes where the string column is only one part (e.g. with `version_id`, `language_id`). Source: `stats-output.txt`.

| table | index | columns |
|---|---|---|
| app | `uniq.name` | name |
| app_action_button | `uniq.app_action_button.action` | action,app_id |
| app_feature | `uniq.app_feature.app_name_type_name` | app_name,type,name |
| app_flow_action | `uniq.app_flow_action.name` | name |
| app_flow_event | `name` | name |
| app_flow_event | `uniq.app_flow_event.name` | name |
| consent_state | `uniq.consent_state` | name,identifier |
| currency | `uniq.currency.iso_code` | iso_code |
| customer | `hash` | hash |
| custom_entity | `name` | name |
| custom_field | `uniq.custom_field.name` | name |
| custom_field_set_relation | `uniq.custom_field_set_relation.entity_name` | set_id,entity_name |
| document | `uniq.deep_link_code` | deep_link_code |
| document | `uniq.document.document_number__type_name` | document_number,type_name |
| document_file | `uniq.document_file.document_id__document_format` | document_id,document_format |
| document_type | `uniq.document_type.technical_name` | technical_name |
| import_export_profile | `uniq.import_export_profile.technical_name` | technical_name |
| invalidation_tags | `tag` | tag |
| locale | `uniq.code` | code |
| mail_template_type | `uniq.mail_template_type.technical_name` | technical_name |
| measurement_display_unit | `uniq.measurement_display_unit.short_name` | short_name |
| measurement_system | `uniq.measurement_system.technical_name` | technical_name |
| media_default_folder | `uniq.media_default_folder.entity` | entity |
| newsletter_recipient | `hash` | hash |
| number_range_type | `uniq.technical_name` | technical_name |
| oauth_auth_code | `uniq.oauth_auth_code.code_id` | code_id |
| oauth_user | `user_sub` | user_sub |
| order | `uniq.deep_link_code` | deep_link_code,version_id |
| payment_method | `uniq.technical_name` | technical_name |
| plugin | `uniq.baseClass` | base_class |
| plugin | `uniq.name` | name |
| product | `uniq.product.product_number__version_id` | product_number,version_id |
| product_export | `file_name` | file_name |
| product_keyword_dictionary | `uniq.language_id_keyword` | language_id,keyword |
| product_search_config_field | `uniq.search_config_field.field__config_id` | field,product_search_config_id |
| product_sorting | `uniq.product_sorting.url_key` | url_key |
| promotion | `code` | code |
| promotion | `individual_code_pattern` | individual_code_pattern |
| promotion_individual_code | `code` | code |
| refresh_token | `uniq.token_id` | token_id |
| sales_channel | `uniq.access_key` | access_key |
| sales_channel_domain | `uniq.sales_channel_domain.url` | url |
| sales_channel_file | `uniq.sales_channel_file.sc_id_family_file_name` | sales_channel_id,file_family,file_name |
| salutation | `uniq.salutation_key` | salutation_key |
| scheduled_task | `uniq.scheduled_task.scheduled_task_class` | scheduled_task_class |
| seo_url | `uniq.seo_url.foreign_key` | language_id,sales_channel_id,foreign_key,route_name,is_canonical |
| seo_url | `uniq.seo_url.seo_path_info` | language_id,sales_channel_id,seo_path_info |
| seo_url_template | `uniq.seo_url_template.route_name` | sales_channel_id,route_name |
| shipping_method | `uniq.technical_name` | technical_name |
| snippet | `uniq.snippet_set_id_translation_key` | snippet_set_id,translation_key |
| state_machine | `uniq.state_machine.technical_name` | technical_name |
| state_machine_state | `uniq.technical_name_state_machine` | technical_name,state_machine_id |
| state_machine_transition | `uniq.state_machine_transition.action_name_state_machine` | action_name,state_machine_id,from_state_id,to_state_id |
| system_config | `uniq.system_config.configuration_key__sales_channel_id` | configuration_key,sales_channel_id |
| tax_provider | `uniq.tax_provider.identifier` | identifier |
| tax_rule_type | `uniq.technical_name` | technical_name |
| theme | `uniq.theme.technical_name` | technical_name |
| theme_runtime_config | `uidx.technical_name` | technical_name |
| user | `uniq.user.email` | email |
| user | `uniq.user.username` | username |
| user_config | `uniq.user_id_key` | user_id,key |
| webhook | `uniq.webhook.name` | name,app_id |

## d. Triggers and generated columns

Triggers: none exist in the installed database (0 rows). `MigrationStep::createTrigger` only executes when `BLUE_GREEN_DEPLOYMENT` is non-zero (`src/Core/Framework/Migration/MigrationStep.php:69-77`); 7 migration files call it or contain `CREATE TRIGGER` (grep in `src/Core/Migration`), `BlueGreenDeploymentService.php:49-52` creates a throw-away `example_trigger` to probe permissions. If blue/green is ever enabled the trigger bodies are MySQL `BEGIN ... END` blocks and would need a PL/pgSQL rewrite (not done, not needed for a default install).

The one `ON UPDATE CURRENT_TIMESTAMP` column becomes a `BEFORE UPDATE` trigger (emitted and applied, see the end of `generated-pg-schema.sql`):

| MariaDB | PostgreSQL |
|---|---|
| `sales_channel_api_context.updated_at datetime DEFAULT current_timestamp() ON UPDATE current_timestamp()` | `"updated_at" timestamp(0) DEFAULT CURRENT_TIMESTAMP` + `CREATE FUNCTION set_updated_at_now()` (`NEW.updated_at := CURRENT_TIMESTAMP`) + `CREATE TRIGGER ... BEFORE UPDATE ... EXECUTE FUNCTION set_updated_at_now()` |

Generated columns (15). PG 18 supports both `STORED` and `VIRTUAL` generated columns. A virtual generated column cannot be indexed in PG 18, so the generator uses `STORED` for any generated column that appears in an index (`sales_channel_domain.external_storefront_language_id`, which is in a unique index; it is VIRTUAL in MariaDB).

| Table.column | MariaDB (type, kind) | Definition | PostgreSQL as applied |
|---|---|---|---|
| `media.file_hash` | varchar(32) STORED | `json_unquote(json_extract(meta_data,'$.hash'))` | `varchar(32) GENERATED ALWAYS AS (("meta_data"->>'hash')) STORED` |
| `document.document_number` | varchar(255) STORED | `json_unquote(json_extract(config,'$.documentNumber'))` | `(("config"->>'documentNumber')) STORED` |
| `order.order_date` | date STORED | `cast(order_date_time as date)` | `CAST("order_date_time" AS date) STORED` |
| `order.amount_total` | double VIRTUAL | `json_extract(price,'$.totalPrice')` | `(("price"->>'totalPrice')::double precision) VIRTUAL` |
| `order.amount_net` | double VIRTUAL | `$.netPrice` | same pattern, `'netPrice'` |
| `order.position_price` | double VIRTUAL | `$.positionPrice` | same pattern |
| `order.tax_status` | varchar(255) VIRTUAL | `$.taxStatus` | `(("price"->>'taxStatus')) VIRTUAL` |
| `order.shipping_total` | double VIRTUAL | `json_extract(shipping_costs,'$.totalPrice')` | `(("shipping_costs"->>'totalPrice')::double precision) VIRTUAL` |
| `order_line_item.unit_price`, `.total_price` | double VIRTUAL | `$.unitPrice`, `$.totalPrice` of `price` | same pattern |
| `order_delivery_position.unit_price`, `.total_price` | double VIRTUAL | same | same |
| `order_delivery_position.quantity` | int(11) VIRTUAL | `$.quantity` | `(("price"->>'quantity')::integer) VIRTUAL` |
| `product_keyword_dictionary.reversed` | varchar(500) STORED | `reverse(keyword)` | `reverse("keyword") STORED` |
| `sales_channel_domain.external_storefront_language_id` | binary(16) VIRTUAL | `if(is_external_storefront = 1, language_id, NULL)` | `uuid GENERATED ALWAYS AS (CASE WHEN "is_external_storefront" THEN "language_id" END) STORED` |

All 15 were created without error. Untested semantics: JSON numbers stored as strings or with unexpected shapes make `::double precision` fail on write in PG where MariaDB would yield 0 or NULL; the `order`-level columns require the DAL to keep writing `price` as a JSON object. Also note the unique index on the generated column provides "unique per sales channel for the external storefront language".

## e. Foreign keys

418 foreign keys. Every one references `id` (single column) or `(id, version_id)`; 0 reference another column (`schema-stats.sh`, last queries).

| ON DELETE | ON UPDATE | Count |
|---|---|---:|
| CASCADE | CASCADE | 263 |
| RESTRICT | CASCADE | 66 |
| SET NULL | CASCADE | 47 |
| CASCADE | RESTRICT | 22 |
| SET NULL | RESTRICT | 8 |
| RESTRICT | RESTRICT | 7 |
| NO ACTION | CASCADE | 3 |
| CASCADE | NO ACTION | 2 |

Totals by ON DELETE: CASCADE 287, RESTRICT 73, SET NULL 55, NO ACTION 3. By ON UPDATE: CASCADE 379, RESTRICT 37, NO ACTION 2. PostgreSQL supports all of these rules with the same keywords.

Composite keys: 63 foreign keys are composite, every one involves a `version_id` column (name ending in `version_id`; 63 FK columns end in `version_id`): 51 ON DELETE CASCADE, 8 RESTRICT, 4 SET NULL. 355 are single column. The referenced side is always the primary key `(id, version_id)` of the versioned table, so PG's requirement that referenced columns have a unique constraint is met (all 418 applied). For the 4 composite SET NULL keys, none has a NOT NULL `*version_id` column (query in `schema-stats.sh`), so `SET NULL` of the whole key is valid, as in MariaDB; PG 15+ also offers `SET NULL (col, ...)` if only the non-version columns should be nulled.

## f. Migration system

### How a fresh install builds the schema

Both: a tiny base SQL file, then all migrations.

1. `SystemInstallCommand::initializeDatabase` (`src/Core/Maintenance/System/Command/SystemInstallCommand.php:225-251`) optionally drops/creates the database (`SetupDatabaseAdapter.php:21-29`, `CREATE DATABASE ... CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`) and calls `SetupDatabaseAdapter::initializeShopwareDb` (`SetupDatabaseAdapter.php:31-38`), which executes the whole file `src/Core/schema.sql` (`getBaseSchema`, `SetupDatabaseAdapter.php:79-92`) only if no `migration` table exists.
2. `src/Core/schema.sql` is 33 lines and contains exactly 2 `CREATE TABLE`: `plugin` and `migration` (grep `-c 'CREATE TABLE'` = 2). Everything else (the other 248 tables) comes from migrations. It uses MySQL syntax: backticks, `ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci`, `UNIQUE KEY` inside `CREATE TABLE`, `JSON` + `CHECK (JSON_VALID(...))`, `DATETIME(3)`, `TIMESTAMP(6)`, `MEDIUMBLOB`, `TINYINT(1)`.
3. `SystemInstallCommand.php:86-95` then runs `database:migrate core --all` and `database:migrate-destructive core --all`. The `core` identifier is the composite built in `src/Core/Installer/Database/MigrationCollectionFactory.php:40-46`: sources `core` (empty), `V6_3`, `V6_4`, `V6_5`, `V6_6`, `V6_7`. `V6_8` is not listed (grep `V6_8` in that file: no match), so the 17 `V6_8` classes are not run by a fresh install of this tree.
4. `MigrationCollection::sync` (`src/Core/Framework/Migration/MigrationCollection.php:34-43`) registers every class in the `migration` table via `MultiInsertQueryQueue` with ignore flag, which builds `INSERT IGNORE INTO ...` (`src/Core/Framework/DataAbstractionLayer/Doctrine/MultiInsertQueryQueue.php:101`; `ON DUPLICATE KEY UPDATE` at line 147).
5. `MigrationRuntime::migrate` (`src/Core/Framework/Migration/MigrationRuntime.php:25-56`) runs `SET default_storage_engine=InnoDB` (`:117-120`), selects pending classes with ``class` REGEXP :pattern` ordered by `creation_timestamp` (`:122-142`, REGEXP at `:127`), calls `update()` on each, and `setExecuted` (`:170`) updates `migration`. Destructive migrations run separately (`:58-87`).
6. `IndexerQueuer` (`src/Core/Framework/Migration/IndexerQueuer.php:69-128`) stores pending indexers in `system_config` through DBAL `insert/update`, using `Uuid::randomBytes()` for the id (`upsert`, `:97-127`); with uuid columns this needs the id conversion layer, not SQL changes.

Evidence in the install: `migration` table holds Core V6_3 335, V6_4 207, V6_5 75, V6_6 66, V6_7 210 (total 893), plus Administration V6_4 2, V6_7 2, Storefront V6_3 9, V6_4 1, V6_5 1, Elasticsearch V6_5 2; all with `update` and `update_destructive` set (query on `migration`).

### Migration classes per namespace

Counted as files containing `extends MigrationStep` (equals the PHP file count in each directory):

| Namespace | Classes |
|---|---:|
| `Shopware\Core\Migration\V6_3` | 335 |
| `V6_4` | 207 |
| `V6_5` | 75 |
| `V6_6` | 66 |
| `V6_7` | 210 |
| `V6_8` | 17 |
| Core total | 910 |
| Administration `V6_4` 2, `V6_7` 2 (`V6_6` dir has 0) | 4 |
| Storefront `V6_3` 9, `V6_4` 1, `V6_5` 1 | 11 |
| Elasticsearch `V6_5` | 2 |

### MySQL-only DDL and helper methods

Migrations mostly write raw SQL. Number of Core migration files (of 910) matching a pattern (`grep -rliE ... src/Core/Migration`, `migration-grep-counts.sh`, case-insensitive; a file can match several):

| Pattern | Files |
|---|---:|
| `ALTER TABLE` | 300 |
| `CREATE TABLE` | 179 |
| `ENGINE = InnoDB` | 176 |
| `Uuid::fromHexToBytes` / `Uuid::randomBytes` | 162 |
| `indexExists` / `columnExists` | 109 |
| `JSON_VALID` | 110 |
| `UNHEX(` / `HEX(` | 51 |
| `MODIFY` / `CHANGE COLUMN` | 51 |
| `registerIndexer` | 52 |
| `dropForeignKeyIfExists` / `dropIndexIfExists` / `dropColumnIfExists` | 47 |
| `JSON_EXTRACT` / `JSON_UNQUOTE` / `JSON_SET` / `JSON_OBJECT` / `JSON_ARRAY` | 39 |
| `GENERATED ALWAYS` / `VIRTUAL` / `STORED` | 18 |
| `AUTO_INCREMENT` | 15 |
| `INSERT IGNORE` | 10 |
| `createTrigger` / `CREATE TRIGGER` | 7 |
| `IFNULL` / `GROUP_CONCAT` | 4 |
| `UNIX_TIMESTAMP` / `DATE_FORMAT` / `NOW()` | 3 |
| `SHOW (COLUMNS|INDEX|TABLES|CREATE|FULL)` / `information_schema` | 2 / 2 |
| `ON UPDATE CURRENT_TIMESTAMP` / `FOREIGN_KEY_CHECKS` | 1 / 1 |

So a dialect-neutral rewrite of 910 raw-SQL migrations is not realistic; at least ~300 contain `ALTER TABLE`.

Helper methods that emit or depend on MySQL-only syntax:

| Location | Method | MySQL-only part | PostgreSQL equivalent |
|---|---|---|---|
| `MigrationStep.php:53-59` | `removeTrigger` | `DROP TRIGGER IF EXISTS name` (PG needs `ON table`) | `DROP TRIGGER IF EXISTS name ON table` |
| `MigrationStep.php:69-77` | `createTrigger` | caller supplies MySQL trigger SQL; gated by `BLUE_GREEN_DEPLOYMENT` | PL/pgSQL function + trigger |
| `MigrationStep.php:91-101` | `indexExists` | `SHOW INDEXES FROM ... WHERE key_name LIKE` (when `v6.8.0.0` inactive; else `TableHelper::indexExists`, `Framework/Util/Database/TableHelper.php:113`, DBAL schema manager) | `pg_indexes` / DBAL introspection |
| `MigrationStep.php:109-112`, `NonStandardFkGuard.php:21-58` | `executeDdlStatement` | `SHOW SESSION VARIABLES`, `SET SESSION restrict_fk_on_non_standard_key` | not needed |
| `MigrationStep.php:114-118` | `dropTableIfExists` | backtick quoting only | `DROP TABLE IF EXISTS "t"` |
| `MigrationStep.php:123-141` | `dropColumnIfExists` | backticks; "missing column" detected via `SQLSTATE[42000]` (PG uses 42703) | `DROP COLUMN IF EXISTS` |
| `MigrationStep.php:146-166` | `dropForeignKeyIfExists` | `ALTER TABLE ... DROP FOREIGN KEY`; SQLSTATE 42000 detection | `DROP CONSTRAINT IF EXISTS` |
| `MigrationStep.php:171-191` | `dropIndexIfExists` | `ALTER TABLE ... DROP INDEX`; SQLSTATE 42000 detection | `DROP INDEX IF EXISTS` (schema-level name) |
| `AddColumnTrait.php:26-50` | `addColumn` | `ADD COLUMN ... , ALGORITHM=INSTANT` then fallback; backticks | `ADD COLUMN` (no algorithm) |
| `ColumnExistsTrait.php:16-26` | `columnExists` | `SHOW COLUMNS FROM ... WHERE Field LIKE` (when `v6.8.0.0` inactive) | `information_schema.columns` |
| `InheritanceUpdaterTrait.php:11-20` | `updateInheritance` | ``ALTER TABLE ... ADD COLUMN ... binary(16) NULL`` | `uuid NULL` |
| `MakeVersionableMigrationHelper.php:22-29` | constants | `DROP FOREIGN KEY`, `DROP KEY`, `binary(16) NOT NULL DEFAULT 0x...`, `AFTER col`, `DROP PRIMARY KEY, ADD ...`, `ADD INDEX` inside `ALTER TABLE`; reads `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` (`:38`) | `DROP CONSTRAINT`, no `AFTER`, separate `CREATE INDEX` |
| `MigrationRuntime.php:117-120,127` | engine and selection | `SET default_storage_engine=InnoDB`, `REGEXP` | drop / `~` |
| `IndexerQueuer.php` | none in SQL | uses DBAL insert/update | works if ids are uuid-aware |

Also relevant outside migrations: `InheritanceUpdater.php:85-93,151-154` uses `UPDATE a, b SET ...` (multi-table UPDATE) and `IFNULL`, both MySQL-only.

## g. Options to obtain a PostgreSQL schema

| Option | Gives | Trade-offs |
|---|---|---|
| 1. Translate the installed MariaDB schema from `information_schema` (prototype, `mysql-to-pg-ddl.py`) | The final schema state of all 250 tables, 726 indexes, 418 FKs, generated columns, types, defaults, uuid ids | Fast and reproducible for a PoC; independent of PHP. Needs a MariaDB install per translated version; drops migration history (fresh PG would need the `migration` table pre-filled with the 893 + 17 executed classes so that `database:migrate` does nothing); mapping rules are hand-written (json to jsonb, collation, generated column expressions). Does not solve runtime SQL (`IFNULL`, `INSERT IGNORE`, `ON DUPLICATE KEY`, `MATCH`, `REGEXP`...) |
| 2. pgloader | Automated MySQL to PG migration including data | Not run and not evaluated here (`which pgloader` finds nothing on the host; it would run as a container if wanted). Open question: how its cast rules treat `binary(16)`; whatever it does, it would still need custom casts to `uuid`, and the generated columns, ICU collation and `ON UPDATE` triggers would have to be added by hand. Most useful for the data copy once a schema exists |
| 3. Generate from DAL definitions via `SchemaBuilder::buildSchemaOfDefinition` (`src/Core/Framework/DataAbstractionLayer/Dbal/SchemaBuilder.php:166`) | Doctrine DBAL `Table` objects (platform neutral `Types::BINARY`, `BOOLEAN`, `JSON`...) which a PG platform could render | It already carries MySQL options (`charset`/`collate` at `:168-170`, binary length 16 fixed at `:156-160`). It builds columns and foreign keys (`addForeignKeyConstraint`, `:356`) but no `addIndex` / `addUniqueIndex` call exists in the file, so unique/regular indexes, generated columns and JSON checks are missing. Only covers DAL entities: 26 of 250 tables have no definition (section h). `MigrationQueryGenerator` (used by `CreateMigrationCommand.php:136`) only produces diffs for MySQL |
| 4. Make migrations dialect-aware | A real, long-term solution keeping history | Approx. 910 core migrations (+ extension migrations) with raw MySQL SQL, ~300 with `ALTER TABLE`; helper methods (table above) can be made dialect-aware cheaply, the raw SQL cannot. Highest effort; sensible only after the PoC proves the runtime works |

Recommended for the PoC: option 1 (done), then fill the `migration` table so the normal migration run is a no-op.

### Prototype result (option 1)

Command (generator reads MariaDB read-only, writes the DDL; applied inside schema `scratch_schema_agent` only):

```
python3 mysql-to-pg-ddl.py > generated-pg-schema.sql
podman exec -i instance-postgres-1 psql -U shopware -d shopware -v ON_ERROR_STOP=0 < generated-pg-schema.sql
podman exec -i instance-postgres-1 psql -U shopware -d shopware < pg-verify.sql > pg-verify-output.txt
```

Generator summary: tables 250, columns 2168, non-PK indexes 476, FKs 418, ON UPDATE triggers 1, index names shortened to 63 bytes 97, JSON_VALID checks dropped 220, other checks kept 2, 0 warnings.

Applied result (counts read back from the PostgreSQL catalogs, `pg-verify-output.txt`): 250 tables, 2168 columns, 726 indexes (250 PK + 476 others, 97 of them UNIQUE), 418 FKs, 2 CHECK, 715 `uuid` columns, 220 `jsonb`, 136 `boolean`, 15 generated columns, 11 identity columns, 1 trigger. Failed statements: 0 (`psql` stderr contained 0 `ERROR` lines; stdout contained 250 `CREATE TABLE`, 476 `CREATE INDEX`/`CREATE UNIQUE INDEX`, 418 `ALTER TABLE`). Created = expected for all object types; nothing failed.

Behaviour notes of the generated DDL: index names are prefixed with the table (`<table>.<index>`) because PG index names are schema-wide (e.g. `hash` exists on `customer` and `newsletter_recipient`; MySQL scopes names per table); 97 names exceeded 63 bytes and got a truncated form plus an 8 character md5 suffix. Every identifier is double-quoted (`"order"`, `"user"`, `"key"`). Prefix indexes (`media.idx.media.file_name` 768, `app_template.idx.template.path` 256) are created on the full column. The schema was only created, no data loaded and no Shopware code run against it, so the suitability for the application is not verified.

## h. Tables unknown to the DAL

Method: `dal-entity-diff.py` (output: first 34 lines, plus `DefinitionValidator` cross-check) collected `const ENTITY_NAME = '...'` and literal `getEntityName()` returns from all non-test PHP under `src` (219 names) and diffed them against the 250 tables. No entity name lacks a table. 31 tables were not matched; 5 of them are false positives of the method and 26 are real:

False positives (defined by other means):
- `product_feature_set_translation`: `ENTITY_NAME = ProductFeatureSetDefinition::ENTITY_NAME . '_translation'` (`ProductFeatureSetTranslationDefinition.php:19`), concatenated constant not matched by the regex.
- `measurement_system`, `measurement_system_translation`, `measurement_display_unit`, `measurement_display_unit_translation`: attribute-defined entities, `#[Entity('measurement_system', since: '6.7.1.0')]` in `src/Core/Content/MeasurementSystem/DataAbstractionLayer/MeasurementSystemEntity.php:24` (and `MeasurementDisplayUnitEntity`), tagged `shopware.entity` in `Content/DependencyInjection/measurement_system.php:20-24`.

Real tables without a definition (26). 25 are listed in `DefinitionValidator::TABLES_WITHOUT_DEFINITION` (`src/Core/Framework/DataAbstractionLayer/DefinitionValidator.php:104-135`), which is the framework's own list, and 1 is in `MAJOR_REMOVED_DEFINITIONS` (`:137`):

`admin_elasticsearch_index_task`, `app_config`, `app_feature`, `cart`, `consent_log`, `consent_state`, `deleted_apps`, `elasticsearch_index_task`, `increment`, `invalidation_tags`, `mcp_list_version`, `mcp_tool_result_cache`, `mcp_toolset_session`, `messenger_messages`, `messenger_stats`, `migration`, `oauth_auth_code`, `oauth_user`, `payment_token`, `refresh_token`, `sales_channel_api_context`, `theme_runtime_config`, `usage_data_entity_deletion`, `webhook_delivery`, `webhook_stream`, and `import_export_profile_translation` (definition removed, table still present).

The validator list additionally names `one_time_tasks` and `subscription_cart`, which do not exist in this install. For the 26, SQL is written by hand in storage classes (e.g. `MySQLInvalidatorStorage`, `MySQLKeyValueStorage`, `MySQLStatsRepository`, `WebhookOutboxStore`, `AuthCodeRepository`, `PaymentTokenLifecycle`), so these classes need a PostgreSQL port in addition to the schema. Custom entities created at runtime via `custom_entity` are not in this install (not verified beyond the table list).

## Open questions

- Content of `webhook_*.partition_key`, `seo_url.foreign_key`, `category_translation.internal_link` and the 20 `product` inheritance columns: tables are empty in the install, so uuid-ness is inferred from source only. `seo_url.foreign_key` holds entity ids per its use in the unique index; the `partition_key` format was not verified.
- Which longblob columns hold serialised PHP vs JSON (`cart.payload`, `rule.payload`, ...): classified by name, not read.
- Whether `jsonb` is acceptable to the DAL's JSON field serializers (key order, number formatting) is untested.
- pgloader was not run; option 2 is not evaluated.
- `citext` and `lower()`-index alternatives not prototyped; only the ICU nondeterministic collation was tested.
- Application SQL that depends on MariaDB semantics (`IFNULL`, `INSERT IGNORE`, `ON DUPLICATE KEY`, `REGEXP`, multi-table `UPDATE`, `JSON_*`, `MATCH`) was not inventoried in this task, only the migration layer.
- The 4 SET NULL composite FKs: runtime behaviour in PG not exercised (no data).
- Extension/plugin migrations are not covered (only the core tree and the 3 bundles).
