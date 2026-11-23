---
id: E1.03
type: Improvement
template: technical_todo.yaml
title: "Remove the select alias in `HAVING`, the unqualified `id` and the partial `GROUP BY` of `StatesUpdater`"
parent: E1
related: [E1.02]
findings: [3, 4]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23290"
---

## Technical TODO

Three statements only work because MySQL and MariaDB are lenient.

1. `CriteriaQueryBuilder::addQueries()` selects the score as an alias and filters on the alias in `HAVING`:

   ```php
   $query->addSelect($select . ' as _score');
   ...
   $query->andHaving('_score >= :_minScore');
   ```

   Standard SQL does not allow a select alias in `HAVING`.

2. `EntityAggregator` builds a score sub query and groups it by the bare storage name of the primary key columns, while the same loop qualifies the selected and joined columns with the table name:

   ```php
   foreach ($pks as $pk) {
       $scoreQuery->addGroupBy($pk);

       $pk = EntityDefinitionQueryHelper::escape($pk);
       $scoreQuery->addSelect($escapedTable . '.' . $pk);
   ```

   A bare `id` is ambiguous as soon as a joined table has an `id` column.

3. `StatesUpdater::update()` selects `product.type` and `product.states` with `GROUP BY product.id` over a `LEFT JOIN product_download`.
   The primary key of `product` is `(id, version_id)`, so the selected columns are not functionally dependent on the grouped column.
   The class and method are already deprecated for removal in v6.8.0.

Proposed change:

- Repeat the score expression in `HAVING` instead of the alias.
- Qualify the grouped column with the table name in `EntityAggregator`.
- Replace the `LEFT JOIN ... GROUP BY` in `StatesUpdater` with an `EXISTS` sub query for the `hasDownloads` flag, or leave it out if the class is removed first.

Acceptance:

- No select alias is used in `HAVING` in the DAL.
- The score sub query groups by a qualified column.
- The existing tests of the three places pass on MySQL and MariaDB, including with `ONLY_FULL_GROUP_BY` enabled.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` rows 3 and 4, `docs/06-phase3-log.md` "Step 3" items 2 and 3 and the file table (`StatesUpdater` row: `LEFT JOIN` + partial `GROUP BY` replaced by `EXISTS`, all platforms).
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Dbal/CriteriaQueryBuilder.php` lines 209 to 224, `Dbal/EntityAggregator.php` lines 180 to 196 (`addGroupBy($pk)` at line 190), `src/Core/Content/Product/DataAbstractionLayer/StatesUpdater.php` lines 45 to 54. All three hold on trunk.
- `StatesUpdater::update()` carries `@deprecated tag:v6.8.0 - Will be removed, as product states are deprecated`. Item 3 can be dropped from this issue if the removal lands first.
- The PoC repeats the score expression in `HAVING` and qualifies the column on every platform; the 153 DAL unit tests passed on MariaDB with these changes (no new tests written).
- Checked statically against trunk c6ef9571261 (2026-11-23).
