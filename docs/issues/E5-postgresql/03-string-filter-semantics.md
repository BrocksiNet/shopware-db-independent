---
id: E5.03
type: Task
template: technical_todo.yaml
title: "Decide the string filter semantics on PostgreSQL"
parent: E5
related: [E1.09, E5.01]
findings: [17]
status: draft
upstream: ""
---

## Technical TODO

MySQL and MariaDB compare strings with a case-insensitive and accent-insensitive collation, so `EqualsFilter`, `ContainsFilter`, `PrefixFilter` and `SuffixFilter` match `'Müller'` for `'muller'`.
PostgreSQL has no equivalent that is also fast.
Using an ICU `ci` collation keeps the MySQL behaviour but is slow on large tables.
Measured on 500,000 rows:

| Filter | `ci` collation | `lower(col)` no index | `lower(col)` with index |
|---|---|---|---|
| equals | 6.2 ms | 56.1 ms | 0.07 ms |
| prefix | 224 ms | 57.1 ms | 6.3 ms |
| contains | 1567 ms | 61.7 ms | 7.6 ms (trigram index) |

Behaviour of the choices for `'Müller' = 'muller'`: true on the `ci` collation, on MariaDB and on MySQL 8.4, false with `lower()` on PostgreSQL and on SQLite.

A proof of concept took the fast option: `lower(col) COLLATE ucs_basic` on PostgreSQL, so filters are case-insensitive but accent-sensitive, with expression indexes on 15 columns such as `product.product_number` and `customer.email`.
Custom field string equals stay case-insensitive on every database.

Technical TODO:

- [ ] Decide, together with the outcome of E1.09 (is accent-insensitivity intended on MySQL), whether PostgreSQL gets accent-insensitive filters.
- [ ] Record the decision in an ADR, with the table above.
- [ ] If accent-sensitive is accepted, document the difference for merchants and extension developers.
- [ ] If accent-insensitive is required, evaluate an `unaccent` based index and its cost.
- [ ] Add tests that fix the chosen behaviour for equals, contains, prefix and suffix, including an accent case.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 17 (and row 18 for the missing statement of intent); measurements in `docs/23`, decision of 2026-11-20 in `docs/02`.
- PoC tests: `testStringFiltersAreCaseInsensitive` and `testStringFiltersAndAccents`.
- Trunk `e9e18ef0e7b`: `SqlQueryParser.php` emits `<field> LIKE :key` for the contains filter (lines 155-166), with prefix, suffix and equals in `parsePrefixFilter` (170), `parseSuffixFilter` (185) and `parseEqualsFilter` (268); there is no collation or `LOWER()` in the parser.
  I did not search trunk for an accent test; row 18 states there is none.
- Related: E1.09 decides the MySQL side of the same question.
