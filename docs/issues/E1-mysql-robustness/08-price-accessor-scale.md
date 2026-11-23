---
id: E1.08
type: Improvement
template: technical_todo.yaml
title: "Make scale and arithmetic of the price accessor explicit"
parent: E1
related: []
findings: [13]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23295"
---

## Technical TODO

Results of the price field accessor (`PriceFieldAccessorBuilder`, and the same cash rounding division in `Content/Product/DataAbstractionLayer/CheapestPrice/CheapestPriceAccessorBuilder`) depend on two MySQL details.

1. The scale of the cash rounding division.
   With cash rounding the accessor ends in `ROUND(#accessor# * #multiplier#, 0) / #multiplier#`.
   The scale of that division comes from the server variable `div_precision_increment`, which gives scale 4 on MySQL and MariaDB.
   `EntityAggregatorTest` asserts the resulting strings, for example `'50.0000'`, `'200.0000'` and `'250.0000'`.
2. The arithmetic type of the currency factor.
   The accessor reads the price with `JSON_UNQUOTE(JSON_EXTRACT(...))` and the code comment says that it casts to float indirectly by adding `0.0`; for other currencies the text is multiplied by `(SELECT factor FROM currency WHERE id = ...)`.
   The comparison therefore runs on a DOUBLE.
   In a proof of concept an exact decimal multiplication gave a different cash rounding result for the same input: `13.016666666666666 * 1.5` is `19.525` in double arithmetic, which rounds up, and `19.52499...` in exact arithmetic.
   `PriceFieldTest::testCashRoundingFilter` depends on the double result.

Proposed change:

- Cast the cash rounding division explicitly, for example `CAST(... AS DECIMAL(30, 4))`, so the scale no longer depends on `div_precision_increment`.
- Decide whether the currency factor is applied to a double or to a decimal, document the choice next to the code that already mentions the cast, and make the cast explicit.
- Keep the results of the existing tests unchanged on MySQL and MariaDB.

Acceptance:

- The scale of cash rounded price expressions is stated in the SQL.
- The arithmetic type of the factor is stated in the SQL and documented.
- `EntityAggregatorTest` and `PriceFieldTest::testCashRoundingFilter` pass unchanged on MySQL and MariaDB.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 13, `docs/21-dal-failures-postgresql.md` ("Wave 6", row for `EntityAggregatorTest` 7 of 8 and `PriceFieldTest::testCashRoundingFilter`; `CheapestPriceTest::testAggregation` row).
- PoC: `SqlDialect::decimalDivisionScale($sql, 4)` (PostgreSQL `CAST(... AS NUMERIC(30, 4))`, MySQL unchanged) and `SqlDialect::castToFloat()` (PostgreSQL `CAST(... AS double precision)`, MySQL unchanged) keep the MySQL results on the other databases.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Dbal/FieldAccessorBuilder/PriceFieldAccessorBuilder.php` lines 73 to 126 (comment on the cast to float at lines 73 to 77, `+ 0.0` at line 87, factor sub select at line 66, cash rounding division at line 125), `tests/integration/Core/Framework/DataAbstractionLayer/Search/EntityAggregatorTest.php` lines 593 to 717 (scale 4 strings), `tests/integration/Core/Framework/DataAbstractionLayer/Field/PriceFieldTest.php` line 500. The finding holds on trunk; the comment in the code already documents the `+ 0.0` cast, only the scale is undocumented.
- The `19.525` example is from the PoC; it was not recalculated on MySQL for this draft. Which type the product `price` JSON number has when multiplied by the factor (`text * decimal`) was not checked on a server.
- Checked statically against trunk c6ef9571261 (2026-11-23).
