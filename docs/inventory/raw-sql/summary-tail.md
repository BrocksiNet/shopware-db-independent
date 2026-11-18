
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
