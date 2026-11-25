# 48 Does the full product document fit OpenSearch `_source`? Custom fields, languages, size

Wave 10, handoff B.
Question: doc 46 "What is not proven", point 2: does the full `ProductDocument` in OpenSearch `_source` stay within OpenSearch limits and at an acceptable size, rebuild time and latency for shops with many custom fields, many languages and large catalogs?
If not, where is the limit, and does Valkey (O1b) take over?

## Verdict

Proven for 0 and 100 custom fields at 1 and 5 languages on all 150,000 products; the larger cells are measured on product subsets and extrapolated (see "OpenSearch (step 4)" for the limits of that method).

- Limits: A's layout (doc 47, `rs_document` mapped `enabled: false`) adds one mapped field, whatever the custom field and language count.
  The limit that breaks is today's custom field mapping, not `_source`: with every custom field mapped, 1,000 custom fields at 20 languages need 49,796 of Shopware's 50,000 fields, and 5,000 at 5 languages need 61,501.
- Size: the document grows with languages × custom fields, because the SQL document builder resolves the language fallback and writes every value into every language.
  At 150,000 products, the median document is 3.9 KB with no custom fields and one language, 52 KB at 1,000 fields × 5 languages, 198 KB at 1,000 × 20 and 934 KB at 5,000 × 20 (130.6 GiB of JSON).
- Valkey does not take over where `_source` gets too big: it holds the same document at 1.08 to 1.13 times the JSON size, and `MGET` of 24 with decoding takes 11.1 ms (p50) at 1,000 × 20 and 52.7 ms at 5,000 × 20.
  The fix for size is the document layout (custom field values once, not once per language), not another store.
- OpenSearch indexes every cell up to 5,000 custom fields × 20 languages with 0 bulk item errors, and the heap stays below 3.0 GB of 4 GiB while indexing.
  Index size for 150,000 products: 0.42 GB at 0 × 1 and 0.96 GB at 100 × 5 (measured); 2.1 GB at 100 × 20, 2.7 GB at 1,000 × 5, 11.4 GB at 1,000 × 20, 12.8 GB at 5,000 × 5 and 53.5 GB at 5,000 × 20 (extrapolated).
  For large documents the index takes about 0.45 bytes per byte of document JSON.
- Rebuild of 150,000 products: 3 to 5 minutes up to 100 × 5 (measured), about 11 minutes at 1,000 × 20, 18 at 5,000 × 5 and 50 at 5,000 × 20 (extrapolated, the per-1,000 rate varies by up to 60 % between runs).
- Latency: the listing (S1, R2) median is 11 to 12 ms at 0 × 5 and 100 × 5 on the full index, then 18 ms at 1,000 × 5, 27 ms at 1,000 × 20, 34 ms at 5,000 × 5 and 111 ms (p95 259 ms) at 5,000 × 20 on subset indices; search (R3b) goes from 26 to 31 ms to 168 ms.
- Bulk: at 5,000 × 20 a batch of 100 product ids (about 84 indexable documents) is 84.2 MB at most, 80 % of the 100 MB `http.max_content_length`; it went through, but 100 indexable documents would be about 94 MB.

Where it is fine: up to 1,000 custom fields × 5 languages or 100 × 20 (index up to 2.7 GB, listing median up to 18 ms, `MGET` of 24 decoded in 2.4 to 3.1 ms).
Where it degrades: 1,000 × 20 and 5,000 × 5 (11 to 13 GB, listing 27 to 34 ms, rebuild 11 to 18 minutes); today's mapping already breaks at 1,000 × 20 (see "Limits").
Where it is not acceptable: 5,000 × 20 (53 GB for 150,000 products, listing 111 ms, bulk requests at 80 % of the request limit).

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
Measured in step 4: a batch of 100 ids holds about 84 indexable documents, and the whole bulk request is 17.6 MB (p50) at 1,000 × 20 and 78.6 MB (p50) and 84.2 MB (max) at 5,000 × 20, which OpenSearch accepted.

## Document size at 150,000 products (step 4, JSON only)

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

## OpenSearch (step 4)

`--mode=opensearch` (instance `poc/wave10` `abfb03dfc3d`), one cell per run, 2026-11-25 10:15 to 10:48.
Each cell creates `rs_w10_b_c<fields>x<languages>__product_<random>` with Shopware's product mapping (`IndexMappingProvider`, language fields expanded to the cell's languages) and index settings (`elasticsearch.index.config`), fetches the documents with `ElasticsearchProductDefinition::fetch()` in batches of 100 product ids as `es:index` does, adds the custom fields and languages to A's `rs_document` (doc 47, `enabled: false`) and sends one bulk request per batch.
Size is the primaries store after `_refresh` and `_flush`, without `_forcemerge`, on a single node without replicas; heap is `_nodes/stats/jvm` before and every 10 batches (`-Xmx4g`).
Every index was deleted right after it was measured; disk stayed at 88 to 89 %, available memory before each cell 1.2 to 1.8 GB.
VM load average 5.1 to 12.4 (`sys_getloadavg()` in `instance-web-1`), host 22 to 47, other lanes stopped: no (handoff C ran PostgreSQL suites).
Raw lines: `docs/inventory/custom-fields/opensearch-cells.jsonl`.

The indexer indexes 126,000 of the 150,000 products (as in doc 47), so a batch of 100 ids carries about 84 documents.

| Custom fields | Languages | Products scanned | Indexed | Index | Bytes per indexed product | `rs_document` p50 / max | Bulk request p50 / max | Rebuild | Per 1,000 scanned | Heap max sampled |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 150,000 | 126,000 | 424.3 MB | 3,368 | 3,936 / 5,791 | 0.58 / 0.67 MB | 204.8 s | 1.37 s | 2.71 GB |
| 0 | 5 | 150,000 | 126,000 | 691.4 MB | 5,488 | 6,197 / 8,809 | 0.95 / 1.09 MB | 290.7 s | 1.94 s | 2.86 GB |
| 100 | 1 | 150,000 | 126,000 | 530.1 MB | 4,207 | 5,068 / 7,430 | 0.66 / 0.76 MB | 249.2 s | 1.66 s | 2.84 GB |
| 100 | 5 | 150,000 | 126,000 | 956.8 MB | 7,594 | 11,252 / 17,028 | 1.34 / 1.55 MB | 176.3 s | 1.18 s | 2.90 GB |
| 0 | 5 | 20,000 | 16,722 | 97.0 MB | 5,799 | 6,202 / 8,809 | 0.94 / 1.07 MB | 22.4 s | 1.12 s | 2.73 GB |
| 100 | 5 | 20,000 | 16,722 | 130.8 MB | 7,821 | 11,247 / 16,965 | 1.33 / 1.49 MB | 36.2 s | 1.81 s | 2.70 GB |
| 0 | 20 | 20,000 | 16,722 | 215.1 MB | 12,862 | 14,624 / 20,089 | 2.30 / 2.60 MB | 119.3 s | 5.96 s | 2.56 GB |
| 100 | 20 | 20,000 | 16,722 | 279.2 MB | 16,698 | 33,890 / 52,665 | 3.85 / 4.29 MB | 33.6 s | 1.68 s | 2.95 GB |
| 1,000 | 1 | 20,000 | 16,722 | 155.2 MB | 9,283 | 13,252 / 15,643 | 1.34 / 1.50 MB | 22.4 s | 1.12 s | 2.66 GB |
| 1,000 | 5 | 20,000 | 16,722 | 352.7 MB | 21,093 | 52,428 / 58,073 | 4.76 / 5.29 MB | 34.9 s | 1.74 s | 2.77 GB |
| 5,000 | 1 | 20,000 | 16,722 | 419.7 MB | 25,097 | 50,133 / 52,887 | 4.41 / 4.88 MB | 41.4 s | 2.07 s | 2.76 GB |
| 1,000 | 20 | 10,000 | 8,366 | 754.1 MB | 90,142 | 198,458 / 216,720 | 17.6 / 19.4 MB | 44.8 s | 4.48 s | 1.75 GB |
| 5,000 | 5 | 10,000 | 8,366 | 850.1 MB | 101,611 | 236,310 / 244,895 | 20.2 / 22.2 MB | 72.9 s | 7.29 s | 2.45 GB |
| 5,000 | 20 | 2,000 | 1,668 | 708.7 MB | 424,894 | 934,467 / 966,561 | 78.6 / 84.2 MB | 40.2 s | 20.1 s | 2.83 GB |

Every cell: 0 bulk item errors; "Indexed" is `_count` of the index; the full cells have 1,196,268 Lucene documents for 126,000 products (nested fields), mapped fields 133 / 281 / 836 at 1 / 5 / 20 languages (A's layout, custom fields never mapped).
MB is 10^6 bytes here.
Rebuild is the probe's wall time (fetch, augment, bulk); fetch alone is 59 to 80 s of it for 150,000 products.

### Extrapolation to 150,000 products

- index_150k = store_bytes / products_indexed × 126,000
- rebuild_150k = rebuild seconds per 1,000 scanned products × 150

| Custom fields | Languages | From | Index for 150,000 | Rebuild for 150,000 |
|---|---|---|---|---|
| 0 | 1 | measured | 0.42 GB | 205 s |
| 0 | 5 | measured | 0.69 GB | 291 s |
| 100 | 1 | measured | 0.53 GB | 249 s |
| 100 | 5 | measured | 0.96 GB | 176 s |
| 0 | 20 | 20,000 | 1.62 GB | 894 s |
| 100 | 20 | 20,000 | 2.10 GB | 252 s |
| 1,000 | 1 | 20,000 | 1.17 GB | 168 s |
| 1,000 | 5 | 20,000 | 2.66 GB | 261 s |
| 5,000 | 1 | 20,000 | 3.16 GB | 311 s |
| 1,000 | 20 | 10,000 | 11.36 GB | 672 s |
| 5,000 | 5 | 10,000 | 12.80 GB | 1,093 s |
| 5,000 | 20 | 2,000 | 53.54 GB | 3,015 s |

Limits of the subset method:

- A subset is the first N product ids in id order (as `ProductIds` yields them), not a random sample; its indexed share is 83.6 to 83.7 % against 84.0 % for all products.
- Bytes per product of a subset index overestimate the full index: by 5.7 % at 0 × 5 and 3.0 % at 100 × 5 (20,000 against 150,000), and by 10.2 % at 0 × 1 for a 2,000-product test run (3,713 against 3,368).
  The extrapolated sizes are therefore upper bounds within about 10 %.
- The rebuild rate is not stable under the other lanes' load: the same cell gave 1.94 s (full) and 1.12 s (20,000) per 1,000 at 0 × 5, and 1.18 s and 1.81 s at 100 × 5; 0 × 20 (5.96 s) ran at VM load 12.4.
  Take the rebuild column as an order of magnitude; only the large cells (4.5 to 20 s per 1,000) are clearly slower.
- Latency on a subset runs against an index of 1,668 to 16,722 products, not 126,000; it shows the cost of large documents in a response, not of a large index.
- Heap is sampled every 10 batches, so the 2,000-product cell has 2 samples.
- No `_forcemerge`, one node, no replicas: a production index with one replica needs twice the size.

### R1 / R2 / R3b sanity

`orm-spike:bench --impl=dal-opensearch --scenario=S2,S1,R3b --iterations=50 --warmup=5`, A's O1a env (`SHOPWARE_ES_SOURCE_DOCUMENT=1`) with `SHOPWARE_ES_INDEX_PREFIX` set to the cell's alias, `APP_ENV=prod`, median / p95 ms.
S2 is the detail of one variant (R1), S1 the listing (R2), R3b the storefront search.

| Custom fields | Languages | Index | S2 (R1) | S1 (R2) | R3b | Heap after |
|---|---|---|---|---|---|---|
| 0 | 5 | 150,000 | 7.03 / 10.97 | 11.07 / 49.76 | 30.71 / 49.83 | 2.61 GB |
| 100 | 5 | 150,000 | 6.60 / 9.47 | 11.89 / 15.79 | 25.95 / 31.63 | 2.36 GB |
| 0 | 20 | 20,000 | - | 9.70 / 13.37 | 16.16 / 18.28 | 2.92 GB |
| 100 | 20 | 20,000 | - | 14.63 / 39.96 | 23.47 / 77.76 | 0.92 GB |
| 1,000 | 5 | 20,000 | - | 18.42 / 33.46 | 25.04 / 39.01 | 1.81 GB |
| 1,000 | 20 | 10,000 | - | 26.57 / 29.68 | 32.84 / 41.70 | 0.76 GB |
| 5,000 | 5 | 10,000 | - | 34.11 / 62.13 | 64.25 / 173.71 | 2.47 GB |
| 5,000 | 20 | 2,000 | - | 110.54 / 258.61 | 167.84 / 402.14 | 1.52 GB |

- S2 fails on every subset ("S2 variant not found or not visible"): the bench's variant is not among the first N products.
- Cells with 1 language have no route numbers: the bench's sales channel reads in Deutsch (`01a20cb3…`), which a 1-language cell drops, and OpenSearch answers "No mapping found for [name.01a20cb3acbe752682b5bc973150d2eb] in order to sort on".
- A measured O1a on the same data at 2 languages and 0 custom fields with 30 iterations: S2 4.71, S1 9.53, R3b 28.39 ms (doc 47); the full cells here are in the same range.
- `instance-opensearch-1` was OOM-killed once by the VM (exit 137, 10:31:19) between two cells, while no index of this handoff was being built; it was started again and the cell (100 × 5) was rerun.

## What core needs: proposed change to E6.03

E6.03 (`docs/issues/E6-read-store/03-opensearch-source-and-valkey-hydration.md`) is not edited; this is the proposed change.

1. Acceptance criterion O1a: the document goes into one field mapped `{"type": "object", "enabled": false}` and into `_source` includes; custom fields are read from it and never add mapped fields.
2. New criterion, mapping rule: a custom field is mapped (searchable, filterable, sortable) only when it is flagged: `include_in_search`, used in a product sorting or stream, or listed in `custom_fields_mapping`.
   App custom field sets lose the blanket `custom_field_set.app_id IS NOT NULL` clause; apps flag their fields like plugins.
3. New criterion, guard: before an index is created, count the mapped fields; above a share of `index.mapping.total_fields.limit` (for example 80 %) log which custom fields cause it, instead of failing in the middle of `es:index`.
4. New criterion, document shape: custom field values are stored once per product plus per language only where a translation has its own value; the language fallback is resolved at read time.
   Today's per-language copy makes the 1,000 × 20 document 15 times the 1,000 × 1 document (198 KB against 13 KB).
5. New criterion, indexing: bulk requests are cut by bytes (well below `http.max_content_length`), not only by `SHOPWARE_ES_INDEXING_BATCH_SIZE` products; at 5,000 × 20 one batch of 100 ids was 84.2 MB of the 100 MB limit.
6. Replace "~454 MB OpenSearch index or ~780 MiB Valkey RAM per 150,000 products" by the size per custom field and language: about 90 bytes of JSON per filled custom field and language plus about 560 bytes per language, and an index of 0.42 GB (0 × 1) to 0.96 GB (100 × 5) measured and 2.7 GB (1,000 × 5) to 53.5 GB (5,000 × 20) extrapolated per 150,000 products, one replica doubling it (this doc, tables above).
7. O1b is a fallback for OpenSearch availability or hydration latency, not for document size: Valkey holds the same document at 1.08 to 1.13 times its JSON size.

## Open

- Cells above 100 × 5 on all 150,000 products (needs up to 54 GB of free disk and a VM without the other lanes), with `_forcemerge` and one replica.
- Route latency for 1,000 custom fields and more on a full-size index, and S2 (R1) on those cells.
- `flat_object` for flagged custom fields as an alternative to one keyword plus two sub-fields per language.
