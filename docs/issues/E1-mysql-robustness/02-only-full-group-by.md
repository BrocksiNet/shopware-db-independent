---
id: E1.02
type: Improvement
template: technical_todo.yaml
title: "Make DAL selects valid under `ONLY_FULL_GROUP_BY` and stop changing `sql_mode`"
parent: E1
related: [E1.01, E1.03]
findings: [2]
status: draft
upstream: ""
---

## Technical TODO

`MySQLFactory` removes `ONLY_FULL_GROUP_BY` from the session `sql_mode` of every connection:

```php
$parameters['driverOptions'][Mysql::ATTR_INIT_COMMAND] = 'SET
    @@session.time_zone = \'+00:00\',
    @@session.group_concat_max_len = CAST(IF(@@group_concat_max_len > 320000, @@group_concat_max_len, 320000) AS UNSIGNED),
    @@session.sql_mode = (SELECT REPLACE(@@sql_mode, \'ONLY_FULL_GROUP_BY\', \'\'))';
```

The DAL depends on that.
`EntityDefinitionQueryHelper::addGroupBy()` groups by `<table>.id` when the query has a to-many join and no group fields:

```php
if ($query->hasState(self::HAS_TO_MANY_JOIN)) {
    $query->addGroupBy(
        self::escape($table) . '.' . self::escape('id')
    );
}
```

`EntityReader::fetch()` and `EntitySearcher::search()` call it and select other columns in the same statement: the primary key columns in the searcher, all selected fields and translation sub selects in the reader.
For versioned entities such as `product` the primary key is `(id, version_id)`, so even the columns of the root table are not functionally dependent on `id` alone.
With strict grouping the server rejects these statements; with the lenient mode it returns the values of an arbitrary row of each group.

Proposed change:

- Make the selects valid under strict grouping, either by grouping by the full primary key or by aggregating the selected expressions that are not part of the group.
- Remove the `sql_mode` change from `MySQLFactory` once the integration suite is green with the server default `sql_mode`.
- Keep the session `time_zone` and `group_concat_max_len` parts.

Acceptance:

- The unit and integration suites run on MySQL and MariaDB with `ONLY_FULL_GROUP_BY` enabled in the server configuration.
- `MySQLFactory` does not touch `sql_mode`.
- Follow-up items such as `StatesUpdater` and the aggregation score subquery are tracked in the sibling issue about `HAVING` and the unqualified `id`.

Not verified for this draft: which statements of the suites fail under strict grouping on MySQL and MariaDB.
The list of places above comes from reading the code and from a run on PostgreSQL in a proof of concept (PostgreSQL always groups strictly).

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 2, `docs/06-phase3-log.md` "Step 3", item 1.
- PoC: `EntityDefinitionQueryHelper::makeSelectValidForGroupBy()` wraps selected expressions in `any_value()` on PostgreSQL 16+ only. It is a stopgap for PostgreSQL; MySQL 8.4 and MariaDB 10.11 were not run under `ONLY_FULL_GROUP_BY`.
  Whether `ANY_VALUE()` is usable on both MySQL and MariaDB as a core fix was not checked.
- Trunk check: `src/Core/Framework/Adapter/Database/MySQLFactory.php` lines 105 to 107, `Dbal/EntityDefinitionQueryHelper.php` lines 736 to 753, `Dbal/EntityReader.php` line 423, `Dbal/EntitySearcher.php` lines 73 to 90. The finding holds on trunk.
- Epic E1 acceptance criterion 1 depends on this issue and E1.01, E1.03.
