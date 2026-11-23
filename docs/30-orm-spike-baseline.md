# ORM spike baseline: branch, data, harness, DAL and DBAL

State: 2026-11-23, wave 8 handoff B.
This doc is the contract for the handoffs D (Doctrine), C (Cycle) and V (DAL v2): everything they need to register an implementation and run it against the same data and scenarios.
Question and candidates: `docs/29-orm-alternatives.md`.

## Branch and packages

- Branch `poc/orm-spike` in `instance/`, created from `poc/db-independent` at `87e1768ce3a`.
- Added with composer (in `instance-web-1`): `doctrine/orm ^3.8`, `cycle/orm ^2.19`, `cycle/annotated ^4.7` and dev `phpstan/phpstan-doctrine ^2.1`.
- `composer.lock` is in `.gitignore` of this checkout, so only `composer.json` is committed (commit `1d6aaa753d7`).
- All spike code lives in `src/Core/Framework/OrmSpike/`.
- The only change outside that folder is in `src/Core/Framework/Framework.php`: after `mcp.php` it loads every `OrmSpike/DependencyInjection/*.php` (a glob), so a new services file needs no further registration.

## Register an implementation (D, C, V)

1. Write a class that implements `Shopware\Core\Framework\OrmSpike\Harness\Implementation` in your folder (`Doctrine/`, `Cycle/`, `DalV2/`).
2. `static key(): string` returns the value of `--impl` (`doctrine`, `cycle`, `dalv2`).
3. Fill your own services file `OrmSpike/DependencyInjection/<doctrine|cycle|dalv2>.php` (a commented stub exists) and tag the service `orm_spike.implementation`.
   See `DependencyInjection/dbal.php` for a complete example.
4. `configure(array $options)` receives the `--option key=value` pairs (V switches levers with them).
5. A scenario you do not implement: throw `Harness\ScenarioNotSupported`, the bench records it as `unsupported`.
6. Run it: `scripts/orm-spike-env.sh` defines `spike_console`, which calls `bin/console` in `instance-web-1` with `APP_ENV=prod`, a separate cache dir and `DATABASE_URL` of the engine.
   Set `SPIKE_CACHE_BASE=/tmp/sw-orm-spike-<yourhandoff>` before sourcing so parallel sessions do not share one cache directory.
   Clear that cache after a services change (`spike_console cache:clear`).

```bash
. scripts/orm-spike-env.sh postgresql   # mysql | mariadb | postgresql | sqlite
spike_console orm-spike:bench --impl=doctrine --scenario=all --iterations=50 --warmup=5 --verify
```

Do not run `scripts/orm-spike-install.sh` (it drops and recreates `orm_spike` and reseeds); the databases are ready.
If a run writes data outside S4, clean it up: the data set must stay identical for everyone.

## Data set

Databases `orm_spike` on MySQL 8.4 (`instance-mysql-1`), MariaDB 10.11 (`instance-database-1`), PostgreSQL 18 (`instance-postgres-1`) and the SQLite file `/var/www/html/var/switch/orm_spike.sqlite`.
URLs are in `scripts/orm-spike-env.sh` (hosts `mysql`, `database`, `postgres` inside the container network).
Created by `scripts/orm-spike-install.sh <engine>` (`system:install` plus `orm-spike:seed`, about 40 s per engine), which can rebuild a database at any time.
The data is generated through the DAL (`product.repository`) with deterministic ids: `md5('orm-spike/<kind>/<parts>')` (`Harness/Fixtures.php`).

| Table | Rows (identical on all four engines) |
|---|---|
| product | 5,000 |
| product_translation | 6,772 |
| product_price | 1,020 |
| product_category | 7,888 |
| product_category_tree | 11,600 |
| product_visibility | 3,060 |
| product_media | 3,800 |
| product_option | 3,200 |
| category | 51 |
| product_manufacturer | 31 |
| product_manufacturer_translation | 54 |
| media | 203 |
| property_group / property_group_option | 2 / 9 |
| rule | 4 |

Counts were taken after the seed on each engine from the seed log (`/tmp/orm-spike-install-<engine>.log`) and are equal on all four.

Content:

- 3,000 simple products and 400 parents with 4 variants each (`Fixtures::SIMPLE`, `PARENTS`, `VARIANTS_PER_PARENT`), 50 categories, 30 manufacturers, 200 media.
- Languages en-GB (system) and de-DE, one sales channel (storefront) with both; currency EUR plus USD.
- 15 percent of the simple products have no de translation (language fallback), every 20th product is inactive, 90 percent of simple products and parents are visible in the sales channel, every fifth product has a USD price and rule price rows.
- Variant 0 inherits everything, variant 1 has its own manufacturer, variant 2 its own name (en only), variant 3 its own price and cover; every variant has its own stock and its options (Color, Size).
- Indexers: product indexer parts search keyword, stream and rating run after the seed; the row count of `product_category_tree` comes from that indexer run.

Dataset invariants the hand-written SQL relies on (a different seed could break them):

- Variants never own `product_visibility` or `product_category` rows, they inherit from the parent.
- Variants never own `product_price` rule rows.
- Prices are compared as gross price in the default currency (key `c<currencyId>` of the `price` JSON), own or inherited.

## Scenario parameters (`Harness/ParamsFactory.php`)

- Sales channel: the storefront one; language de-DE, system language en-GB (fallback chain `[de, en]`), currency EUR.
- S1: category 5 (`Fixtures::categoryId(5)`), page 2, limit 24.
- S2: variant `Fixtures::variantId(15, 0)` (inherits everything from its parent).
- S3: term `LI` (case-insensitive contains in the name), manufacturers 3, 7, 11, 17, 23, page 1, limit 24.
- S4: 50 products per run (`Fixtures::writeProducts(runId)`, numbers `SPK-W-<run>-NN`), 2 translations, 1 price, 2 categories, 1 visibility each, then the stock update of the 50.
- S5: criteria JSON: filters `active equals true`, `stock range gte 20 lte 80`, `name contains o`, sort `productNumber DESC`, limit 10, total-count-mode 1, association `manufacturer`.

All reads are storefront reads: live version, active (inherited), visibility >= 10 in the sales channel (the `ProductAvailableFilter` of `SalesChannelProductDefinition`).

## Result contract (`Harness/ResultContract.php`)

Plain arrays, hex ids in lower case, associative keys sorted before compare (`ResultContract::canonical`), prices as strings with two decimals (`ResultContract::price`), gross price of the default currency.

- S1 `{total, items[{id, productNumber, name, manufacturer, cover, price}]}`, sorted by translated name then product number; `cover` is the media path; `total` is the exact count.
- S2 `{id, productNumber, name, description, manufacturerId, manufacturer, cover, price, prices[{quantityStart, quantityEnd, price}], options[{group, name}], categories[hex]}`; the variant's own to-many rows, else the parent's.
- S3 `{total, items[{id, productNumber, name, manufacturer, price}], aggregations{minPrice, maxPrice, manufacturers{hex: count}}}`; aggregations run over all matches, not only the page.
- S4 returns nothing; correctness is the written rows (`WriteSnapshot`: stock, active, tax, price gross and net, translations per language, categories, visibilities).
- S5 `{total, items[{id, productNumber, manufacturer}]}`.

## Harness usage

```bash
bin/console orm-spike:bench --impl=<dal|dbal|doctrine|cycle|dalv2> --scenario=<S1,S3|all> \
  --iterations=50 --warmup=5 [--verify] [--option key=value ...] [--output-dir=var/orm-spike]
bin/console orm-spike:seed [--simple=N --parents=N --skip-index]   # refuses to run when products exist
```

- Per scenario: warm-up runs, `memory_reset_peak_usage()`, then timed iterations with `hrtime`; median, p95, min, max, statements per iteration, peak memory.
- S4 writes a fresh set per iteration (`SPK-W-m<run>-NN`) and deletes it again outside the timed part (`WriteCleaner`, rows with `product_number LIKE 'SPK-W-%'`).
- Output `var/orm-spike/<engine>-<impl>.json` (merged per scenario, includes `options`, php version, env, date, load average).
  The engine name is the `SqlDialect` name (`mysql`, `mariadb`, `postgresql`, `sqlite`).
- `--verify` compares the implementation with the `dal` result, S1 to S3 and S5 by result, S4 by the written rows, and prints the first difference.
  An empty DAL result counts as a failure so a scenario cannot verify nothing.

### Statements per implementation

`StatementCounter` reads the `QueryCountMiddleware` that `KernelFactory` registers on the default DBAL connection (counts `exec`, `query` and executed prepared statements, not BEGIN or COMMIT).
This covers the DAL, DBAL, DAL v2 and Doctrine (when it uses the shared connection).
Cycle uses its own connection (`cycle/database`): count there with a logger on the driver and report through `StatementCounter::add(int)`, the bench reads the sum.
`StatementCounter::isAvailable()` tells whether a number exists; the JSON has `statementsCounted`.

## DAL reference (`Dal/DalImplementation.php`)

Services used:

- `sales_channel.product.repository` (`SalesChannelRepository`) for S1, S2, S3, S5, with a `SalesChannelContext` from `CachedSalesChannelContextFactory` (created once; language chain de, en, currency).
  `SalesChannelProductDefinition::processCriteria` adds the availability filter and the associations prices, unit, delivery time, cover media and tax by itself.
- `product.repository` (`EntityRepository`) for S4 `create` then `update`, with `EntityIndexerRegistry::DISABLE_INDEXING` set (indexers are out of scope).
- `RequestCriteriaBuilder::fromArray` for S5.
- S3 aggregations: `MinAggregation`, `MaxAggregation` on `price.gross` and `TermsAggregation` on `manufacturerId`.

## DBAL reference (`Dbal/DbalImplementation.php`)

Hand-written SQL on the DBAL connection with `IdBinding` (hex ids on uuid and binary(16)) and `SqlDialect` (case-insensitive compare, JSON number extraction).
Translation fallback is `COALESCE(own de, parent de, own en, parent en)` over four joins, inheritance a `COALESCE` over the parent join, total count `COUNT(*) OVER()`.
The file has 427 lines in total including shared helpers; the methods are about: S1 17, S2 73, S3 43, S4 56, S5 60 lines, helpers about 130.
Statements: S1 1, S2 4, S3 3, S4 inserts into 4 tables plus 1 update, S5 1.

What the DAL does in S4 that DBAL skips: write validation and constraint checks, write protection and flag checks of the fields, `EntityWrittenEvent` and `EntityWrittenContainerEvent` dispatch, the version handling and write command queue, translation and price field serializers, default values and required field checks, `product.indexer` messages and the "indexer after write" subscribers (disabled here by `DISABLE_INDEXING`, so only the event and serializer overhead remains in the measurement).
The DBAL write also hard-codes the columns it fills, so a new required column breaks it silently at runtime.

## Verify results

`--verify` for `dbal` against `dal`, run on 2026-11-23 on all four databases: S1, S2, S3, S4 and S5 pass on MySQL, MariaDB, PostgreSQL and SQLite.
One failure was found and fixed on the way: PostgreSQL rejected `COALESCE(p.active, pp.active)` as a condition because `active` is `smallint` there (fixed with `= 1`).

## Baseline timings

Block of 2026-11-23, `APP_ENV=prod`, warm cache, 5 warm-up and 50 measured iterations per scenario, PHP 8.4.17, database containers with 8 CPUs / 16 GiB.
Host load average (1, 5, 15 min) at the end of the block: 5.63, 5.76, 5.66; 4.45, 5.23, 5.48 at the start.
Other lanes stopped: yes (47 containers, restarted afterwards); the load comes from the host itself, not from the lanes.
Medians in ms, p95 in ms in brackets, statements per iteration, peak memory in MB (peak memory of DBAL is mostly the booted kernel).
Raw JSON: `instance/var/orm-spike/<engine>-<impl>.json` (not versioned).

### mysql

| Scenario | DAL ms (p95) | DAL stmts | DAL MB | DBAL ms (p95) | DBAL stmts | DBAL MB |
|---|---|---|---|---|---|---|
| S1 | 15.29 (18.68) | 4 | 40.9 | 2.14 (2.27) | 1 | 24.8 |
| S2 | 4.65 (6.48) | 5 | 50.5 | 0.51 (0.61) | 4 | 24.8 |
| S3 | 48.92 (72.71) | 7 | 50.9 | 15.65 (19.11) | 3 | 24.8 |
| S4 | 88.05 (116.46) | 371 | 58.1 | 5.95 (7.01) | 5 | 25.4 |
| S5 | 26.95 (36.22) | 4 | 56.7 | 17.32 (20.95) | 1 | 24.8 |

### mariadb

| Scenario | DAL ms (p95) | DAL stmts | DAL MB | DBAL ms (p95) | DBAL stmts | DBAL MB |
|---|---|---|---|---|---|---|
| S1 | 9.99 (10.86) | 4 | 40.9 | 2.99 (4.88) | 1 | 24.8 |
| S2 | 3.95 (4.33) | 5 | 50.5 | 0.63 (0.90) | 4 | 24.8 |
| S3 | 34.02 (42.96) | 7 | 51.0 | 23.12 (25.13) | 3 | 24.8 |
| S4 | 88.76 (119.71) | 371 | 58.1 | 6.32 (8.05) | 5 | 25.4 |
| S5 | 26.87 (29.79) | 4 | 56.7 | 17.40 (19.37) | 1 | 24.8 |

### postgresql

| Scenario | DAL ms (p95) | DAL stmts | DAL MB | DBAL ms (p95) | DBAL stmts | DBAL MB |
|---|---|---|---|---|---|---|
| S1 | 20.22 (21.46) | 4 | 41.4 | 33.36 (41.75) | 1 | 25.1 |
| S2 | 11.51 (12.84) | 5 | 51.1 | 3.00 (4.16) | 4 | 25.1 |
| S3 | 71.66 (81.61) | 7 | 51.7 | 31.93 (36.58) | 3 | 25.1 |
| S4 | 93.43 (115.19) | 123 | 58.6 | 11.85 (13.48) | 5 | 25.8 |
| S5 | 40.33 (43.24) | 4 | 57.5 | 27.56 (28.39) | 1 | 25.2 |

### sqlite

| Scenario | DAL ms (p95) | DAL stmts | DAL MB | DBAL ms (p95) | DBAL stmts | DBAL MB |
|---|---|---|---|---|---|---|
| S1 | 60.51 (67.99) | 4 | 41.4 | 18.20 (19.36) | 1 | 25.2 |
| S2 | 15.96 (16.40) | 5 | 50.9 | 0.28 (0.34) | 4 | 25.2 |
| S3 | 129.01 (144.91) | 7 | 51.5 | 16.94 (26.41) | 3 | 25.2 |
| S4 | 329.35 (375.70) | 371 | 58.7 | 5.52 (13.18) | 5 | 26.0 |
| S5 | 62.17 (75.11) | 4 | 57.2 | 12.68 (13.69) | 1 | 25.3 |

Observations (measured, causes not investigated):

- DBAL is faster than the DAL in every scenario on MySQL, MariaDB and SQLite; on PostgreSQL S1 is slower in DBAL (33.4 ms) than in the DAL (20.2 ms) and S3 and S5 are within a factor of 1.5 to 2.
- The DAL S4 write runs 371 statements on MySQL, MariaDB and SQLite but 123 on PostgreSQL.
- The DBAL numbers are the floor for this data set, the DAL numbers are what ORM candidates have to beat or explain.


## Rebuild the data

```bash
scripts/orm-spike-install.sh mysql     # also mariadb | postgresql | sqlite; optional seed options after the engine
```

It drops `orm_spike`, runs `system:install --basic-setup`, clears the cache and runs `orm-spike:seed` (log in `/tmp/orm-spike-install-<engine>.log`).
Never point it at `shopware`, `shopware_test`, `shopware_switch` or `bench_*`.

## Notes for the others

- The spike code does not pass the Shopware PHPStan rules for core code (native `hrtime`/`date`, `md5`, `new \RuntimeException`); these are spike shortcuts, not findings.
- The DAL needs `DISABLE_INDEXING` for a fair write comparison; an ORM write does not run the indexers either.
- One Shopware detail that cost time: `product.active` is `smallint` on PostgreSQL and `tinyint` on the others, hand-written SQL must compare with `= 1`.
