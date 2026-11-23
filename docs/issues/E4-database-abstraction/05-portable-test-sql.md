---
id: E4.05
type: Improvement
template: technical_todo.yaml
title: "Remove MySQL-only SQL from tests"
parent: E4
related: [E4.01, E1.02, E1.10, E1.11]
findings: [15, 21, 26]
status: checked
upstream: ""
---

## Technical TODO

Several tests depend on MySQL behaviour that has nothing to do with what they test.
Known cases:

- `TreeIndexerTest::testIndexTree` resets rows with `WHERE HEX(id) IN (:ids)`.
  `HEX()` returns upper case and the ids are lower case, so this only matches under a case-insensitive collation.
  Bind the ids as ids instead.
- `VariantListingIndexerTest::fetchListing()` selects columns that are not in the `GROUP BY`.
  `VariantListingUpdaterTest` uses `IF(parent_id IS NULL, NULL, :draftVersion)` in an `INSERT ... SELECT`.
  Group in PHP and bind `NULL`.
- `EntityAggregatorTest` expects min, max and stats values such as `'250.0000'`, which is the `DECIMAL` scale of MySQL.
  Compare as numbers.
- Tests call `SET FOREIGN_KEY_CHECKS` and use `0x...` hex literals.

Technical TODO:

- [ ] Grep `tests/` for each construct above and list the files.
- [ ] Replace each use with SQL that returns the same result on every database, or with a PHP assertion.
- [ ] Keep every test meaning as is; run the touched tests on MySQL and MariaDB.
- [ ] Add a static rule that blocks new `SET FOREIGN_KEY_CHECKS` and `HEX(id) IN` in tests.

## Research notes (not for upstream)

- Findings: `docs/core-findings.md` rows 15, 21, 26; fixes in `docs/21` ("Wave 6", "Wave 7" item 1) and `docs/24` (SQLite).
- Trunk `e9e18ef0e7b`, checked by grep:
  - `HEX(id) IN` appears in one file under `tests` and `src`: `tests/integration/Core/Framework/DataAbstractionLayer/Dbal/TreeIndexerTest.php`.
  - `SET FOREIGN_KEY_CHECKS` appears in 16 files under `tests`.
  - `250.0000` appears in `tests/integration/Core/Framework/DataAbstractionLayer/Search/EntityAggregatorTest.php`.
  - `tests/integration/Core/Content/Product/DataAbstractionLayer/VariantListingUpdaterTest.php` and `.../Indexing/VariantListingIndexerTest.php` exist.
  I did not re-verify the `fetchListing()` and `IF()` content on trunk, nor the `PriceFieldTest` and `0x` literal cases; they come from `docs/21` and `docs/24`.
- SQLite result without the test fixes: 804 DAL tests, 795 pass (`docs/24`).
  `SET FOREIGN_KEY_CHECKS` threw inside a transaction on SQLite and left it open.
- Related: E1.10 (`LockValidator` and `rowCount()`) and E1.11 (untyped numeric parameters) are the production code side of the same SQLite findings.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261, verified: `TreeIndexerTest.php:284` (`WHERE HEX(id) IN (:ids)`), `VariantListingIndexerTest.php:342-351` (`fetchListing()` selects `id` and `option_ids` with `GROUP BY display_group`), `VariantListingUpdaterTest.php:147` (`IF()`), `EntityAggregatorTest.php:593` and `:630` (`'250.0000'`, `'50.0000'`), `SET FOREIGN_KEY_CHECKS` in 16 files, `0x...` literals in `EntityExtensionReadTest.php:74`, `WriterExtensionTest.php:59`, `JsonApiEncoderTest.php:85`.
- Removed from the draft because trunk does not show them: a cash rounding case in `EntityAggregatorTest` (no match for "rounding"), a test depending on `text + 0.0` (the expression exists only in production code, `EntityWriteGateway.php:462`, not in a test), and the implicit backslash escape of `LIKE` in tests (not found). `PriceFieldTest::testCashRoundingFilter` exists at line 500, but its dependence on MySQL scale was not shown.
