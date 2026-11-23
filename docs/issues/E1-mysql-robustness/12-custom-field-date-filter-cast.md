---
id: E1.12
type: Improvement
template: technical_todo.yaml
title: "Date custom field filters cast the column but not the value"
parent: E1
related: [E1.11]
findings: [28]
status: draft
upstream: ""
---

## Technical TODO

`JsonFieldAccessorBuilder::getFieldAccessor()` (also used for custom fields through `CustomFieldsAccessorBuilder`) casts the JSON value of a datetime or date field:

```php
if ($field instanceof DateTimeField) {
    return \sprintf('CAST(JSON_UNQUOTE(%s) AS datetime(3))', $jsonValueExpr);
}

if ($field instanceof DateField) {
    return \sprintf('CAST(JSON_UNQUOTE(%s) AS DATE)', $jsonValueExpr);
}
```

The value of the filter is not cast.
`SqlQueryParser::parseEqualsFilter()` builds `<accessor> = :key` and binds the filter value as a string, as it was given (`'1990-01-01'`, `'1990-01-01T00:00:00.000000'`, `'1990-01-01 00:00:00.000'`).
The comparison is then a datetime against a string, and the result depends on how the server converts the string.
MySQL and MariaDB convert the string operand to a datetime, so the result is correct there today; the existing test `CustomFieldTest::testDateTimeEqualsCriteria` filters with `'1990-01-01'` and `'1990-01-01T00:00:00.000000'` and expects the same four entities for both.
In a proof of concept on a database that does not convert (SQLite), the column side was normalised to `2005-02-28 08:59:59.000`, the filter value stayed `1990-01-01`, and the equality never matched.

Proposed change:

- Cast the filter value the same way as the column, for example `CAST(:key AS datetime(3))` for datetime and `CAST(:key AS DATE)` for date custom fields, so the result no longer depends on the string format of the value or on the server's implicit conversion.

Acceptance:

- The SQL of an equals filter on a datetime or date custom field casts both sides.
- `CustomFieldTest::testDateTimeEqualsCriteria` and the JSON field filter tests pass on MySQL and MariaDB.

Not verified for this draft: the proposed cast has not been run on any engine.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 28, `docs/24-sqlite-dal.md` (failure table rows `CustomFieldTest::testDateTimeEqualsCriteria` and `JsonFieldTest::testNestedJsonFilter`; the second filter with `2005-02-28 08:59:59`, no fraction, matched nothing).
- Finding differs slightly on trunk: the cast is `datetime(3)`, not plain `DATETIME`.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Dbal/FieldAccessorBuilder/JsonFieldAccessorBuilder.php` lines 126 to 132, `Search/Parser/SqlQueryParser.php` lines 268 to 308 (no handling of date fields), `tests/integration/Core/Framework/DataAbstractionLayer/Field/CustomFieldTest.php` lines 673 to 712.
- The mismatch was only observed on SQLite in the PoC; there is no failing case on MySQL or MariaDB. Classified as bug in the findings table; typed here as Improvement (decided 2026-11-23) because MySQL and MariaDB give the right result today.
- The PoC fix on SQLite normalised the bound value through the dialect (`strftime` on the placeholder); the cast form above is a proposal, not run on any engine.
