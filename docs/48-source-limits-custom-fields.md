# 48 Does the full product document fit OpenSearch `_source`? Custom fields, languages, size

Wave 10, handoff B.
Question: doc 46 "What is not proven", point 2: does the full `ProductDocument` in OpenSearch `_source` stay within OpenSearch limits and at an acceptable size, rebuild time and latency for shops with many custom fields, many languages and large catalogs?
If not, where is the limit, and does Valkey (O1b) take over?

## Verdict

Partly proven.

- Limits: A's layout (doc 47, `rs_document` mapped `enabled: false`) adds one mapped field, whatever the custom field and language count.
  The limit that breaks is today's custom field mapping, not `_source`: with every custom field mapped, 1,000 custom fields at 20 languages need 49,796 of Shopware's 50,000 fields, and 5,000 at 5 languages need 61,501.
- Size: the document grows with languages × custom fields, because the SQL document builder resolves the language fallback and writes every value into every language.
  At 150,000 products, the median document is 3.9 KB with no custom fields and one language, 52 KB at 1,000 fields × 5 languages, 198 KB at 1,000 × 20 and 934 KB at 5,000 × 20 (130.6 GiB of JSON).
- Valkey does not take over where `_source` gets too big: it holds the same document at 1.08 to 1.13 times the JSON size, and `MGET` of 24 with decoding takes 11.1 ms (p50) at 1,000 × 20 and 52.7 ms at 5,000 × 20.
  The fix for size is the document layout (custom field values once, not once per language), not another store.
- Not proven: index size, rebuild time on OpenSearch, R1 / R2 / R3b latency and heap.
  `instance-opensearch-1` was OOM-killed (exit 137) during the whole handoff and the podman VM disk is 97 % full, above the flood stage watermark (see "Blocked").

Where it is fine, from what was measured: up to about 1,000 custom fields × 5 languages or 100 × 20 (median 34 to 52 KB, 4.8 to 7.3 GiB of JSON for 150,000 products, `MGET` of 24 decoded in 2.4 to 3.1 ms).
Where it breaks on paper: today's mapping at 1,000 × 20, and a 100-product bulk request at 5,000 × 20 (see "Limits").

## Setup

- Data: `read_store_large` (150,000 products, 2 languages, 0 custom fields), on `poc/wave10` `e57d8cfa9c7`.
- Probe: `read-store:probe:source-limits` (`src/Core/Framework/ReadStore/Probe/`).
  It builds every product once with `SqlDocumentBuilder` (the builder of A's `rs_document` and of every wave 9 store) and turns each document into 12 variants with `CustomFieldDocumentSet`, without writing to the database.
- Custom fields: 0, 100, 1,000 or 5,000 product custom fields, with the type mix of the store inventory below (text 2,129, select 983, bool 855, media 339, html 311, float 242, int 229, datetime 141, colorpicker 132, entity 88, json 39, price 9) and names of 45 characters (median app field name length, below).
- Fill: each product fills 10 % of the defined custom fields, one contiguous block (a product type fills whole sets).
  This is a chosen value, not a measured one: there is no customer data, and a shop with 1,000 fields across product types will not fill them all on one product.
  Every cell also reports one document with 100 % fill as the worst case.
- Value sizes (assumed): text 10 to 50 characters, html 200 to 600 characters, select keys like `option_12`, media and entity as 32 hex characters, colors `#rrggbb`, small json and price objects.
- Languages: 1, 5 or 20.
  Every language-keyed map in the document gets the extra languages as copies of the default language, which is what the builder writes for a language without its own translation (it resolves the fallback per language); custom fields go into every language.
- Run: `APP_ENV=prod`, `SHOPWARE_ES_SOURCE_DOCUMENT=1`, 2026-11-24 20:38 to 20:51, load average of the podman VM 3.8 to 7.2 (`sys_getloadavg()` in `instance-web-1`), host 6.6 to 13.5, other lanes stopped: no.

## Inventory: how many custom fields do extensions ship?

Source: the store mirror of doc 28 (commit `85ee954d70`, 2026-10-02), scanned with `docs/inventory/custom-fields/scan.py` (static scan, nothing executed), output `plugins.csv`, `apps.csv`, `meta.json` next to it.
Customer shops are not in this; a shop adds its own custom fields on top.

| | Plugins | Apps |
|---|---|---|
| Scanned | 3,747 | 625 (0 unparsable manifests) |
| With custom fields | 686 | 151 |
| Custom fields, total | 3,283 | 2,214 |
| Fields per extension, p50 / p90 / p99 / max | 2 / 10 / 46 / 63 | 4 / 58 / 82 / 114 |
| Custom field sets, total | 905 (598 plugins) | 367 |
| With a product set | 302 (lower bound) | 106 |
| Fields in those, p50 / p90 / max | 2 / 9 / 63 (1,509 fields) | 5 / 49 / 114 (1,608 product fields) |
| Insert into `custom_field` with raw SQL | 24 plugins | – |

- Plugins: a field counts when an array has `'type' => CustomFieldTypes::X` (or a known type string) and a `'name' =>` key and is not a field's `config` array.
  Checked by hand: `LenzPlatformClp` 63 (file has 2 set names and 63 field names), `AcrisGpsrCS` 42 (42 names); `DhDeAdminActivityLoggerV2` was a false positive of a first version (108) and is excluded now.
  Product set detection needs `'entityName' => 'product'` or `ProductDefinition::ENTITY_NAME` in the same file, so 302 is a lower bound.
- Apps: `manifest.xml` `<custom-field-set>`, children of `<fields>`, `<related-entities><product/>`.
  App field names: median 45 characters, p90 64, max 97 (2,214 names).
- Types, plugins: text 1,290, bool 635, select 472, int 172, html 150, float 110, datetime 107, media 60, number 54, colorpicker 54, entity 53, switch 50, json 39, checkbox 20, date 11, price 6.
- Types, apps: text 839, single-select 506, media-selection 279, text-area 161, bool 150, float 78, color-picker 78, int 57, single-entity-select 24, datetime 23, multi-entity-select 11, multi-select 5, price 3.

So one extension brings up to 114 product custom fields, and all 4,372 extensions together ship 5,497.
A shop with 100 custom fields is plausible with a few extensions plus its own; 1,000 means many extensions or a large own data model; 5,000 is about every store extension at once and is a stress case.

## Limits

### On paper

OpenSearch 2.19.7 (Lucene 9.12.3) on `instance-opensearch-1`; defaults read from the running cluster (a temporary index and the cluster setting defaults) before it was killed, docs from `opensearch-project/documentation-website` branch `2.19`.

| Limit | OpenSearch default | Shopware product index | Source |
|---|---|---|---|
| `index.mapping.total_fields.limit` | 1,000 | 50,000 | cluster; `src/Elasticsearch/Resources/config/packages/elasticsearch.yaml` lines 140 to 145 (admin index lines 46 to 51) |
| `index.mapping.depth.limit` | 20 | 20 | cluster |
| `index.mapping.nested_fields.limit` | 50 | 500 | cluster; same yaml |
| `index.mapping.nested_objects.limit` | 10,000 | 1,000,000 | cluster; same yaml |
| `http.max_content_length` | 100mb | 100mb | cluster |
| Products per bulk request | – | 100 (`SHOPWARE_ES_INDEXING_BATCH_SIZE`) | yaml line 307, `Configuration.php` line 21 |
| Disk flood stage | 95 % | – | docs (cluster settings): above it every index on the node gets `index.blocks.read_only_allow_delete` |
| Valkey `proto-max-bulk-len` | 512 MB | – | `CONFIG GET` on `instance-valkey-1` (Valkey 9.0.2) |

`enabled: false` on an object: "the object's contents are not indexed or searchable, but they are still retrievable from the _source field" (docs, object field type), and the contents are not parsed, so neither depth nor field count of the document matters.
`flat_object` (since 2.7) maps a whole JSON object as one field and does not create an inverted index for its subfields; it supports term, range, match, prefix and similar queries on dot paths, but not Painless scripts on its subfields.
It is an option for searchable custom fields without a field per key; this probe did not test it.

### How custom fields reach the mapping today

- `ElasticsearchIndexingUtils::getCustomFieldTypes()` (line 67) maps an active custom field when its name is used in a product sorting or a product stream, it is listed in `elasticsearch.product.custom_fields_mapping`, it has `include_in_search = 1`, or its set belongs to an app (`custom_field_set.app_id IS NOT NULL`).
  So every app custom field is mapped, whether it is searched or not; plugin fields mostly are not.
- `ElasticsearchFieldBuilder::customFields()` puts that mapping under every language: `customFields.<languageId>.<name>`.
- `ElasticsearchCustomFieldsMappingHelper::getTypeFromCustomFieldType()`: int, float, bool, datetime, json and price take 1 field; text, select, html, media, entity and colorpicker become `keyword` with `search` and `ngram` sub-fields, 3 fields.
- `ElasticsearchFieldMapper::formatCustomField` drops values of unmapped fields from the indexed document, so unmapped custom fields are not searchable today; in A's layout they are still in `rs_document`.

### Mapped fields per cell

Counted by the probe (`--mode=mapping`) from the real product mapping (`ElasticsearchProductDefinition::getMapping()` with `SHOPWARE_ES_SOURCE_DOCUMENT=1`): every property and every multi-field counts 1, as for `total_fields.limit`.
With 2 languages the mapping has 170 fields: 96 fixed (with `rs_document`) and 37 per language.
The type mix gives 2.45 fields per custom field and language.
Dynamic sub-keys of json and price values are not counted, so the "all mapped" column is a lower bound.

| Custom fields | Languages | All custom fields mapped (today, for app fields) | Custom fields only in `rs_document` (A's layout) |
|---|---|---|---|
| 0 | 1 / 5 / 20 | 133 / 281 / 836 | 133 / 281 / 836 |
| 100 | 1 / 5 / 20 | 379 / 1,511 / 5,756 | 133 / 281 / 836 |
| 1,000 | 1 / 5 / 20 | 2,581 / 12,521 / **49,796** | 133 / 281 / 836 |
| 5,000 | 1 / 5 / 20 | 12,377 / **61,501** / **245,716** | 133 / 281 / 836 |

With OpenSearch's own default of 1,000, today's mapping fails already at 100 custom fields × 5 languages; Shopware's 50,000 moves that to about 1,000 × 20.
A's layout stays at 836 fields at 20 languages, below even the OpenSearch default.

### Bulk request size

A bulk request carries 100 products.
At 5,000 × 20 the `rs_document` alone of 100 products is 93.5 MB at the mean document size and 96.9 MB at the largest, 89.2 and 92.4 MiB of the 100 MiB `http.max_content_length`, before the indexed fields and the action lines; a batch with fully filled products (9.2 MB each) is far above it.
At 1,000 × 20 it is 19.9 MB (mean), so the batch limit matters only for the stress case, but the batch has to be cut by bytes, not by product count, once the document is in `_source`.

## Document size at 150,000 products (step 4, without OpenSearch)

`--mode=documents`, JSON of the full document as A writes it into `rs_document`, every product of `read_store_large`.
Document build (2 languages, no custom fields): 46.1 s for 150,000 products; augment and encode per cell in the last column (CPU of the probe, not OpenSearch indexing).

| Custom fields | Languages | p50 bytes | p95 | max | 100 % fill, one doc | JSON total | Augment and encode |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 3,934 | 4,996 | 5,960 | 3,929 | 604.7 MiB | 3.9 s |
| 0 | 5 | 6,191 | 7,855 | 8,920 | 6,196 | 955.5 MiB | 4.6 s |
| 0 | 20 | 14,613 | 19,065 | 20,089 | 14,596 | 2.2 GiB | 6.7 s |
| 100 | 1 | 5,052 | 6,163 | 7,595 | 13,150 | 737.8 MiB | 4.2 s |
| 100 | 5 | 11,225 | 13,841 | 17,135 | 52,301 | 1.6 GiB | 5.9 s |
| 100 | 20 | 33,843 | 43,003 | 52,983 | 199,016 | 4.8 GiB | 11.2 s |
| 1,000 | 1 | 13,234 | 14,531 | 15,820 | 95,408 | 1.9 GiB | 7.6 s |
| 1,000 | 5 | 52,374 | 55,251 | 58,220 | 463,591 | 7.3 GiB | 18.1 s |
| 1,000 | 20 | 198,424 | 209,426 | 217,389 | 1,844,176 | 27.8 GiB | 50.4 s |
| 5,000 | 1 | 50,097 | 51,503 | 53,360 | 463,548 | 7.0 GiB | 22.0 s |
| 5,000 | 5 | 236,265 | 240,960 | 246,104 | 2,304,291 | 33.0 GiB | 68.1 s |
| 5,000 | 20 | 934,197 | 952,264 | 968,894 | 9,206,976 | 130.6 GiB | 235.3 s |

The 0 × 1 cell matches doc 38 Q2 (median 4,488 B, 691.51 MiB, at 2 languages).
Per filled custom field and language a value costs about 90 bytes ((13,234 − 3,934) / 100 at 1 language), most of it the 45-character name.
Going from 1 to 20 languages multiplies the custom field part by 20: that, not the field count, is what drives the large cells.

## Valkey (step 5)

`--mode=valkey`, database 5, prefix `rs_w10_b`, the first products by id, at most 2,000 documents or 200 MiB of JSON per cell (the VM had about 2.7 GB available), deleted after each cell (0 keys left, `used_memory` back to 1.6 MB).
Memory is `MEMORY USAGE` per key; the `used_memory` delta of the first and second half of each sample agrees within 1 %, so it is linear and the 150,000 column is mean × 150,000.
`MGET` of 24 random stored ids: 5 warm-up, 50 iterations, raw (`\Redis::mget`) and decoded (`ValkeyStorage::mget`, `json_decode`).

| Custom fields | Languages | Docs sampled | Bytes per key, p50 | For 150,000 | `MGET` 24 raw p50 / p95 ms | decoded p50 / p95 ms |
|---|---|---|---|---|---|---|
| 0 | 1 | 2,000 | 4,176 | 654 MiB | 0.119 / 0.150 | 0.633 / 0.777 |
| 0 | 5 | 2,000 | 7,248 | 1.0 GiB | 0.112 / 0.151 | 0.731 / 0.905 |
| 0 | 20 | 2,000 | 16,464 | 2.4 GiB | 0.184 / 0.271 | 1.411 / 1.874 |
| 100 | 1 | 2,000 | 5,200 | 813 MiB | 0.107 / 0.130 | 0.579 / 0.707 |
| 100 | 5 | 2,000 | 12,368 | 1.7 GiB | 0.153 / 0.179 | 0.992 / 1.126 |
| 100 | 20 | 2,000 | 41,040 | 5.3 GiB | 0.243 / 0.302 | 2.391 / 2.817 |
| 1,000 | 1 | 2,000 | 14,416 | 2.0 GiB | 0.158 / 0.206 | 1.088 / 1.275 |
| 1,000 | 5 | 2,000 | 57,424 | 8.0 GiB | 0.353 / 0.616 | 3.143 / 3.535 |
| 1,000 | 20 | 1,056 | 229,456 | 30.4 GiB | 1.102 / 1.267 | 11.119 / 12.689 |
| 5,000 | 1 | 2,000 | 57,424 | 8.0 GiB | 0.319 / 0.391 | 2.726 / 3.285 |
| 5,000 | 5 | 887 | 262,224 | 36.6 GiB | 1.273 / 1.452 | 13.390 / 14.365 |
| 5,000 | 20 | 225 | 1,048,656 | 146.3 GiB | 5.121 / 7.304 | 52.682 / 60.851 |

Doc 38 had 780 MiB for 150,000 products at 2 languages; the 0 × 1 cell here has 654 MiB, consistent with one language less.
Decoding, not the network, dominates in every cell (0.12 against 0.63 ms at 0 × 1, 0.24 against 2.39 ms at 100 × 20); a listing of 24 at 1,000 × 20 decodes 4.8 MB of JSON per request.

## Blocked: OpenSearch columns of step 4

Not measured: indexing success, index size, rebuild time on OpenSearch, R1 / R2 / R3b latency and heap.

- `instance-opensearch-1` (`-Xms4g -Xmx4g`) stayed in "Exited (137)", `OOMKilled=true`, during the handoff (last checked 20:38, killed at 20:27); the VM had 15.9 GB with 0.8 GB free and 2.7 GB available, while other lanes ran (stopping them was refused for A, doc 47).
- The VM disk was 97 % full (100 GB, 3.2 GB free), above the 95 % flood stage, so even a running node would block bulk writes into the index.

To run them: free about 5 GB of VM disk, stop the lanes or give OpenSearch the memory, copy `read_store_large` documents into `rs_w10_b_*` indices per cell (A's env helper `/tmp/wave10-a/env.sh` and this probe's `CustomFieldDocumentSet` give the documents), then `_cat/indices`, `_nodes/stats/jvm` and the route bench of doc 47 "Open".

## What core needs: proposed change to E6.03

E6.03 (`docs/issues/E6-read-store/03-opensearch-source-and-valkey-hydration.md`) is not edited; this is the proposed change.

1. Acceptance criterion O1a: the document goes into one field mapped `{"type": "object", "enabled": false}` and into `_source` includes; custom fields are read from it and never add mapped fields.
2. New criterion, mapping rule: a custom field is mapped (searchable, filterable, sortable) only when it is flagged: `include_in_search`, used in a product sorting or stream, or listed in `custom_fields_mapping`.
   App custom field sets lose the blanket `custom_field_set.app_id IS NOT NULL` clause; apps flag their fields like plugins.
3. New criterion, guard: before an index is created, count the mapped fields; above a share of `index.mapping.total_fields.limit` (for example 80 %) log which custom fields cause it, instead of failing in the middle of `es:index`.
4. New criterion, document shape: custom field values are stored once per product plus per language only where a translation has its own value; the language fallback is resolved at read time.
   Today's per-language copy makes the 1,000 × 20 document 15 times the 1,000 × 1 document (198 KB against 13 KB).
5. New criterion, indexing: bulk requests are cut by bytes (well below `http.max_content_length`), not only by `SHOPWARE_ES_INDEXING_BATCH_SIZE` products.
6. Replace "~454 MB OpenSearch index or ~780 MiB Valkey RAM per 150,000 products" by the size per custom field and language: about 90 bytes per filled custom field and language plus about 560 bytes per language (this doc, tables above), and the note that index size and latency above 0 custom fields are not measured yet.
7. O1b is a fallback for OpenSearch availability or hydration latency, not for document size: Valkey holds the same document at 1.08 to 1.13 times its JSON size.

## Open

- Step 4 on OpenSearch (see "Blocked").
- Point 2 stays "partly proven": limits and sizes are measured, the OpenSearch cost of these sizes is not.
- `flat_object` for flagged custom fields as an alternative to one keyword plus two sub-fields per language.
