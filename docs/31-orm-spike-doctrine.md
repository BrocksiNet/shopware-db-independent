# Doctrine ORM 3.8 on the Shopware schema (wave 8 handoff D)

State: 2026-11-23.
Code: `instance/src/Core/Framework/OrmSpike/Doctrine/` and `.../DependencyInjection/doctrine.php` on branch `poc/orm-spike` (commits `3781221780b` and `e6b4bde5610`, local only).
Context: `docs/29-orm-alternatives.md` (question, probes), `docs/30-orm-spike-baseline.md` (harness, DAL and DBAL baselines).
Doctrine documentation root: https://www.doctrine-project.org/projects/doctrine-orm/en/3.6/index.html (feature statements below are backed by a run or by the vendor source path named next to them).

## Result in short

- All five scenarios pass `orm-spike:bench --verify` (output equals the DAL output) on MySQL, MariaDB, PostgreSQL and SQLite, in both modes (idiomatic and optimized).
  Re-run after the last code change: 5 of 5 OK for each of the 8 combinations.
- Probes: 6 of 7 pass; the one that fails is "plugin adds a field to the core entity" (exact exception below).
- Idiomatic Doctrine needs 15 to 450 statements per scenario (N+1 on collections); the optimized mode (scalar DQL, array hydration) reaches the statement counts of hand written DBAL for S1, S2, S3 and S5.
- Doctrine code: 1830 lines in 23 files, of which 499 are the implementation, 75 the criteria translator, 67 the DQL functions, 53 the id type, 49 the factory, 564 the mapped entities, 523 are probes (command, runtime driver, two probe entities).

## Wiring

- `EntityManagerFactory::create(Connection, cacheDir, namespace, ?driver, ?eventManager)` builds an `EntityManager` on Shopware's existing DBAL `Connection` (the same object, so the same middlewares, one connection).
  The PostgreSQL and SQLite translators of the project therefore apply to everything Doctrine sends.
- Mapping: PHP attributes (`#[ORM\Entity]`, `#[ORM\Table]`) via `AttributeDriver`, mapped onto the existing tables, no schema tool.
- Cache: PSR-6 `ChainAdapter(ArrayAdapter, FilesystemAdapter)` under `%kernel.cache_dir%` for metadata, query and result cache.
- Lazy loading: PHP 8.4 native lazy objects (`enableNativeLazyObjects(true)`), no generated proxy classes and no proxy cache warm-up.
  Reason: fewer moving parts and no generated code to ship; it needs PHP 8.4, which the lane has but Shopware trunk does not require yet.
- No `doctrine/doctrine-bundle`: three service definitions in `doctrine.php` are enough (entity manager factory, the implementation, the probe command).
- Registered DQL functions (built on the project's `SqlDialect`, so one DQL string runs on all four engines):
  - `SW_CI(expr)`: case-insensitive comparison (`lower(col) COLLATE ucs_basic` on PostgreSQL).
  - `SW_PRICE(own, parent, 'c<currencyId>')`: JSON number extraction cast to `DECIMAL(20,4)`.
  - `SW_TOTAL()`: `COUNT(*) OVER()`, used for the total of a page in the same statement.

## Id type

- Custom DBAL type `shopware_id` (`Type/ShopwareIdType.php`, 53 lines).
- PHP side: 32 character lowercase hex string, as everywhere in the DAL.
- Writing and parameters: `IdBinding::value()` and binding type `IdBinding::type()`, so `uuid` text on PostgreSQL and `binary(16)` elsewhere; the decision stays in `IdBinding`.
- Reading: `IdBinding::toHex()`, which also accepts the dashed uuid string PostgreSQL returns.
- DQL parameters and `IN` lists work with `setParameter($name, $value, 'shopware_id')` and `IdBinding::listType()` (used in the S4 stock update and in the S3 manufacturer filter, verified on all four engines).

## Mapping friction list

Everything below was hit while mapping the existing schema.

1. Composite foreign id.
   Doctrine cannot use an association to an entity with a composite key as part of another entity's primary key.
   `ClassMetadata.php:1360` in `vendor/doctrine/orm` throws `MappingException::cannotMapCompositePrimaryKeyEntitiesAsForeignId`.
   `product_translation` and `product_manufacturer_translation` (key: id + version_id of the parent plus language) are mapped with plain `#[Id]` scalar columns and a separate ManyToOne that shares the same join columns.
   Cost: the translation entity sets `productId` and `productVersionId` by hand next to the association (without it S4 fails with `EntityMissingAssignedId`).
   Translations of `property_group` and `property_group_option` (single id parents) have no problem.
2. Parent self-reference with `parent_id` + `parent_version_id`: works as a ManyToOne with two join columns.
   Read-only duplicate columns (`Column(insertable: false, updatable: false)`) next to the join columns give plain fields for DQL conditions (`parentId`, `manufacturerId`, `coverId`).
3. `indexBy` uses the raw database value as the collection key (`ObjectHydrator` and `ArrayHydrator` read `$row[indexByMap]`), which bypasses the custom type.
   The key is binary on MySQL, MariaDB and SQLite and a dashed uuid on PostgreSQL, so `indexBy: 'languageId'` is unusable with hex ids.
   Workaround: no `indexBy`, a helper `in()` that searches the loaded translation collection.
4. `getScalarResult()` does not convert DBAL types (ids came back raw), `getArrayResult()` does.
   Expression results (for example `COALESCE(m.id, pm.id)`) are never converted, so they go through `IdBinding::toHex()` by hand.
5. `product.active` is smallint on PostgreSQL and tinyint elsewhere, so it is mapped as int, not boolean; a bool in the criteria is cast.
6. DQL `ORDER BY` accepts only a path or a result variable, so computed sorts are written as `expr AS HIDDEN sN`.
7. DQL `CASE` requires `ELSE`.
8. A bound parameter that the query does not use raises a "bound variables do not match" error, so the query code must only set the parameters it uses.
9. The price JSON path: `SW_PRICE` puts the currency key into a quoted SQL string, so the key must be a DQL string literal, not a bound parameter (validated with `ctype_xdigit` first).
10. Version columns: every query on `Product` and its children carries `version_id` conditions by hand (live version in `base()`); there is no global filter that the DAL context gives for free.
11. JSON columns (`price`, `cheapest_price`) map as `json` arrays; the cheapest price rule logic is not expressible as mapping and stays in `SW_PRICE` and PHP.

Entities mapped: `Product` (composite id), `ProductTranslation`, `Manufacturer` and translation, `Media`, `ProductMedia`, `ProductPrice`, `ProductVisibility`, `Category`, `ProductCategoryTree` (read only), `PropertyGroup`, `PropertyGroupOption` and their translations.
ManyToMany: `product_category` and `product_option`.

## Scenarios

Two modes, selected with `--option mode=idiomatic|optimized` (default idiomatic).

- Idiomatic: entities, DQL with fetch joins of the to-one associations, `Paginator` for counted pages, lazy collections for the rest, `persist` and `flush` for writes.
- Optimized: scalar DQL with `getArrayResult()`, entity joins `WITH` using `COALESCE` for parent inheritance, `SW_TOTAL()` for the count in the same statement, batched by-id reads for S2, one DQL `UPDATE ... CASE ... ELSE p.stock END` for the stock.

Statements per run (counted by the harness, same on all engines unless noted), verify result on MySQL, MariaDB, PostgreSQL and SQLite, lines of implementation code (method plus its helpers, approximate):

| Scenario | Idiomatic statements | Optimized statements | DBAL statements | DAL statements | Verify | Lines |
|---|---|---|---|---|---|---|
| S1 listing | 32 | 1 | 1 | 4 | OK x4 | about 14 plus `base()` 36, `entityListing` 27, `scalarListing` 26 |
| S2 detail | 15 | 4 | 4 | 5 | OK x4 | about 8 plus `entityDetail` 51, `scalarDetail` 63, `preferOwn` 7 |
| S3 search | 45 | 3 | 3 | 7 | OK x4 | 45 |
| S4 write | 450 | 351 | 5 | 371 on MySQL and MariaDB | OK x4 | 70 |
| S5 criteria | 22 | 1 | 1 | 4 | OK x4 | 17 plus the translator (75) |

Where N+1 appears (idiomatic mode): S1 and S3 load translations, prices and media of each listed product through lazy collections after the page query (32 and 45 statements for a page of 24); S2 loads parent, options, option groups and categories lazily (15).
The S4 write cannot be batched by Doctrine: `flush` sends one INSERT per row (50 products, 100 translations, 50 visibilities, 100 category links), and the idiomatic stock update runs a second flush with one UPDATE per product (450 statements).
The optimized S4 replaces only the stock part with one DQL UPDATE (351 statements).
What the DAL does on top that the ORM path skips in S4 (see `docs/30`): `EntityWrittenEvent` dispatch, the indexers, the write validation and `version_commit` bookkeeping.

## Probes

Run with `bin/console orm-spike:doctrine-probes` (`Probe/ProbeCommand.php`), on all four engines.
Every probe cleans up what it created; PostgreSQL and MySQL showed 0 leftover `SPK-PROBE-%` or `SPK-W-%` rows and no leftover spike tables afterwards.

| Probe | Result | How, cost |
|---|---|---|
| Translations with fallback to the system language | PASS (via S1, S2 verify) | four joins (own and parent translation, requested and system language) with `COALESCE` in DQL for the scalar mode; in entity mode a helper searches the loaded translations. No extension used: see "Extensions" below. |
| Variant inheritance (also cover, manufacturer, prices) | PASS (via S1, S2 verify) | `COALESCE(own, parent)` per field in DQL, entity joins `WITH m.id = COALESCE(p.manufacturerId, pp.manufacturerId)` for associations, `SW_PRICE(own, parent, key)` for prices. Hand written per field; no declarative inheritance. |
| Versioning (read live, write a draft, merge) | PASS | `find(Product::class, ['id' => ..., 'versionId' => ...])` works with the composite key; two rows with the same id and different version ids were persisted, read, merged by copying the draft values onto the live row and removing the draft. Merge is hand written; there is no version, `version_commit` or merge rule machinery. |
| Plugin adds an association (new table, new class) | PASS | `Probe/Entity/PluginNote.php` (31 lines) maps `spike_plugin_note` with a ManyToOne to the core `Product` (composite join columns); persist and DQL joins work. The core `Product` class has no property for it, so `$product->pluginNotes` does not exist. |
| Plugin adds a field to the core `Product` | FAIL | A `loadClassMetadata` listener that calls `mapField(['fieldName' => 'ean', ...])` for the unmapped but existing column `product.ean` fails when the metadata is used: `ReflectionException: Property Shopware\Core\Framework\OrmSpike\Doctrine\Entity\Product::$ean does not exist` (same on all four engines). Doctrine reflects every mapped field, so the core class must declare the property. A typed exposure therefore needs the core entity to declare it (or a generic bag property). Not tried: a subclass entity per plugin with inheritance mapping; it would not compose when two plugins extend the same entity. |
| App custom entity at runtime without a hand written class | PASS with a generated class | `Probe/RuntimeEntityDriver.php` (66 lines) generates a class with `eval` per custom entity and maps columns at runtime through a `MappingDriverChain`; DQL, array hydration, `find`, `persist` and update work on a `custom_entity_*` table created at runtime. Doctrine needs a PHP class per entity; rows without a class are not possible in the ORM (arrays only through DBAL). |
| Criteria from JSON with allow list | PASS | `Query/CriteriaTranslator.php` (75 lines): the field comes from an allow list (active, stock, name, productNumber) mapped to DQL expressions, values are always bound parameters, unknown fields throw `InvalidArgumentException`, unknown filter types throw `ScenarioNotSupported`. Tested: a value `x' OR '1'='1` matches 0 rows, three malicious field or sort names were rejected, a malicious sort direction is normalised to `ASC` or `DESC`. Only what the allow list names is expressible; aggregations and nested multi filters are not translated. |
| Events (what replaces `EntityWrittenEvent`) | PASS, with a gap | An `onFlush` listener sees scheduled inserts and updates per entity class: the idiomatic S4 gave 2 flushes (200 scheduled inserts: 50 `Product`, 100 `ProductTranslation`, 50 `ProductVisibility`; 150 scheduled updates), the optimized S4 gave 1 flush (200 inserts, 50 updates). The DQL `UPDATE` of the optimized stock update runs outside the unit of work (the second flush is missing), so no entity event is fired for it. An indexer built on events would miss bulk DQL writes. |
| DX: new entity `spike_note` | PASS | see below |

## Extensions

- Packagist, checked 2026-11-23: `knplabs/doctrine-behaviors` 3.1.0 (2026-01-09) declares `doctrine/orm ^2.12|^3.0.0`; `gedmo/doctrine-extensions` 3.22.2 (2026-09-29) has no `doctrine/orm` entry in `require`.
- Not checked: whether either supports a language fallback chain with the system language as the second step. I did not use one; the fallback is done with `COALESCE` joins and counted as hand written code.

## DX walkthrough: new entity `spike_note` with table and CRUD

Doctrine (verified by the `dx` probe on all four engines):

1. One class, `Probe/Dx/SpikeNote.php`: 31 lines including the id, title, body and `createdAt` columns, with attributes only.
2. Table: no schema tool was used on Shopware tables, so the probe creates it with one `CREATE TABLE` statement; in a real plugin that is one migration class like today.
3. No definition, no collection class, no repository class, no service registration beyond adding the folder to the mapping path.
4. CRUD: `persist` and `flush`, `find`, a DQL query, a property assignment and `flush`, `remove` and `flush`, all with typed properties in an IDE.

DAL for comparison (an existing small entity, `Tag`): `TagDefinition` 83 lines, `TagEntity` 145 lines, `TagCollection` 25 lines (253 lines in three classes), plus a service definition in `src/Core/System/DependencyInjection/tag.php` and a migration (the original tag migration is 123 lines but also creates other tables, so not a fair number).
The DAL gives in return what Doctrine did not provide in this spike: translations, versioning, extension of fields and associations by plugins, `EntityWrittenEvent`, the criteria and the Store API for free.

## PHPStan level max with phpstan-doctrine

Run: temporary config (not committed) with `level: max`, the phpstan-doctrine extension and rules (loaded by the extension installer) and an `objectManagerLoader` that builds the entity manager with the project factory on an in-memory SQLite connection; paths `OrmSpike/Doctrine`.

- 82 errors in 5 files: `DoctrineImplementation.php` 46, `Query/CriteriaTranslator.php` 24, `Probe/ProbeCommand.php` 9, `Type/ShopwareIdType.php` 2, `Query/DialectFunction.php` 1.
- 67 of the 82 are `mixed` (offset access or casts on rows from `getArrayResult()` and `getResult()`); 3 are redundant nullsafe operators on entity properties; the rest are single findings (a `Collection::add()` argument type at `DoctrineImplementation.php:153` from `getReference()`, a redundant `(int)`, untyped generated classes of the runtime entity probe, an optional constructor argument).
- What the Doctrine extension caught that plain PHPStan cannot: it parsed the literal DQL in `ProbeCommand.php:186` (`SELECT p.ean FROM ...Product p`) and reported `DQL: [Semantical Error] ... Class ...Product has no field or association named ean`, which is the same failure the plugin field probe shows at run time.
  Dynamically built DQL (most of the implementation builds it with the `QueryBuilder`) is not checked.
- IDE typing: entities are typed properties, so entity mode results are typed; array hydration and DQL scalar results are `mixed` and need `@var` shapes, which is where the 67 errors come from.
- Not measured here: the same level on the DAL, so no comparison number is claimed.

## Timings

Block: handoff D under `/tmp/wave8-timing.lock`, `orm-spike:bench --scenario=all --iterations=50 --warmup=5`, `APP_ENV=prod`, warm cache, per engine the order DAL, DBAL, Doctrine idiomatic, Doctrine optimized.
Other lanes stopped: yes (46 containers of other lanes, restored afterwards).
Host load average at the start of each engine (1, 5 and 15 minutes): MySQL 8.40 6.87 6.17, MariaDB 6.46 6.54 6.07, PostgreSQL 4.90 6.12 5.94, SQLite 4.90 5.93 5.88 (the 1 minute value still contains the load of the lanes stopped just before and of the previous engine's runs).
Median ms / p95 ms (the harness also records peak memory; Doctrine peaked at 31.9 to 34.5 MB in the MySQL block).

| Engine | Scenario | DAL | DBAL | Doctrine idiomatic | Doctrine optimized |
|---|---|---|---|---|---|
| MySQL | S1 | 7.63 / 8.79 | 2.02 / 2.06 | 7.30 / 8.03 | 2.23 / 2.96 |
| MySQL | S2 | 4.25 / 4.76 | 0.46 / 0.47 | 1.94 / 2.28 | 0.69 / 0.96 |
| MySQL | S3 | 51.36 / 67.38 | 13.98 / 14.10 | 25.10 / 32.11 | 14.45 / 17.78 |
| MySQL | S4 | 86.10 / 121.00 | 5.56 / 7.72 | 49.38 / 67.44 | 31.97 / 62.66 |
| MySQL | S5 | 22.81 / 26.42 | 15.50 / 22.48 | 13.67 / 19.22 | 16.00 / 19.39 |
| MariaDB | S1 | 7.57 / 10.11 | 2.61 / 4.29 | 19.44 / 21.66 | 2.80 / 3.28 |
| MariaDB | S2 | 4.12 / 5.35 | 0.53 / 0.75 | 1.97 / 2.87 | 0.85 / 1.01 |
| MariaDB | S3 | 36.80 / 42.36 | 23.45 / 28.58 | 33.96 / 41.12 | 21.51 / 30.63 |
| MariaDB | S4 | 95.56 / 120.50 | 7.05 / 8.76 | 55.10 / 72.80 | error |
| MariaDB | S5 | 29.84 / 33.62 | 18.32 / 28.05 | 18.99 / 30.44 | 21.52 / 25.60 |
| PostgreSQL | S1 | 17.36 / 19.27 | 34.15 / 36.25 | 49.98 / 59.59 | 29.05 / 31.97 |
| PostgreSQL | S2 | 11.37 / 13.30 | 3.00 / 3.29 | 5.78 / 6.39 | 4.69 / 5.74 |
| PostgreSQL | S3 | 62.59 / 72.88 | 35.66 / 52.27 | 59.93 / 81.57 | 40.53 / 46.01 |
| PostgreSQL | S4 | error | 13.20 / 15.53 | 70.97 / 84.20 | 55.58 / 87.09 |
| PostgreSQL | S5 | 42.14 / 48.40 | 32.41 / 50.60 | 57.31 / 62.95 | 23.28 / 24.41 |
| SQLite | S1 | 60.51 / 71.70 | 21.52 / 22.92 | 37.37 / 64.72 | 23.03 / 26.95 |
| SQLite | S2 | 16.83 / 18.30 | 0.26 / 0.31 | 1.24 / 2.99 | 0.48 / 0.78 |
| SQLite | S3 | 129.76 / 138.24 | 18.82 / 21.03 | 27.98 / 35.03 | 19.51 / 20.84 |
| SQLite | S4 | error | 6.50 / 12.99 | 210.32 / 238.24 | 123.46 / 138.43 |
| SQLite | S5 | 70.75 / 92.07 | 13.11 / 13.97 | 12.43 / 13.01 | 13.03 / 14.50 |

Cells marked error: the S4 row of that implementation failed in this block (`DeadlockException` for Doctrine optimized on MariaDB, `WriteException` for the DAL on PostgreSQL and SQLite; the table only shows the start of the message).
The cause is not determined.
A short single run of the DAL S4 on PostgreSQL afterwards (2 iterations) passed with 76.7 ms median; I did not re-run the three cells as a block, so they stay empty.
Other agents ran harness code on the same databases in parallel, and the lock only covers timing blocks.

Reading of the table (only what the numbers show):

- Optimized Doctrine is within 0.9 to 1.2 times DBAL on MySQL and MariaDB for S1, S3 and S5, and 1.5 to 1.6 times on S2, with the same statement counts.
- Idiomatic Doctrine beats the DAL on MySQL for S2 to S5 and ties on S1, but loses to it on MariaDB S1 (19.4 against 7.6 ms); on PostgreSQL it loses S1 and S5, wins S2 and is level on S3.
- On PostgreSQL the DBAL baseline S1 (34.2 ms) is slower than the DAL (17.4 ms); this is the baseline of `docs/30` and not something Doctrine changes, so the PostgreSQL comparison depends on that SQL.
- S4: Doctrine writes are 4 to 32 times slower than the hand written DBAL batch (the DBAL write is 5 statements), and SQLite is the slowest (210 ms idiomatic).

## Verdict per 2019 slide reason

Source of the reasons: doc 29, slide 39 of https://speakerdeck.com/janbuecker/insight-into-the-shopware-6-core-architecture.

1. Difficult to optimize: partly holds.
   Evidence: idiomatic S1 sends 32 statements and S3 45, but the same scenarios drop to 1 and 3 statements with scalar DQL and array hydration (table above), and S1, S3 and S5 land within 0.9 to 1.2 times of DBAL on MySQL and MariaDB.
   The price: the optimized path leaves the entity model (arrays, hand written `COALESCE` joins, custom DQL functions, hand converted ids), and writes stay at 351 to 450 statements because Doctrine has no batch insert (S4 in the table; only the stock part could be moved into one DQL UPDATE).
   So it can be optimized with the escape hatches, but not by configuration.
2. Not suitable for core concepts: holds for most of them, with workarounds for the rest.
   Composite keys with `version_id` as an identifier of a parent do not map (friction 1, `ClassMetadata.php:1360`), translation fallback, variant inheritance, version merge and the price rules are all hand written (probe table), and the version filter is repeated per query (friction 10).
   What works: composite primary keys for `find` and `persist` (versioning probe), JSON columns, a custom id type per database, native lazy objects.
3. Entities not extendable for plugins: holds for fields on the core entity, does not hold for new tables.
   A plugin entity with an association to `Product` works (probe), a new field on `Product` fails with the `ReflectionException` quoted above because the core class must declare the property, so typed exposure needs core cooperation.
   Runtime entities (apps) work only with a generated PHP class per entity.
4. Not possible to enforce patterns: holds, with partial mitigation.
   Doctrine does give hooks (`onFlush`, lifecycle events, the `loadClassMetadata` event) and a PHPStan extension that checks literal DQL (it caught the unmapped field in the probe), but nothing stops a caller from running a DQL `UPDATE`/`DELETE`, which skips the unit of work and the events (events probe), and the criteria allow list, the version filter and the language fallback are code of this spike, not framework behaviour.

## Core findings

One row was added to `docs/core-findings.md`: the PostgreSQL DDL translator rejects the native `uuid` type name in `CREATE TABLE` (found while creating the probe tables).
The ORM findings (friction list) concern Doctrine and not the core, so they stay in this doc.

## Cleanup

- Probe tables (`spike_note`, `spike_plugin_note`, `custom_entity_spike_probe`) and `SPK-PROBE-%` rows are dropped by the probes themselves; S4 rows (`SPK-W-%`) are removed by the harness cleaner.
- The temporary PHPStan config lives only in the container (`var/phpstan-spike.neon`, `var/phpstan-spike-loader.php`) and is not committed.
- Stopped containers were restarted (`podman ps` shows 51 running) and the lock file removed.
