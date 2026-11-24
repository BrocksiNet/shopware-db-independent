---
id: E6
type: Epic
template: epic.yaml
title: "Storefront product read store (O1+: OpenSearch search + document hydration from _source or Valkey)"
parent: ""
related: [E2, E3]
findings: [36, 37, 38, 39, 40]
status: draft
upstream: ""
---

## Problem we must solve

Storefront product detail, listing, and search read directly from the normalized write tables in SQL via the DAL. Even with OpenSearch enabled today, `ElasticsearchEntitySearcher` returns only product IDs, totals, and aggregations, and `EntityRepository::_search()` immediately re-hydrates every page of entities from MySQL (`cloneForRead($ids)`). Under high concurrency or large catalogs (150,000+ products), SQL hydration and unindexed DAL search queries saturate the write database CPU and bind Store API read scalability directly to the write database schema.

## WHY we need to solve it

A proof of concept across 150,000 products showed that:

- Plain DAL and DAL v2 listing and search saturate an 8-core MySQL server at c=8 (10.4 req/s, p95 3.3 s, about 6.3 cores of MySQL CPU in the final timing block), whereas today's OpenSearch path (O1) serves 453.8 req/s at p95 35.4 ms with about one MySQL core, all of it the remaining SQL hydration (`docs/38-read-store-plan.md#conclusion`).
- Eliminating SQL product hydration by serving pre-assembled `ProductDocument`s from OpenSearch `_source` or Valkey `MGET` cuts product-read SQL statements to **0** on Detail and Listing, achieves sub-millisecond key-value detail/mget reads (0.1–0.2 ms in Valkey), and decouples storefront read scaling from the write schema.
- Building a full multi-engine query abstraction (translating arbitrary DAL `Criteria` to SQL JSON, MongoDB, and OpenSearch) has poor return on investment: SQL JSON adapters cannot match OpenSearch on 150k search/filter/aggregation queries, and OpenSearch's existing `src/Elasticsearch` query builder already solves Shopware's hardest query semantics (`displayGroup` collapsing, `postFilters`, analyzers, synonym/ngram search).
- Therefore the high-leverage architecture is **O1+**: keep Shopware's existing OpenSearch searcher/aggregator for query execution, introduce a small pluggable `Storage` key-value/document port (`get`/`mget`/`store`/`remove`, blue/green `setup`/`swap`) with OpenSearch `_source`, Valkey, and optional SQL JSON adapters, and keep the SQL write database as the sole source of truth.

## Solution to the problem

- Introduce a narrow `Storage` port and versioned, language-complete `ProductDocument` schema (one document per product) with a tagged `DocumentExtender` plugin extension point (E6.01).
- Build a batch SQL `ProductDocument` builder (`SqlDocumentBuilder`, ~4.7x faster than DAL hydration) and an event-driven `ReadStoreProjector` (`sync` / `queue`) with sibling-variant expansion and low-cardinality referenced-entity listeners (E6.02).
- Implement **O1+ hydration**: hydrate storefront product reads directly from OpenSearch `_source` or Valkey `MGET` instead of SQL `cloneForRead($ids)` (E6.03).
- Integrate into `ProductDetailRoute`, `ProductListingRoute`, and `ProductSearchRoute` via existing `.pre` route extension hooks with zero core route edits, display-time live calculation (`ProductSubscriber`), and circuit-breaker fallback to DAL (E6.04).
- Offload/cache the surrounding route SQL (`CategoryBreadcrumbBuilder`, `ProductConfiguratorLoader`, `CmsPageLoader` — 23 of 30 SQL statements on Detail) so end-to-end Store API latency realizes the full read-store win (E6.05).
- Harden blue/green generation swaps with grace-period garbage collection for pointer-based stores (E6.06).
- Fix the DAL keyword-search terms aggregation over-count bug (E6.07).

## WHO benefits

High-traffic merchants, agencies, and cloud/SaaS hosting teams running large catalogs (50k–1M+ SKUs) who need predictable storefront latency and lower write-database CPU without breaking existing Store API or plugin contracts.

## Accessibility

Backend-only work required

## WHERE will we do it

Core framework (`ReadStore` port, builder, projector), `Elasticsearch` bundle (`_source` document hydration), Store API product routes (`ProductDetailRoute`, `ProductListingLoader`, `ProductSearchRoute`), and developer documentation for `DocumentExtender`.

## Out of scope

- Replacing the DAL or the SQL write model (stays MySQL/MariaDB/PostgreSQL per E3–E5).
- Building a generic multi-engine query/aggregation translation layer (`FilterAware`/`AggregationAware`/`SearchAware`) for SQL JSON or MongoDB in core.
- Database-level CDC (Debezium / MySQL triggers) in phase 1 (documented as an Enterprise/SaaS follow-up if raw-SQL plugin writes require sub-second sync).
- Category/navigation, CMS page, and SEO read-store documents (tracked as next candidates after products prove out).

## Acceptance criteria

- `ProductDetailRoute`, `ProductListingRoute`, and `ProductSearchRoute` serve 0 product-read SQL statements when O1+ is enabled and produce byte-equivalent Store API responses in Entity shape (`SalesChannelProductEntity`), with automatic counted DAL fallback on unsupported criteria or store outage.
- Plugins can project custom fields (0 LOC) and `EntityExtension` attributes (`DocumentExtender`, ~30 LOC) into `ProductDocument` without modifying store adapters.
- Blue/green full rebuild of 150,000 products completes under concurrent storefront load with 0 failed or empty reads.
- Write-to-read lag is <10 ms in `sync` mode and <300 ms p50 in `queue` mode, covering DAL writes, parent/variant inheritance, `StockStorage::alter()`, deletes, version merges, and manufacturer/property/media renames.

## Research notes (not for upstream)

- Full Wave 9 evidence: `docs/38-read-store-plan.md` (Conclusion), `docs/39-read-store-baseline.md` through `docs/45-read-store-consistency.md`.
- Core findings: `docs/core-findings.md` rows 36, 37, 38, 39, 40.
- Working PoC branch: `poc/read-store` in `instance/` (`src/Core/Framework/ReadStore/`).
