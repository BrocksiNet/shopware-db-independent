---
id: E3.06
type: Bug
template: bug_report.yml
title: "Partial read of a variant returns an empty inherited to-many association"
parent: E3
related: [E3.07]
findings: [33]
status: draft
upstream: ""
---

## Shopware Version

trunk (code read on `e9e18ef0e7b`, 2026-11-23); the empty result was observed in a proof of concept on the same DAL code and is not yet reproduced with a test on trunk

## Affected area / extension

Platform(Default)

## Actual behaviour

A partial read with `Criteria::addFields()` of an entity that inherits a to-many association from its parent returns an empty association when `parentId` is not among the requested fields.
Example: a product variant that has no `prices` of its own and inherits them from its parent, read with the fields `id`, `productNumber`, `prices.quantityStart`, `prices.quantityEnd` and `prices.price` in a context with inheritance enabled.
The `prices` list of the variant is empty, although the full read of the same variant returns the prices of the parent.
With `parentId` added to the requested fields the partial result equals the full read.

The inherited fallback of `EntityReader` reads `parentId` from the loaded entity:

- `loadOneToManyWithoutPagination()` collects the parent ids from `$entity->get('parentId')` and looks the group of the parent up with `$grouped[$entity->get('parentId')]` for an entity whose own association is empty.
- `loadOneToManyWithPagination()` does the same with `$entity->get('parentId')`.
- `loadManyToManyWithCriteria()` uses `$struct->has('parentId') ? $struct->get('parentId') : ''` and then looks `''` up in the mapping.

In a partial read only the primary key fields are added to the requested fields automatically (the filter at the start of `EntityReader::_read()`), so `parentId` is only loaded if the caller asks for it.
Nothing tells the caller: no exception, no event, just an empty list.
The trap exists for every inheritance aware entity and every inherited to-many association, not only for products.

## Expected behaviour

A partial read of an inherited association returns the same data as the full read, or fails visibly.

Either of these would do:

- `EntityReader` adds `parentId` implicitly to the selected fields of an inheritance aware entity when an inherited association is requested, as it already does for the primary key.
- Or the behaviour is documented on `Criteria::addFields()` and a clear exception is thrown when an inherited association is requested without `parentId`.

## How to reproduce

1. Create a product with prices (`product_price`) and a variant with `parentId` set to it and no prices of its own.
2. Build `new Criteria([$variantId])` and call `addFields(['id', 'productNumber', 'prices.quantityStart', 'prices.quantityEnd', 'prices.price'])`.
3. Search the product repository with a context that has `setConsiderInheritance(true)` and read `$result->first()->get('prices')`.
4. The list is empty.
5. Add `'parentId'` to the fields and repeat: the list contains the prices of the parent.

Add an integration test for the fix that reads one variant fully and partially and compares the `prices`.

## Research notes (not for upstream)

- Finding 33 in `docs/core-findings.md`; found while building the DTO projections (lever R3, `docs/33-orm-spike-dal-v2.md` "Lever R3", "Verified findings while building it"): the projection of a variant (scenario S2, product detail) returned an empty `prices` list, with `#[Path('parentId')]` in the DTO it equalled the DAL on all four engines.
- Not reproduced on trunk yet: the observation is from the spike on the instance; the code lines below were read on trunk (`review/finding-31`, `Dbal/EntityReader.php`): partial field filter lines 160 to 171, `loadOneToManyWithoutPagination()` lines 601 to 700 (parent ids at 634, fallback at 694), `loadOneToManyWithPagination()` line 716 (parent ids 736, fallback 800), many-to-many with criteria line 1076.
  Status stays `draft` until a test fails on trunk.
- The example paths are those of the spike DTO `ProductDetail` (`prices` with `quantityStart`, `quantityEnd`, `price`); the exact `addFields()` notation for an association field was not tested on trunk.
- `Criteria::addFields()` is at `Search/Criteria.php:649`, its docblock already says it returns `PartialEntity` instances.
