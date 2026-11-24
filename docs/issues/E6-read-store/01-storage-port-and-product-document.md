---
id: E6.01
type: Story
template: story.yaml
title: "Read store Storage port, versioned ProductDocument schema, and DocumentExtender extension point"
parent: E6
related: [E6.02, E6.03, E6.04]
findings: []
status: draft
upstream: ""
---

## User story

As a Shopware core and plugin developer, I want a minimal key-value/document `Storage` interface, a versioned `ProductDocument` contract decoupled from SQL table layout, and a `DocumentExtender` hook, so that storefront product reads can be served from interchangeable storage backends while plugins attach custom data in one place.

## Acceptance criteria

- Define a narrow `Storage` port (`setup`, `swap`, `liveGeneration`, `store`, `remove`, `get`, `mget`, `clear`, `destroy`) with a shared abstract contract test suite.
- Define a versioned `ProductDocument` schema (one document per product holding all translations, currency/rule price matrix, `cheapestPrice` buckets, `categoryTree`, `propertyIds`, `optionIds`, `visibilities`, `cover`/`media`, `manufacturer`, `tax`, `customFields`, and `extensions`) with language fallback resolved at read time.
- Provide an `ArrayStorage` adapter for fast unit tests and a `DocumentExtender` tagged service interface (`read_store.document_extender`) invoked per batch (1 query per batch, not per product).
- Native `customFields` require zero plugin code; an `EntityExtension` requires only a ~30-LOC `DocumentExtender` class.
- Document size stays bounded (~4.6 KB/product uncompressed, ~690 MiB for 150,000 products, ~350–450 MiB compressed in OpenSearch/MongoDB).

## Research notes (not for upstream)

- Source: `docs/40-read-store-port-and-document.md`, `docs/45-read-store-consistency.md` (Section 3, extension probe).
- PoC code: `instance/src/Core/Framework/ReadStore/Port/Storage.php`, `Document/ProductDocument.php`, `Builder/DocumentExtender.php`, `Probe/SamplePluginExtender.php`.
