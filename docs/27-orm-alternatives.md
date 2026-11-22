# Replace the DAL with an ORM? Research and PoC plan

State: 2026-11-22, research before wave 8.
Question: the experiment put a `SqlDialect` under the DAL (`docs/10-architecture.md`).
We never checked how much effort it would be to replace the DAL with an existing ORM or data mapper instead, and what that would bring for developer experience (DX) and performance.
This doc holds the research; the PoC of wave 8 (`docs/28` to `docs/30`) measures it, and the conclusion section at the end is written by wave 8 E.

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
