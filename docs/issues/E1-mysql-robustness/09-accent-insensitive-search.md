---
id: E1.09
type: Task
template: technical_todo.yaml
title: "Decide and test whether string filters are accent-insensitive"
parent: E1
related: [E5.03]
findings: [18]
status: draft
upstream: ""
---

## Technical TODO

The string filters of the DAL (`EqualsFilter`, `EqualsAnyFilter`, `ContainsFilter`, `PrefixFilter`, `SuffixFilter`, parsed in `SqlQueryParser`) compare the plain column with the plain value: `column = :value`, `column IN (:values)` and `column LIKE :value` with the wildcards escaped in PHP.
Case and accent handling come only from the collation of the column.
Tables built by `SchemaBuilder::buildSchemaOfDefinition()` use `utf8mb4_unicode_ci`, and custom field strings are compared with `COLLATE utf8mb4_unicode_ci` (`JsonFieldAccessorBuilder`).

Measured in a proof of concept on MariaDB 10.11 (`utf8mb4_unicode_ci`) and MySQL 8.4 (`utf8mb4_0900_ai_ci`): `'Müller' = 'muller'` is true on both.
A filter for `muller` therefore finds `Müller`.
On SQLite and on PostgreSQL with a case folding (`lower()`) comparison it does not.
`'MÜLLER' = 'müller'` is true on MySQL and MariaDB and false on SQLite.

Nothing in the code says whether accent-insensitive search is intended or a side effect of the collation, and no test asserts it (a search of `tests/` for `Müller`, `muller` and `accent` finds no test of the string filters).
A change of collation, of the column definition or of the server default would change search results without any failing test.

Proposed change:

- Decide and write down the intended behaviour of the string filters for case and for accents (the current behaviour is accent-insensitive and case-insensitive on MySQL and MariaDB).
- Add a test per filter type (`equals`, `equalsAny`, `contains`, `prefix`, `suffix`) that asserts it for a value with an umlaut and for case.
- Document the rule where the filters are described for developers.

Acceptance:

- A test asserts the accent and case behaviour of each string filter on MySQL and MariaDB.
- The behaviour is documented.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 18, `docs/23-postgresql-api-reads.md` section "String filters" (comparison table, lines 115 to 119).
- The PoC test `SqlQueryParserTest::testStringFiltersAndAccents` asserted accent insensitivity for everything except PostgreSQL; this test does not exist on trunk (grep for `Müller`, `muller` and `accent` in `tests/` finds nothing relevant), the name comes from the PoC branch (`docs/24-sqlite-dal.md` line 69). The statement "no test" holds on trunk.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Search/Parser/SqlQueryParser.php` lines 155 to 198 (LIKE filters), 268 to 308 (equals), `Dbal/SchemaBuilder.php` line 170, `Dbal/FieldAccessorBuilder/JsonFieldAccessorBuilder.php` line 135.
- Not checked: whether the developer documentation mentions the behaviour (docs repository not read), the collation of the real `product`, `customer` and other tables, which come from migrations and may differ from `SchemaBuilder`, and the collation of columns on a MySQL install with a different server default.
- PoC decision for PostgreSQL (`lower(col) COLLATE ucs_basic`, accent-sensitive, 2026-11-20): E5.03.
