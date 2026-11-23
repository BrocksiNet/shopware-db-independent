---
id: E3.08
type: Task
template: technical_todo.yaml
title: "Decide on the read shape options join and batch"
parent: E3
related: [E5.02]
findings: []
status: checked
upstream: ""
---

## Technical TODO

This is a decision task.
The likely outcome for MySQL and MariaDB is not to do it, because no measurement shows a gain there.

Today the main statement of a product listing read has 19 joins, 6 of them are derived tables for the translations (`TranslationFieldResolver` joins a translation sub query per language, built through `QueryBuilder::getTranslationQueryBuilder()`), and the to-one associations of the entity (manufacturer, unit, cover, tax, delivery time) are joined into the same statement (`EntityReader::joinBasic()`, "many-to-one associations can be directly fetched in same query").

Two alternatives were built and measured in a proof of concept on MySQL, MariaDB, PostgreSQL and SQLite:

- Join: replace the derived translation tables by direct `LEFT JOIN`s per language with `COALESCE`.
- Batch: leave the first level to-one associations out of the main statement (19 joins become 5) and read them afterwards with one `WHERE id IN (...)` statement per association.
  The statement count of listing, detail, search and JSON criteria goes from 4, 5, 7, 4 to 8, 10, 11, 8.
  Partial loading, associations below the root, extensions, self references and to-one associations without a foreign key field are not batched.

Result, median against the unchanged DAL in the same measurement block (differences below about 20 percent are inside the noise of the block):

| Engine | Join | Batch |
|---|---|---|
| MySQL, MariaDB | no change outside the noise; the optimizer already merges the derived tables (plan size and execution time equal) | no change outside the noise |
| PostgreSQL | none (search 17 percent slower, inside the noise) | listing 15 to 25 percent lower, detail 32 to 36 percent lower, search unchanged, JSON criteria 5 to 14 percent lower (inside the noise) |
| SQLite | listing 45, detail 67, JSON criteria 38 percent lower, the main read goes from 16.5 to 1.3 ms | none |

The PostgreSQL gain comes from the planning time of the 19 join statement (3.6 ms, against 0.7 ms with the batch), measured without a plan cache.
With a plan cache most of the planning time is gone and the gain would be smaller; that was not measured.

Neither MySQL nor MariaDB gains anything, and the batch costs four to five more statements per request.
The core runs on MySQL and MariaDB.
PostgreSQL and SQLite are not supported databases of the core today, so the only measured gains are on engines the core does not run on.

TODO:

- [ ] Decide for MySQL and MariaDB: do not change the read shape, unless a measurement on trunk with a production sized catalog shows a gain.
- [ ] Record the decision with the numbers above.
- [ ] If a second database is ever supported: re-measure join on SQLite and batch on PostgreSQL with the connection setup of that database (persistent connections, plan cache) before building them.
- [ ] If anything is built: `batch` needs the exceptions above covered by tests per engine (partial loading, nested associations, extensions, self references, to-one without foreign key field), and the flat translation join needs the query builder of the translation join in one place.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Lever R1 in `docs/33-orm-spike-dal-v2.md` ("Lever R1", "Plans", "Timings", "Gain against DAL v2 default", "Reading"); doc 29 conclusion "DAL v2, levers in order" row 6 (judgement: 1 to 2 weeks).
- Scenario ids: S1 listing, S2 detail, S3 search, S5 JSON criteria.
  Statement counts S1/S2/S3/S5: default 4/5/7/4, with batch 8/10/11/8.
- Plans of the main read of S1 (doc 33 "Plans", median of 7 runs):

  | Engine | Shape | joins | derived tables | plan nodes | planning ms | execution ms |
  |---|---|---|---|---|---|---|
  | mysql | default / join / batch / join+batch | 19 / 19 / 5 / 5 | 6 / 0 / 2 / 0 | 56 / 56 / 16 / 16 | n/a | 0.443 / 0.355 / 0.216 / 0.243 |
  | mariadb | default / join / batch / join+batch | 19 / 19 / 5 / 5 | 6 / 0 / 2 / 0 | 20 / 20 / 6 / 6 | 0.485 / 0.299 / 0.349 / 0.132 | 0.33 / 0.336 / 0.306 / 0.172 |
  | postgresql | default / join / batch / join+batch | 19 / 19 / 5 / 5 | 6 / 0 / 2 / 0 | 50 / 52 / 11 / 11 | 3.592 / 3.948 / 0.718 / 0.707 | 1.508 / 1.957 / 0.358 / 0.414 |
  | sqlite | default / join / batch / join+batch | 19 / 19 / 5 / 5 | 6 / 0 / 2 / 0 | 38 / 20 / 12 / 6 | n/a | 16.526 / 1.292 / 14.672 / 0.658 |

- Planning share on PostgreSQL without plan cache (sum of the medians of every statement of a scenario run): S1 61 percent, S2 80, S3 16, S5 17; with join+batch the planning sum drops to 4.5, 1.9, 6.1 and 3.4 ms (S1, S2, S3, S5).
- Timing block (doc 33, "Timings" under R1), medians in ms, DAL v2 default to batch / join+batch:
  PostgreSQL S1 22.0 to 18.8 / 16.4, S2 14.0 to 9.5 / 9.0; SQLite S1 64.0 to 35.0 (join) / 35.6 (join+batch), S2 17.2 to 5.7 / 5.3, S5 62.6 to 38.9 / 38.7.
  "DAL v2 untouched" differed from the DAL by up to 20 percent in that block, and the host load stayed at 7.6 to 10.0.
  With the other levers on top the MySQL and MariaDB numbers go both ways (MySQL S1 5.1 to 7.3 ms, MariaDB S1 5.5 to 3.8 ms), which doc 33 reads as noise of a 2 to 7 ms call.
- Spike code: `src/Core/Framework/OrmSpike/DalV2/Read/FlatTranslationQueryBuilder.php` (91 lines), `ShapeEntityReader.php` (copy of `EntityReader`, about 130 changed lines), 10 changed lines in `WindowCountSearcher`.
- The storefront product detail request of core finding 9 was not reproduced; finding 9 has no issue (README: with the plan cache the remaining planning does not justify splitting the statement, `docs/22`).
- Trunk references (`review/finding-31`): `EntityReader::joinBasic()` to-one join at line 273, `loadToOne()` at line 1369 (only for to-one associations with nested associations), `TranslationFieldResolver.php:108`, `QueryBuilder::getTranslationQueryBuilder()` line 69.
- Effort estimate from doc 33 / doc 29 (estimate): one to two weeks, judgement.
