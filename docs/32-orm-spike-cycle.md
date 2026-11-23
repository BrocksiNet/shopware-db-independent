# Cycle ORM 2.19 on the Shopware schema (wave 8 handoff C)

Question: can Cycle ORM 2.19 (`cycle/orm` 2.19, `cycle/database` 2.24, `cycle/annotated` 4.7, `cycle/schema-builder` 2.13) carry the read and write paths of S1 to S5 on the Shopware schema on four databases, and what does it cost in code and time?
Scenarios, parameters and the result contract come from `docs/30-orm-spike-baseline.md`, the probes from `docs/29-orm-alternatives.md`.
Code: `instance/src/Core/Framework/OrmSpike/Cycle/` on branch `poc/orm-spike` (local, not pushed).
Official docs: https://cycle-orm.dev/docs.
Every claim below was checked in the vendor sources (`vendor/cycle/`) or by a run, the file is named where it matters.

## Result in short

- S1 to S5 pass `--verify` against the DAL on MariaDB, MySQL, PostgreSQL and SQLite, in the idiomatic and the optimized variant .
- Cycle reuses Shopware's connection: a `Driver` subclass hands out the PDO of the DBAL connection, no second connection is opened.
- Mapping Shopware's schema works but needs hand work in every place where Shopware's concepts are not Cycle's: translation fallback (four joins), parent inheritance (PHP code), `version_id` composite keys (work), merge of a version (hand written).
- Reads: Cycle needs 11 to 17 statements where the DAL needs 4 to 7 (one postload per relation and level), and is faster than the DAL in every read cell (S1, S2, S3, S5 on four engines), see the timings.
- Writes: the unit of work sends one statement per row, 350 statements for S4 (DAL: 371, on PostgreSQL 123).
- Plugin extension and app custom entity work at runtime (schema is a plain PHP array, `StdMapper` needs no class), but a field added at runtime does not appear on a typed entity class.
- PHPStan level max: 191 errors on the spike code with the repo configuration, 121 of them about `mixed` coming back from Cycle's untyped results, no Cycle PHPStan extension found.

## Wiring

Cycle has its own connection layer (`cycle/database`, PDO), not Doctrine DBAL.
It can reuse Shopware's connection without a second one:

- `Cycle\Database\Driver\Driver::createPDO()` is `protected` (`vendor/cycle/database/src/Driver/Driver.php`), so `Connection/SharedPdo.php` (a trait, 38 lines) overrides it to return `$connection->getNativeConnection()` of the Shopware DBAL connection.
- `Connection/SharedMySQLDriver.php`, `SharedPostgresDriver.php`, `SharedSQLiteDriver.php` are three 15 line classes (`final class X extends XDriver { use SharedPdo; }`), `CycleBootstrap::database()` (70 lines with the schema/ORM part) builds the `DatabaseManager` with those drivers and a dummy DSN that is never used.
- The same trait counts every statement in `StatementCounter` (the harness counter), by overriding `statement()`.
- `DependencyInjection/cycle.php` registers `CycleImplementation` and the probe command, `Connection` and `StatementCounter` are the only arguments.

What Cycle bypasses, because it talks to the PDO and not to the DBAL connection:

| Shopware layer | Effect on Cycle |
|---|---|
| PostgreSQL `SessionMiddleware` (`SET NAMES`, time zone, search path) | settings live on the shared native PDO, they apply to Cycle too; Cycle's own `SET` statements are skipped because `createPDO()` is overridden |
| `SqlTranslationMiddleware` (MySQL to PostgreSQL SQL) | not applied, Cycle emits its own dialect SQL; the raw fragments we wrote (`COALESCE`, `EXISTS`, JSON extract) go through `SqlDialect` by hand |
| `IdCodecMiddleware` (hex to `uuid` / `binary`) | not applied, the id typecast does it (below) |
| `PlanCacheMiddleware` | not applied, Cycle's statements are not plan cached on PostgreSQL |
| `ExceptionConverterMiddleware` | not applied, errors surface as `Cycle\Database\Exception\StatementException` (seen in probe errors) |
| SQLite `SessionMiddleware`, `TextBindingStatement` and the PHP functions of `SqliteFactory` | the PHP functions live on the native PDO and stay registered; the text binding wrapper is a DBAL statement and is not used, Cycle binds plain values as `PARAM_STR` |

Cycle binds plain values as `PARAM_STR`.
That is what the DAL does for ids on SQLite as well (binary ids bound as text), and PostgreSQL infers `uuid` from an untyped parameter, so no extra handling was needed.
`Select::where()` values are not passed through the typecast, so `IdBinding::value()` is applied by hand in every `where()` with an id.

Cost of a second connection on PostgreSQL (not needed, measured earlier in this handoff to answer the question, ad hoc script, not kept in the repo): about 4 ms to connect, 0.13 ms for the session setup and about 7.5 ms for the first case-insensitive compare per backend (ICU collator warm-up).
`docs/22-postgresql-connection-and-planning.md` has the wave 7 numbers for new connections.
A separate Cycle connection would therefore add roughly 4 ms plus up to 7.5 ms of warm-up per request on PostgreSQL, and would hold a second backend and a second transaction.
With the shared PDO this cost is zero, and a Cycle transaction and a DBAL transaction are the same transaction (note: starting a DBAL transaction and then a Cycle unit of work fails with PDO "There is already an active transaction", the Cycle driver counts its own level; I hit this in the versioning probe and used `$database->begin()` instead).

## Schema variants

| Variant | Files | Lines | Notes |
|---|---|---|---|
| Runtime schema array (used for S1 to S5) | `SchemaFactory.php` | 155 for 15 roles | plain PHP arrays, no reflection, no annotations; `build()` takes 11.5 us, a `var_export` cache file takes 95 us to include without opcache, so a cache in `var/cache` only pays with opcache |
| Attributes via `cycle/annotated` | `Probe/Attr/AttrManufacturer.php` | 27 | `#[Entity]` and `#[Column]`, compiled with `Entities`, `Embeddings`, `MergeColumns`, `GenerateRelations`, `ValidateEntities`, `GenerateTypecast`; no `RenderTables` or `SyncTables`, so Shopware tables are never touched; entity read with the hex id typecast on all four engines (probe `attribute schema`) |

The compile step of the attribute variant (tokenizer scan of the directory, reflection) was not timed; it must run at cache warm-up, not per request.
The 15 entity classes (`Entity/*.php`, 362 lines) are plain classes with public typed properties generated by a script outside the repo.

## Id typecast

`HexIdTypecast.php` (62 lines) is a typecast handler for the rule `hexid`, composed with Cycle's own `Typecast` through `TYPECAST_HANDLER => [HexIdTypecast::class, Typecast::class]` (a handler list is supported by Cycle ORM 2.x for `S::TYPECAST_HANDLER`).
`cast()` (database to PHP) uses `IdBinding::toHex()`, `uncast()` (PHP to database) uses `IdBinding::value()`, so the per-database decision (`uuid` on PostgreSQL, `binary(16)` elsewhere) stays in `IdBinding`.
Works for primary keys, foreign keys, composite keys and `where` with lists (`IdBinding::values()`).
Only the root row is typecast by `Select::fetchData()` (`Select.php:987`), relation data are raw, the optimized variant converts ids by hand (`toObject()`).

## Mapping friction list

1. The `product` table has `binary(16)` columns that are named like associations (`tax`, `manufacturer`, `cover`, `media`, `translations`, `prices`, `categories`, `visibilities`, `unit`, checked in `information_schema` on MariaDB); they are simply not mapped as columns.
2. `version_id` is part of almost every key, so every relation has a composite key (`INNER_KEY => ['id', 'versionId']`).
   Composite keys and relations over them work; a composite postload becomes `(a = ? AND b = ?) OR ...` per parent.
3. `version_id` columns are `NOT NULL` even where the id is null (optional foreign keys), so a plain nullable belongs-to cannot be saved for those; reads are fine.
4. A relation is joined once per path and alias, so reading two languages of one translation table needs a second relation to the same table (`translationsAlt`); the S1 query joins `translations`, `translationsAlt`, `parent.translations`, `parent.translationsAlt` (aliases `t1` to `t4`).
5. Relation `where` options use plain field names (`languageId`), the `{@}.column` syntax throws `LoaderException: Undefined relation`.
6. `product.active` is `smallint` on PostgreSQL, a typecast `int` is needed.
7. The price is a JSON column, kept as a string and read with `json_decode` (a JSON typecast would work, we did not need it for the contract).
8. The parent self-reference (`parent_id`, `parent_version_id`) works as a belongs-to to the same role; inheritance itself is PHP code (below).
9. `Select::count()` is a separate `COUNT(*)` statement with the same joins; `addGroupByPK()` forces `GROUP BY` on the primary key when `limit > 1` or an offset is set and joined loaders exist (`Select.php`), so aggregates for S3 are built with `buildQuery()->columns(...)` on a select without limit (3 more statements, same joins).
10. Reading a relation that was not loaded on an entity runs a query per entity (lazy proxy).
    My first S3 version did that by accident for `cover` and ran 35 statements instead of 11 (24 extra `product_media` selects, found with the statement log); fixed in commit `f6b69006646`.
    `fetchData()` objects have no lazy proxy and return `null` silently, so the same mistake there is invisible.

## Scenarios

Both variants are `CycleImplementation` (452 lines for S1 to S5 and the shared helpers; DBAL implementation 427, DAL 255).
Idiomatic: entities, `Select` with `with()` (joins for filter and sort), `load()` with `POSTLOAD` for the collections, `EntityManager` for writes.
Optimized: the same `Select`, read with `fetchData(false)` (no mapper, no heap), ids converted by hand; S4 and S5 are the same code in both variants (S5 has no collection loads, S4 is a write).
`--verify`: `OK (cycle equals dal)` for S1 to S5, both variants, MariaDB, MySQL, PostgreSQL and SQLite.
On the shared `orm_spike` databases S4 (DAL side) sometimes failed with `WriteTypeIntendException` or "dal wrote 0 products" while other handoffs ran S4 or a cleanup on the same database; every repeat without a concurrent run passed.

| Scenario | Statements (idiomatic = optimized) | Where N+1 appears | Code |
|---|---|---|---|
| S1 listing | 13: count, page query with 5 joins (parent, 4 translations), then one postload per relation and per level (translations, manufacturer, manufacturer translations, cover, media, and again for the parent) | none, one postload per relation; the parent chain doubles the postloads | `s1Listing` 28 lines plus `availableProducts` 20 |
| S2 detail | 18: one postload per relation, own and parent (options, option, option group and their translations, prices, categories) | none | `s2Detail` 62 lines |
| S3 search | 11: count, min/max, terms, page query, 7 postloads | the lazy `cover` load before the fix (35 statements) | `s3Search` 41 lines |
| S4 write | 350: 50 products x (1 product, 2 translations, 2 categories, 1 visibility, 1 stock update); inserts are separate statements per row | the unit of work does not batch | `s4Write` 48 lines |
| S5 criteria | 4: count, page, two postloads | none | `s5CriteriaFromJson` 52 lines |

S5 turns the JSON into the `Select` through an allow list (`active`, `stock`, `name`, `productNumber`), filter types `equals`, `contains`, `range`, sort and limit.
It can express what the DAL JSON in the contract uses; anything outside the allow list throws, an unknown filter type throws `ScenarioNotSupported`.
What does not map: the DAL `associations` key (we load a fixed association), nested `multi` and `not` filters (not built, they are `Fragment` trees), `total-count-mode` (always counted).

What the DAL does on top in S4 and Cycle skips: field serializers and validation (a blank translation name is rejected, seen as "This value should not be blank" in a DAL run), write protection, `EntityWrittenContainerEvent`, version handling, indexer messages.
Cycle sets `created_at` and the stock update itself and fires nothing.

## Probes

All probes below ran on MariaDB, MySQL, PostgreSQL and SQLite; the four write probes are in `Probe/ProbeCommand.php` (`bin/console orm-spike:cycle-probe`, 241 lines with the table setup), they create `spike_probe_note` and a draft version in `orm_spike` and remove both afterwards.

| Probe | Result | How | Lines | Cost |
|---|---|---|---|---|
| Translations with fallback | PASS (S1, S2, S3, S5 verify) | four joined translation relations for filter and sort (`COALESCE(t1..t4)`), postloads with `languageId IN (de, system)` and a PHP loop over the language chain for the displayed value | about 25 (relations in `SchemaFactory`, `translated()`, the joins in `availableProducts`) | no N+1; 4 joins per page query |
| Variant inheritance (also associations) | PASS (S1, S2 verify) | `COALESCE(product, parent)` in SQL for filters, in PHP `$product->manufacturer ?? $parent?->manufacturer`, for to-many (prices, options, categories) own rows if present, else the parent rows | about 15 | the parent chain doubles the postloads (13 and 18 statements) |
| Versioning (`version_id` in the key) | PASS | read by `(id, version_id)`, copy of the live row persisted as draft with the same id and another `version_id`, both versions read independently; merge is hand written (copy fields, persist), tested inside a rolled back transaction; there is no version or merge API | about 35 | one extra statement per read of a version |
| Plugin extension | PASS, with a limit | an association `notes` to a new table and a field `ean` added to the schema array at runtime, the class `Product` is not edited; association loads 2 notes; the field is selected and present in `fetchData()` rows but not set on the typed `Product` object | about 15 | none; the limit: runtime fields are invisible to typed entity code, array code only |
| App custom entity | PASS | table created at runtime with the schema builder of `cycle/database` (`$database->table()->getSchema()`, works the same on four engines), role with `StdMapper` and `\stdClass`, insert and read back | about 25 | none |
| Criteria from JSON | PASS (S5 verify) | allow list map plus `Fragment` (raw SQL) per filter | 52 | 4 statements |
| Ids | PASS | `HexIdTypecast` and `IdBinding`, also in lists and composite keys | 62 | none |
| Events | PASS, hand built | a `Mapper` subclass wraps `queueCreate()`; a command decorator (`EventCommand`, a `CompleteMethodInterface`) runs a callback after the command executed; one bulk `run()` of 50 rows gave 50 queued and 50 written callbacks, 50 insert statements; no `cycle/entity-behavior` installed | 80 | per row closure call; no event dispatcher is provided by the core ORM |
| Attribute schema | PASS | see schema variants | 27 | compile not timed |
| New entity walkthrough | see DX | | | |
| Static analysis | see PHPStan | | | |

## DX walkthrough: new entity `spike_note`

Steps and files for a small entity with a table and CRUD, from `ProbeCommand` (the same table and role are used by the app custom entity and event probes):

1. Table: Shopware migrations stay raw SQL `MigrationStep` classes for every engine (the DAL has the same step); Cycle's own migrations (`cycle/migrations`) are not installed, in the probe the table is created through the schema builder (about 10 lines: `string()`, `uuid()` or `binary()` per dialect, `setPrimaryKeys()`, `save()`).
2. Mapping: either a class with public typed properties (`ProbeNote`, 18 lines) or none (`StdMapper`), plus a role array of about 8 lines (table, columns, primary key, typecast).
3. Registration: the role must be merged into the schema array (`$schema + $roles`); there is no auto discovery without `cycle/annotated` and its tokenizer.
4. CRUD: `new EntityManager($orm)`, `persist($entity)`, `run()` for writes (4 lines), `(new Select($orm, 'note'))->where('id', ...)->fetchOne()` for reads (1 line); delete is `EntityManager::delete()`, not exercised by the probe (the probe drops the table).

In total about 5 files or none (migration, entity class optional, schema role, service registration if shared) and about 40 lines for the entity side.
The DAL needs `EntityDefinition`, `Entity`, `EntityCollection`, a definition registration and the migration; the existing `ProductManufacturer` set is 216 lines in three files (`ProductManufacturerDefinition` 73, `ProductManufacturerEntity` 105, `ProductManufacturerCollection` 38) with more fields than a note entity.
What the DAL adds for that: the Admin and Store API routes, ACL, criteria JSON, events, translation and versioning; none of that comes with Cycle.

IDE typing of results: `Select::fetchAll()` returns `iterable` of `mixed` unless the entity class is passed as a generic in a docblock (`Select<Product>`, used here); relations on the entity are typed by the property type, the results of `fetchData()` and of the builder are `array<string, mixed>`.

## PHPStan level max

Command: `vendor/bin/phpstan analyse --level=max src/Core/Framework/OrmSpike/Cycle` (PHPStan 2.3.5, repo `phpstan.neon.dist`, Shopware rules active).
Result: 191 errors in 29 files (`CycleImplementation` 121, `Probe` 42, `Entity` 13, `Connection` 9, `HexIdTypecast` 5, `CycleBootstrap` 1).
121 of them are about `mixed` (property fetches on results of `Select` and `fetchData()`, casts of `mixed`), 19 are Shopware's own rules for the spike code (domain exception pattern, `Hasher` instead of `md5`), the rest are mostly relation properties typed as plain arrays (`iterable` value type) and the shared-trait context.
No Cycle PHPStan extension was found (a packagist search "cycle orm phpstan" returns only `pivotphp/cycle-orm`, a framework integration; the search is not exhaustive).
php-cs-fixer ran over `OrmSpike/Cycle` and the services file without changes left.

## Timings

`APP_ENV=prod`, 5 warm-up and 50 measured iterations per scenario, median / p95, statements per run, peak memory.
Host load average 3.76 at the start and 3.66 at the end of the block (`uptime`, the box has other users), other lanes stopped: yes (43 non-`instance-*` containers stopped for the block and started again), lock `/tmp/wave8-timing.lock` held as `C`.
No other `orm-spike:bench` process was running at the end of the block; during the block I did not check for the other handoffs' runs continuously, and S4 of an earlier block failed because of one (see above), so S4 numbers are from a block whose S4 cells all passed.
DAL, DBAL and Cycle are from the same block.
The first block of the session had a few S4 cells of DAL and DBAL fail from concurrency, and one S3 cell was dominated by the lazy `cover` load; both are not used.


mariadb

| Scenario | DAL | DBAL | Cycle idiomatic | Cycle optimized |
|---|---|---|---|---|
| S1 | 8.54 / 11.26 ms, 4 st, 42.7 MB | 2.28 / 2.60 ms, 1 st, 24.8 MB | 5.01 / 6.94 ms, 13 st, 33.0 MB | 3.94 / 4.46 ms, 13 st, 33.1 MB |
| S2 | 4.22 / 5.59 ms, 5 st, 52.3 MB | 0.54 / 0.67 ms, 4 st, 24.8 MB | 2.82 / 4.38 ms, 18 st, 32.8 MB | 2.39 / 2.93 ms, 18 st, 32.7 MB |
| S3 | 37.72 / 48.03 ms, 7 st, 52.8 MB | 17.51 / 19.61 ms, 3 st, 24.8 MB | 26.29 / 35.93 ms, 11 st, 33.0 MB | 24.15 / 26.98 ms, 11 st, 33.7 MB |
| S4 | 94.71 / 113.06 ms, 371 st, 59.8 MB | 5.64 / 7.27 ms, 5 st, 25.4 MB | 41.69 / 45.26 ms, 350 st, 33.8 MB | 42.07 / 47.07 ms, 350 st, 33.7 MB |
| S5 | 25.30 / 28.78 ms, 4 st, 58.4 MB | 16.14 / 18.91 ms, 1 st, 24.8 MB | 11.22 / 13.66 ms, 4 st, 33.3 MB | 10.34 / 12.38 ms, 4 st, 33.7 MB |

mysql

| Scenario | DAL | DBAL | Cycle idiomatic | Cycle optimized |
|---|---|---|---|---|
| S1 | 7.94 / 9.45 ms, 4 st, 42.7 MB | 1.98 / 2.27 ms, 1 st, 24.8 MB | 5.16 / 8.07 ms, 13 st, 33.0 MB | 5.11 / 6.20 ms, 13 st, 33.1 MB |
| S2 | 3.93 / 4.76 ms, 5 st, 52.3 MB | 0.48 / 0.58 ms, 4 st, 24.8 MB | 3.40 / 5.48 ms, 18 st, 32.8 MB | 2.48 / 3.10 ms, 18 st, 32.6 MB |
| S3 | 47.33 / 65.53 ms, 7 st, 52.8 MB | 14.95 / 18.88 ms, 3 st, 24.8 MB | 34.61 / 37.41 ms, 11 st, 33.0 MB | 40.60 / 56.21 ms, 11 st, 33.7 MB |
| S4 | 81.95 / 89.01 ms, 371 st, 59.7 MB | 5.71 / 7.71 ms, 5 st, 25.4 MB | 31.95 / 40.39 ms, 350 st, 33.8 MB | 44.17 / 56.31 ms, 350 st, 33.7 MB |
| S5 | 24.01 / 28.88 ms, 4 st, 58.4 MB | 17.43 / 22.46 ms, 1 st, 24.8 MB | 11.05 / 13.96 ms, 4 st, 33.3 MB | 11.79 / 17.27 ms, 4 st, 33.6 MB |

postgresql

| Scenario | DAL | DBAL | Cycle idiomatic | Cycle optimized |
|---|---|---|---|---|
| S1 | 16.67 / 17.47 ms, 4 st, 43.4 MB | 34.23 / 39.14 ms, 1 st, 25.1 MB | 11.74 / 18.28 ms, 13 st, 33.5 MB | 10.94 / 13.57 ms, 13 st, 33.6 MB |
| S2 | 9.08 / 9.49 ms, 5 st, 53.0 MB | 3.51 / 4.00 ms, 4 st, 25.1 MB | 5.51 / 7.84 ms, 18 st, 33.3 MB | 3.64 / 4.36 ms, 18 st, 33.1 MB |
| S3 | 67.40 / 92.85 ms, 7 st, 53.6 MB | 37.91 / 52.38 ms, 3 st, 25.2 MB | 41.42 / 48.60 ms, 11 st, 33.5 MB | 43.75 / 48.83 ms, 11 st, 34.3 MB |
| S4 | 79.03 / 91.34 ms, 123 st, 60.3 MB | 14.98 / 18.50 ms, 5 st, 25.8 MB | 59.72 / 64.60 ms, 350 st, 34.6 MB | 60.25 / 67.37 ms, 350 st, 34.5 MB |
| S5 | 38.11 / 40.52 ms, 4 st, 59.2 MB | 29.02 / 30.38 ms, 1 st, 25.3 MB | 31.93 / 35.14 ms, 4 st, 34.1 MB | 31.54 / 35.38 ms, 4 st, 34.6 MB |

sqlite

| Scenario | DAL | DBAL | Cycle idiomatic | Cycle optimized |
|---|---|---|---|---|
| S1 | 60.56 / 66.23 ms, 4 st, 43.2 MB | 18.85 / 19.80 ms, 1 st, 25.3 MB | 6.82 / 9.56 ms, 13 st, 33.4 MB | 4.90 / 5.80 ms, 13 st, 33.6 MB |
| S2 | 16.09 / 17.15 ms, 5 st, 52.8 MB | 0.28 / 0.49 ms, 4 st, 25.2 MB | 1.95 / 3.66 ms, 18 st, 33.3 MB | 1.04 / 1.15 ms, 18 st, 33.1 MB |
| S3 | 125.78 / 134.97 ms, 7 st, 53.3 MB | 16.82 / 18.14 ms, 3 st, 25.3 MB | 24.54 / 29.53 ms, 11 st, 33.5 MB | 18.37 / 20.91 ms, 11 st, 34.1 MB |
| S4 | 288.99 / 350.50 ms, 371 st, 60.3 MB | 5.94 / 11.86 ms, 5 st, 26.0 MB | 16.11 / 23.34 ms, 350 st, 34.3 MB | 15.91 / 22.16 ms, 350 st, 34.3 MB |
| S5 | 62.12 / 65.89 ms, 4 st, 58.9 MB | 11.60 / 12.63 ms, 1 st, 25.3 MB | 8.12 / 10.15 ms, 4 st, 33.8 MB | 8.19 / 9.20 ms, 4 st, 34.2 MB |

Reading:

- Cycle (both variants) is faster than the DAL in every S1, S2, S3, S5 cell on all four engines, with 11 to 18 statements against 4 to 7 for the DAL (one postload per relation).
- Hand written DBAL is faster than Cycle on S1 to S4 on MariaDB and MySQL, on S2 to S4 on PostgreSQL and SQLite.
  Exceptions: S1 on PostgreSQL (DBAL 34 ms, Cycle 11 ms) and on SQLite (DBAL 19 ms, Cycle 5 to 7 ms), where the single DBAL statement is slower than Cycle's several.
  I did not analyse those plans, so why the single statement is slow there is not established here.
- S5: Cycle (4 statements) is faster than the DBAL statement with the window count on MariaDB, MySQL and SQLite, DBAL is slightly faster on PostgreSQL (29.0 against 31.5 to 31.9 ms).
  The cause was not analysed.
- Optimized against idiomatic ranges from about 45 percent faster to slower depending on the cell (some S3 and S4 cells are slower, within what looks like run noise, p95 not compared); statement counts are equal.
- S4: 350 statements in Cycle take 16 ms on SQLite and 32 to 60 ms on the server databases, against 80 to 290 ms for the DAL and 6 to 15 ms for the hand written 5 statement DBAL path.
- Peak memory is 33 to 35 MB for Cycle, 43 to 60 MB for the DAL and 25 MB for DBAL (the harness process baseline is part of all numbers).

## Verdict per 2019 slide reason

1. Difficult to optimize.
   Does not hold for reads: the same `Select` can be read as arrays (`fetchData()`), raw SQL fragments and the builder of `cycle/database` are available per query, and the statement log is one logger away (`FileQueryLog`, 26 lines).
   Holds in part for writes and for composite postloads: the unit of work sends one statement per row (350 for 50 products), and I did not write a batch insert variant, so what a hand built bulk path would save in Cycle is not measured here.
   Evidence: S1 to S5 tables above, the lazy load N+1 found and removed in S3.
2. Not suitable for core concepts.
   Holds in part: composite keys with `version_id` and parent self reference work, but translation fallback (4 joins, duplicated relations), inheritance (PHP and `COALESCE`), version draft and merge are all hand written; nothing of it is provided by Cycle.
   Evidence: probes translations, inheritance, versioning, friction list items 2 to 4.
3. Entities not extendable for plugins.
   Does not hold for the mapping: the schema is an array, a plugin can add a relation to a new table and a column to a role at runtime, and a role without a PHP class works (`StdMapper`).
   Holds for typed access: a runtime field is not set on the typed entity class, only in `fetchData()` arrays or on `stdClass` roles.
   Evidence: probes plugin extension and app custom entity.
4. Not possible to enforce patterns.
   Holds in part: Cycle offers hooks (typecast handler, custom mapper, command decorator) where a rule can be enforced for every write of a role, and the id typecast shows it for ids; but nothing stops code from building any `Select` or raw `Fragment` (S1 uses raw SQL fragments for the visibility filter), there is no write protection, ACL or criteria validation, and the events are a hand built hook.
   Evidence: id typecast, events probe, `availableProducts()` fragments.

## Core findings

No row added to `docs/core-findings.md`: everything found here is about Cycle and the mapping, not about the Shopware core.

## Cleanup

The probe command drops `spike_probe_note` and deletes its draft version and product row in the probe run; `orm_spike` holds no data of this handoff.
No setting of a database was changed.
No Shopware lane database (`shopware`, `shopware_test`, `shopware_switch`, `bench_*`) was touched; the connection microbench ran against `orm_spike`.
Timing lock removed and the 43 stopped containers started again (48 containers running as before).
