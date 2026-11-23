---
id: E2.02
type: Improvement
template: technical_todo.yaml
title: "One fixed row order in the product indexer updaters against deadlocks"
parent: E2
related: [E2.01, E3.04]
findings: [10]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23302"
---

## Technical TODO

Parallel product writes can deadlock on `product` rows.
The updaters of `ProductIndexer::handle()` lock rows in different orders:

- `InheritanceUpdater`, `ManyToManyIdFieldUpdater` and `StockStorage::index` use bulk statements and lock in the order of the query plan.
- `ProductCategoryDenormalizer`, `CheapestPriceUpdater` and `RatingAverageUpdater` update one product at a time in the order of their input.
- The write gateway updates rows in payload order.

The updaters run in autocommit or in short transactions after the write has committed (`ProductCategoryDenormalizer` does its delete, updates and insert in one transaction), so two requests that touch the same products in a different order can wait for each other.
MySQL and MariaDB detect such a cycle at once and the retry logic handles it.
PostgreSQL waits for `deadlock_timeout` (default 1 s) before it aborts one transaction.

Technical TODO:

- [ ] Reproduce the deadlocks on trunk with parallel syncs that share products, and count them per run on MySQL and MariaDB.
- [ ] Decide on the mechanism and measure it against the baseline. Two mechanisms are known:
  - Sorting the batches of each updater by id.
  - Taking the row locks first, in id order, in one transaction around the updaters (`SELECT id FROM product WHERE version_id = :version AND id IN (:ids) ORDER BY id FOR UPDATE`, with the ids of the products, their children and their parents).
- [ ] Keep the locking in one place in `ProductIndexer`, so that new updaters inherit it.
- [ ] Add a parallel write test or benchmark that fails when an updater locks in another order.

Result of the two mechanisms in a proof of concept on PostgreSQL:

- Sorting the update commands by primary key and sorting the category map gave no reduction in deadlocks.
- Locking the rows up front in id order, inside one `RetryableTransaction`, reduced the deadlocks from 31 to 0 in a parallel run and raised the throughput from 1.59 to 3.09 requests per second.
- The trigger in the benchmark data were two products that were visible in all six sales channels.
- The lock up front adds about 40 ms to a sequential request of 50 products.
  The cause was not isolated.

So a fixed order inside each updater alone is not shown to be enough, and the issue has to check this on MySQL and MariaDB before it commits to one mechanism.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 10; measurements in `docs/19`, cost in `docs/26`.
- Baseline in `docs/19`: 7 to 22 deadlocks per parallel run on PostgreSQL and 1 to 5 on MariaDB.
  All deadlocks were on `product`.
- The lock is `ProductIndexer::withProductRowLocks()` in the proof of concept.
  It was applied on PostgreSQL only, because MySQL and MariaDB detect the cycle immediately.
  With `--dedupe` (no duplicate products in the list) it was 0 deadlocks before and after, 5.02 to 5.72 requests per second.
  An earlier informal session went from 45 deadlocks to 0.
- Trunk checked on `e9e18ef0e7b`: `ProductIndexer::handle()` runs the updaters in sequence (lines 199 to 262) and has no row lock step.
  Locking precedent with `FOR UPDATE` on trunk: `ChildCountUpdater.php:64` and `ProductStreamUpdater.php:263` (the latter with `ORDER BY id`).
- The per product loops exist as described for E2.01 (same files).
- The claim "fixed order in updaters removes the deadlocks" is the proposal of finding 10 and is not proven by `docs/19`; this is why the Technical TODO starts with a measurement.
- Related: E2.01 reduces the number of statements, which also shortens the lock windows.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261: `ProductIndexer::handle()` is at lines 182 to 268, the updaters at lines 199 to 262 still run in sequence without a row lock step. `FOR UPDATE` precedents unchanged: `ChildCountUpdater.php:64`, `ProductStreamUpdater.php:263`. Since commit cd82d5c58f8 the category tree rewrite is one transaction, which holds its row locks longer than before.
