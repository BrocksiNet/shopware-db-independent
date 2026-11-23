# Replace the DAL with an ORM? Research and PoC plan

State: 2026-11-22, research before wave 8.
Question: the experiment put a `SqlDialect` under the DAL (`docs/10-architecture.md`).
We never checked how much effort it would be to replace the DAL with an existing ORM or data mapper instead, and what that would bring for developer experience (DX) and performance.
This doc holds the research; the PoC of wave 8 (`docs/30` to `docs/33`) measures three candidates (Doctrine ORM, Cycle ORM and an improved DAL v2), and the conclusion section at the end is written by wave 8 E.

Raw notes of the research (not versioned): `handoffs/wave8-notes/orm-landscape.md`, `handoffs/wave8-notes/dal-inventory.md`.

## Why Shopware 6 has no ORM

Shopware 5 used Doctrine ORM.
The only primary source for the switch found is the talk "Insight into the Shopware 6 core architecture" (2019-05-23, https://speakerdeck.com/janbuecker/insight-into-the-shopware-6-core-architecture), slide 39 "Why? Reasons not to use Doctrine ORM":

- Difficult to optimize
- Not suitable for core concepts
- Entities not extendable for plugins
- Not possible to enforce patterns

No ADR in `shopware/shopware` records the decision.
The reasons are bullets without numbers; the PoC turns each one into something measurable (see "What the PoC has to answer").

## Candidates

Latest stable releases checked on Packagist on 2026-11-22:

| Candidate | Latest stable | PHP | Own connection layer | Installs next to Shopware trunk (`composer require --dry-run` in the lane) |
|---|---|---|---|---|
| Doctrine ORM | 3.8.0 (2026-11-14) | ^8.1 | no, uses Doctrine DBAL (Shopware already uses DBAL 4.4) | yes |
| Cycle ORM | 2.19.0 (2026-11-21) | >=8.2 | yes, `cycle/database` 2.24 (PDO), not DBAL | yes (with `cycle/annotated` 4.7) |
| Laravel Eloquent (`illuminate/database`) | 13.43.0 (2026-11-17) | ^8.3 | yes, its own | not tried |
| Propel | 2.0.1 (2026-08-21) | >=8.0 | yes, its own | not tried |

Not in the PoC, with the reason:

- Eloquent: needs PHP 8.3 while Shopware supports 8.2, is Active Record (the entity knows the database) and was the slowest in the only multi-ORM benchmark found (below).
- Propel: build-time class generation, so entities that plugins or apps add at runtime would need a code generation step per install; 2.0.0 came in 2026 after a beta that stood since 2024.
- Atlas.Orm (last release 2021) and Tempest DB (marked experimental, PHP 8.5 only).

The "no ORM" variant, hand-written DBAL SQL per use case, is in the PoC as the lower bound for time and the upper bound for code.

## Candidate 3: DAL v2

The third candidate keeps the DAL's concepts and public API (definitions, `EntityRepository`, `Criteria`, translations, inheritance, versioning, extensions, events, Admin/Sync/Store API) and changes what makes it slow or awkward.
So the comparison at the end has three candidates: Doctrine ORM, Cycle ORM and DAL v2, each against the trunk DAL and hand-written DBAL.

What v2 builds on (checked on `87e1768ce3a`):

- `EntityRepository` already has `@template TEntityCollection` generics.
- `Criteria::addFields()` already does partial loading.
- Attribute entities (`Framework/DataAbstractionLayer/Attribute/`, 26 attributes incl. `Translations`, `Inherited`, `Version`) exist, but only 2 core entities use them.

What v2 targets, each tied to a measured finding:

| Lever | Target | Source |
|---|---|---|
| Read shape | The detail read is one statement with 19 joins and 9 translation subqueries; try a root query plus batched by-id reads and one join per language with `COALESCE` | `core-findings.md` row 9, `docs/22`, `docs/25` |
| Compiled hydrators | One generated hydrator per definition instead of the generic field loop of `EntityHydrator`, only if the profile shows hydration matters | profile in wave 8 V |
| DTO projections | Readonly DTOs whose properties define the field list (automatic partial loading, typed results, no "maybe loaded" nullable properties) | `docs/08-dto-slice.md` |
| Write batching | Fewer statements per write (multi-row upserts through `SqlDialect`); one 50 product sync runs about 475 single row `UPDATE product` statements in the indexers | `core-findings.md` row 29, `docs/26` |
| SQL hygiene | Strict `GROUP BY`, `ROW_NUMBER()`, stated NULL order, typed numeric binds | `core-findings.md` rows 2, 6, 14, 27 |
| One source of truth | Attribute entities instead of definition + entity + collection classes | DX |
| Typed criteria | Field paths are strings (`'manufacturer.translations.name'`); generated constants or a typed builder, plus a PHPStan rule for unknown paths | DX |

Every lever is measured alone and combined with the same harness and scenarios as the ORMs, and labelled internal, additive or breaking for plugins and apps (`docs/33`).

## Performance data found

Only one benchmark compares current ORMs (https://github.com/compositephp/php-datamapper-benchmark, 10,000 CRUD operations, MySQL 8.0, PHP 8.1+):

| ORM | Time (s) | Memory (KB) | Peak memory (MB) |
|---|---|---|---|
| Doctrine | 37.45 | 870.24 | 6.408 |
| Cycle ORM | 44.32 | 288.15 | 7.007 |
| Laravel Eloquent | 61.51 | 4950.91 | 8.063 |

None of the sources compares an ORM with the Shopware DAL, and none uses PostgreSQL or SQLite, so the PoC measures it itself.

## How much code depends on the DAL

Measured on `instance/` (`poc/db-independent` at `87e1768ce3a`), commands in `handoffs/wave8-notes/dal-inventory.md`:

| What | Number |
|---|---|
| DAL itself (`src/Core/Framework/DataAbstractionLayer`) | 474 PHP files, 45,602 lines |
| Entity definitions | 281 (190 entity, 51 translation, 40 mapping), about 2,580 field declarations |
| Definitions with translated fields / custom fields / version fields / parent inheritance | 50 / 86 / 30 / 10 |
| Files in `src/` outside the DAL that use `EntityRepository` | 409 |
| Files in `src/` that build a `Criteria` | 436 |
| Files that handle entity written or loaded events | 115 |
| Files that use `EntityExtension` (plugins add fields at runtime) | 29 |
| Entity classes / collection classes (hand-written, typed properties) | 149 / 186 |
| Entities that use the attribute-based definition (`#[Entity(`) | 2 (MeasurementSystem, MeasurementDisplayUnit) |
| Test files (`*Test.php`) that reference `EntityRepository` or `Criteria` | 1,247 of 4,540 |
| App custom entities (`CustomEntity`, entities defined at runtime from XML) | 54 files, 3.9k lines |
| Raw SQL outside the DAL and migrations (already bypasses it) | 303 files |

Public contracts built on the DAL besides the PHP API: the generic Admin API (`ApiController`), the Sync API, the Store API routes that accept a `Criteria` as JSON (`RequestCriteriaBuilder`), the entity schema and OpenAPI generators used by the administration, and the Elasticsearch integration (28 of 126 files reference definitions).
Every plugin and app that reads or writes data uses `EntityRepository`, `Criteria` and definitions, so replacing the DAL breaks the public extension API, not only core internals.

## What the PoC has to answer

Each slide reason and each DAL concept becomes a probe with a pass/fail result, the lines of code it took and a measured cost:

| Probe | Slide reason | Question |
|---|---|---|
| Listing, detail, search with aggregations | "Difficult to optimize" | time, statements, peak memory against the DAL and hand-written DBAL on MySQL, MariaDB, PostgreSQL and SQLite |
| Bulk write of 50 products | "Difficult to optimize" | same, against the DAL write path |
| Translations with language fallback | "Not suitable for core concepts" | can the ORM read the name in language A with fallback to the system language without N+1 or a hand-written query? |
| Variant inheritance | "Not suitable for core concepts" | can a variant read name, manufacturer and prices of its parent when its own are empty? |
| Versioning (`version_id` in the primary key) | "Not suitable for core concepts" | composite keys and associations over them, read live, write into a draft version |
| Plugin extension | "Entities not extendable for plugins" | can a plugin add an association and a field to `product` at runtime without changing the core class? |
| App custom entity | "Entities not extendable for plugins" | can an entity defined at runtime (no PHP class) be read and written? |
| Criteria from JSON | API contract | can a Store API criteria JSON be turned into a safe ORM query? |
| Ids | this experiment | `binary(16)` on MySQL, MariaDB and SQLite and native `uuid` on PostgreSQL from one mapping, ids as hex strings above the connection (`IdBinding`) |
| New entity walkthrough | DX | files, lines and steps for a small new entity with a migration and CRUD, against the DAL |
| Static analysis | DX | PHPStan on the spike code (with `phpstan/phpstan-doctrine` for Doctrine) |

## Conclusion

Written by wave 8 E after the PoC.

State: 2026-11-23, written by wave 8 E2 from docs 30 to 33 and `docs/core-findings.md`.
The timing block is `docs/34-orm-spike-final-timings.md` (wave 8 E1); the two sections that depend on it are placeholders below.
Every number below is copied from the doc named next to it, and the judgements are labelled as such.
Numbers of different docs come from different timing blocks and are not compared with each other here.

### Probe summary

Candidates: DAL (the reference, passes every probe by construction), DBAL (hand-written SQL, doc 30), Doctrine ORM 3.8 (doc 31), Cycle ORM 2.19 (doc 32) and DAL v2 (doc 33).
"Not exercised" means the doc has no run for that probe, which is not a pass.
Lines are the lines the doc gives for that probe.

| Probe | DAL | DBAL | Doctrine (doc 31) | Cycle (doc 32) | DAL v2 (doc 33) |
|---|---|---|---|---|---|
| Listing, detail, search (S1 to S3) | pass | pass, verify OK on four engines, 1, 4 and 3 statements | pass in idiomatic and optimized mode, verify OK on four engines; idiomatic 32, 15, 45 statements, optimized 1, 4, 3 | pass in both variants, verify OK on four engines; 13, 18, 11 statements | pass, verify OK on four engines, also with all levers and with projections |
| Bulk write of 50 products (S4) | pass, 371 statements (123 on PostgreSQL) | pass, 5 statements, skips validation, events, version handling | pass, 70 lines, 450 idiomatic and 351 optimized statements, no batch insert; one optimized MariaDB cell failed with `DeadlockException`, cause not determined | pass, 48 lines, 350 statements, no events, no validation | pass, same output as the DAL; key fix 371 to 121 statements, with update batching 23 on MySQL and MariaDB, no change on PostgreSQL (123) |
| Translations with language fallback | pass | pass (S1, S2 verify), `COALESCE` over four joins | pass, four joins with `COALESCE` in DQL, hand written | pass, about 25 lines, four joined relations, no N+1 | pass, resolved by the DAL |
| Variant inheritance | pass | pass (S1, S2 verify), `COALESCE` over the parent join | pass, `COALESCE` per field, no declarative inheritance | pass, about 15 lines, parent chain doubles the postloads | pass, with the `parentId` trap of core finding 33 for partial reads |
| Versioning (`version_id` in the key) | pass | not exercised | pass, composite key works for `find` and `persist`; merge hand written; a composite-key parent cannot be a foreign id in a primary key (friction 1) | pass, about 35 lines, merge hand written | pass, `createVersion`, draft update, `merge` |
| Plugin adds an association (new table, new class) | pass | not exercised | pass, `PluginNote` 31 lines | pass, about 15 lines (together with the field below) | pass, `SpikePluginNote` 41 lines, partial loading works on it |
| Plugin adds a field to a core entity | pass (`EntityExtension`) | not exercised | FAIL, `ReflectionException`, the core class must declare the property | pass with a limit, the field is in `fetchData()` rows but not on the typed `Product` object | not exercised (needs a registered `EntityExtension`, which would change the DAL for other lanes) |
| App custom entity at runtime | pass (`CustomEntity`) | not exercised | pass with a generated class (`eval`), 66 lines | pass, about 25 lines, `StdMapper` needs no class | not exercised (needs an app lifecycle) |
| Criteria from JSON | pass | pass, S5 verify, 60 lines | pass, 75 lines translator plus 17, allow list of four fields, no aggregations or nested multi filters | pass, 52 lines, allow list of four fields, no `associations`, nested `multi` and `not` | pass, S5 verify, also with projections |
| Ids on four engines | pass | pass | pass, `shopware_id` type 53 lines; `indexBy` and `getScalarResult()` bypass it (friction 3 and 4) | pass, `HexIdTypecast` 62 lines; only the root row is typecast, relation data are raw | pass, all verify runs |
| Events (`EntityWrittenEvent`) | pass | skipped | pass with a gap, `onFlush` sees unit-of-work writes, a DQL `UPDATE` fires nothing | pass, hand built, 80 lines, no dispatcher | not listed in doc 33, the DAL writer is used unchanged |
| New entity walkthrough (`spike_note`) | pass (existing classes) | not exercised | pass, 31 lines in one class | pass, about 40 lines on the entity side | pass, 31 lines in one attribute class |
| Static analysis | n/a | not exercised | 82 errors | 191 errors | checker prototype only |

Reading of the table, only what it shows:

- Neither ORM provides translations, inheritance, versioning, merge or events; each probe that passes passes with hand-written code, listed in the cells.
- The one outright probe failure is Doctrine's plugin field on a core entity.
- Cycle's runtime schema array is the only ORM result that lets a plugin add a field and an association at runtime, but not on the typed class.
- DAL v2 keeps the probes that the DAL passes, and three of them (plugin field, app custom entity, events) were not run in doc 33.

### Developer experience

Lines per scenario, as the docs give them (implementation code of the method plus its helpers, approximate where the doc says so):

| Scenario | DAL | DBAL (doc 30) | Doctrine (doc 31) | Cycle (doc 32) | DAL v2 (doc 33) |
|---|---|---|---|---|---|
| S1 listing | not given per scenario | 17 | about 14 plus `base()` 36, `entityListing` 27, `scalarListing` 26 | 28 plus `availableProducts` 20 | not given per scenario |
| S2 detail | not given | 73 | about 8 plus `entityDetail` 51, `scalarDetail` 63, `preferOwn` 7 | 62 | not given |
| S3 search | not given | 43 | 45 | 41 | not given |
| S4 write | not given | 56 | 70 | 48 | not given |
| S5 criteria | not given | 60 | 17 plus the translator 75 | 52 | not given |
| Whole implementation file | 255 | 427 | 499 of 1,830 lines in 23 files (rest: mapped entities 564, probes 523, criteria translator 75, DQL functions 67, id type 53, factory 49) | 452, plus entities 362 and `SchemaFactory` 155 | projection mechanism 128 (`Path` 23, `Projector` 105), four DTOs 121, scenario glue 203 |

The `spike_note` walkthrough (a small entity with a table and CRUD):

| | Classic DAL | Doctrine | Cycle | DAL v2 |
|---|---|---|---|---|
| Files | 3 classes plus a service definition and a migration (`Tag`: 83 + 145 + 25 = 253 lines) | 1 class, 31 lines, plus a migration and a mapping path | about 5 files or none: migration, optional entity class (18 lines), schema role (about 8 lines), service registration | 1 attribute class, 31 lines, plus a migration |
| Registration | service definition | folder added to the mapping path | role merged into the schema array by hand, no discovery without `cycle/annotated` | one `shopware.entity` tag line, the repository service exists automatically |
| CRUD | repository, `Criteria` | `persist`, `flush`, `find`, DQL, `remove` | `EntityManager::persist`, `run()`, `Select` (delete not exercised) | repository create, search, update, delete |
| What comes with it | Admin and Store API routes, ACL, criteria JSON, events, translations, versioning | none of that (doc 31) | none of that (doc 32) | all of the classic DAL (same repositories) |

For comparison, the classic definitions of the slice are `product_manufacturer` 216 lines (73 + 105 + 38), `product_translation` 342 and `product` 1,740 (doc 33).
Attribute entities cannot yet express `product`: the compiler has no `ParentFkField`, `ParentAssociationField`, `ChildrenAssociationField`, `ChildCountField`, `ManyToManyIdField`, `VariantListingConfigField` and `NumberRangeField`, and no counterpart for entity extensions (doc 33, X1).
No line count is claimed for an attribute version of a slice entity.

Static analysis, level max, run in the docs on different bases (not like for like, and no PHPStan number exists for the DAL):

| | Result | Basis |
|---|---|---|
| Doctrine | 82 errors in 5 files, 67 of them `mixed` | temporary config, `phpstan-doctrine` and its rules, entity manager loaded on in-memory SQLite, path `OrmSpike/Doctrine` (doc 31) |
| Cycle | 191 errors in 29 files, 121 `mixed`, 19 from Shopware's own rules for the spike code | repo `phpstan.neon.dist` with the Shopware rules, no Cycle extension found (doc 32; the packagist search is stated as not exhaustive) |
| DAL v2 | no error count; `FieldPathChecker` prototype (79 lines) accepts 7 valid paths and rejects 5 typos with the failing segment named, 1,025 paths generated for `product` at depth 2 | no PHPStan rule written; `Criteria` carries no entity type, so a rule knows the entity only at a `->search($criteria)` call on a typed repository (doc 33, X2) |

What the Doctrine extension caught that plain PHPStan cannot: literal DQL that names a field the entity does not have, the same failure the plugin-field probe shows at run time (doc 31).
Dynamically built DQL is not checked.

IDE typing:

- Doctrine: entity mode results are typed properties; array hydration and scalar DQL results are `mixed` and need `@var` shapes (doc 31).
- Cycle: relations are typed by the property type; `Select::fetchAll()` is `mixed` unless `Select<Product>` is written in a docblock, and `fetchData()` results are `array<string, mixed>` (doc 32).
- DAL v2: attribute entities come back as instances of the attribute class (`SpikeNote`), projections as readonly DTOs; field paths in criteria stay strings (doc 33).

Learning curve and community, from the research notes of doc 29 (`handoffs/wave8-notes/orm-landscape.md`, Packagist and GitHub API, 2026-11-22):

| | Doctrine ORM | Cycle ORM | DAL (reference) |
|---|---|---|---|
| Packagist downloads per month | 8.86 million | 55.6 thousand | Shopware only |
| GitHub stars | 10,169 | 1,326 | n/a |
| Backer | Doctrine project, no source fetched | Spiral Scout (https://cycle-orm.dev/docs/intro-about/2.x/en) | Shopware |
| Static analysis extension | `phpstan/phpstan-doctrine`, 3.67 million downloads per month | none found | PHPStan rules of the core, none for criteria paths |
| Already in Shopware | DBAL 4.4 is the connection layer, Doctrine ORM is not | no | yes |

Learning curve is not measured by any doc.
Judgement: Shopware developers already know the DAL and DBAL; Doctrine has the larger body of documentation and Q and A, Cycle the smaller; DAL v2 needs no new concepts, only the attribute entities and DTO projections that the core already half has (2 of 281 entities use attributes today).

### Effort estimate

Unit: person-weeks of core development in the open source core, one experienced developer, including tests and review.
The ranges are judgements, not measurements; each line states what the range rests on.
Plugin and app side work of third parties is not in the numbers.

#### What the size of the dependency rests on

From doc 29, "How much code depends on the DAL": 281 definitions (about 2,580 field declarations), 409 `EntityRepository` consumer files and 436 `Criteria` files in `src/`, 1,247 of 4,540 test files, 54 `CustomEntity` files, 115 event files, 29 `EntityExtension` files, the generic Admin API, the Sync API, Store API criteria JSON, the administration entity schema and OpenAPI generators, and 28 of 126 Elasticsearch files that reference definitions.
Every plugin and app that reads or writes data uses `EntityRepository`, `Criteria` and definitions.

#### Full replacement by an ORM

The friction lists decide the items.
Doctrine (doc 31): composite foreign id with `version_id` does not map (11 items in total), `indexBy` and scalar results bypass the id type, no batch insert, a field added to a core entity fails, a PHP class per custom entity.
Cycle (doc 32): `version_id` NOT NULL breaks plain nullable belongs-to on write, one relation per path and alias (`translationsAlt`), relation data not typecast, lazy N+1 invisible in `fetchData()`, no batch insert.
Judgement: the dominant items are the same for both ORMs, because the DAL concepts have to be rebuilt either way, so one range covers both; where one ORM is easier it is said in the row.

| Item | Range (person-weeks) | What it rests on |
|---|---|---|
| Map the 281 definitions | 6 to 12 | Spike: Doctrine 564 lines for 14 mapped entities, Cycle 362 lines of classes plus 155 of schema for 15 roles (about 35 to 40 lines each); Cycle's classes were generated by a script. A generator from the definitions is assumed, `product` (1,390-line entity) and the field types without an ORM equivalent are the hand work. Judgement. |
| Rebuild translations, inheritance, versioning, extensions, custom entities, write protection, field serializers, validation, events on the ORM | 30 to 60 | Every probe passes only with hand-written code (about 15 to 35 lines per probe on one slice in doc 32, more in doc 31), plus what the DAL does in S4 and the ORMs skip: serializers, validation, write protection, `EntityWrittenContainerEvent`, version handling, indexer messages. The slice is a handful of definitions; generic code for all 281 (50 translated, 86 with custom fields, 30 versioned, 10 inheriting) is the unknown. Judgement. |
| Port the 409 consumer files and 436 `Criteria` files | 20 to 60 | Up to 845 files (the overlap is not measured, so the sum is an upper bound), 1 to 3 hours each for a change that is not mechanical. Judgement. |
| Admin, Sync and Store API contracts, administration entity schema, OpenAPI | 8 to 16 | S5 expresses an allow list of four fields in 52 to 92 lines; it does not express `associations`, nested `multi` and `not`, aggregations (docs 31, 32). The generic API needs all of it per entity. Judgement. |
| Elasticsearch | 2 to 4 | 28 of 126 files reference definitions. Judgement. |
| Tests | 25 to 60 | 1,247 test files reference `EntityRepository` or `Criteria`. Judgement, 1 to 3 hours each. |
| Public API break: compatibility layer, migration path, deprecation period | 10 to 20 for the core side | Replacing the DAL breaks the extension API (doc 29); the 29 `EntityExtension` files and 54 `CustomEntity` files show what plugins and apps use. Judgement. |
| Total | about 100 to 230, two to four and a half person-years | Sum of the rows. |

Where the ORMs differ for this effort:

- Doctrine: custom entities need generated classes, plugin fields on a core entity need the core class to declare them, and the composite-key friction hits every translation of a versioned parent, so the mapping rows sit at the upper end.
  Judgement: it is the one with the better tooling (PHPStan extension that checks literal DQL, 8.86 million downloads per month).
- Cycle: the runtime schema array fits plugin extension and custom entities better, but typed code does not see runtime fields, no PHPStan extension exists and 11 to 18 statements per read need postload tuning.
  Judgement: it is the better technical fit for Shopware's extension model, and the worse fit for the tooling the core uses.
- Neither is shown to reduce the rows above: both send one statement per row on S4, and both were measured against 4 to 7 DAL statements per read with 11 to 45 (idiomatic) statements.

#### ORM only underneath the DAL API

Idea: `EntityRepository`, `Criteria` and the definitions stay, the reader and writer run on Doctrine or Cycle.
Gain, from the docs:

- The profile of doc 33 puts hydration at 15 percent of a call at most (S1 on MySQL and MariaDB) and 7 percent or less in every other cell; SQL is 84 to 92 percent of S3 and S5.
  Replacing the DAL's hydration with an ORM's can therefore win that share at best, and the optimized ORM paths in docs 31 and 32 leave the entity model (arrays) to be fast.
- The S4 gain of the DAL is not in the unit of work: both ORMs send one statement per row (350 and 351 to 450 statements), and the DAL write path got to 23 statements with its own two fixes (doc 33, W1).
- The DAL's reader logic (translation fallback, inheritance, version filter, `Criteria` to SQL) would still have to be written, now as DQL or `Select` code.

Verdict from these three points: no measured gain, and the cost of both layers.
Effort, judgement: 30 to 60 person-weeks to rebuild reader, searcher, aggregator and writer (the DAL is 474 files and 45,602 lines) with the ORM below them and the public API untouched; no BC break, no benefit shown.
Not recommended on the evidence of docs 31 to 33.

#### DAL v2, levers in order

Split by BC label, from doc 33.
The effort column of doc 33 is its own estimate from the size of the change; the rows marked judgement are mine.

| Order | Lever | Label | Effort | Gain (doc 33 and core findings) | Rests on |
|---|---|---|---|---|---|
| 1 | W1a key fix in `EntityWriteGateway::getCurrentState()` (core finding 31) | internal bug fix | hours plus a regression test | S4 371 to 121 statements on MySQL, MariaDB, SQLite; no change on PostgreSQL | about 5 lines; verified in the code, see below |
| 2 | C1 window count (core finding 32) | internal | days | S3 and S5 15 to 45 percent lower on four engines | 33 changed lines in a copy of `EntitySearcher`; needs count fallback tests per engine |
| 3 | A1 stats fusion | internal, additive | days | one statement less on S3, no gain outside the noise | 86 lines |
| 4 | W1b update batching (core finding 29 is the related indexer side) | internal | 1 to 2 weeks | S4 371 to 23 statements on MySQL and MariaDB; on PostgreSQL the batch did not engage, on SQLite the time did not move | about 130 changed lines in a copy of the gateway; casts on PostgreSQL, events, tests |
| 5 | SQL hygiene (core findings 2, 6, 14, 27) | internal | 2 to 4, judgement | removes MySQL-only behaviour (session `sql_mode`, `@n:=IF`, implicit NULL order, untyped binds) | doc 33 lists the open state per row; each is a core change; the range is mine |
| 6 | R1 read shape | internal | 1 to 2 (doc 33), judgement | `shape=join`: SQLite S1 45, S2 67, S5 38 percent lower, nothing on MySQL, MariaDB, PostgreSQL; `shape=batch`: PostgreSQL S1 15 to 25, S2 32 to 36 percent lower, nothing on MySQL, MariaDB, SQLite | about 91 lines flat join builder, about 130 in a reader copy; statements 4 to 8 on S1 |
| 7 | R3 DTO projections | additive | 1 to 2 for the mechanism and first entities (doc 33), 3 to 6 for broad coverage, judgement | S1 and S2 about 15 to 50 percent, nothing on S3 and S5 | 128 lines mechanism, 121 for four DTOs; the `parentId` trap (core finding 33) needs a core fix or a rule |
| 8 | Typed criteria: PHPStan rule on top of `FieldPathChecker` | additive | 1 to 3, judgement | catches typos at analysis time | checker 79 lines; `Criteria` has no entity type |
| 9 | Attribute entities for new and simple entities; close the compiler gaps for `product` | additive | 3 to 6 for the gaps, judgement | 31 lines instead of about 250 per small entity | 7 field types and the extension point missing in the compiler |
| 10 | Move the existing classic definitions to attributes | breaking for plugins that extend or subclass definitions, entities and collections (judgement) | 15 to 40, judgement | one source of truth instead of 149 entity and 186 collection classes | only 2 of 281 entities use attributes today; optional |
| not built | R2 compiled hydrators | internal | not justified | at most 3 to 15 percent | profile of doc 33 |

Totals, judgement from the rows: internal 6 to 12 person-weeks (rows 1 to 6), additive 5 to 15 (rows 7 to 9, the low end uses the 1 to 2 weeks of doc 33 for projections), together about 11 to 27 without a public API break; the optional breaking row adds 15 to 40.

Core finding 31 checked in the code: `EntityWriteGateway::getCurrentState()` (`instance/src/Core/Framework/DataAbstractionLayer/Dbal/EntityWriteGateway.php`, from about line 650) decodes with `$definition->getField($fieldName)` where `$fieldName` is a storage name, `getField()` looks up by property name (`EntityDefinition.php:255`), and `PrimaryKeyBag` builds its key with `implode('_', ...)` of the stored values (`PrimaryKeyBag.php:67`).
A mismatch on binary ids is therefore a miss on MySQL, MariaDB and SQLite; the measured effect (371 to 121 statements) is from doc 33, not re-run here.

#### DAL as today plus targeted DBAL for hot paths

Idea: keep the DAL and `SqlDialect`, write the hottest read paths as DBAL SQL.
Where DBAL was clearly faster than the DAL in the docs: S2 (0.26 to 3.5 ms against 4 to 17 ms), S3 (14 to 38 ms against 37 to 134 ms) and S4 (5 to 15 ms against 80 to 330 ms) on every engine of doc 33 and doc 32 blocks.
Counter-evidence: on PostgreSQL the single-statement DBAL S1 is slower than the DAL (34 ms against 17 to 22 ms, docs 30 to 33), and the DBAL S5 is slower than the DAL v2 with all levers on MySQL, MariaDB and PostgreSQL in doc 33 (17.84 against 12.27, 17.98 against 13.88, 31.08 against 17.54 ms), faster only on SQLite (13.03 against 22.54 ms); hand-written SQL is not faster by default and has to be measured per engine.
Costs from doc 30: the DBAL S4 skips validation, write protection, events, version handling and indexers, and "hard-codes the columns it fills, so a new required column breaks it silently at runtime"; doc 29 counts 303 files that already bypass the DAL with raw SQL.
Effort, judgement: 1 to 3 person-weeks per hot path (the DBAL methods of the spike are 17 to 73 lines, plus per engine verification and tests), 4 to 10 for five paths.
Gain: read paths only, up to the DBAL numbers above; writes must stay on the DAL if events and versioning matter.

### Variants side by side

| Variant | Effort (person-weeks) | BC impact | Gain shown by the docs |
|---|---|---|---|
| Full ORM replacement (Doctrine or Cycle) | about 100 to 230 | breaks the public extension API of every plugin and app | reads: optimized ORM paths reach DBAL statement counts, idiomatic ones have 11 to 45 statements; writes: 350 to 450 statements, no gain against the fixed DAL; no translations, inheritance, versioning, events |
| ORM underneath the DAL API | 30 to 60 | none | none measured; at most the hydration share of 15 percent or less |
| DAL v2, internal and additive levers | about 11 to 27 | none | doc 33: S1 11.33 to 3.38 ms, S2 6.19 to 1.84, S3 55.90 to 31.20, S4 81.62 to 54.36, S5 22.77 to 12.27 on MySQL (all levers, DBAL 2.42, 0.49, 14.12, 6.12, 17.84); DAL v2 does not reach DBAL on S3 and S4 |
| DAL v2 plus the breaking attribute migration | about 26 to 67 | breaking for plugins that extend definitions | as above plus one source of truth |
| DAL plus targeted DBAL hot paths | 4 to 10 for five paths | none for readers, hand-written paths skip DAL behaviour | read paths up to DBAL numbers, per engine |

### Performance per engine (from doc 34)

All numbers are from one timing block in `docs/34-orm-spike-final-timings.md` (50 iterations, 5 warm-up, other lanes stopped, every verify cell equal to the DAL).
Host load was high and falling (1-minute load 16.4 on MySQL down to 7.3 on SQLite), so compare implementations within one engine, not engines with each other.
Median ms / statements per run; the full tables with all nine configurations, peak memory and ratios are in doc 34.

| Engine | Impl | S1 listing | S2 detail | S3 search | S4 write | S5 JSON |
|---|---|---|---|---|---|---|
| MySQL | DAL | 12.42/4 | 4.60/5 | 56.67/7 | 90.11/371 | 28.24/4 |
| MySQL | DBAL | 2.21/1 | 0.55/4 | 20.29/3 | 7.16/5 | 19.47/1 |
| MySQL | Doctrine optimized | 2.83/1 | 0.78/4 | 20.23/3 | 43.48/351 | 23.78/1 |
| MySQL | Cycle optimized | 6.14/13 | 2.98/18 | 48.80/11 | 52.29/350 | 12.54/4 |
| MySQL | DAL v2 all levers | 3.78/2 | 1.90/5 | 32.67/4 | 57.49/23 | 14.11/2 |
| MariaDB | DAL | 11.91/4 | 6.26/5 | 41.72/7 | 94.01/371 | 29.33/4 |
| MariaDB | DBAL | 2.68/1 | 0.56/4 | 23.21/3 | 6.22/5 | 18.83/1 |
| MariaDB | Doctrine optimized | 2.97/1 | 0.77/4 | 23.01/3 | 41.59/351 | 21.65/1 |
| MariaDB | Cycle optimized | 4.49/13 | 2.34/18 | 29.24/11 | 41.68/350 | 12.65/4 |
| MariaDB | DAL v2 all levers | 4.48/2 | 2.52/5 | 23.83/4 | 54.87/23 | 14.51/2 |
| PostgreSQL | DAL | 21.35/4 | 12.07/5 | 68.39/7 | 84.65/123 | 41.24/4 |
| PostgreSQL | DBAL | 33.34/1 | 2.98/4 | 34.64/3 | 12.72/5 | 28.48/1 |
| PostgreSQL | Doctrine optimized | 31.88/1 | 4.57/4 | 36.23/3 | 57.22/351 | 23.35/1 |
| PostgreSQL | Cycle optimized | 11.03/13 | 4.02/18 | 40.82/11 | 59.07/350 | 32.91/4 |
| PostgreSQL | DAL v2 all levers | 10.05/2 | 5.61/5 | 35.57/4 | 89.15/123 | 17.33/2 |
| SQLite | DAL | 62.34/4 | 17.02/5 | 130.22/7 | 339.01/371 | 62.44/4 |
| SQLite | DBAL | 19.03/1 | 0.27/4 | 17.42/3 | 5.81/5 | 12.63/1 |
| SQLite | Doctrine optimized | 19.72/1 | 0.44/4 | 18.53/3 | 125.83/351 | 13.63/1 |
| SQLite | Cycle optimized | 5.34/13 | 1.14/18 | 23.10/11 | 16.86/350 | 8.98/4 |
| SQLite | DAL v2 all levers | 33.46/2 | 10.08/5 | 67.84/4 | 287.10/23 | 22.47/2 |

What the table shows:

- Reads: DAL v2 with all levers is 1.7 to 3.3 times faster than the DAL on S1, S2, S3 and S5 on MySQL, MariaDB and PostgreSQL, and 1.7 to 2.8 times on SQLite.
- Optimized Doctrine reaches DBAL level on reads, but only by leaving the entity model (scalar DQL or native SQL with array results, doc 31), so it no longer provides what the ORM was chosen for.
- Cycle is the fastest implementation on SQLite S1 and S5 and beats the DAL and DBAL on PostgreSQL S1 (DAL v2 is slightly faster there), with 11 to 18 statements per read.
- Hand-written DBAL is slower than the DAL on PostgreSQL S1 (33.34 against 21.35 ms); the DBAL plan analysis in doc 34 shows a join filter on `COALESCE` that cannot use an index and a window count before the top-N sort, the DAL plan could not be captured.
- Writes are the weak spot of DAL v2: it is slower than both ORMs on S4 on every engine, although it sends far fewer statements (23 against 350).
  The ORM write paths skip what the DAL write does (validation, write protection, the written events), so the comparison is not like for like, but on SQLite Cycle writes the 50 products in 16.86 ms against 287.10 ms for DAL v2, which says the DAL write cost on SQLite is not the statement count.
- On PostgreSQL the batched update of DAL v2 does not engage (123 statements, as the DAL): an earlier spike run of the batched update failed there with `column "stock" is of type integer but expression is of type text`, so the `CASE` needs a cast per column type there.
- Cold cache: one S2 call after `cache:clear --no-warmup` takes about 1.0 to 1.1 s for DBAL, Doctrine and Cycle and 1.6 to 1.8 s for the DAL and DAL v2 on every engine (warm 0.2 to 0.35 s, wall time including the kernel boot).

### Recommendation

Keep the DAL as the public API and build DAL v2 step by step; do not replace the DAL with Doctrine ORM or Cycle ORM, and do not put either underneath it.
Doc 34 does not change the draft below: no optimized ORM variant is ahead of DAL v2 on reads on all four engines while keeping its entity model, and the ORMs' write advantage comes from skipping DAL behaviour, not from batching.
It adds one point: the write path is the next DAL v2 lever to work on (writer PHP is 58 to 59 percent of S4 per doc 33, the SQLite write cost is unexplained, the PostgreSQL batched update needs typed `CASE` expressions).

Recommendation (originally drafted from the probe, DX and effort evidence, confirmed against doc 34):

1. Do not replace the DAL with Doctrine or Cycle.
   Neither provides translations, inheritance, versioning or events, so every probe passed only with hand-written code; Doctrine fails the plugin field probe, Cycle's runtime fields are invisible to typed code; both write one statement per row; the effort is 100 to 230 person-weeks (judgement) and breaks every plugin and app.
2. Do not put an ORM underneath the DAL API: no gain is shown, the hydration ceiling is 15 percent (doc 33 profile), the cost is both layers.
3. Pursue DAL v2 as internal changes first, in the order of the table: the `EntityWriteGateway` decode fix (core finding 31, hours), the window count (finding 32), the other write and SQL hygiene items, then the additive API (projections, typed criteria, attribute entities for new entities).
   That is 11 to 27 person-weeks (judgement) with no BC break, and its levers are measured on four engines in doc 33.
4. Use targeted DBAL for a read path only where a per-engine measurement shows DBAL clearly ahead, because hand-written SQL lost to the DAL on PostgreSQL S1.
5. What would change this: if doc 34 shows an optimized ORM variant clearly ahead of DAL v2 with all levers on all four engines, the full replacement would still cost 100 to 230 person-weeks and a public API break, so the gain would have to justify that.
