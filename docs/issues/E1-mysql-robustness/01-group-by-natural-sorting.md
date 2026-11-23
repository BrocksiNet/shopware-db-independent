---
id: E1.01
type: Bug
template: bug_report.yml
title: "Natural sorting in a grouped query sorts by a non-aggregated column"
parent: E1
related: [E1.02]
findings: [1]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23288"
---

## Shopware Version

trunk (code checked on `c6ef9571261`, 2026-11-23)

## Affected area / extension

Platform(Default)

## Actual behaviour

`CriteriaQueryBuilder::addSortings()` adds the length part of a natural sorting with the plain field accessor, before it decides whether the query is grouped:

```php
if ($sorting->getNaturalSorting()) {
    $query->addOrderBy('LENGTH(' . $accessor . ')', $sorting->getDirection());
}

if (!$this->hasGroupBy($criteria, $query)) {
    $query->addOrderBy($accessor, $sorting->getDirection());

    continue;
}
```

For a grouped query (a to-many join or `Criteria::addGroupField()`) the value part of the same sorting is wrapped in `MIN()` (ascending) or `MAX()` (descending), but the `LENGTH()` part is not.
`LENGTH(accessor)` is therefore a non-aggregated expression in a query that groups by the primary key.
MySQL and MariaDB run it with `ONLY_FULL_GROUP_BY` removed from the session (`MySQLFactory`) and take the value of an arbitrary row of each group.
The length part is the first sort key, so a group can be ordered by the length of a value that is not the value used by the second sort key.

## Expected behaviour

The length part follows the value part: `LENGTH(MIN(accessor))` for an ascending and `LENGTH(MAX(accessor))` for a descending sorting when the query is grouped.
Both sort keys then describe the same row of the group, and the query stays valid when `ONLY_FULL_GROUP_BY` is on.

## How to reproduce

Found by reading the code, not run on trunk.

1. Build a `Criteria` for an entity with a text column, for example `product`, with `addGroupField(new FieldGrouping('displayGroup'))` (this makes `hasGroupBy()` true) and `addSorting(new FieldSorting('productNumber', FieldSorting::ASCENDING, true))`.
2. Run it through `EntitySearcher::search()` and read the generated SQL: `ORDER BY LENGTH(product.product_number) ASC, MIN(product.product_number) ASC`.
3. With a group that holds values of different lengths, the first key depends on which row MySQL picks.

The admin search on `property_group_option` with a natural sorting is the use case in which this showed up.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 1, `docs/06-phase3-log.md` (table near the end, row "Admin product detail, `property-group-option` search").
- The PoC uses `LENGTH(MIN(col))` / `LENGTH(MAX(col))` on every platform when the query has a group by; PostgreSQL rejected the unaggregated form.
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Dbal/CriteriaQueryBuilder.php` lines 133 to 152. The finding holds on trunk, the code is unchanged in shape.
- No test or run on MySQL was done for this draft. Status stays draft until a unit test on the generated SQL exists.
- Checked statically against trunk c6ef9571261 (2026-11-23).
