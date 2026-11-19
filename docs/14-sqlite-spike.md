# SQLite feasibility spike

Date: 2026-11-19.
Scope: how far does Shopware get on SQLite, which dialect methods and decisions are missing, is SQLite realistic for dev and CI.
Base: `instance/` branch `poc/db-independent`, PHP 8.4.17, SQLite 3.51.2 (`pdo_sqlite`), DBAL 4.
Code: `src/Core/Framework/Adapter/Database/Sqlite/` (about 1,200 lines in 8 files), `SqliteFactory` and the `DATABASE_URL=sqlite:///...` branch in `ConnectionFactory`.

## How far it got

The installation gets through, with 5 migrations missing out of 1,542.

- Regular migrations: 906 of 910 run, 4 fail.
- Destructive migrations: 631 of 632 run, 1 fails.
- The 5 failing migrations were marked as executed by the test loop to continue; their effect is missing in the database.
- `user:create`, `sales-channel:create:storefront`, `system:configure-shop`, `system:config:set` and `dal:refresh:index` run.
- Storefront: `/` and `/account/login` answer 200 (105 KB of HTML), a missing category answers 404 as expected.
- Admin: `POST /api/oauth/token` gives a token, `GET /api/_info/version`, `POST /api/search/tax`, `/search/currency` and `/search/product` answer 200.
- Product write: `POST /api/product` answers 204, the product is found again by `productNumber`, `PATCH /api/product/{id}` answers 204.
- Not tried: the storefront product page, checkout, the admin UI in a browser, the message queue, anything beyond the routes above.

How the pieces work (all in the driver middleware, no change to the DAL):

- A `SessionMiddleware` sets `PRAGMA foreign_keys = ON`, WAL and `busy_timeout`, registers 28 PHP functions for the missing MySQL functions and creates temp views for `information_schema.columns` and `tables`.
- A `SqlTranslationMiddleware` rewrites DML and DDL statements. It reuses the PostgreSQL `UpdateRewriter`, `DeleteRewriter`, `InsertSetRewriter`, `UpsertRewriter` and `DdlRewriter::splitTopLevel`, so the shared rewriter design carries over.
- A `SqliteDdlRewriter` turns `ALTER TABLE` into one of three things: a patched `CREATE TABLE` text in `sqlite_master` (`PRAGMA writable_schema`), a table rebuild, or a plain `ALTER`.
- A `MultiStatement` wrapper runs the several statements one MySQL DDL statement expands to, because `pdo_sqlite` prepares one statement only.
- A `SqliteDialect` implements every `SqlDialect` method of handoff C, and `SqlDialectFactory` returns it for the `SQLitePlatform`.

The DDL rewriter is 335 lines and the translation middleware 371 lines.
The handoff said to stop and document before a 1,000 line DDL rewriter, that line was not reached, but the `writable_schema` patch is the part that carries the most risk (see below).

## Blockers by cause

The counts are distinct blocker shapes, each one a failing statement shape that needed its own rule, not the number of failing statements (one shape often fails hundreds of times).
They come from the work log of this spike, "open" means no rule exists yet.

| Cause | Count | Open | Dialect method or decision that solves it |
| --- | --- | --- | --- |
| Syntax | 19 | 1 | A per-dialect SQL translation step, already needed for PostgreSQL. |
| Missing function | 28 | 0 | PHP functions through `createFunction`, no per-statement rewrite. |
| `ALTER TABLE` limit | 8 | 1 | A DDL strategy decision, see below. |
| Type | 5 | 1 | `bindIds()` / `idParameterType()` and the id codec decision. |
| Schema introspection | 5 | 1 | A per-dialect schema query, as in `MakeVersionableMigrationHelper`. |
| Locking and transactions | 2 | 0 | A decision for the test and dev use case. |
| Test and install bootstrap | 2 | 2 | A driver-aware `DatabaseConnectionInformation`. |

### Syntax (19, 1 open)

Hex literals `0x..` (DML and DDL), backslash escapes in string literals, `<=>`, `UPDATE .. LIMIT`, `UPDATE .. JOIN`, `DELETE alias JOIN`, `UPDATE alias SET alias.col`, `INSERT .. SET`, `ON DUPLICATE KEY UPDATE`, `FOR UPDATE` and `LOCK IN SHARE MODE`, `@@variable`, `TRIM(TRAILING 'x' FROM y)`, `GROUP_CONCAT(.. SEPARATOR ..)`, single-argument `COALESCE`, `#` comments, index prefix lengths, `FOREIGN KEY name (col)`, `DROP INDEX x ON t`, `CONVERT(x, DATE)`.
Open: `Migration1773826242RenameAgenticCommerceSalesChannelType` (`UPDATE` with alias and `JOIN`, fails with `near sctt`).

The hex literal and the backslash rewrite must run after the PostgreSQL derived rewriters, whose tokenizers know the MySQL string syntax.
Running them first broke the `UpdateRewriter`.

### Missing functions (28, 0 open)

`CONCAT`, `CONCAT_WS`, `IF`, `CHAR_LENGTH`, `CHARACTER_LENGTH`, `REVERSE`, `DATABASE`, `LPAD`, `LOCATE`, `GREATEST`, `LEAST`, `MD5`, `SHA2`, `UUID`, `RAND`, `NOW`, `UTC_TIMESTAMP`, `CURDATE`, `UNIX_TIMESTAMP`, `DATE_FORMAT`, `FIND_IN_SET`, `SUBSTRING_INDEX`, `REGEXP`, `UNHEX`, `HEX` and the JSON helpers `JSON_UNQUOTE`, `JSON_CONTAINS`, `JSON_CONTAINS_PATH`, `JSON_ARRAY_APPEND`.
Two pitfalls: functions that return a different value per call (`UUID`, `RAND`, `NOW`, `UNIX_TIMESTAMP`, `UTC_TIMESTAMP`, `CURDATE`) must not be flagged deterministic, SQLite then evaluated `UUID()` once per statement and the unique key on `state_machine_transition.id` failed.
`HEX(NULL)` is `''` in SQLite but `NULL` in MySQL, the shim for `HEX` fixes the `LOWER(HEX(parent_id)) === null` checks in the DAL.

### `ALTER TABLE` limit (8, 1 open)

SQLite has no `ALTER COLUMN`, `MODIFY`, `CHANGE` with changed type, `ADD CONSTRAINT`, `ADD STORED` column or primary key change.
What the spike does:

1. `MODIFY`, `CHANGE` type and `ADD FOREIGN KEY`: patch the stored `CREATE TABLE` text with `PRAGMA writable_schema` and `schema_version` bump. `writable_schema = RESET` is needed, `OFF` leaves the writing connection with a stale schema.
2. `DROP PRIMARY KEY` and `ADD PRIMARY KEY`: a table rebuild (new table, copy, drop, rename, recreate indexes and triggers). `PRAGMA foreign_keys` is a no-op inside a transaction.
3. `DROP COLUMN` on an indexed column or a column used by a trigger: drop the dependent indexes and triggers first.
4. `AUTO_INCREMENT` on a non-primary-key column: an `AFTER INSERT` trigger plus a backfill, only an `INTEGER PRIMARY KEY` auto-increments.
5. Generated `STORED` through `ADD COLUMN`: `VIRTUAL` instead.
6. Index names are schema wide: every index gets a `table.` prefix, `TableHelper::indexExists` needed a SQLite branch.

Open: `Migration1595321666v3` (destructive) drops a column that an FK or a `CHECK` uses, SQLite answers "no such column" after the drop, a rebuild would fix it.

Decision: the `writable_schema` patch is unsupported territory for SQLite, it works with 3.51.2 but a wrong patch corrupts the file without an error.
A rebuild for every change is slower and bigger.
For anything beyond a throw-away dev or CI database, the migrations should be authored per dialect (see "Recommendation").

### Type (5, 1 open)

- A `BLOB` is never equal to a `TEXT` in SQLite. The DAL binds ids as bytes with the default string type on write and with `ArrayParameterType::BINARY` in `IN (?)` on read, so rows written by one path are invisible to the other (the sales channel was "not found"). The spike binds every `BINARY` parameter as text (`TextBindingStatement`), the cleaner fix is one canonical id representation, as in the hex id binding commits on the branch (`cc96946ac39`, `c20c6e630ae`), which was not tested together with the SQLite layer.
- `HEX(NULL)` (above) and the non-deterministic flag (above) count here as well.
- `NOW(6)` needs a variadic function that returns UTC with milliseconds.
- Open: `Migration1778072247AddDocumentBaseConfigTypedColumns` fails with "malformed JSON", `JSON_TYPE` and `JSON_UNQUOTE` on a non-JSON value raise in SQLite and return `NULL` or the value in MySQL.

### Schema introspection (5, 1 open)

`information_schema.columns` and `tables` (temp views), `KEY_COLUMN_USAGE` (emulated with `pragma_foreign_key_list` and a PHP function that parses the constraint name from the stored SQL), `SHOW` statements (`SqliteShowRewriter`), `TableHelper::indexExists`.
Open: DBAL's SQLite schema manager does not see generated columns, because `table_info` hides them.
`Migration1767604966UpdateTotalPriceOrderDeliveryPosition` and `Migration1767611523UpdateUnitPriceOrderDeliveryPosition` fail on it (`getColumnOfTable`), `pragma_table_xinfo` does show them (checked: `hidden = 2` for `total_price`, `unit_price`, `quantity`).

### Locking and transactions (2, 0 open)

- `FOR UPDATE` is stripped, SQLite locks the whole database on the first write instead. WAL and `busy_timeout` are set. This is fine for one process, not for the queue workers in parallel with web requests.
- DDL runs inside the migration transaction in SQLite (and is rolled back), where MySQL commits implicitly. Migrations that mix `PRAGMA foreign_keys` and transactions need the rebuild helper to run outside of them.

### Test and install bootstrap (2, 2 open)

- `bin/console system:install` fails at `DatabaseConnectionInformation::fromEnv`, which expects a host and a database name in the DSN. The spike used the console commands one by one instead (`database:migrate`, `user:create`, ...).
- The PHPUnit bootstrap calls the same method after appending `_test`, so `tests/integration` cannot start on SQLite (`Environment variable "DATABASE_URL" with value "mysql://localhostroot_test" is not valid`).

Other runtime blockers found after the migrations: `COALESCE(x)` with one argument, `GROUP_CONCAT .. SEPARATOR`, `TRIM(.. FROM ..)` and `#` comments in the context factory SQL, all counted above, each fixed in one rule.
`dal:refresh:index`, the storefront home page and the product write needed no further rule after those.

## Timing against MariaDB

Setup: same code, same container, `php -S` with one worker, one fresh database each, MariaDB database `shopware_spike_cmp` (installed with `system:install --basic-setup`, not the lane database).
Each number is the sum of 30 sequential requests in seconds, two runs.

| Request | SQLite run 1 | SQLite run 2 | MariaDB run 1 | MariaDB run 2 |
| --- | --- | --- | --- | --- |
| `GET /account/login` | 6.34 | 6.28 | 6.21 | 6.18 |
| `POST /api/search/product` (25, two associations) | 2.09 | 2.31 | 1.97 | 2.16 |
| `POST /api/product` (write) | 3.76 | 3.47 | 3.79 | 3.65 |

- SQLite is not faster for these requests, the difference is inside the noise, a request is dominated by PHP (kernel boot, Twig, DAL hydration), not by the database.
- Installing: the 910 regular and 632 destructive migrations run in 6 seconds on SQLite (the loop, 7 console runs).
  MariaDB `system:install --basic-setup` takes 12 seconds, but it includes the cache clear and the setup steps, so the numbers are not like-for-like.
- Tests: no test timing. `tests/unit` does not touch the database, so the platform makes no difference there, and the integration bootstrap does not start on SQLite (see above).

## Recommendation

SQLite for dev and CI is realistic only as a later, narrow goal, not as the next step.

What speaks for it:

- The route from an empty file to a working storefront, admin login and product write took one translation layer of about 1,200 lines, with no change to the DAL.
- The dialect interface of handoff C carried the DAL part (upsert, JSON extraction, group concat, id binding).
- Install time is short, and a database is a file, which suits a disposable test database.

What speaks against it, and what it costs:

1. Migrations are the problem. Every `ALTER TABLE` rule above is a rewrite of the migration, 5 of 1,542 migrations still fail, and the `writable_schema` patch can corrupt the file silently. A supported SQLite needs hand-written per-dialect migrations or one dialect-neutral schema definition for the core (the DBAL schema tools do not see generated columns and cannot alter columns either). That is the main cost: a permanent maintenance burden, because every new migration needs a test on a fourth platform (not estimated in days, the spike did not measure it).
2. The speed argument does not hold for the requests measured, and the test suite cannot be timed until the bootstrap works. Whether the integration tests gain anything is not measured.
3. One writer at a time: queue workers, the scheduled tasks and web requests in parallel contend for the database lock, so SQLite is fine for one process (a developer, a single CI job) and not for a lane like the PostgreSQL one.
4. Semantics differ in small ways that only show at runtime: `HEX(NULL)`, BLOB against TEXT, JSON functions that raise, `COALESCE` and `TRIM` forms, the collations (registered as PHP functions, slower than the MySQL ones).
5. The open list: 5 migrations, the DSN bootstrap, an unknown number of runtime shapes in the code paths not probed (checkout, product page, search, flows, the admin UI).

Suggested decision: keep SQLite out of the supported set for the first version, keep the spike code as an experiment branch, and revisit after the migrations have a dialect-neutral definition (the same work also removes the `writable_schema` patch and the MySQL-specific DDL for PostgreSQL).

## Commits (`instance/`, not pushed)

- `5e78d68af38`, `60ac9479054`, `077ac7d8ad3`, `3e3198c0f21`: `SqliteFactory`, `ConnectionFactory` branch, driver middleware, function shims, first DML rewrites.
- `dbe0ceaba38`: translation middleware, DDL rewriter, `SqliteDialect`.
- `24aeb7db777`: storefront, admin login and product write (TRIM, GROUP_CONCAT, COALESCE, comments, HEX, text binding, introspection views, PK rebuilds).
- `e5d246f6e63`: `SqlDialectFactory` returns `SqliteDialect`.
