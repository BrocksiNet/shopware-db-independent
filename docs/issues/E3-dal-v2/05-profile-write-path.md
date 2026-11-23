---
id: E3.05
type: Task
template: technical_todo.yaml
title: "Profile the DAL write path"
parent: E3
related: [E3.01, E3.04]
findings: []
status: draft
upstream: ""
---

## Technical TODO

After the fix of E3.01 and the batched updates of E3.04 the write path of the DAL still sends few statements and is still slow.
Bulk create and update of 50 products, measured in a proof of concept with both changes (23 statements):

- MySQL 54.36 ms against 6.12 ms for hand-written DBAL, about 9 times.
- A hand-written Doctrine ORM path took 43.48 ms and a Cycle ORM path 52.29 ms on MySQL, with about 350 statements each.
  Those paths skip validation, write protection and the written events, so the comparison is not like for like.
- PostgreSQL: 89.15 ms against 57.22 ms (Doctrine) and 59.07 ms (Cycle).

A profile of the existing write path (timer probes around the reader, searcher, aggregator, hydrator, events and the connection) put 58 to 63 percent of the call in PHP of the writer outside the SQL: command extraction, field serializers, validation, change sets and events.
SQL was 36 to 41 percent of the call on MySQL, MariaDB and PostgreSQL.
Where inside the writer the time goes was not measured.

One result is unexplained: on SQLite the 50 product write took 287.10 ms with 23 statements, while a hand-written ORM path wrote the same 50 products in 16.86 ms with 350 statements.
A profile of the SQLite run showed 76.5 percent of the time in SQL, and the single `UPDATE product` statement with 50 rows accounted for 249.9 ms per run, about 5 ms per row.
That is not a property of SQLite, so something in the statement shape or in how the DAL runs it is expensive.
It may point at a statement problem that is not specific to SQLite.

TODO:

- [ ] Profile `EntityWriteGateway`, `WriteCommandExtractor`, the field serializers, `WriteCommandQueue`, change set generation and the written event dispatch for the 50 product scenario with a sampling profiler (the proof of concept used timer probes, because a tracing profiler slowed the run by about 12 times and distorted the shares).
- [ ] Report the exclusive time per class and per field serializer on MySQL and MariaDB, not only the writer total.
- [ ] Count the events dispatched and the listeners that run per write, and measure them with and without the indexers and extensions of a plain installation.
- [ ] Find the cause of the 5 ms per row of the batched `UPDATE product` on SQLite: check the statement shape, the connection middleware that wraps the statements there, and the transaction handling, one at a time.
- [ ] Derive from the profile a list of follow-up issues with the expected saving each; drop what is below the noise.
- [ ] Do not build compiled or generated writers before the profile shows a share that justifies them.

## Research notes (not for upstream)

- Source: `docs/33-orm-spike-dal-v2.md` sections "Profile: where the DAL time goes", "Reading the numbers" (last bullet) and "Follow-up from the final timing block"; timing block `docs/34-orm-spike-final-timings.md`.
- Profile shares for S4 (bulk create and update of 50 products), the `other` column is the writer PHP: MariaDB 63 percent (sql 36), MySQL 58 percent (sql 41), PostgreSQL 61 percent (sql 37); SQLite S4 left out because parallel sessions wrote to the same file.
  The follow-up section of doc 33 quotes "58 to 59 percent" for the same profile, and doc 29's recommendation repeats it; the table gives 58, 63 and 61, so the range above uses the table.
  The `sql` category only covers statements run through the wrapped connection inside the probe.
- Final block (doc 33 "Follow-up"): DAL v2 with all levers on S4 57.49 ms against optimized Doctrine 43.48 and optimized Cycle 52.29 (MySQL), 89.15 against 57.22 and 59.07 (PostgreSQL).
  Doc 33 lever table with all levers on S4: MySQL 54.36 ms, DBAL 6.12 ms (doc 33 "Reading the numbers", other timing block).
  The 54.36 and 57.49 ms are from different blocks, both are quoted as the docs give them.
- SQLite: Cycle 16.86 ms with 350 statements, DAL v2 287.10 ms with 23 statements (doc 33 follow-up); the profile re-run showed 76.5 percent SQL and 249.9 ms for the one `UPDATE product` (doc 33 "Reading the numbers", W1 on SQLite).
  Candidate causes the doc names: statement shape of the DAL update, the `TextBindingStatement` middleware (a PoC SQLite middleware, not core), transaction handling.
  The cause was not found; the SQLite part is a PoC database, so this item matters upstream only if the statement shape is the cause.
- Profile method: `src/Core/Framework/OrmSpike/DalV2/Profile/` (decorators with `hrtime`, 60 iterations after 5 warm-up calls, `APP_ENV=prod`); SPX and xhprof were not installed in the container, Xdebug profiling was dropped.
- Effort: not estimated in docs 29 or 33.
