---
id: E6.03
type: Story
template: story.yaml
title: "O1+ hydration: serve full ProductDocuments from OpenSearch _source or Valkey MGET"
parent: E6
related: [E6.01, E6.02, E6.04]
findings: [39]
status: draft
upstream: ""
---

## User story

As a hosting engineer running Shopware with OpenSearch, I want product detail, listing, and search routes to hydrate products directly from OpenSearch `_source` or Valkey `MGET` instead of re-querying MySQL after OpenSearch returns product IDs, so that storefront read traffic removes product-read load from the write database.

## Acceptance criteria

- Option O1a (`_source` mode): store the compact `ProductDocument` in OpenSearch `_source` alongside the existing `src/Elasticsearch` mapped fields so `ElasticsearchEntitySearcher` queries return both hit IDs/aggregations and full documents in a single round-trip (0 product-read SQL statements).
- Option O1b (Valkey `MGET` mode): implement a `ValkeyStorage` adapter behind `Storage` (stored per generation, 0.1–0.2 ms `get`, <1 ms `mget` of 24 products) and compose it with OpenSearch IDs/aggregations for detail, listing, search, wishlist, and cross-selling.
- Keep `src/Elasticsearch`'s existing query builder, `displayGroup` collapsing, `postFilters`, language analyzers, and relevance scoring unchanged (no duplicate query-translation layer).
- Measure and document storage overhead: ~454 MB OpenSearch index or ~780 MiB Valkey RAM per 150,000 products.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 39.
- Evidence: `docs/42-read-store-opensearch.md`, `docs/43-read-store-mongodb-valkey.md`, `docs/38-read-store-plan.md` (Conclusion).
- PoC code: `instance/src/Core/Framework/ReadStore/Adapter/OpenSearch/`, `Adapter/Valkey/`, `Adapter/OpenSearchValkey/`.
