---
id: E6.05
type: Improvement
template: technical_todo.yaml
title: "Offload or cache surrounding SQL in ProductDetailRoute and ProductListingLoader"
parent: E6
related: [E6.04]
findings: [38]
status: draft
upstream: ""
---

## Technical TODO

Profiling `ProductDetailRoute::load()` and `ProductListingLoader::load()` with a read store serving 0 product-read SQL statements revealed that surrounding route SQL still dominates total database round-trips:

- **`ProductDetailRoute::load()` (full page)**: 30 SQL statements total → 7 product-read SQL eliminated, leaving **23 surrounding SQL statements** (`CategoryBreadcrumbBuilder` 5, `ProductConfiguratorLoader` 4, `CmsPageLoader` 14).
- **`ProductDetailRoute::load()` (`skipConfigurator=1&skipCmsPage=1`)**: 9 SQL statements total → 4 product-read SQL eliminated, leaving **5 breadcrumb SQL statements**.
- **`ProductListingLoader::load()`**: 20 SQL statements total → 12 product-read SQL eliminated, leaving **8 surrounding SQL statements** (category, navigation, sales-channel config).

Tasks:
1. Embed or cache category breadcrumbs and configurator option groups in the product read store (or short-lived Valkey/object cache keyed by category/parent ID).
2. Add a CMS page read-store document / object cache for `CmsPageLoader` (highest leverage: removes 14 SQL statements per full Detail request).
3. Measure before/after SQL count and Store API HTTP p50/p95 on `ProductDetailRoute` and `ProductListingRoute`.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 38.
- Evidence: `docs/44-read-store-integration.md` (Section 3, surrounding route SQL accounting).
