---
id: E4.05
type: Improvement
template: technical_todo.yaml
title: "Remove MySQL-only SQL from tests"
parent: E4
related: [E4.01, E1.02, E1.10, E1.11]
findings: [15, 21, 26]
status: draft
upstream: ""
---

## Technical TODO

Several tests depend on MySQL behaviour that has nothing to do with what they test.
Known cases:

- `TreeIndexerTest::testIndexTree` resets rows with `WHERE HEX(id) IN (:ids)`.
  `HEX()` returns upper case and the ids are lower case, so this only matches under a case-insensitive collation.
  Bind the ids as ids instead.
- `VariantListingIndexerTest::fetchListing()` selects columns that are not in the `GROUP BY`.
  `VariantListingUpdaterTest` uses a bare `IF()` as a placeholder.
  Group in PHP and bind `NULL`.
- `EntityAggregatorTest` expects min, max and stats values such as `'250.0000'`, which is the `DECIMAL` scale of MySQL.
  Compare as numbers.
- Tests call `SET FOREIGN_KEY_CHECKS`, use `0x...` hex literals and rely on the implicit backslash escape of `LIKE`.
- `PriceFieldTest::testCashRoundingFilter` and a cash rounding case in `EntityAggregatorTest` depend on the scale and type of a division or of `text + 0.0`.

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
