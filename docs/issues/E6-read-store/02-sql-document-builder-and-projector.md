---
id: E6.02
type: Story
template: story.yaml
title: "Batch SQL ProductDocument builder, ReadStoreProjector, and referenced-entity sync listeners"
parent: E6
related: [E6.01, E6.03, E6.06]
findings: [37]
status: draft
upstream: ""
---

## User story

As a merchant running a large catalog, I want fast batch document rebuilds and reliable incremental projection across DAL writes, stock changes, variant inheritance, and referenced-entity renames, so that the read store stays fresh without overloading the write database.

## Acceptance criteria

- Implement `SqlDocumentBuilder` (batch SQL reads resolving parent/child inheritance, translations, price matrix, cheapest-price buckets, categories, properties, media, and `DocumentExtender`s), verified bit-for-bit equivalent to DAL hydration on all product fields.
- Implement `ReadStoreProjector` supporting `sync` (inline after indexer) and `queue` (deduplicated Symfony Messenger `async` message) modes plus a CLI blue/green `Rebuilder`.
- Subscribe to `ProductIndexerEvent` (expanding affected parent IDs to all sibling variants so variant price/config updates never leave stale sibling documents), `ProductStockAlteredEvent`, and `product.deleted`.
- Subscribe to low-cardinality referenced-entity writes/translations (`product_manufacturer`, `property_group_option`, `media`) to re-project affected products; route catalog-wide mutations (`tax`, `currency`) to an async blue/green rebuild instead of inline fan-out.
- Document the raw-SQL plugin write caveat and provide a scheduled reconciliation/rebuild command.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 37 (variant write omits sibling variants in `ProductIndexerEvent`).
- Evidence: `docs/40-read-store-port-and-document.md` (`SqlDocumentBuilder` 28.3 s / 5,297 docs/s vs `DalDocumentBuilder` 132.6 s — 4.68x faster on 150k products), `docs/45-read-store-consistency.md` (17-probe miss matrix, R6 lag 0.2–1.8 ms sync / 25–265 ms queue).
- PoC code: `instance/src/Core/Framework/ReadStore/Builder/SqlDocumentBuilder.php`, `Projector/ReadStoreProjector.php`, `Projector/ReadStoreProjectorSubscriber.php`.
