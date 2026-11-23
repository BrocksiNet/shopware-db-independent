---
id: E3.04
type: Improvement
template: technical_todo.yaml
title: "Batch update commands of one entity in the write gateway"
parent: E3
related: [E2.01, E3.01, E3.05]
findings: [29]
status: draft
upstream: ""
---

## Technical TODO

`EntityWriteGateway::executeCommands()` batches inserts (`MultiInsertQueryQueue`), but runs every `UpdateCommand` as its own `Connection::update()` statement, after flushing the pending inserts.
A write that updates many rows of one entity with the same changed columns, for example a stock update of 50 products or the update half of a sync request, therefore sends one `UPDATE` per row.

Measured in a proof of concept on MySQL and MariaDB, bulk create and update of 50 products (with the fix of E3.01 applied, 121 statements):

| Variant | MySQL | MariaDB |
|---|---|---|
| Existing write path | 88.55 ms, 371 statements | 90.40 ms, 371 statements |
| Fix of E3.01 only | 60.60 ms, 121 statements | 59.05 ms, 121 statements |
| Batched updates only | 76.20 ms, 273 statements | 83.62 ms, 273 statements |
| Both | 49.33 ms, 23 statements | 57.81 ms, 23 statements |

On top of the E3.01 fix the batching saves 98 statements and 19 percent of the time on MySQL, but only 2 percent on MariaDB, which is inside the measurement noise (about 20 percent in that run).
The statement count is the reliable gain, the time gain is small.

The batch did not help on two other engines:

- PostgreSQL: the batched statement was not used (123 statements before and after), because an untyped `CASE` result is text there.
  A first run of the batched statement failed with `column "stock" is of type integer but expression is of type text`.
  The proof of concept falls back to single row updates whenever a changed column on PostgreSQL has a non-integer value.
  Which column of the product update triggers the fallback was not checked, and no variant with a cast per column type was built.
- SQLite: the statements went from 371 to 23 and the median did not change (see E3.05).

PostgreSQL is not supported by the core today.
The cast problem still matters for E2.01 (batching the single row `UPDATE product` statements of the product indexer updaters), which needs the same typed `CASE` or `WHERE id IN` statements if the core is ever run on a second database.

TODO:

- [ ] Add a batched update to `EntityWriteGateway::executeCommands()` for a run of consecutive `UpdateCommand`s of one entity with the same payload columns, in chunks of at most 100 rows.
- [ ] Build the statement as `UPDATE t SET c = CASE WHEN <pk> THEN ? ... ELSE c END WHERE (<pk>) OR (<pk>)`, and set a column directly when its value is equal in every row of the chunk.
- [ ] Keep single row updates for `JsonUpdateCommand`, for a chunk with the same primary key twice, and for commands that do not share their payload columns.
- [ ] Keep `PreWriteValidationEvent`, `generateChangeSets()`, `validateCommands()` and the written events exactly as they are, they run before the loop.
- [ ] Keep the execution order of the commands: the pending inserts are flushed before an update, an update must not move across a delete or an insert of another entity.
- [ ] Bind the values with their type (integer and string) so the statement does not rely on implicit conversion.
- [ ] Decide the row order inside a batch, see E2.02 for the deadlock topic of the indexer updaters.
- [ ] Find out which column of the product update is not an integer, and check whether a cast per field type (derived from the field serializer or the schema) makes the statement valid on PostgreSQL.
- [ ] Share the statement builder with E2.01 if both end up in the same shape.
- [ ] Tests: unit tests of the statement builder per field type, integration tests that compare the rows written by a batch with the rows written by single updates, and the `EntityWrittenEvent` payloads.

## Research notes (not for upstream)

- Lever W1b in `docs/33-orm-spike-dal-v2.md` ("Lever W1", "Reading the numbers", "Follow-up from the final timing block"), scenario S4.
  Numbers above are from the lever table: "DAL v2 untouched" 88.55 / 90.40 ms, `write=key` 60.60 / 59.05, `write=upd` 76.20 / 83.62, `write=key+upd` 49.33 / 57.81 (MySQL / MariaDB).
- The percentages are computed from those numbers (60.60 to 49.33 is 18.6 percent, 59.05 to 57.81 is 2.1 percent).
- PostgreSQL S4 stays at 123 statements and 78.47 to 98.28 ms in every configuration; SQLite S4 329.71 ms untouched, 345.53 ms with `write=key+upd`.
- Spike code: `src/Core/Framework/OrmSpike/DalV2/Write/WriteGatewayV2.php` on `poc/orm-spike`, a copy of the gateway, about 130 changed lines.
  `executeBatchedUpdate()` chunks by 100, sets columns with equal values directly, builds a `CASE` per differing column, and falls back to `updateSingly()` for a duplicate primary key and, on PostgreSQL, for a non-integer value (lines 586 to 590 per doc 33).
- Trunk references (`review/finding-31`): `EntityWriteGateway::executeCommands()` line 150, the `UpdateCommand` branch lines 215 to 227, `generateChangeSets()` line 514.
- The W1b numbers depend on W1a (E3.01): the 248 extra existence lookups of the old path are part of the 371 statements (doc 33, "Verified statement analysis").
- Core finding 29 is the indexer side (`docs/26-postgresql-bulk-write.md`: about 475 single row `UPDATE product` statements per 50 product sync, E2.01).
  The gateway side and the indexer side are separate code paths.
- Effort estimate from doc 33 / doc 29 (estimate): one to two weeks (casts on PostgreSQL, events, tests).
- After this and E3.01 the 50 product write is still about 9 times hand-written DBAL on MySQL (54.36 against 6.12 ms), see E3.05.
