---
id: E1.07
type: Improvement
template: technical_todo.yaml
title: "State the NULL order of `FieldSorting` in the SQL"
parent: E1
related: [E5.04]
findings: [14, 22]
status: checked
upstream: ""
---

## Technical TODO

The DAL never states a NULL order.
`CriteriaQueryBuilder::addSortings()` and `EntityAggregator::addSorting()` (which delegates to it) add `ORDER BY <accessor> ASC|DESC` only, so the order of NULL values is whatever the database does by default.
MySQL and MariaDB sort NULL as the smallest value: first for `ASC`, last for `DESC`.
Code and tests rely on it without saying so:

- `EntityAggregatorTest::testTermsAggregationWithSorting` sorts a terms aggregation by `product.categories.name` and expects the bucket with the empty key last for `DESC` and first for `ASC`.
- A sorted search decides which entities land on the first page.
  In a data set of a proof of concept, 834 of 1916 `product_translation` rows had a NULL `name`, and the admin product search sorted by `name ASC` returned a first page of 25 variants with a NULL name on MariaDB.
  A database with a different default NULL order returned 25 named products for the same request.
  The order inside the NULL rows is not defined on either database.
- `EntityReader` cuts the last four characters of an order part to find the direction (`substr((string) $sorting, 0, -4)` and `trim(substr((string) $sorting, -4))` in `fetchPaginatedOneToManyMapping()`), which breaks as soon as anything is appended after `ASC` or `DESC`, such as a NULL placement.

Proposed change:

- Decide and document the NULL order of `FieldSorting` (the current MySQL order is the compatible choice).
- State it in the SQL with an `IS NULL` sort key in front of the column (MySQL 8.4 and MariaDB 10.11 reject `NULLS FIRST` / `NULLS LAST` with a syntax error; databases that have the clause can use it in their dialect), in `CriteriaQueryBuilder::addSortings()` and the `COUNT` and `_score` sortings where it applies.
- Replace the four character cut in `EntityReader` by a parser of the order part (expression, direction, NULL placement).
- Add tests for the order of NULL values in sorted searches and aggregations.

Measured cost in a proof of concept on PostgreSQL 18 (500 000 row table, `ORDER BY num ... LIMIT 25`): an explicit `ASC NULLS FIRST` took 34.3 ms against 0.060 ms for plain `ASC` on the default btree index, and `DESC NULLS LAST` 32.5 ms against 0.034 ms for plain `DESC`.
An explicit NULL placement therefore needs a matching index to keep serving `ORDER BY ... LIMIT`.
Not measured on MySQL or MariaDB.

Related idea, needs a core decision: `product.product_number` is `VARCHAR(64) NULL` in the schema although `ProductDefinition` flags the field `Required`.
A `NOT NULL` column would make the NULL order of that sort irrelevant, and the default index would serve it.

Acceptance:

- The NULL order is documented and appears in the generated SQL of every `FieldSorting`.
- The result order of sorted searches containing NULL values is covered by a test.
- `EntityReader` no longer derives the direction from the last four characters.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` rows 14 and 22; `docs/21-dal-failures-postgresql.md` ("Wave 6" failure row for `testTermsAggregationWithSorting`; "Wave 7" item on `product_number`); `docs/23-postgresql-api-reads.md` section "NULL order" (admin search 25 NULL-name variants on MariaDB, 25 named products on PostgreSQL; index table).
- The decision on PostgreSQL in the PoC (`docs/02-decisions.md`, 2026-11-20) is to emit MySQL's order (`ASC NULLS FIRST`, `DESC NULLS LAST`) through `SqlDialect::sortDirectionWithMySqlNulls()`; `EntityReader::splitSortDirection()` replaced the four character cut. The index part is E5.04.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Dbal/CriteriaQueryBuilder.php` lines 106 to 153, `Dbal/EntityAggregator.php` lines 656 to 674, `Dbal/EntityReader.php` lines 1199 and 1212 (the four character cut), `tests/integration/Core/Framework/DataAbstractionLayer/Search/EntityAggregatorTest.php` line 299. `product_number VARCHAR(64) NULL` in `src/Core/Migration/V6_3/Migration1536233120Product.php` line 27, `NumberRangeField` with `Required` in `Content/Product/ProductDefinition.php` line 175; grep found no later migration that changes the column.
- The first-page example is from the PoC data set (`bench_pg`) and was not run on trunk.
- Checked 2026-11-23: `ORDER BY a DESC NULLS LAST` is a syntax error (1064) on MySQL 8.4.13 and MariaDB 10.11.16. Not measured: the effect of the `IS NULL` sort key on index use on MySQL.
- Checked statically against trunk c6ef9571261 (2026-11-23).
