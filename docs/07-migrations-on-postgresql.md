# Migrations on PostgreSQL

## Result

All 910 core migrations run on an empty PostgreSQL database through `system:install`.
The update and destructive timestamps are set for all 910 migrations (910 | 910 | 910).
The resulting `public` schema matches the lane schema: columns 2168/2168, indexes 726/726, constraints 1878/1878, 0 differences.
The whole check takes about 9 seconds.

## Approach

The migrations stay written in MySQL syntax.
A DDL rewriter in the driver middleware translates them at runtime, so future and plugin migrations need no hand work.
The rewriter is `Core/Framework/Adapter/Database/PostgreSQL/DdlRewriter.php`, next to `UpdateRewriter`.
It expects SQL that `MySQLToPostgreSQLTranslator` has already translated, which means identifiers are quoted with double quotes.
Code changes are limited to places where SQL cannot be translated (`information_schema`, `SHOW`, triggers, default comparisons).

Each migration runs in one PostgreSQL transaction.
Every DDL statement is wrapped in a savepoint, so migrations that catch a failing DDL statement keep working.

## How to run the check

Run one command from the research repo:

```bash
scripts/check-migrations-on-postgresql.sh
```

The script drops and creates the database `shopware_migrations`, applies `mysql-compat.sql` and runs `system:install --force --no-interaction`.
It requires equal counts in the migration table and then runs `scripts/compare-schema.py check`.
The container names, user, password and database can be overridden with `PG_CONTAINER`, `WEB_CONTAINER`, `PG_USER`, `PG_PASSWORD` and `CHECK_DATABASE`.

The expected schema lives in `scripts/expected-catalog.json`.
Regenerate it from a database with `scripts/compare-schema.py update <db>`.
The lane database `shopware` is only read, never changed.

## Failure classes and rules

### DDL rewriter rules

- Type mapping, the same as `docs/inventory/schema/mysql-to-pg-ddl.py`.
- `CREATE TABLE`, including `TEMPORARY`, optional index names, quoted `COLLATE` and column-level `UNIQUE` (index named after the column).
- `MODIFY` and `CHANGE`, including the smallint `USING col::integer::smallint` cast and `DROP DEFAULT` before `TYPE`.
- Generated columns, and `MODIFY ... GENERATED` as drop and re-add.
- `DROP EXPRESSION` and virtual column rebuilds, because PostgreSQL 18 has neither.
- Indexed virtual generated columns are rebuilt as STORED.
- `DROP TRIGGER`.
- A primary key `NOT NULL` guard.
- Foreign keys: unspecified `ON DELETE` and `ON UPDATE` become explicit `RESTRICT`.
- MySQL creates an implicit index for a foreign key only when no index starts with the key columns.
  The rewriter does the same and marks the implicit index with an index comment.
  A later index that covers the columns drops the implicit one, and explicit keys named like the foreign key are kept.
- `DEFAULT NULL` is dropped, JSON defaults become `'{}'` and `'[]'`.
- `SET DEFAULT` on boolean columns maps 0 and 1 to false and true.

### Other statement rewriters

- `UPDATE`: `IGNORE`, `LEFT JOIN`, `RIGHT JOIN`, `LIMIT` and `ORDER BY` without `LIMIT`.
- Multi-table `DELETE`.
- `INSERT ... SET`, `REPLACE ... SET`, and `INSERT ... SELECT` with placeholder casts.
- `SHOW` forms, with the boolean `Default` column mapped to `'1'` and `'0'`.
- `information_schema` queries.

### Translator rules

- `REGEXP`, `JSON_OBJECT` and `JSON_ARRAY` (with placeholder casts), `0x` literals and `JSON_EXTRACT` comparisons.
- `CONCAT` placeholders, `AS SIGNED` and `AS UNSIGNED`, and `@@vars`.

### Shims in `mysql-compat.sql`

`now(int)`, the `ci` collation, `database()`, `jsonb LIKE`, `replace(jsonb)`, `ifnull(text, bigint)`, `json_set`, `substring_index`, `json_contains_path`, `json_extract_text`, `json_remove`, jsonb scalar operators, `uuid()`, `json_valid`, `json_array_append` and a text to bytea cast.

### Platform helpers

- `MakeVersionableMigrationHelper`: the foreign key query and the drop-key name (it now also matches the PostgreSQL index name).
- `TableHelper::indexExists` fallback.
- `Column::normalizeDefault` maps boolean defaults to `'1'` and `'0'`.
  This fixes `Migration1782906166RepairUserActiveDefault`, which compared the default with `'0'` and skipped itself.
- IdCodec nil-uuid handling, `dropForeignKeyIfExists` and the savepoint around DDL.
- `system:install` and the setup classes accept a PostgreSQL connection.

### Migration changes

- `Migration1571990395UpdateDefaultStatusMailTemplates`
- `Migration1587039363AddImportExportLabelField`: behaviour change.
- `Migration1602494495SetUsersAsAdmins`
- `Migration1625816310AddDefaultToCartRuleIds`
- `Migration1627929168UpdatePriceFieldInProductTable`
- `Migration1654839361ProductDownloadMedia`: an upstream bug fix.

Everything else ran without edits.

## Remaining differences

The comparison covers columns, index definitions and constraint definitions of the `public` schema.
It ignores names, column order and comments, so the following differences are expected.

- Index and constraint names are shortened and prefixed with the table name, with a 63-character limit and an md5 suffix.
- Indexed virtual generated columns are STORED, which the Python script also emits.
- Column order differs after a drop and re-add.
- The migration database gets the newer shims from `mysql-compat.sql`, the lane does not.
- Implicit foreign key indexes carry an index comment.

## Caveats

- The type mapping exists twice: in the Python script, which reads MySQL `information_schema`, and in the PHP rewriter.
  They are verified equal only through the schema diff.
- The install log shows errors that the migrations catch themselves: `ADD PRIMARY KEY` on `app_config` (multiple primary keys), and `DROP CONSTRAINT` for `fk.sales_channel.home_cms_page_id` and `fk.product.main_variant_id`.
- The `SHOW` forms outside those the migrations use, and `SET FOREIGN_KEY_CHECKS` as a no-op, are covered by unit tests only.
- Unit tests: 719 tests pass over the migration, util, maintenance and database adapter suites.
- The PHPUnit bootstrap on a PostgreSQL `DATABASE_URL` (the bonus) is not done.
