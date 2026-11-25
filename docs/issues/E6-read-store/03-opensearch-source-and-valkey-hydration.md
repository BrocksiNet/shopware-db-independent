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

- Option O1a (`_source` mode): store the compact `ProductDocument` in one field mapped `{"type": "object", "enabled": false}` and in `_source` includes alongside the existing `src/Elasticsearch` mapped fields so `ElasticsearchEntitySearcher` queries return hit IDs, aggregations, and full documents in one round-trip (0 product-read SQL on listing and search); custom fields are read from it and never add mapped fields. Include `mainCategories` (breadcrumb) in `ProductDocument` so product detail routes do not fall back to SQL for breadcrumbs (`docs/47`), and evaluate checking visibility on the document for `STATE_ELASTICSEARCH_AWARE` reads by ID.
- Mapping rule for custom fields (`docs/48`): a custom field is mapped (searchable, filterable, sortable) only when explicitly flagged (`include_in_search`, used in a product sorting or stream, or listed in `custom_fields_mapping`). Remove the blanket `custom_field_set.app_id IS NOT NULL` clause so apps flag their fields like plugins instead of exhausting `index.mapping.total_fields.limit` (~330 app fields today).
- Pre-index mapping guard (`docs/48`): before creating an index, count mapped fields; above a threshold of `index.mapping.total_fields.limit` (e.g. 80 %), log which custom fields cause it instead of failing mid-`es:index`.
- Document shape for custom fields (`docs/48`): store custom field values once per product plus per-language overrides only where a translation differs, resolving language fallback at read time (today's per-language copy inflates 1,000 × 20 documents 15×, from 13 KB to 198 KB).
- Byte-budgeted bulk indexing (`docs/48`): split OpenSearch `_bulk` requests by byte size (well below `http.max_content_length`, default 100 MB), not only by `SHOPWARE_ES_INDEXING_BATCH_SIZE` product count (at 5,000 × 20, one batch of 100 products hit 84.2 MB).
- Option O1b (Valkey `MGET` mode): implement a `ValkeyStorage` adapter behind `Storage` (stored per generation, 0.1–0.2 ms `get`, <1 ms `mget` of 24 products) as a fallback for OpenSearch availability or ultra-low-latency hydration — **not** for document-size reduction (Valkey stores the same document at 1.08–1.13× JSON size, `docs/48`).
- Keep `src/Elasticsearch`'s existing query builder, `displayGroup` collapsing, `postFilters`, language analyzers, and relevance scoring unchanged (no duplicate query-translation layer).
- Document storage overhead per custom field and language (`docs/48`): ~90 bytes of JSON per filled custom field and language plus ~560 bytes per language; index size per 150,000 products is **0.42 GB** (0 × 1) to **0.96 GB** (100 × 5) measured and **2.7 GB** (1,000 × 5) to **53.5 GB** (5,000 × 20) extrapolated (1 replica doubles it), with O1a rebuild time ~2× O1.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 39.
- Evidence: `docs/42-read-store-opensearch.md`, `docs/43-read-store-mongodb-valkey.md`, `docs/38-read-store-plan.md` (Conclusion), `docs/47-o1a-source-hydration.md` (O1a built & measured; effort estimate 4–7 person-weeks holds at the upper half), `docs/48-source-limits-custom-fields.md` (custom-field matrix 0..5,000 × 1..20), `docs/51-timing-reliability.md` (3e canonical paired CIs: 150k O1a 1.42× c=8 throughput, −84 % MySQL CPU).
- PoC code: `instance/src/Core/Framework/ReadStore/Adapter/OpenSearch/`, `Adapter/Valkey/`, `Adapter/OpenSearchValkey/`.
