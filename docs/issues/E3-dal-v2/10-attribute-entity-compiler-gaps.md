---
id: E3.10
type: Story
template: story.yaml
title: "Close the attribute entity compiler gaps"
parent: E3
related: [E3.11]
findings: []
status: filed
upstream: "https://github.com/shopware/shopware/issues/23314"
---

## User story

As a developer of a plugin or of the core, I would like to declare every field type and the entity extension points of the DAL on an attribute entity, so that I can write a new entity as one class and do not need a definition, an entity and a collection class when the entity uses inheritance, a parent tree or a number range.

## Acceptance criteria

- The attribute entity compiler (`AttributeEntityCompiler`, registered through the `shopware.entity` tag) can express the fields that `ProductDefinition` uses and the compiler cannot express today: `ParentFkField`, `ParentAssociationField`, `ChildrenAssociationField`, `ChildCountField`, `ManyToManyIdField`, `VariantListingConfigField` and `NumberRangeField`.
- There is an attribute counterpart of `EntityExtension` (adding fields, modifying fields, extending protections to an entity), so that a plugin can add a field to an attribute entity without a definition class.
- Each new attribute has a test that compiles it and compares the result with the field of the classic definition (same class, storage name, property name, flags).
- The generated definition of an entity that uses all new attributes passes the same DAL integration tests as a classic one: read with inheritance, write, translation, child count after a write.
- Documentation of the attribute set with one example per attribute.
- No change for existing attribute entities.

What exists today (by reading the compiler):

- The compiler maps the field types `uuid`, `text`, `string`, `int`, `float`, `bool`, `enum`, `json`, `datetime`, `date`, `date-interval`, `time-zone`, `email` and `price`, the associations one-to-one, many-to-one, one-to-many, many-to-many and translations, and auto increment, serialized, password, foreign key, state machine state, version, reference version, custom fields and list fields.
- `Field::$type` can also be the class name of a DAL field (`getFieldClass()`), and the field is then built with the arguments storage name and property name only.
  By its constructor signature that fits `VariantListingConfigField` and `NumberRangeField` (its maximum length has a default of 64); it does not fit `ParentFkField`, `ParentAssociationField`, `ChildrenAssociationField`, `ChildCountField` and `ManyToManyIdField`, whose constructors need other arguments or none.
- The attributes `Inherited`, `Version`, `ReferenceVersion`, `CustomFields` and `Translations` exist.
- An attribute entity written this way needs one class and one tag line: a small example entity with id, title and body built in the proof of concept was 31 lines, a classic small entity such as `Tag` is 253 lines in three classes (`TagDefinition` 83, `TagEntity` 145, `TagCollection` 25) plus a service definition.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261: `getFieldClass()` is at line 249 (`is_a` check line 251), `getFieldArgs()` default at line 319, field constructors unchanged, `ProductDefinition` still uses all seven fields.
- X1 and X3 in `docs/33-orm-spike-dal-v2.md`; doc 29 conclusion row 9 (3 to 6 weeks for the gaps, judgement).
- Doc 33 says the type map has no `ParentFkField`, `ParentAssociationField`, `ChildrenAssociationField`, `ChildCountField`, `ManyToManyIdField`, `VariantListingConfigField` and `NumberRangeField`, and no attribute for entity extensions.
  On trunk (`review/finding-31`, `DataAbstractionLayer/AttributeEntityCompiler.php`) the `getFieldClass()` method accepts a `DalField` class name as `Field::$type` (line 251) and `getFieldArgs()` passes `[$column, $property]` as default (line 319).
  I read the constructors of the seven fields: `ParentFkField(string $referenceClass)`, `ParentAssociationField(string $referenceClass, string $referenceField = 'id')`, `ChildrenAssociationField(string $referenceClass, string $propertyName = 'children')`, `ChildCountField()` (fixed names), `ManyToManyIdField(storageName, propertyName, associationName)`, `VariantListingConfigField(storageName, propertyName)`, `NumberRangeField(storageName, propertyName, ...)`.
  Whether the `type` route yields a working field for the two that fit (serializer, flags, tests of an entity using it) was not tested; doc 33 did not consider it.
- Entity extensions: no `EntityExtension` reference in the compiler; `AttributeManyToManyReverseExtension` exists next to it (not read in detail).
- The spike entities: `Attr/SpikeNote.php` (31 lines) and `Attr/SpikePluginNote.php` (41 lines, association to `product`, foreign key, reference version), CRUD through the real repositories on four engines, the search returned instances of the attribute class.
- Classic definition sizes of the slice (lines, definition + entity + collection): `product_manufacturer` 216, `product_translation` 342, `product` 1740 (320 + 1390 + 30), `MeasurementSystemEntity` as attribute entity 56 lines in one class.
  No line count is claimed for an attribute version of a slice entity.
- Effort estimate from doc 29 (estimate, judgement): 3 to 6 weeks for the gaps.
