# Phase 2: connection factory and schema in `public`

State: branch `poc/postgresql` in `instance/` (uncommitted working tree on top of `ae0190f5892`), PostgreSQL 18.7, DBAL 4.4.5, PHP 8.4.17.

## What changed in the core

| File | Change |
|---|---|
| `src/Core/Framework/Adapter/Database/ConnectionFactory.php` (new) | Reads the scheme of `DATABASE_URL` and delegates to `PostgreSQLFactory` (`pgsql`, `postgres`, `postgresql`, `pdo-pgsql`) or `MySQLFactory` (everything else). |
| `src/Core/Framework/Adapter/Database/PostgreSQLFactory.php` (new) | `pdo_pgsql` connection, charset `utf8`, `ATTR_STRINGIFY_FETCHES`, 5 second connect timeout, optional persistent connection. |
| `src/Core/Framework/Adapter/Database/PostgreSQLSessionMiddleware.php` (new) | Runs `SET TIME ZONE 'UTC'` after connect. |
| `Kernel.php`, `KernelFactory.php`, `KernelLifecycleManager.php`, `Plugin.php`, `DependencyInjection/services.php` | Call `ConnectionFactory` instead of `MySQLFactory`. |
| `Plugin/KernelPluginLoader/DbalKernelPluginLoader.php` | Query rewritten to portable SQL, see findings. |

`MySQLFactory` is untouched.
`MySQLFactory::hasNoDatabaseAvailable()` is still called directly by `EntityTemplateLoader` and `AppTemplateIterator`, it only compares against a placeholder URL.

## Verified

- `ConnectionFactory::create()` with `DATABASE_URL=$POSTGRES_URL` returns a connection on `PostgreSQL120Platform`, session time zone `UTC`.
  With the lane's MariaDB URL it returns `MariaDB1010Platform` as before.
- `docs/inventory/schema/generated-pg-schema.sql` loaded into `public` in one transaction (schema name replaced with `sed`): 250 tables, 418 foreign keys, collation `public.ci`.
- `bin/console about` and `bin/console system:config:get` boot the kernel against PostgreSQL without warnings.
  `bin/console about` and `plugin:list` still work against MariaDB.
- PHPUnit: `tests/unit/Core/Framework/Adapter/Database` and `tests/unit/Core/Framework/Plugin/KernelPluginLoader` (25 tests) and the two matching integration directories (40 tests, 3 skipped) pass on MariaDB.
- `php-cs-fixer` reports nothing for the touched files.
- Not run: PHPStan (its container cache `var/cache/static_phpstan_dev` is not built in the lane).
  No tests were written for the new classes yet.

## Findings

1. **pdo_pgsql has no init command.**
   MySQL sets time zone, `group_concat_max_len` and `sql_mode` through `Mysql::ATTR_INIT_COMMAND`.
   The DBAL `pdo_pgsql` driver builds its DSN from a fixed list of parameters (host, port, dbname, `ssl*`, `application_name`, `gssencmode`) and has no `options` parameter, so session settings need a driver middleware.
2. **Fetch types with `ATTR_STRINGIFY_FETCHES`.**
   `boolean` comes back as `'1'` / `'0'`, integers and numerics as strings, `bytea` as a raw binary string, `uuid` as a 36 character string with dashes, `jsonb` as normalised text (`{"a": 1}`, with a space).
   Booleans therefore behave like MySQL `TINYINT(1)` on read.
   In SQL they do not: `WHERE active = 1` fails with `operator does not exist: boolean = integer`.
3. **DBAL turns server-side prepares off for pdo_pgsql by default** (`Pgsql::ATTR_DISABLE_PREPARES`), unless the driver option is set to `false`.
4. **The first query on the boot path was MySQL only.**
   `DbalKernelPluginLoader` used a `#` comment (syntax error on PostgreSQL), backticks, `IF()` and unquoted camel case aliases.
   PostgreSQL folds unquoted aliases to lower case, so `AS baseClass` arrives as `baseclass`.
   The rewrite uses a `/* */` comment, `CASE WHEN`, no quoting and snake case column names mapped in PHP, and runs on both databases.
5. **No multi statement switch on PostgreSQL.**
   `createMigrationConnection()` only exists to enable `ATTR_MULTI_STATEMENTS` on MySQL.
   The PostgreSQL variant just returns a second, non-persistent connection.
6. **Not ported:** read replicas (`DATABASE_REPLICA_n_URL`) and the `DATABASE_SSL_*` variables.
   PostgreSQL TLS goes through the `sslmode` / `sslrootcert` / `sslcert` / `sslkey` DSN parameters.

## Blocker for switching the lane

The translator creates the schema only.
The base data of an installation comes from the migrations: 130 of the 910 core migration files contain inserts, and the fresh MariaDB install holds 2 languages, 250 countries, 9 currencies and 910 `migration` rows.
With an empty `public` schema the storefront and the installer cannot work, so the lane still points at MariaDB.

Next step: a data copy script MariaDB to PostgreSQL (binary ids to `uuid`, `tinyint(1)` to `boolean`, JSON text to `jsonb`), then set `DATABASE_URL` in `~/shopware-dev/instances/pg.yaml` to the PostgreSQL URL.
