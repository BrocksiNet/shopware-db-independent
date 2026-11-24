# Read store: OpenSearch adapter

Status: draft, written by handoff O of wave 9.
The adapter is implemented and passes the contract suite.
Timings are pending milestone 2.
The O1a decision is made from the code and is in the section "O1a versus O2".

Code lives in `instance/src/Core/Framework/ReadStore/Adapter/OpenSearch/` (commit `e1a9257bc5a` in `instance/`).
The contract test is `instance/tests/unit/Core/Framework/ReadStore/Adapter/OpenSearch/OpenSearchStorageTest.php`.
It ran against OpenSearch 2.19 (`instance-opensearch-1`).

## Contract result

52 tests, 195 assertions, 51 pass, 1 incomplete, 0 fail.
The test skips when `opensearch:9200` is unreachable.
It only creates and deletes indices with the prefix `rs_test_<random>_`.

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

## Timings (pending milestone 2)

To be filled once the pipeline and bridge exist: bulk index time per generation, index size on disk, query latency for the contract scenarios, refresh interval versus lag.

## O1a timings (pending milestone 2)

To be filled from handoff P's O1 baseline, not from a prototype.
