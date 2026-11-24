---
id: E6.07
type: Bug
template: bug_report.yml
title: "DAL terms aggregation over keyword search counts products matching multiple interpreted terms twice"
parent: E6
related: [E2.03]
findings: [36]
status: draft
upstream: ""
---

## Shopware Version

trunk (6.8-dev)

## Affected area / extension

Platform(Default) — `ProductSearchBuilder`, `ProductSearchTermInterpreter`, `EntityAggregator`

## Actual behaviour

When a storefront keyword search runs through the SQL DAL (`ProductSearchBuilder` + `ProductSearchTermInterpreter`), `ProductSearchTermInterpreter` selects up to `relevant_keyword_count` (default 8) matching dictionary keywords. A product that owns more than one of those keywords matches multiple rows in `product_search_keyword`. While the ID query groups by `product.id` and returns each product once, a `TermsAggregation` (for example on `manufacturerId`) joins `product_search_keyword` without deduplicating `product.id`, counting multi-matching products two or more times.

Observed on a 5,000-product and 150,000-product catalog searching for `Hotel` (matches `hotel` plus 7 `hotel 000xx` dictionary tokens): 7 products were counted twice, inflating three manufacturer facet counts from `71 / 68 / 71` to `73 / 70 / 74` (and `2,167 / 2,165 / 2,168` to `2,169 / 2,167 / 2,171` at 150k products), disagreeing with OpenSearch and with the actual distinct hit set.

## Expected behaviour

`TermsAggregation` over a keyword search counts each distinct matching product exactly once, matching the hit set and matching OpenSearch.

## How to reproduce

1. Seed products where at least one product has both `hotel` and a second token matching `ProductSearchTermInterpreter` (e.g. `hotel 00007`) in `product_search_keyword`.
2. Run a `SalesChannelRepository::search()` on `product` with `Criteria::setTerm('Hotel')` and `new TermsAggregation('manufacturer', 'product.manufacturerId')` against MySQL/MariaDB/PostgreSQL (without OpenSearch).
3. Compare the `manufacturer` bucket counts against `COUNT(DISTINCT product.id)` of the matching hits (or against OpenSearch).

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 36.
- Evidence: `docs/39-read-store-baseline.md` ("O1 `--verify` differences", item 3) and `docs/40-read-store-port-and-document.md` (5 `dal-defect` entries in the 35-entry criteria corpus).
