---
id: E1.05
type: Improvement
template: technical_todo.yaml
title: "Do not continue a transaction after a failed statement without a savepoint"
parent: E1
related: []
findings: [5]
status: checked
upstream: ""
---

## Technical TODO

Some code catches the exception of a failed statement and carries on inside the same transaction.
That works on MySQL and MariaDB, where a failed statement is rolled back alone and the transaction stays usable.
PostgreSQL, for example, aborts the whole transaction after an error and rejects every following statement with `current transaction is aborted`.

Places on trunk that catch a failed statement and continue:

- `SalesChannelContextPersister::save()` catches `UniqueConstraintViolationException` from `INSERT ... ON DUPLICATE KEY UPDATE` and then runs `REPLACE INTO` on the same connection:

  ```php
  try {
      $query->execute($data);
  } catch (UniqueConstraintViolationException) {
      // When both unique keys conflict, retain REPLACE's behavior of removing both conflicting rows.
      ...
      $query->execute($data);
  }
  ```

  If a caller has an open transaction, the second statement runs in it.
- `CustomEntitySchemaUpdater` sets `FOREIGN_KEY_CHECKS = 0`, swallows the exception of a failing `DROP INDEX IDX_...` statement and continues with the next statement.
- `WebhookOutboxStore::backfillDelivery()` and `recordOutboxEntryWithStatus()` catch `UniqueConstraintViolationException` inside `RetryableTransaction::retryable()`.
  Both return `null` right after the catch, so only the commit of the failed transaction is affected.

Proposed change:

- Where an expected failure is part of the control flow, wrap the statement in a savepoint (`createSavepoint()` / `rollbackSavepoint()` on the connection) or check before writing.
- For the context persister, an `INSERT ... ON DUPLICATE KEY UPDATE` followed by a `REPLACE` only on a double conflict could be replaced by one statement or a check, which also removes the exception from the normal path.
- List the remaining `catch` blocks that continue after a database exception and decide for each whether a savepoint is needed.

Acceptance:

- No catch block in core code continues to use the connection inside a transaction after a failed statement without a savepoint.
- A test for the context persister conflict path runs inside a transaction.

Not verified for this draft: whether production callers of `SalesChannelContextPersister::save()` run inside a transaction, and whether the list above is complete.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` row 5, `docs/09-test-run-on-postgresql.md` (lines 14 to 16: each test runs in a transaction, application code catches failing statements; PostgreSQL answers `current transaction is aborted`), `docs/summary.md` ("Correctness").
- In the PoC the PHPUnit run on PostgreSQL uses one savepoint per statement (`SHOPWARE_PG_STATEMENT_SAVEPOINTS=1`), which hides the problem in tests; production paths are not all checked (`docs/27-final-report.md` line 41).
- Trunk check: `src/Core/System/SalesChannel/Context/SalesChannelContextPersister.php` lines 63 to 91, `src/Core/System/CustomEntity/Schema/CustomEntitySchemaUpdater.php` lines 66 to 86, `src/Core/Framework/Webhook/Outbox/WebhookOutboxStore.php` lines 82 and 473. The context persister now uses `INSERT ... ON DUPLICATE KEY UPDATE` first and the `REPLACE` fallback only on a double conflict, which differs from the plain description in docs/09.
- `TaskRegistry` (line 196) also catches `UniqueConstraintViolationException` around a repository create and ignores it; not checked whether a transaction is open there.
- The webhook outbox lines were found while checking trunk, they are not in the findings table.
- Checked statically against trunk c6ef9571261 (2026-11-23).
