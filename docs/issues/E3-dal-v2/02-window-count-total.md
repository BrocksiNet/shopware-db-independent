---
id: E3.02
type: Improvement
template: technical_todo.yaml
title: "Return the exact total of a paginated search with a window count"
parent: E3
related: [E1.04, E3.03]
findings: [32]
status: checked
upstream: ""
---

## Technical TODO

A paginated search with an exact total count (`Criteria::TOTAL_COUNT_MODE_EXACT` and a limit) runs two statements: the id statement of `EntitySearcher::search()` and a second `SELECT COUNT(*) FROM (<same query>) total` in `EntitySearcher::getTotalCount()`.
Both statements run the same joins and filters.

Trunk already avoids the second statement in two cases:

- A partial last page (fewer rows than the limit) gives the total as offset plus row count (`getTotalCount()`).
- A scored search with an exact total and a limit adds `COUNT(*) OVER() AS _total` through `buildWindowTotalQuery()` (https://github.com/shopware/shopware/pull/22937).

A search without a score field and a full page still runs the count statement.
This is the case for every request that asks for an exact total, for example `total-count-mode=1` in a criteria request.

Measured in a proof of concept on MySQL, MariaDB, PostgreSQL and SQLite, with `COUNT(*) OVER() as __total` in the id statement for every exact count with a limit and no score field:

- Product search with a term, five manufacturer filters, three aggregations and a page of 24: median 15 to 43 percent lower on the four engines (MySQL 49.89 to 42.56 ms, MariaDB 39.70 to 30.76 ms, PostgreSQL 71.55 to 41.09 ms, SQLite 129.22 to 108.41 ms), statements 7 to 6.
- Criteria from a JSON request with filters, sorting, limit 10 and total count mode 1: median 29 to 39 percent lower (MySQL 25.72 to 15.77 ms, MariaDB 25.20 to 17.86 ms, PostgreSQL 36.70 to 24.46 ms, SQLite 61.49 to 41.91 ms), statements 4 to 3.
- Product listing of a category with a page of 24: statements 4 to 3, MySQL 9.08 to 7.49 ms.

The gain on the MySQL and SQLite search (15 and 16 percent) is inside the measurement noise of that run (about 20 percent), the statement count is not.

TODO:

- [ ] Extend the window count of `EntitySearcher::search()` from the scored case to every search with `TOTAL_COUNT_MODE_EXACT`, a limit and no score field.
- [ ] Keep the existing fallback to the `COUNT(*)` statement for an empty page with an offset, because no row carries the total then.
- [ ] Decide whether the window count is added to the id statement itself or through an outer query as `buildWindowTotalQuery()` does (the outer query is needed there because of the score ranking).
- [ ] Test every combination that changes the row count of the id statement: group fields, to-many filters and sorting, post filters, `ids`, offset beyond the last page, limit 1.
- [ ] Compare the total with the old `COUNT(*)` statement in an integration test for each of these combinations.
- [ ] Re-measure on trunk on MySQL and MariaDB with a production sized catalog, with a selective and a non-selective filter, before the change is merged.
- [ ] Release notes: the SQL text of the id statement changes (extra `_total` column).

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261: same line numbers (`search()` 43, `buildWindowTotalQuery()` 221, `getTotalCount()` 271, `WINDOW_TOTAL` 34).
  The window count condition is `$scored && TOTAL_COUNT_MODE_EXACT && limit !== null` (`Dbal/EntitySearcher.php:93-95`), group fields are not part of it, so the draft text was corrected.
- Finding 32 in `docs/core-findings.md`, lever C1 in `docs/33-orm-spike-dal-v2.md` ("Lever C1", lever table in "Timings").
- Spike code: `src/Core/Framework/OrmSpike/DalV2/Read/WindowCountSearcher.php` on `poc/orm-spike`, a copy of `EntitySearcher` with 33 changed lines.
  It puts `COUNT(*) OVER() as __total` straight into the id statement; trunk's scored variant wraps the query in an outer query instead.
- Scenario ids: S1 listing (4 to 3 statements), S3 search (7 to 6), S5 criteria JSON (4 to 3), S2 and S4 not affected.
- Trunk references (`e9e18ef0e7b` plus the E3.01 fix commit, `review/finding-31`): `EntitySearcher::search()` line 43, `buildWindowTotalQuery()` line 221, `getTotalCount()` line 271, constant `WINDOW_TOTAL` line 34.
  The window count for scored searches is in trunk, so finding 32 as written in the docs is narrower now: it still applies to searches without a score field.
- Window functions are already used in this class (`ROW_NUMBER() OVER(PARTITION BY ...)` in `buildScoreRankedQuery()`), so the change adds no new minimum database version on top of that.
- The MariaDB 10.11 and MySQL 8.0.22 window function support in finding 32 comes from the finding text, not re-checked here.
- Effort estimate from doc 33 (estimate): days, needs the count fallback tests per engine.
- Timings are medians of 50 iterations with 5 warm-up calls, `APP_ENV=prod`, "DAL v2 untouched" against the lever alone, from the lever table of doc 33.
