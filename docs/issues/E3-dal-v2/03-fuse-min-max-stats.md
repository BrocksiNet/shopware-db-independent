---
id: E3.03
type: Improvement
template: technical_todo.yaml
title: "Fuse min and max aggregations of one field into one statement"
parent: E3
related: [E3.02]
findings: []
status: filed
upstream: "https://github.com/shopware/shopware/issues/23307"
---

## Technical TODO

`EntityAggregator::aggregate()` runs one statement per aggregation (`fetchAggregation()` is called in a loop over `Criteria::getAggregations()`).
A `MinAggregation` and a `MaxAggregation` on the same field, for example the price range of a listing, therefore send two statements with the same joins and filters.
`StatsAggregation` can already select both in one statement (`fetchMin()` and `fetchMax()` in `parseStatsAggregation()`).

Measured in a proof of concept on MySQL, MariaDB, PostgreSQL and SQLite: a wrapper that turns a min and a max aggregation of the same field into one stats aggregation and fills both results from it saves one statement in the search scenario with a minimum price, a maximum price and a manufacturer terms aggregation (7 to 6 statements).
It saves no statement in the product listing and the JSON criteria scenarios.
The measured time gain of the search scenario was 14 to 24 percent on the four engines (MySQL 49.89 to 42.00 ms, MariaDB 39.70 to 31.71 ms, PostgreSQL 71.55 to 61.75 ms, SQLite 129.22 to 97.76 ms), which is at most as large as the run to run noise of about 20 percent in that measurement, so no gain is claimed.

This is a weak improvement.
It is only worth doing if the change stays small and the existing aggregation tests cover it.
The decision is part of this issue.

TODO:

- [ ] Decide whether to do it: one statement per request is saved only when both aggregations exist on the same field and criteria, and no time gain was measured with confidence.
- [ ] If yes: merge the aggregations inside `EntityAggregator::aggregate()` before the loop, so the results are still returned under the original names and types (`MinResult`, `MaxResult`).
- [ ] Only merge aggregations that are equal in everything except their type and name, including the filter and the to-many path logic of `findToManyPath()`.
- [ ] Test that the result collection contains the original aggregation names in the original order.
- [ ] If no: close the issue with the measurement as the reason.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Lever A1 in `docs/33-orm-spike-dal-v2.md` ("Lever A1", "Reading the numbers": "A1 shows no gain outside the noise on S1 and S5, on S3 the count drops by one statement").
- Spike code: `src/Core/Framework/OrmSpike/DalV2/Read/StatsFusionAggregator.php` (86 lines) on `poc/orm-spike`, a wrapper around the aggregator, no copy of a DAL class.
  Verified equal to the DAL on S1, S3 and S5 on all four engines.
- Per-engine S3 numbers are in the text above (doc 33 lever table, DAL v2 untouched to stats fusion, 6 statements instead of 7); doc 33 does not claim them because of the noise.
- Trunk references: `EntityAggregator::aggregate()` line 84, `fetchAggregation()` line 136, `parseStatsAggregation()` line 431 (`review/finding-31`).
- Effort estimate from doc 33 (estimate): days.
