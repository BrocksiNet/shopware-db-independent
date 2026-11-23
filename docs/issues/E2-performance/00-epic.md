---
id: E2
type: Story
template: story.yaml
title: "Fewer statements and fewer deadlocks in product writes and search"
parent: ""
related: [E3]
findings: [10, 23, 24, 29]
status: checked
upstream: ""
---

## User story

As a merchant with a large catalog and frequent ERP syncs, I want product imports and storefront search to send fewer statements and not deadlock, so that imports finish faster, need no retries and search stays fast under load.

Today:

- One sync of 50 products runs about 475 single row `UPDATE product` statements from the product indexer updaters (category tree, display group, cheapest price, rating, DAL write), one per product and updater.
- Parallel product writes deadlock on shared `product` rows, because the indexer bulk updates and the per-product loops run in no fixed row order against the writer and against each other.
- A search request evaluates the keyword score subquery on `product_search_keyword` about seven times (search plus every aggregation), each time with a `LIKE '%term%'` filter that scans the whole table.

The work is split into three sub-issues:

- Batch the indexer updaters per updater, one `UPDATE ... WHERE id IN (...)` or one `CASE` per batch (E2.01).
- Give the updaters one fixed row order, so concurrent writers lock rows in the same order (E2.02).
- Compute the scored product ids once per search request and reuse them in the aggregations (E2.03).

Out of scope: the write path of the DAL itself (`EntityWriteGateway`), see E3.

## Acceptance criteria

- A 50 product sync sends at least an order of magnitude fewer `UPDATE product` statements than before, measured with a statement counter.
- A parallel product import benchmark shows no deadlocks caused by the indexer updaters.
- A search request with aggregations evaluates the keyword score once.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` rows 10, 23, 24, 29; `docs/19` (deadlocks), `docs/25` (search), `docs/26` (bulk write); `docs/27-final-report.md` "Required core changes" row 4.
- The related DAL write path levers (W1a, W1b) are in epic E3.
- Converted from Epic to Story on 2026-11-23: three small items on one theme.
- Checked statically against trunk c6ef9571261 (2026-11-23).
