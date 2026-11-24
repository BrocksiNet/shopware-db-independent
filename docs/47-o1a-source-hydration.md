# 47 O1a: full product document hydrated from OpenSearch `_source`

Wave 10, handoff A.
Question: doc 46 "What is not proven", point 1: is O1+ with `_source` hydration end to end as fast and as correct as wave 9 inferred?

## Status

Not answered yet: the code is built and committed, the measurements are blocked.
`instance-opensearch-1` (heap `-Xms4g -Xmx4g`) was OOM-killed three times on 2026-11-24 (exit 137, `OOMKilled=true`), the last time during the first `es:index` of this handoff.
The podman VM has 15.9 GB, about 60 containers of other sw-dev lanes run, and `free -m` showed 0.5 to 3.8 GB available, less than the 4 GB heap plus JVM overhead.
Stopping the other lanes with the wave 10 lock procedure was refused in this session, so no index exists and no number below rests on a run.
Point 1 stays "not proven" until the steps in "Open" run.

## Design

### Where the document goes

One extra field in the existing product index: `rs_document`, mapped as `{"type": "object", "enabled": false}`.
OpenSearch keeps it in `_source` only: no inverted index, no doc values, no mapped sub-fields, so it adds no field count and cannot change query semantics.
The `_source` includes of the product index grow from `id, autoIncrement` to `id, autoIncrement, rs_document` (`ElasticsearchProductDefinition::getMapping()`).
`ElasticsearchProductDefinition::fetch()` fills it with wave 9's `SqlDocumentBuilder::build()`, the same builder with the same `DocumentExtender`s as every other read store (doc 40), so the document equals the projector's document by construction.
All of it sits behind `SHOPWARE_ES_SOURCE_DOCUMENT` (default `0`): with `0` the mapping, `_source` and `fetch()` are exactly O1.

Query fields, `displayGroup` collapsing, `postFilters`, aggregations, analyzers and word search are not touched: they still read the existing indexed fields.

### How the document reaches the route

`SalesChannelRepository::_search()` runs the search (OpenSearch returns ids), then `read(cloneForRead($ids))`, which calls `EntityReaderInterface::read()` and then dispatches the loaded events.
O1a keeps that flow and replaces only the SQL read:

1. `ElasticsearchEntitySearchHydrator` takes `rs_document` out of every hit's `_source` and puts it into a request-scoped `SourceDocumentBuffer` (reset by `kernel.reset`).
   It removes the field from the hit data, so the full document never lands in the `search` extension of the entities.
2. `SourceDocumentEntityReader` decorates `EntityReaderInterface`.
   For `SalesChannelProductDefinition`, the live version and an ids-only criteria it takes the documents from the buffer.
   Ids that are not in the buffer (a read without a search, for example detail by id) come from one `_mget` on the product alias with `_source_includes=rs_document`.
3. Wave 9's `DocumentHydrator` turns the documents into `SalesChannelProductEntity` objects (shape (a) of doc 44) through a new event-free method.
   `categories` and `tags` are read by id from the `categoryIds` and `tagIds` of the document, without a product query.
4. `SalesChannelRepository::read()` dispatches the loaded events on these entities as before, so live prices and purchase limits are computed at display time; stock and availability come from the document, as in wave 9.

Everything else goes to the inner SQL reader unchanged and is counted by reason: filters, sortings, aggregations, partial fields or a limit on the read criteria, a non-live version, associations the document does not hold, and ids without a document (the product indexer skips products without visibilities).

No change to `SalesChannelRepository`, `EntityRepository` or the DAL write path.

## Code

Branch `poc/wave10` in `instance/`, commit `df32669d50c` `feat(elasticsearch): write full product document into _source and read it back (O1a)`.

- `src/Elasticsearch/Product/ElasticsearchProductDefinition.php`: mapping, `_source` includes, `fetch()`.
- `src/Elasticsearch/Product/SourceDocument/`: `SourceDocument` (field name), `SourceDocumentBuffer`, `SourceDocumentEntityReader`.
- `src/Elasticsearch/Framework/DataAbstractionLayer/ElasticsearchEntitySearchHydrator.php`: hits to buffer.
- `src/Elasticsearch/DependencyInjection/services.php`: wiring, env default `SHOPWARE_ES_SOURCE_DOCUMENT=0`.
- Core, with the reason:
  - `DocumentHydrator::hydrateEntitiesWithoutEvents()`: the repository dispatches the events, so the hydrator must not dispatch them a second time.
  - `SourceDocumentReaderSwitch` (interface) and an `o1a` mode in `read-store:bench:integration`: the bench switches between O1 and O1a in one process, and core must not depend on the Elasticsearch bundle (PHPStan rule).

Checked: PHPStan is clean on all touched files, php-cs-fixer applied, the prod container compiles with the decorator, and the existing unit tests `ElasticsearchProductDefinitionTest` and `ElasticsearchEntitySearchHydratorTest` pass (19 tests).
Not checked yet: anything that needs an index.

## Open

Every measurement of the handoff, in this order, once OpenSearch can run:

1. Build `rs_w10_o1_read_store_large_` (O1) and `rs_w10_o1a_read_store_large_` (O1a) with `es:index --no-queue --only=product` and compare size and rebuild time at 150,000 products.
2. Projector: a `Storage` adapter that writes `{"doc": {"rs_document": ...}}` partial updates into the product alias, then the doc 45 miss probes.
3. Equality: `orm-spike:bench --verify` with the O1a env, `read-store:bench:integration --store=o1a --mode=equality` (O1 against O1a), the corpus.
4. Statements per request and where they come from, R1 to R4 and c=8 against O1 and `store-opensearch-valkey`, `_mget` against Valkey for detail.

The helper `/tmp/wave10-a/env.sh <db>` defines `a_console o1|o1a|plain <console args>` with separate cache directories and prefixes `rs_w10_o1_<db>_` and `rs_w10_o1a_<db>_`.
