---
id: E3.11
type: Task
template: technical_todo.yaml
title: "Decide whether classic definitions move to attribute entities"
parent: E3
related: [E3.10]
findings: []
status: checked
upstream: ""
---

## Technical TODO

This is a decision task, to be taken after E3.10 and separately from the rest of the work in this epic.

Every entity of the core is written as a classic definition: an `EntityDefinition` class (or `MappingEntityDefinition`, `EntityTranslationDefinition`), an entity class and a collection class, registered as a service.
On trunk 283 classes extend one of these definition base classes, and only 2 entities are attribute entities (`MeasurementSystemEntity` and `MeasurementDisplayUnitEntity`).
A small classic entity such as `Tag` is 253 lines in three classes plus a service definition; the attribute entity `MeasurementSystemEntity` (translations, one-to-many, custom fields) is 56 lines in one class.
The large entities are far bigger: `product` is 1,755 lines in its definition, entity and collection.

Moving the classic definitions to attribute entities would give one source of truth per entity, but it is a breaking change for every plugin and app that extends or subclasses a core definition, entity or collection or uses their class names in the container.
Without E3.10 the compiler cannot express `product` at all.

The benefit has not been measured.
The proof of concept only built new small entities as attribute classes, it did not convert an existing one.

TODO:

- [ ] Wait for E3.10: no decision before `product` can be expressed.
- [ ] Convert one existing mid-size core entity with translations in a branch and record the lines before and after, the generated service ids and every public class name that changes.
- [ ] List the plugin and app extension points that depend on the classic classes (definition decoration, `EntityExtension`, entity subclasses, collection classes in type hints) and check which of them would break.
- [ ] Decide between: keep classic definitions for existing entities and use attributes only for new ones (no break), convert behind a deprecation period with both forms supported, or convert in a major release.
- [ ] Record the decision with the reason.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261: counts re-done, 283 definition classes and 2 attribute entities are still right; `product` grew from 1,740 to 1,755 lines (322 + 1403 + 30), the draft text was updated.
- Doc 29 conclusion "DAL v2, levers in order" row 10: "Move the existing classic definitions to attributes", breaking for plugins that extend or subclass definitions, entities and collections (judgement), effort 15 to 40 person-weeks (judgement), "one source of truth instead of 149 entity and 186 collection classes", "only 2 of 281 entities use attributes today; optional".
  The 149, 186 and 281 counts are doc 29's, counted on the instance; I did not recount them.
  The trunk counts used above (283 definition classes, 2 attribute entities) were counted with grep on `review/finding-31/src` (`extends (EntityDefinition|MappingEntityDefinition|EntityTranslationDefinition)` and `^#[Entity(`).
- Sizes: `Tag` 83 + 145 + 25 = 253 (trunk files `Core/System/Tag/`), `MeasurementSystemEntity` 56, `product` 320 + 1390 + 30 = 1740 (doc 33, "X1").
- The effort for the whole row is doc 29's judgement, not a measurement.
