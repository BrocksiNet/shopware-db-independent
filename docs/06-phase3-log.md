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

## Findings outside the request path

- `Maintenance/System/Service/DatabaseConnectionFactory` and `DatabaseConnectionInformation::toDBALParameters()` hard code `pdo_mysql` and a MySQL / MariaDB version check.
  `system:install`, and with it the PHPUnit bootstrap, therefore can not run against a PostgreSQL `DATABASE_URL`.
  Unit tests were run with `DATABASE_URL=$MYSQL_URL`.
