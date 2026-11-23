---
id: E3.12
type: Task
template: technical_todo.yaml
title: "Verify plugin fields and app custom entities on the DAL v2 changes"
parent: E3
related: [E3.04, E3.07, E3.10]
findings: []
status: checked
upstream: ""
---

## Technical TODO

The changes of this epic were verified against the classic DAL on a fixed set of probes, but two extension scenarios were not exercised, so they are not verified:

- A plugin adds a field to a core entity through an `EntityExtension` (`extendFields()`).
- An app defines a custom entity at runtime (`CustomEntity`, created through the app lifecycle, with `DynamicEntityDefinition` classes).

The probes that were run and passed on MySQL, MariaDB, PostgreSQL and SQLite: translations with fallback, variant inheritance, versioning with merge, a plugin that adds a new entity with an association to a core entity (also with partial loading), criteria from JSON, and ids on every engine.
The two missing probes were skipped because they need a registered extension or an app lifecycle that would change the DAL for other work on the same instance.

Each of the changes could touch an extension:

- Batched updates (E3.04) run on entities with plugin fields and custom entity tables.
- DTO projections (E3.07) read through `Criteria::addFields()`, which has to find extension fields and custom entity fields.
- Attribute entities (E3.10) and the planned `EntityExtension` counterpart must give the same field set as an extended classic entity.

TODO:

- [ ] Write an integration test with a registered `EntityExtension` that adds a field (storage field and association) to a core entity, and run it with each change of this epic switched on: batched updates, window count, projection with the extension field in the field list.
- [ ] Write an integration test with an app that defines a custom entity (with a translation and an association to a core entity), and run create, update, search with total, aggregation and a projection on it, before and after each change.
- [ ] For each test, compare the result and the written rows with the classic path, as the existing probes do.
- [ ] Run the tests in the CI of the core, not only locally.
- [ ] Record which extension scenarios behave differently and open an issue for each difference.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Doc 33 "Probes of doc 29": "Plugin adds a field to a core entity (entity extension)" and "App custom entity at runtime" are both "not exercised"; the reasons are quoted above (needs a registered `EntityExtension`, which would change the DAL for the other lanes of the same instance; needs an app lifecycle with `custom_entity`, not part of the seeded data set).
  Doc 33 "Follow-up from the final timing block": "Not exercised for DAL v2 and still open".
- Doc 29 probe summary: the classic DAL passes both (`EntityExtension`, `CustomEntity`); Doctrine fails the plugin field probe with `ReflectionException`, Cycle passes it with a limit; Doctrine and Cycle pass the app custom entity probe (66 and about 25 lines).
- Events (`EntityWrittenEvent`) were also not listed for DAL v2 in doc 33 because the classic writer is used unchanged; E3.04 changes the writer path and has to keep the events (see its TODO).
- Trunk references (`review/finding-31`): `DataAbstractionLayer/EntityExtension.php` (`extendFields()` line 18, `modifyFields()` line 35, `extendProtections()` line 44), `src/Core/System/CustomEntity/` (`CustomEntityLifecycleService`, `Schema/DynamicEntityDefinition.php`).
- Effort: not estimated in docs 29 or 33.
