---
id: E1.06
type: Improvement
template: technical_todo.yaml
title: "Merge rows with the same key in `MultiInsertQueryQueue`"
parent: E1
related: []
findings: [12]
status: checked
upstream: ""
---

## Technical TODO

`MultiInsertQueryQueue::addUpdateFieldOnDuplicateKey()` makes the queue append `ON DUPLICATE KEY UPDATE col = VALUES(col)` to the multi-row `INSERT`:

```php
$updateParts[] = \sprintf('%s = VALUES(%s)', EntityDefinitionQueryHelper::escape($field), EntityDefinitionQueryHelper::escape($field));
...
return ' ON DUPLICATE KEY UPDATE ' . implode(', ', $updateParts);
```

If two rows of the queue have the same key, MySQL and MariaDB apply the rows one after the other and the last row wins for the update columns.
`MultiInsertQueryQueueTest::testAddUpdateFieldOnDuplicateKey` relies on it: it queues two `category` rows with the same `id` and `version_id` (type link, then type folder) and asserts that the stored type is the folder.
Neither the method nor the class states this rule.
A standard conform upsert (`INSERT ... ON CONFLICT DO UPDATE`, SQL `MERGE`) rejects two rows with the same key in one statement.

Callers that set update fields: `SeoUrlPersister::persistSalesChannelSeoUrls()` (seven columns) and `CustomFieldSubscriber` (`snippet.value`).

Proposed change:

- Merge rows with the same key inside the queue before the statement is built: keep the first row, take the update columns from the last row.
- The key is the primary key or the unique key that the `ON DUPLICATE KEY` clause reacts to; decide how the queue learns it (new optional parameter or from the table schema).
- Document the rule on `addUpdateFieldOnDuplicateKey()`.

Acceptance:

- Two queued rows with the same key produce one row in the statement, with the update columns of the last row.
- `testAddUpdateFieldOnDuplicateKey` passes unchanged on MySQL and MariaDB.
- The behaviour is documented in the method comment.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 12, `docs/21-dal-failures-postgresql.md` (failure row for `MultiInsertQueryQueueTest::testAddUpdateFieldOnDuplicateKey`: `ON CONFLICT DO UPDATE command cannot affect row a second time`; fix section "Wave 6").
- PoC: `MultiInsertQueryQueue::mergeCollidingRows()` with the key from `SqlDialect::upsertCollisionColumns()` (PostgreSQL: conflict target or primary key, other dialects: empty list, nothing merged).
- Trunk check: `src/Core/Framework/DataAbstractionLayer/Doctrine/MultiInsertQueryQueue.php` lines 87 to 148 (class is 204 lines, `ignoreErrors` and `useReplace` options also exist), test `tests/integration/Core/Framework/DataAbstractionLayer/Doctrine/Doctrine/MultiInsertQueryQueueTest.php` lines 67 to 102, callers `src/Core/Content/Seo/SeoUrlPersister.php` line 105 and `src/Core/System/Snippet/Subscriber/CustomFieldSubscriber.php` line 72. The finding holds on trunk.
- Not checked: whether `SeoUrlPersister` and `CustomFieldSubscriber` ever queue two rows with the same key in practice.
- Checked statically against trunk c6ef9571261 (2026-11-23).
