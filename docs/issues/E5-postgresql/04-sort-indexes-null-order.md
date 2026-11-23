---
id: E5.04
type: Improvement
template: technical_todo.yaml
title: "Sort indexes with the NULL order the DAL emits"
parent: E5
related: [E1.07, E5.01]
findings: [19]
status: draft
upstream: ""
---

## Technical TODO

MySQL sorts `NULL` first in ascending order.
To keep this on PostgreSQL, where `NULL` sorts last in ascending order, every sort has to state the order (`ASC NULLS FIRST`, `DESC NULLS LAST`).
An explicit `NULLS FIRST` does not match a default btree index, so the planner stops using the index for the sort.
On 500,000 rows the same `ORDER BY ... LIMIT` took 0.060 ms with a matching default index and 34.3 ms with the explicit order.

In a proof of concept the statements of 7 request scenarios were logged: 1260 statements with an explicit NULL order, 39 distinct.
For 37 of them no index could serve the sort anyway (translation names through `COALESCE`, `MIN()` aggregates, `stock`, positions, priorities).
Two lose an index scan: the admin product search sorted by `productNumber`, `ORDER BY product.product_number ASC NULLS FIRST LIMIT 25`.
It took 9.2 ms instead of 6.0 ms per page on 1840 products.
With `CREATE INDEX ON product (product_number NULLS FIRST, version_id)` it took 0.1 ms.
The effect grows with the table.

Technical TODO:

- [ ] Find the sort columns that are used with an index today (admin lists by `productNumber`, `createdAt`, `name`) and check their plans with the explicit NULL order on PostgreSQL.
- [ ] Add indexes that match the emitted order, starting with `product (product_number NULLS FIRST, version_id)`.
- [ ] Ship them as PostgreSQL-only migrations.
- [ ] Check whether `product_number` can be `NOT NULL`, which makes the order irrelevant for that column (see E1.07).

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 19; statement analysis in `docs/13` ("NULL order check" and "Rerun after wave 6"), plan checks in `docs/21` and `docs/23`.
- Plan-check execution times (`docs/21`): 1,840 rows 0.237 ms, 50,000 rows 5.956 ms, 500,000 rows 28.284 ms; with the index 0.058, 0.080 and 0.071 ms.
- In the timed benchmark the NULLS FIRST index showed no visible effect on the admin search scenario (`docs/13`, rerun after wave 7), the gain is about 3 ms per request that sorts by product number at 1840 rows.
- The PoC migration is `Migration1795000200PostgreSqlProductNumberNullsFirstIndex`.
- Trunk `e9e18ef0e7b`: `CriteriaQueryBuilder::addSortings()` (line 106) adds `ORDER BY` with the sorting direction and no NULL clause, so on MySQL there is no explicit NULL order today; the explicit order exists only if E1.07 lands or on the PoC.
  The unique index `uniq.product.product_number__version_id` exists on `product` (`Migration1536233120Product.php:84`).
  I did not re-check on trunk where the "cuts last four characters" order parsing in `EntityReader` sits.
- Finding 22: `product_number` is nullable although the field is `Required`.
