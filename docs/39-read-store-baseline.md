# Read store baseline (wave 9, handoff P)

Handoff P of wave 9: branch, engine containers, dataset, harness extension and the O0 / O0b / O1 baselines for the read store research (`docs/38-read-store-plan.md`).

## Branch

`poc/read-store` exists in `instance/`.
It was created by the orchestrator from `poc/orm-spike` at `46a47f1a7c9` with a clean tree and is checked out.
All wave 9 code goes there.
Handoff K may create its folders under `src/Core/Framework/ReadStore/` now (branch ready).

## Engine containers

Both containers are defined in the lane override `~/shopware-dev/instances/pg.yaml` (sw-dev mechanism, section "wave 9 read store"), started with `podman compose up -d opensearch mongodb web` in `instance/`.

| Container | Image | Digest | Limits |
|---|---|---|---|
| `instance-opensearch-1` | `opensearchproject/opensearch:2` (2.19.7, Lucene 9.12.3), security plugin disabled as in `compose.yaml` | `sha256:d89333b6bd4a13b9a95aef7f373c0a6e73440f59bc0d8d1460f9b347289ed0ef` | 8 CPUs / 16 GiB, JVM heap `-Xms4g -Xmx4g` (set in pg.yaml) |
| `instance-mongodb-1` | `mongo:8` (8.3.17) | `sha256:747773029b84309981a3624a1af64ffc8c4d792283cc0834f26fe01fc6d28b34` | 8 CPUs / 16 GiB |
| `instance-web-1` | `localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy` rebuilt with `mongodb` | image id `d0d0d0f5959e` (`sha256:54c51f408eb15dcb062a539d2d24f6f30040d8cfeaa3e1b25f6e6a65caa478e2` local digest) | unchanged |

The shared override `shared.podman-mutagen.yaml` puts `opensearch` behind the compose profile `opensearch`; `pg.yaml` resets it with `profiles: !reset []` so the lane always starts it.
Volumes `opensearch-data` and `mongodb-data` are new (named volumes of the compose project `instance`).
Reachable from `instance-web-1` as `http://opensearch:9200` (`OPENSEARCH_URL` is set by the upstream compose file) and `mongodb://mongodb:27017`.

## PHP extension and composer

`docs/environment/web.Dockerfile` now runs `install-php-extensions pdo_pgsql pgsql mongodb`.
Steps (no hand-patching of the running container):

1. `cd docs/environment && podman build -t localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy -f web.Dockerfile .`
2. `cd instance && podman compose up -d opensearch mongodb web` (recreates `instance-web-1`; the code lives in the named volume `instance_shopware-src`, so `vendor/` and the synced tree stay).
3. The mutagen session `shopware-pg` lost its beta side on the recreate (`Connecting to beta`), `mutagen sync resume shopware-pg` brought it back to `Watching for changes`.

Result: `php -r 'echo phpversion("mongodb");'` prints `2.5.8`.
`composer require mongodb/mongodb` installed `mongodb/mongodb` 2.5.1 (`^2.5` in `composer.json`, commit `7819b64`).
`composer.lock` is in `.gitignore` of the checkout (line `/composer.lock`), so it cannot be committed; the version above is what `composer.json` resolves to today.

## Datasets

Both datasets are seeded by `orm-spike:seed` (same deterministic rules) through `scripts/read-store-install.sh <engine>`, which installs the database, seeds it and builds the search keywords.
The script defaults to `--simple=100000 --parents=10000 --keywords` and writes its log to `/tmp/read-store-install-<db>-<engine>.log`.
`scripts/read-store-env.sh` defines `RS_DB` (default `read_store_large`), `spike_console`, `spike_console_for <impl>` and the OpenSearch index prefix.

| Dataset | Engine | Role | `product` rows |
|---|---|---|---|
| `orm_spike` | MySQL 8.4 and PostgreSQL 18 | wave 8 dataset, small | 5,000 (3,000 simple, 400 parents with 4 variants each) |
| `read_store_large` | MySQL 8.4 | write model for all timings | 150,000 (100,000 simple, 10,000 parents with 4 variants each) |
| `read_store_large` | PostgreSQL 18 | one correctness run | 150,000 (same row counts as MySQL) |

The 150,000 target was kept; the seeder was fast enough (see below), so the reduced size from the handoff was not needed.

`read_store_large` on MySQL 8.4:

| Step | Time |
|---|---|
| Write of 150,000 products (DAL `create()`, 100 per batch) | 297.6 s |
| Indexer incl. keyword updater | 868.2 s |
| Total | about 1,166 s |

Row counts (MySQL): `product_translation` 215,715, `product_price` 33,000, `product_category` 255,200, `product_category_tree` 348,000, `product_visibility` 99,000, `product_media` 120,000, `product_option` 80,000, `category` 51, `media` 203, `property_group` 2, `property_group_option` 9, `rule` 4, `product_manufacturer` 31.
`product_search_keyword` holds 1,645,715 rows over 150,000 distinct products, `product_keyword_dictionary` 750,285 rows.
Database size is about 1,398 MB.

`read_store_large` on PostgreSQL 18: write 214.8 s, indexer 949.3 s (including keywords), about 1,165 s total.
All row counts equal MySQL, including `product_search_keyword` (1,645,715 rows over 150,000 products); database size 2,057 MB.
Correctness run (`dalv2 --verify`, `RS_DB=read_store_large`, no timings): S1 to S5, R3b and R4 are equal to `dal`.
`dal` R3b on PostgreSQL gives total 3,667 grouped and 4,669 without grouping, equal to MySQL.

`orm_spike` got its keywords with `orm-spike:seed --keywords-only` (8.5 s): `product_search_keyword` 54,972 rows (identical on MySQL and PostgreSQL), dictionary about 24,119 rows.

`product_search_keyword` matters because R3b uses `ProductSearchBuilderInterface` (keyword tables) on the DAL, and the OpenSearch path needs it for nothing but the SQL fallback.

## Harness

All code is in `instance/src/Core/Framework/OrmSpike/Harness` (wave 8) and `instance/src/Core/Framework/ReadStore/Bench` (new).
Commit `86920d52b39` on `poc/read-store` ("feat(core): read store harness ready").

### Interfaces

- `Implementation` (wave 8): `configure`, `s1Listing`, `s2Detail`, `s3Search`, `s4Write`, `s5CriteriaFromJson`.
- `ReadStoreScenarios` (new): `r3bStorefrontSearch(Params)` and `r4Mget(Params)`.
- `StoreLifecycle` (new, optional): `rebuild(): array{documents,bytes}` (R7), `flush()` (make writes searchable) and `currentName(Params, string $productId)` (R6 poll).
- A scenario a store cannot answer throws `ScenarioNotSupported`; `orm-spike:bench` reports the status `unsupported` for it.
  S4 and S5 may use this.
- `StatementCounter` counts the statements on the write connection (`QueryCountMiddleware`), so every store implementation reports its statements on the write database.

### Registering a store

A store registers one service in its own file `ReadStore/DependencyInjection/<name>.php` (K loads `ReadStore/DependencyInjection/*.php`, commit `dd8edca9875`):

```php
$services->set('read_store.bench.<name>', MyStoreImplementation::class)
    ->tag('orm_spike.implementation', ['key' => 'store-<adapter>']);
```

`ImplementationRegistry` is backed by `tagged_locator('orm_spike.implementation', 'key', 'key')`; the tag attribute `key` wins, else the static `key()` of the class.
Without the attribute index in `harness.php` the key was ignored and `dal-opensearch` was "not registered"; this is fixed in `86920d52b39`.
The class implements `Implementation` and `ReadStoreScenarios` and may implement `StoreLifecycle`.
The registered keys today are `dal`, `dalv2` and `dal-opensearch`.

### Running

```bash
cd /Users/b.meyer/Documents/Projects/shopware-postsql
. scripts/read-store-env.sh mysql      # or postgresql; RS_DB=orm_spike to switch dataset
spike_console_for dal-opensearch orm-spike:bench --impl=dal-opensearch --scenario=all --verify
```

`spike_console_for <impl>` adds the OpenSearch environment (`SHOPWARE_ES_ENABLED`, index prefix `rs_o1_<db>_`, for PostgreSQL `rs_o1_<db>_pg_`) for implementations that need it.
`--scenario` accepts `S1` to `S5`, `R3b`, `R4` and `all`; `--verify` compares each result with the `dal` result through `ResultContract` and prints `equal` or the first difference; `--option show=1` prints `total` and the item count for R3b and R4.
The result JSON has a `database` field.
Defaults: 5 warm-up, 50 measured iterations.

| Command | Purpose | Example |
|---|---|---|
| `orm-spike:bench` | S1 to S5, R3b, R4 with median, p95, statements, peak memory | `--impl=dal --scenario=R3b,R4 --verify` |
| `read-store:bench:rebuild` | R7: full rebuild of the store from SQL; prints time, documents per second, store size, statements | `--impl=dal-opensearch` |
| `read-store:bench:lag` | R6: renames one product 100 times through `product.repository`, polls `currentName`; prints p50, p95, max and missed writes; restores the name | `--impl=<key> --writes=100 --timeout=30` |
| `read-store:load` | R5 mixed load with pre-booted worker processes | `--impl=<key> --concurrency=1,8,32 --duration=60s` |

`read-store:load` starts one long-lived `read-store:load-worker` process per concurrent client (Symfony `Process`, started together through a go-file), so no Symfony kernel boot is inside the measurement.
The mix is fixed at 50 % R1 (`s2Detail`), 30 % R2 (`s1Listing`), 20 % R3b (`r3bStorefrontSearch`), as the repeating cycle `R1 R1 R2 R1 R3b R1 R2 R3b R1 R2`.
It prints requests, throughput, p50, p95, errors, statements per request and per-scenario medians.
CPU seconds of the write database come from `scripts/read-store-load.sh`: it reads `usage_usec` from the container cgroup file `/sys/fs/cgroup/cpu.stat` on the host at the `MARK start` and `MARK end` lines the load command prints.
`scripts/read-store-baseline.sh` runs the whole baseline block under the lock protocol of `_shared.md`.

### R3b contract

R3b is a real word search (`Criteria::setTerm('Hotel')`) through `SalesChannelRepository` with `ProductAvailableFilter(VISIBILITY_SEARCH)`, the manufacturer filter as `postFilter`, `FieldGrouping('displayGroup')`, and min/max price plus manufacturer terms aggregations.
The contract is in the docblock of `ResultContract::R3B`: only the `displayGroup` of each hit is compared (not the representative variant), `total` is the number of groups, and the aggregations run over the hits without grouping and without the post filter.
`--option group=0` runs the DAL without the grouping to report the total without grouping.

| Dataset | Term | Total grouped | Total without grouping |
|---|---|---|---|
| `orm_spike` | Hotel | 114 | 156 |
| `read_store_large` | Hotel | 3,667 | 4,669 |

R4 is `mget` of 24 fixed ids (`Params::mgetIds`), normalized per product like S2.

### What K provides

K's port lives in `ReadStore/Port` and the document builders in `ReadStore/Builder` (`DocumentBuilder`, `DalDocumentBuilder`, `SqlDocumentBuilder`).
An adapter implements `Storage` (`setup`, `swap`, `liveGeneration`, `store`, `remove`, `get`, `mget`, `clear`, `destroy`) and, where the engine can, `FilterAware`, `AggregationAware` and `SearchAware`; an engine that cannot answer throws `NotSupportedByEngine`.
The adapter's harness class turns these into `Implementation` and `ReadStoreScenarios` and registers as shown above.
The harness gives an adapter the scenarios, the contract comparison (`--verify`), statement counting, R5, R6 and R7; the harness does not provide the documents, K's builders do.

## Baseline timings (O0, O0b, O1)

Run by `scripts/read-store-baseline.sh` on 2026-11-24 around 10:07 (log `/tmp/read-store-baseline-20261124-100707.log`), MySQL 8.4 as write model, `APP_ENV=prod`, warm cache, 5 warm-up and 50 measured iterations.
Other lanes stopped: yes (47 containers, 60 s pause after stopping, started again afterwards, lock released).
Host load average (1 minute) during the block: 9.2 at the start, 10.6 to 19.2 during the S/R runs; the run's own workers are included.
The load was high for a stopped-lanes block; treat absolute values as indicative and compare only rows of this block.

Implementations: `dal` = O0, `dalv2` = O0b (all levers and projections of wave 8), `dal-opensearch` = O1 (the DAL with `Criteria::STATE_ELASTICSEARCH_AWARE`, product ids from the lane's OpenSearch index built from the same database, entities from SQL).
Cells: median / p95 in ms, statements on the write database per run in parentheses.

| Dataset | Impl | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|---|
| `orm_spike` | dal | 14.78 / 21.77 (4) | 8.36 / 13.42 (5) | 78.03 / 100.09 (7) | 57.99 / 85.20 (9) | 19.45 / 37.81 (5) |
| `orm_spike` | dalv2 | 19.52 / 26.74 (4) | 13.25 / 16.17 (5) | 82.31 / 121.77 (7) | 40.53 / 42.87 (9) | 12.17 / 12.96 (5) |
| `orm_spike` | dal-opensearch | 12.72 / 13.47 (2) | 9.95 / 11.33 (4) | 17.05 / 35.18 (2) | 17.81 / 20.62 (2) | 12.40 / 17.60 (4) |
| `read_store_large` | dal | 110.99 / 128.50 (4) | 4.53 / 4.95 (5) | 2723.72 / 3650.25 (7) | 1140.19 / 1313.87 (9) | 11.95 / 16.76 (5) |
| `read_store_large` | dalv2 | 125.42 / 170.62 (4) | 6.25 / 7.05 (5) | 2941.69 / 4463.88 (7) | 1136.29 / 1449.40 (9) | 8.74 / 12.29 (5) |
| `read_store_large` | dal-opensearch | 12.02 / 15.32 (2) | 9.73 / 19.91 (4) | 17.64 / 21.88 (2) | 28.36 / 47.67 (2) | 15.62 / 18.43 (4) |

Peak memory is 41 to 58 MB for every cell (in the JSON and the log).

### R5 mixed load on `read_store_large`

60 s per level, mix 50 % R1, 30 % R2, 20 % R3b, 0 errors on every level.
Same block, same load and lane state as above.
The runs end 0 to 8 s after the deadline because the last slow requests finish late.
The MySQL container has 8 CPUs, so 8 CPU seconds per second is its maximum.

| Impl | c | requests | throughput/s | p50 ms | p95 ms | statements per request | MySQL CPU s |
|---|---|---|---|---|---|---|---|
| dal | 1 | 205 | 3.4 | 22.2 | 1338 | 5.2 | 58.5 |
| dal | 8 | 958 | 15.5 | 153.1 | 2363 | 5.3 | 465.1 |
| dal | 32 | 928 | 14.0 | 274.4 | 10282 | 5.3 | 497.8 |
| dalv2 | 1 | 208 | 3.4 | 43.4 | 1287 | 5.2 | 59.4 |
| dalv2 | 8 | 846 | 13.8 | 169.3 | 2595 | 5.3 | 421.5 |
| dalv2 | 32 | 777 | 11.5 | 241.4 | 12664 | 5.3 | 449.1 |
| dal-opensearch | 1 | 4460 | 74.3 | 10.6 | 28.3 | 2.7 | 10.9 |
| dal-opensearch | 8 | 29946 | 498.4 | 12.6 | 34.3 | 2.7 | 58.1 |
| dal-opensearch | 32 | 28244 | 469.1 | 58.0 | 145.5 | 2.7 | 61.0 |

`dal` and `dalv2` use about 7.5 of the 8 cores at c=8 and c=32, so the write database is the limit; `dal-opensearch` still needs 2.7 statements per request, which is the SQL part of O1.
Per-scenario p50 inside R5 at c=1: dal R1 6.4 ms, R2 134.6 ms, R3b 1244 ms; dal-opensearch R1 8.4 ms, R2 11.9 ms, R3b 24.6 ms.

### R7 rebuild and R6 lag of O1

Both ran on `read_store_large` after the timing block, so without the lock and with the other lanes running (`other lanes stopped: no`).

| Measure | Value |
|---|---|
| R7 `dal-opensearch` rebuild (`es:index --no-queue --only=product`) | 50.6 s, 126,000 documents, 2,489 documents/s, 190.8 MiB |
| R6 `dal-opensearch` lag, 100 writes | 0 missed, p50 9.3 ms, p95 12.0 ms, max 13.4 ms |

R7 statements show 0 because `es:index` runs in a child process, which `StatementCounter` does not see.
R6 for O1 measures a read from SQL (`currentName` goes through `r4Mget`, and the name is read from the entity), so it says nothing about the lag of the search index; it is only the harness check.
R6 for the stores that hold documents (K's and the adapters') measures the real lag.

## Findings

### O1 `--verify` differences

`dal-opensearch` is equal to `dal` on S2, S4 and R4 on both datasets and differs on four scenarios; `dalv2` is equal to `dal` on S1 to S5, R3b and R4 on both datasets.
Observed values (expected = `dal`, got = `dal-opensearch`):

| Scenario | `read_store_large` | `orm_spike` |
|---|---|---|
| S1 | total 6,000 vs 5,600 | item order differs |
| S3 | manufacturer aggregation 2,335 vs 2,168 | 78 vs 71 |
| S5 | total 40,600 vs 37,900 | 1,354 vs 1,246 |
| R3b | manufacturer aggregation 2,169 vs 2,167 | 73 vs 71 |

Causes, verified with runs (temporary env-driven code in `DalImplementation` and `BenchCommand`, reverted and not committed):

1. S1 (total), S3 and S5.
   The first explanation in this doc, "the index holds only visible products", was wrong: the DAL scenarios go through `SalesChannelProductDefinition::processCriteria`, which already adds `ProductAvailableFilter` (active, visibility in the sales channel), so visibility is the same on both sides.
   The real cause is the index WHERE clause in `ElasticsearchProductDefinition` (line 421): `p.child_count = 0 OR p.parent_id IS NOT NULL OR variant_listing_config displayParent = 1`.
   Parents that have variants are not indexed (without `displayParent`), while the DAL counts them.
   Experiment: a temporary filter `childCount = 0 OR parentId != null` on every DAL criteria of both implementations, then `orm-spike:bench --impl=dal-opensearch --scenario=S1,S3,S5,R3b --verify` with the ES environment of `spike_console_es`.
   Result on `orm_spike`: S3 OK, S5 OK (before: 78 vs 71 and 1,354 vs 1,246).
   Result on `read_store_large`: S1 OK, S3 OK, S5 OK (before: totals 6,000 vs 5,600, 40,600 vs 37,900 and aggregation 2,335 vs 2,168).
   Status: verified.
   The 126,000 documents are therefore 90,000 visible simple products plus 36,000 variants of visible parents; the index also holds inactive and invisible products, which the query filters, so the earlier phrase "only active products with a visibility row" is dropped.
2. S1 on `orm_spike` still differs in the item order after the filter (item 7 expected `SPK-P-00005-1`, got `SPK-P-00005-2`).
   Both variants have the same inherited name.
   The index stores `productNumber` as a multi-valued field holding the parent number and the variant number (docvalues of the two documents: `["spk-p-00005","spk-p-00005-1"]` and `["spk-p-00005","spk-p-00005-2"]`).
   The ascending sort on a multi-valued field uses the minimum, so both variants sort as `spk-p-00005` and tie, and the tie order is arbitrary; the DAL sorts by the variant's own number.
   The multi-valued docvalues are read from the index; that the sort takes the minimum is OpenSearch's default for multi-valued fields, I did not run a sort query to confirm the tie order.
   On `read_store_large` S1 is equal (no such tie in the first page).
3. R3b manufacturer aggregation (73 vs 71 on `orm_spike`, 2,169 vs 2,167 on `read_store_large`) is a DAL over-count, not an index difference.
   Three manufacturers differ, by 2, 2 and 3: `Maker 17` (`52d4c43cd3e4d8d31786f96db688a710`, 73 vs 71), `Maker 27` (`873b81e0aeb6067dfe9500e76fdfa917`, 70 vs 68) and `Maker 07` (`96c86feb432f092a6e6c031536df0493`, 74 vs 71) on `orm_spike`; the same three on `read_store_large`, where the DAL aggregation gives 2,169, 2,167 and 2,171 and the same seven products are counted twice, so the distinct counts are 2,167, 2,165 and 2,168 by arithmetic (`--verify` only reports the first difference, 2,169 vs 2,167).
   The hit set is identical: with the post filter removed, the ids and manufacturers of the 230 hits (orm_spike) are equal between `dal` and `dal-opensearch`, and counting that set by manufacturer gives 71, 68, 71 for those three, which is what OpenSearch returns.
   A terms aggregation by product `id` on the DAL side returns 7 products with count 2 (all other buckets 1): `SPK-S-00007`, `-00027`, `-00047`, `-00067`, `-00087`, `-00107`, `-00127`; two belong to Maker 17, two to Maker 27, three to Maker 07, which accounts for the 2, 2 and 3.
   Mechanism: `ProductSearchTermInterpreter` keeps only the best `relevant_keyword_count` terms (8 in `shopware.yaml`), here `hotel` and seven dictionary terms `hotel 00007`, `hotel 00027`, ..., `hotel 00127`.
   Each of the seven products owns one of those terms next to `hotel`, so it matches two rows in `product_search_keyword` for the context language and the DAL aggregation counts the product twice; the id query groups by product and counts once.
   I confirmed the counts, the seven products, the cap of 8 and the keyword rows; I did not capture the SQL of the aggregation, so that the aggregation joins without `DISTINCT` is inferred from the doubled counts.
   Effect: with the keyword search, a DAL terms aggregation can over-count products that match several of the interpreted terms; this is a core finding (finding 36 in `docs/core-findings.md`).

So O1 (and a store that holds documents) is a drop-in for S1, S3 and S5 only when the DAL side excludes parents with variants, and for R3b the stores must not copy the DAL's duplicate count: the contract result is the distinct count.

### PostgreSQL id codec treats some ids as text

`IdCodecMiddleware::encode()` in guess mode (an untyped 16 byte parameter) treated the value as text when it is valid UTF-8.
About 1 in 65,000 random ids is valid UTF-8; at about 9,050 products a parent id hit it and `VariantListingUpdater` (`execute(['id' => $parentId, ...])`, untyped) failed with an invalid uuid error on PostgreSQL, which stopped the seed.
Commit `cddda24a6e1` on `poc/read-store` treats untyped 16 byte values with control bytes (`[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]`) as ids and has a unit test with the failing id; it still guesses text for printable 16 character strings, so it narrows the problem but does not remove it (the cause is untyped binding in core code, see `docs/core-findings.md` finding 35).
This file is owned by the PostgreSQL work, not by handoff P; the change was necessary to seed `read_store_large` on PostgreSQL.

## Deviations

- The R3b, S/R timings and R5 are from one block; R6 and R7 ran outside the lock (see above).
- The PostgreSQL run is a correctness run only (no timings, no OpenSearch index in the timing block).
  Its index prefix is `rs_o1_<db>_pg_`, so it cannot clash with the MySQL indices.
- `DalImplementation` is no longer `final` (`DalOpenSearchImplementation` extends it).
- `harness.php`: `tagged_locator` needed the index attribute `key` (fixed).
- The codec fix touched `IdCodecMiddleware.php`, which is outside the harness; it is a separate commit.
- `read-store:bench:rebuild` does not count the statements of the `es:index` child process.
- `docs/environment/eb.Dockerfile` and `presentations/` in the research repo are not part of this handoff.
- The host load was 9 to 24 during the block despite the stopped lanes.

## Commits

| Repo | Commit | Content |
|---|---|---|
| `instance/` | `7819b64` | `composer.json`: `mongodb/mongodb ^2.5` |
| `instance/` | `86920d52b39` | `feat(core): read store harness ready` |
| `instance/` | `cddda24a6e1` | PostgreSQL id codec fix |
| `instance/` | `7a82cabebff` | R3b contract docblock |
