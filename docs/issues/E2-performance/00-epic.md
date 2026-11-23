---
id: E2
type: Epic
template: epic.yaml
title: "Fewer statements and fewer deadlocks in product writes and search"
parent: ""
related: [E3]
findings: [10, 23, 24, 29]
status: draft
upstream: ""
---

## Problem we must solve

- One sync of 50 products runs about 475 single row `UPDATE product` statements from the product indexer updaters (category tree, display group, cheapest price, rating, DAL write), one per product and updater.
- Parallel product writes deadlock on shared `product` rows, because the indexer bulk updates and the per-product loops run in no fixed row order against the writer and against each other.
- A search request evaluates the keyword score subquery on `product_search_keyword` about seven times (search plus every aggregation), each time with a `LIKE '%term%'` filter that scans the whole table.

## WHY we need to solve it

Bulk imports, ERP syncs and storefront search are the hottest database paths of large shops.
Fewer statements cut round trips and index maintenance on every database, fewer deadlocks cut retries in parallel imports.

## Solution to the problem

- Batch the indexer updaters per updater (one `UPDATE ... WHERE id IN (...)` or one `CASE` per batch) (E2.01).
- Give the updaters one fixed row order, so concurrent writers lock rows in the same order (E2.02).
- Compute the scored product ids once per search request and reuse them in the aggregations (E2.03).

## WHO benefits

Merchants with large catalogs and frequent syncs, hosting partners (database load), developers of import tooling.

## Accessibility

Backend-only work required

## WHERE will we do it

Core platform: product indexer and its updaters (`ProductIndexer`, `ProductCategoryDenormalizer`, `CheapestPriceUpdater`, rating and display group updaters, inheritance and tree updaters), `ProductSearchBuilder`, `EntityAggregator`, `CriteriaQueryBuilder`.

## Out of scope

- The write path of the DAL itself (`EntityWriteGateway`), see epic E3.
- Index changes that only help PostgreSQL (epic E5).

## Acceptance criteria

- A 50 product sync sends at least an order of magnitude fewer `UPDATE product` statements than before, measured with a statement counter.
- A parallel product import benchmark shows no deadlocks caused by the indexer updaters.
- A search request with aggregations evaluates the keyword score once.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` rows 10, 23, 24, 29; `docs/19` (deadlocks), `docs/25` (search), `docs/26` (bulk write); `docs/27-final-report.md` "Required core changes" row 4.
- The related DAL write path levers (W1a, W1b) are in epic E3.
