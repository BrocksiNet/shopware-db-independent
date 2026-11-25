---
id: E6.04
type: Story
template: story.yaml
title: "Store API route integration via .pre hooks, display-time live parts, and circuit-breaker DAL fallback"
parent: E6
related: [E6.01, E6.03, E6.05]
findings: [40]
status: draft
upstream: ""
---

## User story

As a storefront operator, I want `ProductDetailRoute`, `ProductListingRoute`, and `ProductSearchRoute` to read from the read store with zero breaking changes to existing Store API responses or plugins, while automatically falling back to the DAL on unsupported criteria or read-store outages.

## Acceptance criteria

- Integrate through Shopware's existing `ExtensionDispatcher` `.pre` hooks (`product-detail-route.load.pre`, `listing-loader.resolve.pre`) with zero edits to core route classes.
- Hydrate `ProductDocument` into `SalesChannelProductEntity` (BC default, Shape a) and run `ProductSubscriber::salesChannelLoaded()` live so dynamic rule prices, stock, `isNew`, and `sortedProperties` match DAL responses (<1–2 ms PHP, 0 extra SQL when warm).
- Fall back transparently to the DAL (with metrics/counters) on unsupported criteria (arbitrary plugin associations, custom query-time rounding, dynamic app price scripts) or store exceptions, protected by a short connect timeout (150–300 ms) and circuit breaker so outages add ~0 ms overhead once open.
- Verify Store API response equality against DAL across 50+ detail, listing, and search requests.
- Ensure HTTP cache invalidation never races ahead of OpenSearch `refresh_interval` (`docs/51` 3d: immediate invalidation under `refresh=false` poisoned Storefront HTTP cache in 5/5 trials with stale `_source` names next to fresh MySQL SEO URLs).
- Evaluate an opt-in slim DTO response profile (Shape b) for headless storefronts as a follow-up (cuts Listing JSON ~4x from 129–165 KB to 32 KB and saves 10–18 ms of `JsonEntityEncoder` CPU).

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 40.
- Evidence: `docs/44-read-store-integration.md` (50/50 identical on `sql-mysql`, 47/50 on `opensearch` with 5 clean `price-desc` fallbacks + 3 tied-price tie-breaks; SQL drops 30->23 on full Detail, 9->5 on skipCfg+Cms, 20->8 on Listing, 21->8 on Search), `docs/45-read-store-consistency.md` (Section 4.2 outage fallback), `docs/47-o1a-source-hydration.md` (O1a: 50/50 identical Store API responses, 46 from document + 4 counted SQL fallbacks, 0 product-read SQL on listing/search), `docs/51-timing-reliability.md` (3d HTTP cache poisoning proof).
- PoC code: `instance/src/Core/Framework/ReadStore/Integration/`.
