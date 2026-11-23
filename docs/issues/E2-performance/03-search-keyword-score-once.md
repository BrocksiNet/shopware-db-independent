---
id: E2.03
type: Improvement
template: technical_todo.yaml
title: "Compute the search keyword score once per search request"
parent: E2
related: [E3.02]
findings: [23, 24]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23303"
---

## Technical TODO

A storefront search adds score queries to the criteria in `ProductSearchBuilder`: one `ScoreQuery` with an `EqualsFilter` on `product.searchKeywords.keyword` per search term, and one with a `ContainsFilter` for the original term.
`SqlQueryParser::parseContainsFilter()` turns the contains filter into `<field> LIKE '%term%'`, which cannot use an index.
`CriteriaQueryBuilder` builds the `_score` select as `SUM(...)/COUNT(pk)` with `HAVING _score >= :_minScore`.
`EntityAggregator::fetchAggregation()` clones the criteria for every aggregation, keeps the score queries, builds the same score subquery grouped by primary key and joins it as `score_table`.
The subquery with the `LIKE` filter on `product_search_keyword` is therefore evaluated once for the search and once for each aggregation.

In a proof of concept a search request sent 66 statements on PostgreSQL and 64 on MariaDB, and about 7 of them repeated this scan.
On PostgreSQL each scan was a sequential scan of 34,193 rows, 8.4 ms warm and 17 ms cold, about 56 ms per request in total.
On MariaDB the same statements took under 1 ms each.
The gain on MySQL and MariaDB is therefore not measured.

Technical TODO:

- [ ] Count the statements of a search request with aggregations on trunk and measure the time of the score subquery on MySQL and MariaDB.
- [ ] Evaluate the score once and hand the scored product ids to the aggregations, for example as a temporary id list or as a derived table that is built once.
- [ ] Keep the result of the search and of every aggregation identical, including the minimum score filter.
- [ ] Add a test that fixes the number of score evaluations for a search with aggregations.
- [ ] Decide separately whether the `LIKE '%term%'` filter stays; with a trigram index on PostgreSQL it ran in 0.1 to 0.2 ms instead of 8.4 ms, but keywords shorter than 3 characters still scan sequentially.

## Research notes (not for upstream)

- Findings: `docs/core-findings.md` rows 23 and 24 (row 24 is flagged "Idea, not measured"); measurements in `docs/25`.
- Trunk checked on `e9e18ef0e7b`:
  - `src/Core/Content/Product/SearchKeyword/ProductSearchBuilder.php`, around lines 67 to 80.
  - `src/Core/Framework/DataAbstractionLayer/Search/Parser/SqlQueryParser.php:155-166`.
  - `src/Core/Framework/DataAbstractionLayer/Dbal/CriteriaQueryBuilder.php:203-229`.
  - `src/Core/Framework/DataAbstractionLayer/Dbal/EntityAggregator.php:150-211`.
  All hold structurally.
- `search::detect-keywords` took 5.3 ms on PostgreSQL and 13.1 ms on MariaDB (`docs/25`).
- Aggregations on MariaDB ran in 0.6 to 1.0 ms, so the MySQL benefit may be small.
  If the measurement shows no gain on MySQL, this issue only pays on PostgreSQL and should move to E5.
- Related: E3.02 changes the total count of a paginated search and touches the same query builder.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261: `SqlQueryParser.php:155-166`, `CriteriaQueryBuilder.php:203-229` (`_score` select) and `EntityAggregator.php:136-211` (`fetchAggregation`, score_table join at 180-210) are unchanged in content; no relevant commit since ae0190f5892.
