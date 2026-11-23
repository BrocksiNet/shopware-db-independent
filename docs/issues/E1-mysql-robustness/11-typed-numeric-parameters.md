---
id: E1.11
type: Improvement
template: technical_todo.yaml
title: "Bind numeric criteria parameters with their type"
parent: E1
related: [E1.12]
findings: [27]
status: checked
upstream: ""
---

## Technical TODO

The DAL binds the values of numeric filters as strings.
`ParseResult::addParameter()` defaults its type argument to `ParameterType::STRING`:

```php
public function addParameter(string $key, mixed $value, ParameterType|ArrayParameterType $type = ParameterType::STRING): void
```

`SqlQueryParser::parseRangeFilter()` calls it without a type for `GT`, `GTE`, `LT` and `LTE`, so `price <= :value` receives the number as a string.
The same holds for the score threshold: `CriteriaQueryBuilder::addQueries()` calls `$query->setParameter('_minScore', $minScore)` without a type, and `EntityReader` sets the integer `limit` and `offset` parameters of the paginated association query without a type.

MySQL and MariaDB convert the string to a number on comparison.
In a proof of concept `pdo_sqlite` sent floats and ints as text, and the comparison of a number with text gave wrong results (8 tests of count mode and totals failed until floats and ints were bound as numbers).

Proposed change:

- Bind numeric values of range filters with `ParameterType::INTEGER` for integers, and cast explicitly where the placeholder is numeric and the value can be a float (for example `CAST(:value AS DECIMAL(...))`), or bind them through a typed `ParseResult::addParameter()` call chosen by the field type.
- Type the `_minScore`, `limit` and `offset` parameters.
- Keep the SQL results unchanged on MySQL and MariaDB.

Acceptance:

- A unit test asserts the parameter types of a `RangeFilter` on an int field and on a float field.
- The integration suite for range filters and aggregations passes on MySQL and MariaDB.

Not verified for this draft: how DBAL's `pdo_mysql` driver binds `ParameterType::INTEGER` for float values, and which field types need the explicit cast.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 27, `docs/24-sqlite-dal.md` (failure table: "Count mode and total counts (8): float and int bound as TEXT", fixed by `TextBindingStatement` in the PoC; line 20 on `castToFloat()`).
- Finding differs on trunk: the finding says "bound untyped". On trunk `ParseResult::addParameter()` and `ParseResult::getType()` default to `ParameterType::STRING`, and `CriteriaQueryBuilder::addFilter()` passes `$parsed->getType($key)` to `setParameter()`. So the values are bound explicitly as strings, not without a type; the effect is the same.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Search/Parser/ParseResult.php` lines 35 and 65 to 68, `Search/Parser/SqlQueryParser.php` lines 117 to 153, `Dbal/CriteriaQueryBuilder.php` lines 98 to 100 and 222 to 223, `Dbal/EntityReader.php` lines 1245 and 1246.
- Other binding sites (aggregations, custom field filters) were not enumerated.
- Checked statically against trunk c6ef9571261 (2026-11-23).
