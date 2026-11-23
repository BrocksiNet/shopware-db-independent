---
id: E3.09
type: Story
template: story.yaml
title: "Check criteria field paths with PHPStan"
parent: E3
related: [E3.07]
findings: []
status: draft
upstream: ""
---

## User story

As a developer of a plugin or an app backend, I would like PHPStan to check the field paths I write in a `Criteria` (`new EqualsFilter('manufacturer.name', ...)`, `FieldSorting`, `addAssociation()`), so that a typo fails in the static analysis instead of at run time in an integration test or in production.

## Acceptance criteria

- A PHPStan rule, shipped with the core rules, resolves a literal field path against the registered entity definitions, through associations, translated fields and to-many paths, for example `manufacturer.translations.name`.
- A path with an unknown segment is reported with the failing segment named, for example `"nam" is not a field of product_manufacturer`.
- The rule knows the entity at a `->search($criteria)` call on a repository whose entity is known from its type or service, and it stays silent where the entity cannot be derived.
- Paths that exist only on a definition variant (for example `cheapestPrice`, which belongs to the sales channel product definition, not to `product`) are checked against the right definition, or the rule stays silent for them.
- Dynamically built paths are not reported.
- The rule has unit tests with valid paths, typos, translated fields, inherited associations and an unknown entity.
- The rule is documented, including how to turn it off for a line.

Limits that the design has to deal with:

- `Criteria` has no reference to an entity or definition (it does not mention `EntityDefinition`), so the entity is not known where the filter is written, only where the criteria is passed to a repository.
- `EntityRepository` is generic over its collection class (`@template TEntityCollection of EntityCollection`), not over the entity name, so the rule has to derive the entity from the collection type or from the service that is injected.
- The core has no rule that checks a criteria field path today; the existing DAL rule (`DALFieldsMustBeRegisteredWithSchemaBuilder`) concerns the schema builder.

## Research notes (not for upstream)

- X2 in `docs/33-orm-spike-dal-v2.md` ("X2: typed criteria"); doc 29 conclusion row 8 (1 to 3 weeks, judgement).
- Prototype: `src/Core/Framework/OrmSpike/DalV2/Typed/FieldPathChecker.php` (79 lines) on `poc/orm-spike` resolves a path against the registered definitions.
  Probe `fieldPaths` (`orm-spike:dalv2-probes`): 7 valid paths accepted, 5 typos rejected with the failing segment named, 1,025 paths generated for `product` at depth 2.
  Run on MariaDB and PostgreSQL; the check reads definitions only.
- No PHPStan rule was written, only the checker that such a rule would call.
- The limits above (no entity in `Criteria`, `cheapestPrice` only on the sales channel definition) are from doc 33; the first was re-checked on trunk by counting `EntityDefinition` in `Criteria.php` (0 matches), the second not.
- Trunk references (`review/finding-31`): `src/Core/DevOps/StaticAnalyze/PHPStan/Rules/` (no rule that mentions `Criteria`), `EntityRepository::search()` at `DataAbstractionLayer/EntityRepository.php:66`.
- The Doctrine spike's PHPStan extension caught literal DQL with an unknown field (doc 29 "Static analysis"); that is the comparison point.
- Effort estimate from doc 29 (estimate, judgement): 1 to 3 weeks on top of the checker.
