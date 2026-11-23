---
id: E2.01
type: Improvement
template: technical_todo.yaml
title: "Batch the single row UPDATE product statements of the product indexer updaters"
parent: E2
related: [E3.04, E2.02]
findings: [29]
status: checked
upstream: ""
---

## Technical TODO

`ProductIndexer::handle()` runs its updaters after the write has committed.
Several of them send one `UPDATE product` per product inside a loop:

- `ProductCategoryDenormalizer` runs `UPDATE product SET category_tree = :tree WHERE id = :id AND version_id = :version` once per product.
- `CheapestPriceUpdater` runs `UPDATE product SET cheapest_price = :price ...` and the `cheapest_price_accessor` update once per product.
- `RatingAverageUpdater` runs `UPDATE product SET rating_average = :average ...` once per distinct average.
- `VariantListingUpdater` runs its `display_group` updates once per parent.

A sync of 50 products through `POST /api/_action/sync` sent about 475 `UPDATE product` statements in one request.
Of these, 158 set `category_tree`, 50 come from the DAL write itself, 50 set `cheapest_price`, 87 set `display_group` and 41 set `rating_average`.
The remaining statements were not attributed to an updater.

Technical TODO:

- [ ] Count `UPDATE product` statements per updater for a sync of 50 products on trunk and record the numbers in the issue.
- [ ] Write the `category_tree`, `cheapest_price` and `rating_average` values with one statement per batch, either `UPDATE ... WHERE id IN (...)` or a `CASE` expression, or a multi row upsert through `MultiInsertQueryQueue`.
- [ ] Do the same for the `display_group` updates of `VariantListingUpdater`.
- [ ] Keep the version condition on every batch statement.
- [ ] Add a test that fixes the statement count of a multi product index run.
- [ ] Check that MySQL and MariaDB return the same data as before and that the timing does not get worse.

## Research notes (not for upstream)

- Findings: `docs/core-findings.md` row 29; counts and timings in `docs/26`.
- Trunk checked on `e9e18ef0e7b` (checkout `review/finding-31`), all four loops still exist:
  - `ProductCategoryDenormalizer.php:80` prepares the update, lines 82-84 run it per product in a `RetryableTransaction`.
  - `CheapestPriceUpdater.php:47` and `:52`, loop at lines 74-107; it already reads the existing accessors in one SELECT.
  - `RatingAverageUpdater.php:35` is already one bulk `UPDATE ... rating_average = NULL`; the per average update at line 59 is looped at lines 62-68.
  - `VariantListingUpdater.php:49`, `:54`, `:59` and `:108` (the last one per parent, with `SHA2`).
- The 475 statements are measured on MariaDB and PostgreSQL alike (`docs/26`).
  The listed parts sum to 386, the doc does not attribute the other 89.
- On PostgreSQL, the updates took 188 ms against 117 ms on MariaDB, and only 7 percent were HOT updates with 18 indexes on `product` (`docs/26`).
  `fillfactor` 70 raised HOT to 46 percent with little timing effect.
  Timing differences below about 10 percent are not reliable in that benchmark.
- `VariantListingUpdater` and `VariantListingIndexer` (87 `display_group` updates) were not changed in the proof of concept, so there is no measured gain for them.
- No gain from batching is measured yet, only the statement counts.
- Related: E3.04 batches the update commands of the write gateway (the 50 DAL write statements), E2.02 covers the row order of these updaters.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- On trunk c6ef9571261 `ProductCategoryDenormalizer.php:71-87` runs the DELETE, the per product `UPDATE` loop and the tree insert in one `RetryableTransaction` (commit cd82d5c58f8, #23117); the per product loop is unchanged. Line numbers of the other updaters are unchanged since e9e18ef0e7b.
