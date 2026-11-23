---
id: E3.07
type: Story
template: story.yaml
title: "Read into typed DTO projections through partial loading"
parent: E3
related: [E3.06, E3.09]
findings: [33]
status: checked
upstream: ""
---

## User story

As a developer of a Store API route or a plugin, I would like to read an entity list or detail straight into a typed read-only object that names its source paths, so that I get typed results for the fields I need and the DAL skips the generic entity hydration and the fields I do not read.

## Acceptance criteria

- A DTO declares per constructor parameter where its value comes from, for example `#[Path('manufacturer.name')]`, and for an association the sub fields to read.
- A projector turns the paths into `Criteria::addFields()`, runs the normal repository search (also the sales channel repositories) and builds the DTOs from the resulting `PartialEntity` objects.
- No new SQL path: the same reader runs and only selects the listed fields.
- Translated and inherited values come out resolved, because the DAL resolves them while loading.
- A variant that inherits a to-many association gets it in the projection without the DTO having to name `parentId` (depends on the fix of E3.06, or the projector adds `parentId` itself for inheritance aware entities).
- A path that does not exist on the entity fails with the failing segment named.
- An existing criteria without `addFields()` behaves as before; no change to the public criteria API.
- A DTO exists for at least one core read (for example a product listing item) and is covered by an integration test that compares it with the full entity read.
- Documentation of the mechanism, including the cases where a projection is not worth it (see below).

Measured in a proof of concept on MySQL, MariaDB, PostgreSQL and SQLite, median per call:

- Product listing of a category with a page of 24 products: MySQL 9.08 to 4.82 ms, MariaDB 8.07 to 6.79 ms, PostgreSQL 22.69 to 12.90 ms, SQLite 61.46 to 50.44 ms.
- Detail read of a variant that inherits everything from its parent: MySQL 4.96 to 2.70 ms, MariaDB 4.64 to 3.70 ms, PostgreSQL 11.59 to 6.15 ms, SQLite 16.56 to 11.55 ms.
- Gain about 16 to 47 percent on these two reads, depending on the engine.
- Search with aggregations and a JSON criteria request with a total: no measurable gain, because the SQL dominates (84 to 92 percent of the call on every engine) and a projection does not change the statements.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Lever R3 in `docs/33-orm-spike-dal-v2.md` ("Lever R3", lever table, "Reading the numbers"); finding 33 is the `parentId` trap (E3.06).
- Spike code: `src/Core/Framework/OrmSpike/DalV2/Projection/` on `poc/orm-spike`: `Path` 23 lines, `Projector` 105, four DTOs 121 lines, scenario glue 203 lines; `Projector::project()` calls `Criteria::addFields()` with the collected paths.
  Verified equal to the DAL on S1, S2, S3 and S5 on all four engines.
- Percentages computed from the lever table: MySQL S1 47 percent, S2 46; MariaDB S1 16, S2 20; PostgreSQL S1 43, S2 47; SQLite S1 18, S2 30.
  The noise of the block was up to 20 percent (doc 33 "Timings"), so the MariaDB and SQLite S1 gains are at the edge of it.
- The profile that justifies the range: hydration is 15 percent of a call at most, so a projection cannot save more than that from hydration; the rest of the gain is the narrower select and the skipped entity creation (doc 33 "Profile", R3 upper bound).
- Trunk references: `Criteria::addFields()` at `Search/Criteria.php:649`, `PartialEntity` at `DataAbstractionLayer/PartialEntity.php`.
- Effort estimate from doc 29 (estimate, labelled judgement there): 1 to 2 weeks for the mechanism and first entities (doc 33), 3 to 6 for broad coverage.
- Open design points not decided in the docs: where the attribute lives, whether DTOs are generated, how the projector maps nested association lists.
