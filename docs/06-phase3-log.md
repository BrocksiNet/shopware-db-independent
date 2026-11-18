# Phase 3 log: getting requests through on PostgreSQL

Running log of what each step needed.
State: lane `pg` on PostgreSQL, branch `poc/postgresql` in `instance/`.

## Step 1: id codec at the driver boundary

Problem: `GET /admin` failed with `invalid byte sequence for encoding "UTF8": 0xb7`.
The PHP side binds ids as 16 raw bytes (`Uuid::fromHexToBytes`), the column is `uuid`.

Change: `Adapter/Database/PostgreSQL/IdCodecMiddleware.php` (plus `IdCodecStatement`, `IdCodecResult`), a DBAL driver middleware registered by `PostgreSQLFactory`.

- Bound values: a 16 byte string bound as `BINARY` or `LARGE_OBJECT` becomes a 32 character hex string, which PostgreSQL accepts as `uuid` input.
  A 16 byte string bound as `STRING` is converted only if it is not valid UTF-8.
- Results: a value in canonical uuid form (36 characters, lower case, dashes) becomes 16 raw bytes.

Verified with a script against the copied data: lookup by binary id, `fetchFirstColumn`, an `IN (:ids)` list bound as `ArrayParameterType::BINARY`, and a 16 character text that must stay untouched.
No call site had to change.

Limits, both because the driver middleware API exposes no column or parameter types:

- An id whose 16 bytes happen to be valid UTF-8 and that is bound as `STRING` is not converted and the query fails.
  Call sites that bind ids without `ParameterType::BINARY` are therefore a finding of their own.
- A text column that holds a dashed uuid string would be turned into bytes on read.
- A type-driven codec needs an own driver (access to `PDOStatement::getColumnMeta`).

Later addition: a 16 byte string that contains a NUL byte is always treated as an id, also when bound as `STRING`.
The lane's MariaDB holds a `media_folder` row with the all-zero id (the "Product downloads" folder).
Sixteen NUL bytes are valid UTF-8, so the value went through as text and PostgreSQL received an empty string (`invalid input syntax for type uuid: ""`).
PostgreSQL text can not contain NUL, so this rule can not hit a real text value.

## Step 2: SQL translation at the driver boundary

Decision: MySQL flavoured SQL is translated in a driver middleware instead of porting every call site first.
Call sites and the DAL only change where the difference is structural.

Three parts, all under `src/Core/Framework/Adapter/Database/PostgreSQL/`:

1. `MySQLToPostgreSQLTranslator.php`, a tokenizer based rewrite, wired in by `SqlTranslationMiddleware.php` for `prepare`, `query` and `exec`.
2. `ColumnCaseStatement.php` / `ColumnCaseResult.php`, which restore the case of result column names.
3. `mysql-compat.sql`, functions, operators and aggregates created inside PostgreSQL.
   It is idempotent and currently applied by hand, nothing in the core loads it yet.

### Lexical rewrites

| MySQL | PostgreSQL | Note |
|---|---|---|
| `` `ident` `` | `"ident"` | |
| `"string"` | `'string'` | Double quotes are string literals with the MySQL `sql_mode` Shopware sets. |
| `'a\'b'` | `E'a\'b'` | Only literals that contain a backslash. |
| `# comment` | removed | `--` and `/* */` comments are kept. |
| `a <=> b` | `a IS NOT DISTINCT FROM b` | |
| `GROUP_CONCAT(x SEPARATOR ',')` | `GROUP_CONCAT(x , ',')` | `SEPARATOR` becomes a comma, the aggregate has a two argument form. |

Translated statements are cached per SQL string (limit 5000 entries).

### Result column case

PostgreSQL folds unquoted identifiers to lower case, so `AS snippetSetId` comes back as `snippetsetid` and the PHP code fails with `Undefined array key "snippetSetId"`.
The translator records every unquoted mixed case word of the statement.
`ColumnCaseResult` maps the lower cased column names of associative fetches back to the recorded spelling.

### Shims inside PostgreSQL

| Shim | Reason |
|---|---|
| `hex(uuid)`, `hex(bytea)`, `hex(text)`, `unhex(text)` | `LOWER(HEX(id))` and `UNHEX(:id)` are used all over the core. |
| implicit cast `bytea` to `uuid` | `UNHEX(...)` compared with an id column. |
| `"if"(boolean, a, b)`, `ifnull(a, b)` | Polymorphic (`anycompatible`), so they need a quoted function body. |
| operators `boolean = integer`, `boolean <> integer`, `integer = boolean` | `WHERE active = 1`. |
| aggregates `group_concat(text)`, `group_concat(text, text)` | |
| aggregates `min(uuid)`, `max(uuid)` | The DAL sorts with `MIN(id)` in grouped queries. |
| aggregates `min(boolean)`, `max(boolean)`, `sum(boolean)` | `MAX(shipping_free)` in the listing aggregations. |
| `json_extract(jsonb or text, path)`, `json_unquote(jsonb or text)` | Built on `jsonb_path_query_first`. |
| operators `text * integer`, `text + numeric` | MySQL idiom to cast a JSON value to a number (`JSON_UNQUOTE(...) * 1`, `... + 0.0`). |
| `lower(jsonb)` | `LOWER(product_search_config.excluded_terms)` on a JSON column. |

Not equal to MySQL: a text that is not a number raises an error in the arithmetic operators, MySQL silently uses 0.
`GROUP_CONCAT` with an inner `ORDER BY` is not handled yet.

### Bound booleans

DBAL binds a PHP `false` given without a type as an empty string.
PostgreSQL rejects that for a `boolean` column (`invalid input syntax for type boolean: ""`).
`IdCodecStatement::bindValue` now sends PHP booleans as `'1'` / `'0'`.

## Step 3: structural changes in the DAL

These could not be solved by rewriting tokens.

1. **Strict GROUP BY.**
   PostgreSQL rejects selected columns that are neither grouped, functionally dependent on the grouped primary key, nor aggregated.
   The DAL groups by `"table"."id"` whenever a to-many join is involved and selects other columns, including columns of joined translation sub selects.
   For versioned entities such as `product` the primary key is `(id, version_id)`, so not even the root columns are covered.
   This answers the open question about `ONLY_FULL_GROUP_BY`: the DAL relies on it being off.
   Change: `EntityDefinitionQueryHelper::makeSelectValidForGroupBy()` wraps the selected expressions in `any_value()` (PostgreSQL 16+).
   It is called on PostgreSQL only, from `EntityReader::fetch()`, `EntitySearcher::search()` and the score ranked query.
2. **Select alias in HAVING.**
   `CriteriaQueryBuilder` added `HAVING _score >= :_minScore`.
   PostgreSQL does not resolve select aliases in `HAVING`, the score expression is now repeated there, on every platform.
3. **Unqualified GROUP BY column.**
   The score sub query of `EntityAggregator` grouped by a bare `id`, which is ambiguous on PostgreSQL once tables are joined.
   It is now qualified with the table, on every platform.

The existing unit tests in `tests/unit/Core/Framework/DataAbstractionLayer/Dbal` (153 tests) pass on MariaDB with these changes.
No tests were written for the new code and PHPStan was not run.

## State after step 3

The copied installation has no products and one category, so the listings are empty.

| Request | Result |
|---|---|
| `GET /` | 200 |
| `GET /account/login`, `GET /account/register` | 200 |
| `GET /checkout/cart` | 200 |
| `GET /search?search=a`, `GET /suggest?search=a` | 200 |
| `GET /cookie/offcanvas`, `GET /sitemap.xml` | 200 |

Not tested yet: any write (registration, cart, order), the admin API, indexers and scheduled tasks.

## Step 4: writes, indexers, cart and checkout

Driven through the admin API (`PATCH /api/product/...`) and the store API (cart, registration, order).

### Statement rewrites in the driver middleware

Both run in `SqlTranslationMiddleware` after the lexical translation.

1. `UpsertRewriter.php`
   - `INSERT IGNORE` becomes `ON CONFLICT DO NOTHING`.
   - `ON DUPLICATE KEY UPDATE` becomes `ON CONFLICT (primary key) DO UPDATE SET`, `VALUES(col)` becomes `EXCLUDED.col`.
   - Columns on the right side of an assignment are qualified with the table.
     `count = count + 1` is ambiguous on PostgreSQL (existing or `EXCLUDED` row), MySQL reads the existing row.
   - `REPLACE INTO` becomes an upsert on the primary key.
   - The primary key is read from `pg_index` and cached per connection.
2. `UpdateRewriter.php`
   - Qualified `SET` targets lose the qualifier.
   - `UPDATE a, b SET ... WHERE w` becomes `UPDATE a SET ... FROM b WHERE w`.
   - `UPDATE a [INNER] JOIN b ON c SET ... WHERE w` becomes `UPDATE a SET ... FROM b WHERE (c) AND (w)`.
   - `LEFT JOIN` is not rewritten, those call sites were changed (see below).

Limits:

- The conflict target is always the primary key.
  MySQL `ON DUPLICATE KEY` and `REPLACE` react to every unique index.
- `INSERT IGNORE` on PostgreSQL only skips duplicates, MySQL also turns other errors (for example a too long value) into warnings.
- A rewritten `REPLACE` keeps the values of columns that are not part of the statement, MySQL deletes the row and resets them to their defaults.

### REPLACE in `MultiInsertQueryQueue`

The keyword dictionary indexer failed with `duplicate key value violates unique constraint "product_keyword_dictionary.uniq.language_id_keyword"`.
The table has a primary key and a second unique key, `REPLACE` on MySQL resolves a conflict on either.
On PostgreSQL the queue no longer emits `REPLACE`.
For every unique key (primary key and unique indexes from `pg_index`) whose columns are all part of the insert it deletes the matching rows, then it inserts.
Both run in the existing `RetryableTransaction`.
Duplicates inside one batch are not removed, a batch that contains the same key twice still fails.

### Call sites changed

| File | Change | Platforms |
|---|---|---|
| `Content/Product/Stock/StockStorage.php` | `UPDATE product LEFT JOIN product parent` replaced by a correlated sub select | PostgreSQL branch |
| `Content/Product/DataAbstractionLayer/StatesUpdater.php` | `LEFT JOIN` + partial `GROUP BY` replaced by `EXISTS` | all |
| `Content/Newsletter/.../CustomerNewsletterSalesChannelsUpdater.php` | reset statement without `LEFT JOIN`, sub select on `newsletter_recipient` | all |
| `System/NumberRange/.../IncrementSqlStorage.php` | MySQL user variable `@nr... :=` replaced by `ON CONFLICT ... RETURNING last_value` | PostgreSQL branch |

### Translator additions

- Bare `user` is quoted, it is a reserved word on PostgreSQL and a table name in Shopware.
- A string literal used as alias (`AS '0'`) becomes a quoted identifier.
- Identifiers longer than 63 bytes are shortened to a prefix plus a hash, the column case map restores the full name in the result.
  PostgreSQL cuts identifiers after 63 bytes (`max_identifier_length`), MySQL allows 256 characters for an alias.
  The DAL builds aliases like `order_delivery.shippingOrderAddress.country.translation.addressFormat` (69 characters), the order read failed with an undefined array key.
  Plain cutting could make two aliases equal, hence the hash.

### Binary strings and serialized PHP

`product.cheapest_price` is a MySQL `LONGTEXT` that holds `serialize()` output, which contains NUL bytes.
Bound as text, PostgreSQL ended the value at the first NUL byte without an error, reading it back failed in `unserialize()`.

- The column is `bytea` now, the schema generator has an explicit list for such columns (`SERIALIZED_TEXT_COLS`).
- `IdCodecStatement` binds a string parameter as binary when it contains a NUL byte or is not valid UTF-8.
- Verified in the container: a value with NUL bytes round trips through `bytea` when bound as `BINARY` or `LARGE_OBJECT`, bound as `STRING` it came back shortened (53 of 82 bytes).

#### Audit of the other text columns

No further column needs to change, `SERIALIZED_TEXT_COLS` stays as it is.

Code: every `serialize(` and `PHPUnserializeFieldSerializer` / `SerializedField` write in `src/` (without migrations and tests) was followed to its target column.

| Writer | Target column | Type on PostgreSQL |
|---|---|---|
| `CheapestPriceUpdater` | `product.cheapest_price` | `bytea` (fixed above), the only `SerializedField` user (`CheapestPriceField`) |
| `RulePayloadUpdater` | `rule.payload` | `bytea` |
| `FlowPayloadUpdater` | `flow.payload` | `bytea` |
| `RuleConditionLifecycleHandler` | `app_script_condition.constraints` (`BlobField`) | `bytea` |
| `MediaIndexer`, `FileSaver` | `media.thumbnails_ro`, `media.media_type` | `bytea` |
| `MediaFolderConfigurationIndexer` | `media_folder_configuration.media_thumbnail_sizes_ro` | `bytea` |
| `OutboxInsert` via `WebhookOutboxStore::insertEventLog` | `webhook_event_log.serialized_webhook_message` | `bytea` |
| `CartPersister` | `cart.payload` | `bytea` |
| Messenger (`messenger_messages.body`, `text`) | `PhpSerializer` writes `addslashes(serialize(...))`, NUL becomes the two characters `\0` | safe as `text` |
| `MailSender` | written to the filesystem, not the database | n/a |

The `LONGTEXT payload` columns from the handoff (`version_commit_data`, `order_transaction`, `order_delivery`, `promotion_individual_code`, `sales_channel_api_context`, `order_line_item`, `app_feature`) are `jsonb` on PostgreSQL and written with `JsonField` / `json_encode`, not `serialize()`.
Example: `SalesChannelContextPersister` line 57 and `OrderLineItemDefinition` line 103.

Data: a scan of all 725 text-like MariaDB columns (NUL byte, `O:`, `a:`, `s:` prefixes) and of the 64 `text` columns on PostgreSQL gave no hit.
This only shows that the lane data is nearly empty (for example `product` has 0 rows on MariaDB), it is no evidence for the other columns, the code audit is.

Read side, verified with real reads through the running application:

- Store API `POST /product` returns `calculatedCheapestPrice`, which is computed from the unserialized `product.cheapest_price` (861 bytes with NUL bytes).
- Admin API `GET /api/media-folder-configuration` returns `mediaThumbnailSizes` with three sizes, unserialized from the `bytea` column.
- `GET /api/flow`, `/api/rule` and `/api/media` answer 200.

Related, not changed: PostgreSQL `jsonb` rejects the escape `\u0000` (`select '"a\u0000b"'::jsonb` gives `unsupported Unicode escape sequence`).
A `JsonField` value that contains a NUL byte in a string would therefore fail on PostgreSQL, where MySQL `JSON` accepts it.
No such value was found in the lane data, whether the core produces one is not verified.

### More shims

| Shim | Reason |
|---|---|
| `sha2(text, integer)` | Used in raw SQL. |
| `json_quote(text)` | `ManyToManyIdFieldUpdater` builds JSON arrays with `GROUP_CONCAT(JSON_QUOTE(...))`. |
| assignment cast `text` to `jsonb` | The JSON built as text is written into a `jsonb` column. |
| `integer` to `boolean` cast made an assignment cast | `UPDATE seo_url SET is_deleted = 0`. |

The last one changes `pg_cast` directly, because a second cast for the same type pair can not be created.
That needs a superuser and is not possible on most managed services.
It is a proof of concept shortcut, the real fix is to bind booleans or write `false`.

This shortcut was removed again in Step 7, the call sites now write real booleans.

### State after step 4

| Flow | Result |
|---|---|
| Admin API: create tax, property group, product; update product | 2xx, indexers write keywords, SEO URL, `property_ids`, states, cheapest price |
| Storefront: home listing, search, suggest, product detail with the new product | 200, product shown |
| Store API: add to cart, read cart | 200, cart persisted |
| Store API: register customer | 200, customer number from the number range |
| Store API: place order | 200, order number 10002, state `open` |

Not tested yet: the administration UI, scheduled tasks and the message queue, media upload, theme compile, the installer.
No tests were written for the new classes.

## Findings outside the request path

- `Maintenance/System/Service/DatabaseConnectionFactory` and `DatabaseConnectionInformation::toDBALParameters()` hard code `pdo_mysql` and a MySQL / MariaDB version check.
  `system:install`, and with it the PHPUnit bootstrap, therefore can not run against a PostgreSQL `DATABASE_URL`.
  Unit tests were run with `DATABASE_URL=$MYSQL_URL`.

## Step 5: administration UI and scheduled tasks

All 27 runnable scheduled tasks were run with `scheduled-task:run-single`, `messenger:consume async` ran without errors.
The two tasks with status `skipped` (`telemetry.collect_periodic_metrics`, `shopware.elasticsearch.create.alias`) are skipped by the framework itself, they were not run.
In the administration the dashboard, product list and detail, order list and detail, customer list and detail and the settings start page load without a PostgreSQL error.

| Area | Error | Fix | Platforms |
| --- | --- | --- | --- |
| Scheduled tasks (version, webhook log, cart, customer recovery, MCP cache, keyword dictionary) | `DELETE FROM t WHERE ... LIMIT n` is a syntax error | `DeleteRewriter` rewrites it to `DELETE FROM t WHERE ctid IN (SELECT ctid FROM t WHERE ... LIMIT n)` | PostgreSQL only |
| Scheduled task `log_entry.cleanup` | `DELETE ld FROM t ld LEFT JOIN ...` (multi table delete) | `DeleteRewriter` rewrites it to `DELETE FROM t ld WHERE ld.ctid IN (SELECT ld.ctid FROM t ld LEFT JOIN ...)`, only for a single target | PostgreSQL only |
| Scheduled task `shopware.sitemap_generate` | `COALESCE(bool, bool, 0)` mixes boolean and integer | `ProductUrlProvider` uses `COALESCE(..., FALSE) = TRUE` | both |
| Admin `/api/app-system/modules` | `json_contains(jsonb, json)` missing | shim in `mysql-compat.sql` (two argument form) | PostgreSQL only |
| Admin dashboard `order-amount` | `date_format(timestamp, text)` missing | shim in `mysql-compat.sql`, translates MySQL specifiers to `to_char` patterns | PostgreSQL only |
| Admin product list (natural sorting) | `length(timestamp)` and `length(integer)` missing | shims in `mysql-compat.sql` | PostgreSQL only |
| Admin product detail, `property-group-option` search | natural sorting `ORDER BY LENGTH(col)` in a grouped query, column not aggregated | `CriteriaQueryBuilder` uses `LENGTH(MIN(col))` / `LENGTH(MAX(col))` when the query has a group by | both (the MySQL result was an arbitrary row value before, now the min / max) |
| Admin order detail | `json_type(jsonb)` missing | shim in `mysql-compat.sql`, returns the MySQL type names | PostgreSQL only |

Not covered: other administration modules (rules, flows, media, themes, import / export) and a full click through of every tab.
`json_contains` ignores the optional path argument.

## Step 6: remaining administration areas

Every area below was driven through the admin API, the store API or the console on PostgreSQL, with the PostgreSQL log checked after each call.
Test data used ids starting with `c0000000`, the order for the flow and promotion checks went through `/store-api/checkout/order`.

| Area | What was run | Error | Fix | Platforms |
| --- | --- | --- | --- | --- |
| Rules | create a rule with `andContainer`, `cartCartAmount`, `cartLineItemOfType`, `customerBillingCountry`, `dayOfWeek`, set it as availability rule of a shipping method, add a product to the cart | none, the payload was indexed and the cart blocked the shipping method as expected | none | |
| Flow builder | create a flow on `checkout.order.placed` with `action.add.order.tag`, place an order, `messenger:consume async` | none, one `order_tag` row was written (the first attempt failed on a foreign key because the test tag did not exist, same on MySQL) | none | |
| Media | create media, upload a PNG through `/api/_action/media/{id}/upload`, rename, delete, media folder with child and configuration, folder tree search, `media:generate-thumbnails`, `media:generate-media-types` | none | none | |
| Theme | `theme:compile`, read the configuration, change `sw-color-brand-primary`, assign the theme | none | none | |
| Import / export | export the product profile, import a CSV with one updated and one new product | none, both logs reached `succeeded` | none | |
| Promotions | create a promotion with a code and a 10 % cart discount, add the code to the cart, place the order | `orders_per_customer_count` was written with the key `"\"<id>\""`, because `JSON_SET(doc, '$."<id>"', n)` kept the quotes | the path helper in `mysql-compat.sql` parses quoted keys (`$."key"`), `json_set` and `json_remove` use it | PostgreSQL only |
| Category | create, nest, move, delete | none | none | |
| Sales channel | create with domain and relations, update, delete | none | none | |
| Product variants | property group with two options, configurator settings on `aaaaaaaaaaaa4aaa8aaaaaaaaaaaaa10`, two variants written as children, storefront detail page | none | none | |

Known remaining difference: the count in `orders_per_customer_count` is stored as a JSON string (`"2"`) instead of a number, because the integer parameter reaches `json_set` as text.
Nothing in core reads the column (it is deprecated and only written), so this has no effect.
`storefront detail` probes with `/tmp/pg-step.sh` printed status `000` but rendered the page title without an error in the PostgreSQL log, the cause of the `000` was not investigated.
Not covered: a click through of the administration modules in the browser, theme compile with a changed value in the storefront output, and promotions with individual codes or advanced rules.

## Step 7: hardening

This step removes the proof of concept shortcuts that were left in the shims.
All code changes are in `instance/` on `poc/postgresql`, in four commits: `09022c2ea0e`, `f9bb4e5cdff`, `a6009d13658` and `4c998b16740`.

### The `pg_cast` shortcut is gone

The `UPDATE pg_cast SET castcontext='a'` block is removed from `mysql-compat.sql`.
Writes of `0` and `1` to boolean columns now fail on PostgreSQL, so the call sites were changed to PHP booleans or `TRUE` and `FALSE` literals (commit `09022c2ea0e`).

Fixed call sites:

- `RetryWebhookMessageFailedSubscriber` and `WebhookHealthService`: `active => false`.
- `WebhookLifecycleHandler`: `active => true`, and `only_live_version` is cast to bool.
- `ProductExportGenerateTaskHandler`: `is_running => false`.
- `PaymentTokenLifecycle` and `JWTFactoryV2`: `consumed => true`.
- `AppSeoUrlLifecycleHandler`, `RepairLinkCategorySeoUrlTakeoverCommand`, `RuleIndexerSubscriber`: `is_deleted`, `is_modified` and `invalid` as literals.
- `ProductStreamIndexer`: `invalid => true`.
- `SeoUrlPersister`: `is_canonical`, `is_modified`, `is_deleted` in the UPDATE, the insert values and the query builder.
- Test helpers `TestUser` and `ElasticsearchTestTestBehaviour`.
- Unit tests `RuleIndexerSubscriberTest` and `SeoUrlPersisterTest` follow the new SQL.

The `product` PATCH first still failed with `column "is_deleted" is of type boolean but expression is of type integer`.
The cause was `SeoUrlPersister`, which a first search had missed, and after the fix the request returned 204.
The storefront, the checkout (`/tmp/pg-store.sh`) and a product write (`/tmp/pg-w.sh`) work without the cast.

Comparisons such as `is_deleted = 0` still work, because the `boolean = integer` operators stay in the shims.
Only the assignment of an integer to a boolean column needed the code changes.

### Upsert conflict targets

`UpsertRewriter` used the primary key as the only conflict target, because `ON CONFLICT` takes exactly one target and MySQL reacts to every unique key.
A statement can now name its target with a leading comment `/* conflict-target: col_a, col_b */`.
MySQL ignores the comment, and `UpsertRewriter` reads it from the statement prefix and uses it instead of the primary key (commit `f9bb4e5cdff`).

The hint is used at these call sites:

- `MultiInsertQueryQueue::setConflictTarget()` writes the hint in front of the statement.
- `SeoUrlPersister` sets `language_id, sales_channel_id, seo_path_info`.
- `ConsentRepository` sets `name, identifier`.

`SalesChannelContextPersister` had a `REPLACE` that could hit two unique keys, the token and the customer per sales channel.
In the `UniqueConstraintViolationException` branch it now runs a `DELETE` of both matches and an `INSERT` in `RetryableTransaction`.

Unit tests: a new case in `UpsertRewriterTest` and `MultiInsertQueryQueueTest::testConflictTargetIsPassedAsCommentForUpserts`.

Documented, not changed:

- The hint is opt-in, all other `ON DUPLICATE KEY UPDATE` and `REPLACE` statements still use the primary key.
- `theme_runtime_config` has the primary key `theme_id` and a unique `technical_name`, a conflict only happens when the same technical name is saved under another theme id.
- `INSERT IGNORE` becomes `ON CONFLICT DO NOTHING` without a target, so it skips every unique key like MySQL, but it does not downgrade foreign key errors.
- The `ShopConfigurator` upsert of `system_config` looks up the id first, so it is not affected.

### GROUP_CONCAT with ORDER BY

MySQL writes `GROUP_CONCAT(x ORDER BY y DESC SEPARATOR '|')`.
PostgreSQL needs the separator as a second argument before `ORDER BY`.
Without a rewrite the separator was not rejected but silently ended up as part of the sort key.

`MySQLToPostgreSQLTranslator` now moves the separator in front of `ORDER BY`, so the example becomes `GROUP_CONCAT(x , '|' ORDER BY y DESC)` (commit `a6009d13658`).
The test `testGroupConcatSeparatorMovesBeforeOrderBy` has a data provider with the cases.

Still not valid on PostgreSQL: `DISTINCT` combined with an `ORDER BY` expression that is not in the argument list.
Only `ORDER BY NULL` is dropped.

### Aborted transactions

After a failed statement PostgreSQL aborts the whole transaction (SQLSTATE `25P02`), and a later `COMMIT` rolls back silently.
MySQL keeps the transaction usable, so code that catches the exception and continues breaks on PostgreSQL.
DBAL 4 uses savepoints for nested transactions, so wrapping the risky statement in `$connection->transactional()` makes catch and continue safe.

`WebhookOutboxStore` had two such sites, both catching `UniqueConstraintViolationException` after a failing insert.
Both inserts now run in their own `transactional()` call, with a comment that explains the difference (commit `4c998b16740`).

Not examined in detail: the other `catch (DBALException)` and `catch (DriverException)` sites such as `Translator`, `FeatureFlagRegistry` and `Kernel`.
They only matter when an enclosing transaction is open and more statements or a commit follow the caught error.
`LockWaitTimeout` (`55P03`) is not mapped to `LockWaitTimeoutException` and was not tested.

### Verification

PHPUnit only runs against MySQL (`DATABASE_URL=$MYSQL_URL`), it can not bootstrap against PostgreSQL.
The rewriter and queue unit tests ran there, and the PostgreSQL behaviour was checked with the flows above and with small scripts against the running containers.
