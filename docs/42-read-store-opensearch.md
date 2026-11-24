# Read store: OpenSearch adapter

Status: milestone 2 complete, written by handoff O of wave 9.
The adapter passes the contract suite, `--verify`, the 35-entry criteria corpus, and both `orm_spike` and `read_store_large` sanity benchmarks.
The O1a decision is made from the code and is in the section "O1a versus O2".

Code lives in `instance/src/Core/Framework/ReadStore/Adapter/OpenSearch/` (commits `e1a9257bc5a`, `636bd51`, and `8aea9bb` in `instance/`).
The contract test is `instance/tests/unit/Core/Framework/ReadStore/Adapter/OpenSearch/OpenSearchStorageTest.php`.
It ran against OpenSearch 2.19.7 (`instance-opensearch-1`).

## Contract result

52 tests, 195 assertions, 51 pass, 1 incomplete, 0 fail.
The test skips when `opensearch:9200` is unreachable.
It only creates and deletes indices with the prefix `rs_test_<random>_`.

Milestone 2 fixes (`636bd51` and `8aea9bb`):

- Added `l` (language id) to `rs.k` entries and enforced K's 1-filter context-language scoring rule inside the Painless score script.
- Added exact `value_count` for `Count('id')`, `Min`/`Max` on `BOOL` (`shippingFree`), and ascending-key tie-breaking for `Terms` with a limit.
- Added exact scored collapse via `terms` + `top_hits(size: 1, _source: false, docvalue_fields)` + `mget` (enabling `R3b`, `search-name-asc`, and `search-price-range`), plus `limit === 0` collapse support and 1-sort + `id ASC` native collapse.
- Added `$this->client->indices()->refresh(['index' => $new])` before `updateAliases()` in `swap()` (`8aea9bb`) after `read_store_large` rebuild showed 149,500 instead of 150,000 searchable docs in the 1 s refresh window right after swap.

The incomplete test is `FilterContract::testCollapseByCheapestPriceAlwaysUsesTheMinimum`.
The adapter throws `NotSupportedByEngine`: the reference orders collapse groups by the minimum price, native `collapse` orders groups by the top hit, so a descending sort cannot be exact.
This is intended behaviour, not a defect.

## Layout

Every document is stored as indexed `_source` plus an `rs` object that holds derived values.

| Key | Content | Used for |
| --- | --- | --- |
| `_source` (original document) | the port document unchanged | hydration of `get`, `mget` |
| `rs.f` | folded (lowercased) values, `rs.f.kw.<lang>` keywords | equals, contains, prefix, range on numbers and dates |
| `rs.s` | hex ICU sort keys (collator `root`, primary strength) | string sort and string range |
| `rs.n` | list length | empty list checks |
| `rs.g` | collapse group, sentinel `~null` | native `collapse` |
| `rs.k` | keyword and ranking list, `enabled: false` | read by the score script through `params['_source']` |

All fields are addressed through `FieldResolver`, so language, currency and rule scoped keys and the price rounding rule (`roundsLikeCurrency()`) are handled in one place.
The mapping uses dynamic templates restricted to the JSON types `long` and `double`, because a template without `match_mapping_type` also matches objects and fails with a mapper parsing exception.
Index settings: 1 shard, 0 replicas, `max_result_window` 100000, `total_fields.limit` 20000.

## Generations

Index `<prefix><name>_<gen>`, live alias `<prefix><name>`.
The live generation is the index that carries the alias, there is no pending alias.
Pending generations are all other indices matching `<alias>_*`.
Swap is one `_aliases` call (remove the old index, add the new one), then the old index is deleted.
Prefix must match `^rs_[a-z0-9_]*\z`, so the adapter cannot touch other indices.
Production prefix is `rs_os_`, name `product`.
Writes use `_bulk`; the `refresh` constructor flag makes writes visible immediately (tests only).
`get` and `mget` go through `mget` on the alias and are realtime.
`clear` is a `_delete_by_query` on the alias.
`destroy` deletes only the indices it lists itself.

## Capability matrix (standalone adapter)

| Feature | Support | Notes |
| --- | --- | --- |
| equals, equalsAny, range, not, and/or | yes | positive and negative query translation to keep three-valued logic |
| null semantics | yes | `known()` and `coalesced()` paths |
| contains | yes | wildcard on the folded keyword |
| prefix | yes | on the folded keyword |
| string range and string sort | yes | ICU sort keys |
| word search and ranking | yes | script score over keywords, sum over all languages |
| `displayGroup` collapse | partly | native `collapse` on `rs.g.<field>`, exact total through cardinality |
| collapse by `cheapestPrice` descending | no | `NotSupportedByEngine` |
| collapse without or with several sortings | no | `NotSupportedByEngine` |
| collapse with a group count of 40000 or more | no | cardinality is only exact below `precision_threshold` 40000 |
| postFilters | yes | aggregations run as `filter` wrapper aggregations |
| Min, Max, Avg, Sum, Stats | INT and FLOAT only | Sum and Avg may differ in the last float digits from `array_sum` |
| Count (distinct) | yes, not ANY or OBJECT | cardinality, throws at 40000 or more |
| Terms | ID, LIST, INT, FLOAT, BOOL, single path | size 60000, throws when `sum_other_doc_count` is above 0; null bucket from a sibling filter agg |
| translation fallback | yes | resolved per language chain by `FieldResolver`, stored per language at index time |
| price and cheapestPrice with a differing rounding | `NotSupportedByEngine` | handled by `FieldResolver` |

## Gaps and concerns

- The reference orders Terms results at the limit by key descending when counts tie.
  The adapter replicates this in PHP, which depends on an undocumented behaviour of the reference.
- Collapse without sortings is rejected, because the reference picks the representative in storage order.
- Without sortings the adapter returns id order; the reference returns storage order.
  Search without sortings defaults to score descending, the reference returns document order.
  No contract test depends on either.
- `ANY` fields (custom fields, extensions) only answer non-numeric string candidates.
- Booleans and lists are not mirrored into `rs.f`.
- Min and Max on strings, dates and booleans are unsupported.
- Scores are float32.
- Keywords longer than 32000 bytes throw at index time.
- ICU sort keys can order strings differently than the MySQL collation.
- `cheapestPrice` creates one field per rule, currency and accessor, so `total_fields.limit` has to be raised (20000 now).
- Bulk failures are thrown as `ReadStoreException::invalidCriteria`, because the port has no factory for an engine failure.
  That is a port concern, K decides.
- The DI definition in `o.php` needs the `OpenSearch\Client` service from the Elasticsearch bundle (accepted by K).

## Rebuild time, index size, refresh lag

Not measured, no benchmarks were run in this phase.
What the code determines:

- Index size: each document stores `_source` plus the `rs` object.
  Per language the folded values and keywords are stored again, and a hex sort key is stored per sortable string, so the index will be larger than the plain `_source`.
  The `rs.k` list has `enabled: false`, so it costs only `_source` space, not index structures.
- Refresh interval: the constructor takes `refreshInterval`, default `1s`.
  Reads through `get` and `mget` are realtime and do not wait for a refresh, search and aggregations see a write after the next refresh (at most the interval).
  Bulk writes during a rebuild into a pending generation can use a longer interval; the swap makes the new generation visible only after a refresh of it.
- Rebuild: a generation is built in a new index, so the live index keeps serving and a swap is atomic.
  The time depends on the bulk size and the document transformation in PHP, to be measured at milestone 2.

## Comparison: standalone port adapter, O1a, SEAL

O1a means reusing `src/Elasticsearch` (criteria parser, searcher, aggregator) and hydrating from `_source`.
All paths in the O1a column are relative to `instance/src/Elasticsearch/`.

| Aspect | Standalone port adapter (this) | O1a: `src/Elasticsearch` plus `_source` | SEAL OpenSearch adapter |
| --- | --- | --- | --- |
| Query input | `StoreCriteria` | DAL `Criteria` plus `EntityDefinition`; `ElasticsearchHelper::allowSearch` only answers for criteria with `Criteria::STATE_ELASTICSEARCH_AWARE` (`Framework/ElasticsearchHelper.php:85-95`) | SEAL `Search` conditions |
| Conditions | all port filters, three-valued null logic, contains, prefix | all DAL filters through `CriteriaParser::parseFilter` (`Framework/DataAbstractionLayer/CriteriaParser.php:180-191`, unknown filters throw `unsupportedFilter`); `ContainsFilter` is a `WildcardQuery` `*value*`, per language chain in a `DisMaxQuery` (`CriteriaParser.php:673-695`) | Identifier, Search, Equal, NotEqual, GT, GTE, LT, LTE, In, NotIn, Geo, And, Or; no Not, Contains, Prefix, null-aware equality |
| postFilters | yes | yes (`ElasticsearchHelper::addPostFilters`, line 135) | no |
| Filters, queries, ids | translated to `bool` filters | `addFilters` wraps all filters in one AND `MultiFilter` as a `FILTER` clause (`ElasticsearchHelper.php:118-133`); ids become an `EqualsAnyFilter('id')` (`:98-116`) | ids and conditions |
| `displayGroup` collapse | native collapse with exact total, limits above | native `collapse` (nested groupings via `inner_hits`, `CriteriaParser.php:175-188`) plus a `CardinalityAggregation` total in the searcher | `distinct` is native collapse, no exact total |
| Word search | script score on keywords, all languages | `buildTermQuery` of the entity definition, added through `addTerm` with an optional `core.search.minScore` (`ElasticsearchHelper.php:152-172`, `:264-272`); `ProductSearchBuilder` only resets the queries and sets `criteria->setTerm()` (`Product/ProductSearchBuilder.php:29-51`) | `multi_match` on a query string only |
| Score queries | not part of the port | `addQueries` adds `ScoreQuery` filters as `should` clauses with boost, `fuzziness` 2 on `MatchQuery` (`ElasticsearchHelper.php:174-214`) | none |
| Translation fallback | resolved per language chain by `FieldResolver`, stored per language at index time | one index for all languages, translated fields are objects keyed by language id, searched through the context, parent and default language (ADR `adr/2023-04-11-new-language-inheritance-mechanism-for-opensearch.md`, sections "Decision" and "Searching"); `ElasticsearchFieldMapper::translated` fills null child values from the parent items (`Framework/ElasticsearchFieldMapper.php:45-74`); `ElasticsearchFieldBuilder::translated` builds one mapping entry per language with a language analyzer (`Framework/ElasticsearchFieldBuilder.php:88-128`) | none, static field schema |
| Custom fields | `ANY` fields, string candidates only | per language object, typed from the custom field set (`ElasticsearchFieldBuilder::customFields` line 135, `getCustomFieldsMapping` line 187) | `JsonObjectField`, not queryable |
| Aggregations | Min, Max, Avg, Sum, Stats, Count, Terms | all DAL aggregations through `ElasticsearchEntityAggregator`, same `Helper` filters, `size` 0 and `track_total_hits` false (`Framework/DataAbstractionLayer/ElasticsearchEntityAggregator.php:82-94`); the result is hydrated into the DAL aggregation collection | only CountFacet (terms) and MinMaxFacet |
| Sort | field direction, ids position, score, always id tiebreak | `addSortings` parses every `FieldSorting` (`ElasticsearchHelper.php:216-223`) | plain field direction, no missing control, no tiebreak, no script sort |
| Result size | up to the window with a window guard | `size` is `MAX_LIMIT` 10000 when no limit is set (`Framework/DataAbstractionLayer/ElasticsearchEntitySearcher.php:33`, `:123`) | limit and offset |
| Hydration | `_source` holds the port document | the searcher returns ids and scores; `_source` of the product index holds only `id` and `autoIncrement` unless `SHOPWARE_ES_EXCLUDE_SOURCE` is set to true (config `Resources/config/packages/elasticsearch.yaml:136`, `:309`) or the environment is dev or test (`Product/ElasticsearchProductDefinition.php:181-183`) | documents stored marshalled in `_source` |
| Document shape | port `Document` | the ES product document of `ElasticsearchProductDefinition::getMapping` (lines 53-186): names, prices, ids of associations, visibility fields, not the entity graph | the schema the caller defines |
| Mapping | dynamic templates, key families per language, currency, rule | fixed properties, dynamic templates for prices, `cheapest_price_rule*` and long to double (`ElasticsearchProductDefinition.php:150-179`) | `dynamic: strict`, integer and float types |
| Generations | index per generation behind an alias, swap | index name is `<prefix>_<entity>` (`ElasticsearchHelper::getIndexName`, line 58) with alias handling of the indexer | no alias, create and drop an index per name |
| Cost to adopt | new code (this adapter), needs the port | reuse of mapping, indexer and parser, but the query path takes DAL `Criteria`, so it is a second path next to the port and needs the `_source` change | dependency plus schema mapping, would need extensions for most Shopware criteria |

SEAL sources read: `OpensearchSearcher.php` and `OpensearchSchemaManager.php` of the SEAL checkout (HEAD `3708776`, 2026-11-03).

## O1a versus O2 (decision from code)

Question: is O1a the same code as the standalone adapter?
No.
The two share ideas (native `collapse`, cardinality for the total, `filter` aggregations for postFilters, language chain lookups), but not code or data shape.

Evidence:

- O1a takes a DAL `Criteria` and an `EntityDefinition`, and every parser step resolves fields through the DAL definition (`ElasticsearchHelper.php:98-133`, `CriteriaParser.php:180-191`).
  The port takes `StoreCriteria` and resolves fields through `FieldResolver`.
  A prototype would need a translation `StoreCriteria` to DAL `Criteria`, which only exists as far as the port's field names match DAL names.
- O1a queries the ES product document, field names are `name.<languageId>`, `price.<currencyId>...`, `visibility_<salesChannelId>` and so on (`ElasticsearchProductDefinition.php:53-143`).
  The port document has other keys (`rs` object, per language and rule key families).
  `_source` of an O1a index is therefore not the port `Document`, even with the line 181 change.
  What `_source` can contain is whatever `fetch()` writes, a subset of the product (no media, no cross selling, no full association data), so it cannot serve the full documents of the read store without extending the indexer.
- The ES indexer writes `<prefix>_product` indices.
  My rules limit me to indices starting with `rs_`, and the lane's `rs_o1_*` indices belong to handoff P, so I cannot create or fill a product index for O1a without touching indices I must not touch.

Conclusion: a `store-opensearch-source` prototype adds nothing the code reading does not already answer.
What O1a would give is the existing ids plus aggregations path (O1, already a baseline of handoff P) plus a `_source` that holds a reduced ES product document once `SHOPWARE_ES_EXCLUDE_SOURCE` is true.
Whether that reduced document is enough for a listing is a question for the milestone 2 timings and for F, not for another adapter.
If K wants the prototype anyway, the minimal change is the flag on line 181 (already a config value) and a hydration step that reads `hits[]._source` in `ElasticsearchEntitySearcher`.
It can be built when handoff P frees an index prefix for it.

## Timings, index sizes, and corpus (milestone 2)

All milestone 2 timings below are sanity runs (`other lanes stopped: no`, `APP_ENV=prod`, MySQL 8.4 write DB).
Canonical stopped-lanes timings belong to handoff F.

### `--verify` and 35-entry criteria corpus

- **`orm_spike` `--verify`**: S1, S2, S3, R4, S5 all OK; R3b matches every hit and aggregation except DAL finding 36 (`manufacturers` count 71 vs DAL 73).
- **`rs_k_corpus` (35 entries)**: **27 match, 5 dal-defect, 3 fallback, 0 diff**.
  The 3 fallbacks are `criteria-term` and `criteria-association-field` (bridge limits, shared by every store) plus `listing-price-desc` (collapse sorted by `cheapestPrice DESC`, rejected by design because native `collapse` orders groups by top hit rather than minimum price).

### Rebuild and index size

| Dataset | Products | R7 rebuild | Docs/s | Write-DB stmts | Index store size (`_cat/indices`) | O1 (`dal-opensearch`) index size |
|---|---|---|---|---|---|---|
| `orm_spike` | 5,000 | 5.1 s | 989 | 204 | 14.1 MB (1 shard, 0 replicas) | 6.9 MB (40,080 docs) |
| `read_store_large` | 150,000 | 98.8 s | 1,518 | 6,004 | **454.0 MB** (1 shard, 0 replicas) | 190.8 MB (1,196,268 docs) |

The standalone OpenSearch store holds full `_source` documents plus derived `rs.f`/`rs.s`/`rs.k` fields in 454 MB on disk for 150,000 products (~2.4× the O1 index size, and 3.5× smaller than MySQL 8.4's 1,576 MiB table).
With `refreshInterval = '1s'`, `get()`/`mget()` are realtime, while search and aggregations wait up to 1 s for a refresh; calling `indices()->refresh()` inside `swap()` (`8aea9bb`) eliminates the refresh window immediately after a blue/green rebuild swap.

### Query timings (sanity run)

Cells: median / p95 in ms (write-DB statements in parentheses).
`orm_spike`: 5 warm-up, 50 iterations (host load ~6.6); `read_store_large`: 3 warm-up, 20 iterations (host load ~6.9).

| Dataset | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|
| `orm_spike` (5k) | 9.64 / 25.72 (0) | 1.72 / 4.14 (0) | 10.07 / 16.91 (0) | 29.62 / 38.40 (2) | 5.03 / 5.91 (0) |
| `read_store_large` (150k) | **12.87 / 30.73** (0) | 1.89 / 2.76 (0) | **15.49 / 16.68** (0) | 620.30 / 740.14 (2) | 8.39 / 10.26 (0) |

Short R5 sanity load on `read_store_large` (`c=1`, 15 s, 0 errors): **7.2 req/s**, p50 12.4 ms, p95 701.9 ms (R1 2.7 ms, R2 23.4 ms, R3b 583.3 ms), 0.4 write-DB stmts/req, `instance-mysql-1` CPU 11.6 s.
(At `c=8` with all 47 other lane containers running, `instance-opensearch-1` hit host memory pressure and was OOM-killed mid-run; multi-worker R5 for OpenSearch is measured cleanly in handoff F with other lanes stopped.)

## O1 / O1a versus standalone `store-opensearch` (milestone 2 comparison)

Comparing `store-opensearch` (`read_store_large` sanity run) with handoff P's O1 (`dal-opensearch`) baseline from `docs/39-read-store-baseline.md`:

| Scenario (`read_store_large`) | O0 (`dal`) | O1 (`dal-opensearch`) | Standalone `store-opensearch` | Delta (O2 vs O1) |
|---|---|---|---|---|
| S1 (listing) | 110.99 ms (4 SQL) | 12.02 ms (2 SQL) | **12.87 ms (0 SQL)** | Same latency, 0 SQL |
| S2 (detail) | 4.53 ms (5 SQL) | 9.73 ms (4 SQL) | **1.89 ms (0 SQL)** | **5.1× faster**, 0 SQL |
| S3 (filtered + 7 aggs) | 2,723.72 ms (7 SQL) | 17.64 ms (2 SQL) | **15.49 ms (0 SQL)** | Slightly faster, 0 SQL |
| R3b (keyword search + collapse) | 1,140.19 ms (9 SQL) | **28.36 ms (2 SQL)** | 620.30 ms (2 SQL) | **22× slower** (see below) |
| R4 (24-doc mget) | 11.95 ms (5 SQL) | 15.62 ms (4 SQL) | **8.39 ms (0 SQL)** | **1.9× faster**, 0 SQL |

**Critical finding on R3b**: `store-opensearch` is 22× slower than O1 on R3b at 150k products (620 ms vs 28 ms) for two architectural reasons inherited from exact DAL parity:

1. `StoreImplementation::r3bStorefrontSearch()` still invokes Shopware's SQL `ProductSearchBuilder` / `SearchKeywordInterpreter` (2 SQL `LIKE` queries on `product_search_keyword` in `instance-mysql-1`) before calling the read store, burning 11.6 s of MySQL CPU at `c=1` even though the read store itself uses 0 SQL.
2. To reproduce DAL's exact `score * ranking` formula over `searchKeywords`, `store-opensearch` runs a Painless `script_score` scanning `_source.rs.k` inside a `terms` + `top_hits` collapse aggregation, whereas O1 uses OpenSearch's native inverted-index BM25 `buildTermQuery()` + native `collapse`.

In short: O1 already wins S1/S3/R3b query execution with 190.8 MB of index space and 28 ms R3b, while only paying 2–4 SQL hydration queries per request.
Eliminating those 2–4 hydration queries is what O1a (`_source` hydration on `src/Elasticsearch`) or an O1b built on `src/Elasticsearch` would buy, without sacrificing native OpenSearch text scoring.
The wave 9 `opensearch-valkey` store (`docs/43-read-store-mongodb-valkey.md`) is not that O1b: it wraps this standalone `OpenSearchStorage` (`DependencyInjection/m.php`), so its `search()` runs the same Painless `script_score`, its R3b path keeps the SQL keyword interpreter in front of the store, and its R3b is as slow (582.72 ms in the final block, `docs/38`).
It proves Valkey hydration of hits, not the recommended O1+ query path; O1+ end to end is open (wave 10 handoff A).
