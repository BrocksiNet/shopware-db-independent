---
id: E1.04
type: Improvement
template: technical_todo.yaml
title: "Replace session variable row counting with `ROW_NUMBER() OVER (PARTITION BY ...)`"
parent: E1
related: []
findings: [6]
status: draft
upstream: ""
---

## Technical TODO

The paginated read of a many-to-many association (`EntityReader::loadManyToManyWithCriteria()`, used when the association criteria has a limit) counts rows per parent with MySQL user variables set inside an expression, and resets them with a separate statement:

```php
$this->connection->executeStatement('SET @n = 0, @c = null');
```

```php
'@n:=IF(@c=#table#.#source_column#, @n+1, IF(@c:=#table#.#source_column#,1,1)) as id_count'
```

(`buildManyToManyLimitQuery()`.)
MySQL 8 deprecates setting user variables in expressions.
The limit query only has `ORDER BY <source column>`, so the order of the rows inside one parent is not stated in the SQL.

The one-to-many path of the same class (`fetchPaginatedOneToManyMapping()`) already uses `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` on trunk.
The remaining place is the many-to-many path.

Proposed change:

- Build `id_count` in `buildManyToManyLimitQuery()` with `ROW_NUMBER() OVER (PARTITION BY <mapping>.<source column> ORDER BY <criteria sorting>, <reference column>)`.
- Remove the `SET @n = 0, @c = null` statement.
- Use the sorting of the association criteria in the window, as the one-to-many path does, so that the rows inside the limit are the first rows of the stated order.

Window functions are available on both supported minimum versions (MySQL 8.0.22 and MariaDB 10.11).

Acceptance:

- No `@n` or `@c` user variable remains in `EntityReader`.
- Existing tests of paginated many-to-many reads pass on MySQL and MariaDB.
- A test covers a many-to-many association with a limit and a sorting and asserts which rows are returned per parent.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 6, `docs/21-dal-failures-postgresql.md` (failure row `SET @n = 0, @c = null` for paginated many to many, 3 tests on PostgreSQL), `docs/summary.md`.
- Finding differs on trunk: the finding names "to-many limit per parent" in general. On trunk the one-to-many limit already uses `ROW_NUMBER()` (`EntityReader.php` line 1179, `fetchPaginatedOneToManyMapping()`, with a comment about a deterministic window order). Only the many-to-many limit still uses session variables: `EntityReader.php` line 1030 (`SET @n = 0, @c = null`) and line 1290 (`buildManyToManyLimitQuery()`). The issue text is narrowed accordingly.
- The method that holds the many-to-many code is `loadManyToManyWithCriteria()` (line 892).
- PoC: `SqlDialect::rowNumberPerPartition()`, used for PostgreSQL and SQLite; MySQL kept the variables in the PoC.
