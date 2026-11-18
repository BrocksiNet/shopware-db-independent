# DAL: where MySQL-specific SQL is generated

Source: sub-agent read of `instance/src/Core/Framework` at `ae0190f5892`. Every
line cited below was re-checked by hand. Paths are relative to
`src/Core/Framework/`; `DAL/` is `DataAbstractionLayer/`.

## Existing seams

The four storage interfaces are plain service definitions and can be replaced:

| Interface | Implementation | Wiring |
|---|---|---|
| `EntityReaderInterface` | `EntityReader` | `DependencyInjection/data-abstraction-layer.php:349` |
| `EntityAggregatorInterface` | `EntityAggregator` | same file `:363` |
| `EntitySearcherInterface` | `EntitySearcher` | same file `:375` |
| `EntityWriteGatewayInterface` | `EntityWriteGateway` | same file `:422` |

Below these interfaces everything is concrete: the classes get a `Connection`
and build SQL as strings. Swapping the four services alone would mean
duplicating all of that logic, so a dialect service inside them is the smaller
change.

## MySQL-specific generation points

| Location | Emits | PostgreSQL | Effort |
|---|---|---|---|
| `DAL/Dbal/EntityDefinitionQueryHelper.php:43` | `escape()` is static and quotes with backticks | double quotes | dialect helper; static call sites need the service |
| `Adapter/Database/MySQLFactory.php:107` | removes `ONLY_FULL_GROUP_BY` from `sql_mode` | PostgreSQL always enforces full GROUP BY | unknown until queries run, see open questions |
| `DAL/Dbal/EntityReader.php:515` | `GROUP_CONCAT(HEX(col) SEPARATOR '\|\|')` | `string_agg(col::text, '\|\|')` | dialect helper |
| `DAL/Dbal/EntityReader.php:1002` | `LOWER(HEX(col)) as \`key\`` | `col::text` (dashes to strip) | dialect helper |
| `DAL/Dbal/EntityReader.php:1030` | `SET @n = 0, @c = null` user variables as row counter for limited many-to-many loads | `ROW_NUMBER() OVER (PARTITION BY ...)` | structural |
| `DAL/Indexing/ManyToManyIdFieldUpdater.php:71` | `CONCAT('[', GROUP_CONCAT(JSON_QUOTE(LOWER(HEX(...)))), ']')` | `jsonb_agg(...)` | rewrite |
| `DAL/Dbal/FieldAccessorBuilder/JsonFieldAccessorBuilder.php:66,81` | `JSON_EXTRACT`, `IF(JSON_TYPE(...) != "NULL", ...)` | `->`, `->>`, `jsonb_typeof` | swap the accessor builder service |
| `DAL/Dbal/EntityWriteGateway.php:409` | `executeJsonUpdate()` builds `JSON_SET` statements | `jsonb_set` / `\|\|` | structural |
| `DAL/Doctrine/MultiInsertQueryQueue.php:101,105,147` | `INSERT IGNORE`, `REPLACE INTO`, `ON DUPLICATE KEY UPDATE` | `ON CONFLICT (...) DO NOTHING/UPDATE`; needs a conflict target the queue does not know today | structural |
| `DAL/Dbal/CriteriaQueryBuilder.php:222` | `HAVING _score >= :_minScore` on a select alias | aliases are not visible in HAVING; wrap in a subquery | structural |
| `DAL/Indexing/InheritanceUpdater.php:152` | `UPDATE ... JOIN ... SET ... = IFNULL(...)` | `UPDATE ... FROM ...`, `COALESCE` | rewrite |
| `DAL/Version/Cleanup/CleanupVersionTaskHandler.php:63,77` | `DELETE/UPDATE ... LIMIT 1000` | delete by `ctid`/id subquery | rewrite |
| `DAL/Dbal/EntityAggregator.php:307,311` | `CONVERT_TZ`, `DATE_FORMAT` for date histograms | `AT TIME ZONE`, `to_char` | dialect helper |
| `DAL/Search/Parser/SqlQueryParser.php:162` | `LIKE` relying on a case-insensitive collation | `ILIKE` or a case-insensitive collation | dialect helper plus schema decision |
| `DAL/Dbal/ForeignKeyConstraintViolationExceptionHandler.php:34` | matches the text `Integrity constraint violation: 1452` | SQLSTATE `23503` | dialect helper |
| `DAL/Doctrine/RetryableExceptionDetector.php:17,57` | MySQL error 1020 and a `SAVEPOINT ... does not exist` message regex | SQLSTATE `40001` / `40P01` | dialect helper |

## Ids

`DAL/Dbal/SchemaBuilder.php:90` maps `IdField` to `Types::BINARY`, and the read
path converts with `HEX()` in SQL (see above). With native `uuid` on PostgreSQL
ids are bound as strings and come back dashed, while Shopware's PHP side uses
32 hex characters without dashes. The conversion has to live in one place (the
dialect), not at each call site.

## SchemaBuilder

`DAL/Dbal/SchemaBuilder.php` builds a Doctrine schema from entity definitions
and sets `charset utf8mb4` (`:169`). The only user of the class found is
`DAL/MigrationQueryGenerator.php`. It truncates foreign key names at 64
characters (`:364`); PostgreSQL's identifier limit is 63 bytes.

## Proposed seam for the proof of concept

A `SqlDialect` service with a MySQL and a PostgreSQL implementation, covering:
identifier quoting, id to hex, id and id-list binding, group concat, JSON
extract and set, case-insensitive like, date format and time zone conversion,
upsert, limited delete, and error classification. `EntityDefinitionQueryHelper::escape`
delegates to it; the reader, searcher, aggregator, write gateway, query
builders, field resolvers, `MultiInsertQueryQueue`, the exception handlers and
the indexing updaters receive it.

## Open questions

- Which DAL queries only work because `ONLY_FULL_GROUP_BY` is removed. Needs a
  run against PostgreSQL.
- PostgreSQL aborts the whole transaction after a failed statement. Whether the
  retry logic in `DAL/Doctrine/RetryableTransaction.php` survives that needs a test.
- Longest generated table alias versus the 63-byte identifier limit.
- `Search/Term/*` scoring SQL and `VersionManager` were not read in detail.
