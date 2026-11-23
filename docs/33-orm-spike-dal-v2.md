# Wave 8 V: DAL v2, the DAL kept and improved

Handoff V of wave 8.
Question: how far do targeted changes to the existing DAL get, measured on the same slice and the same four databases as Doctrine (doc 31) and Cycle?
Harness and scenarios S1 to S5: [docs/30](30-orm-spike-baseline.md).
Candidate description: [docs/29](29-orm-alternatives.md), section "Candidate 3: DAL v2".

Code: `instance/src/Core/Framework/OrmSpike/DalV2/` on the instance branch `poc/orm-spike`.
No DAL class was edited.
Where a lever needs a changed DAL class the class is copied into `DalV2/` and named as a copy below.

## Status

Profile, levers C1, A1, R3 and W1, the DX results X1 to X3, the probes and one timing block are done and verified.
R2 (compiled hydrators) is not built because the profile does not justify it.
R1 (read shape) is built as two options and measured, see its section.

## Method

### Implementation

`--impl=dalv2` rebuilds the DAL stack by composition (`DalV2Implementation`): a new `EntityReader`, `SalesChannelRepository` and `EntityRepository` with the container's definitions, searcher, aggregator and version manager, and it runs the scenarios of the harness `DalImplementation` on top.
Levers are switched with `--option key=value`, so each one is measured alone and combined.

| Option | Lever |
|---|---|
| `count=window` | C1, exact total from `COUNT(*) OVER()` |
| `write=key` | W1a, existence lookups hit the prefetch |
| `write=upd` | W1b, batched `UPDATE` per run of equal rows |
| `profile=1` | hrtime profile mode, no lever |

### Profile method

SPX and xhprof are not installed in the container.
Xdebug profiling was tried and dropped, it slows the run down about 12 times and distorts the shares.
The shares come from `hrtime` probes in decorators (`DalV2/Profile/`):

- decorators around `EntityReaderInterface`, `EntitySearcherInterface`, `EntityAggregatorInterface`, the event dispatcher and the `EntityHydrator`,
- a wrapper around the driver connection (reflection on `Doctrine\DBAL\Connection::$_conn`) that times every statement and counts calls,
- an exclusive-time stack, so the time of a nested probe is subtracted from its parent (reader time without the SQL and hydration inside it).

Categories: `sql` (driver execution and fetch), `read.php` (reader PHP without SQL and hydration: building the query, associations), `search.php`, `aggregate.php`, `hydrate`, `events`, `other` (the rest of the wall time: context, writer, serializers).
60 measured iterations after 5 warm-up calls, `APP_ENV=prod`, warm cache.
The shares are not from the final timing block (other lanes were running), only the shares are used from them, not the absolute milliseconds.

## Harness issues found

- The result file name uses the dialect name, which is `mysql` for MariaDB, so the MySQL and MariaDB result files collide in one output directory.
  Workaround used here: a separate `--output-dir` per engine and configuration.
- `--scenario` takes one value, the last flag wins; `--scenarios` is not an option.
  Scenarios are run one per call.
- S4 runs of parallel sessions collide on the shared write cleaner (`WriteException`, deadlocks, lock wait timeouts seen), so S4 numbers are only valid while holding the timing lock.

## Profile: where the DAL time goes

Share of the wall time of one scenario call, DAL stack with the sales channel context, per engine.

| Engine | Scen. | Wall ms | sql | read.php | search.php | aggregate | hydrate | events | other |
|---|---|---|---|---|---|---|---|---|---|
| MariaDB | S1 | 10.3 | 45% | 20% | 5% | 0% | 15% | 8% | 7% |
| MariaDB | S2 | 5.1 | 38% | 46% | 4% | 0% | 6% | 3% | 4% |
| MariaDB | S3 | 51.0 | 84% | 5% | 2% | 3% | 3% | 2% | 2% |
| MariaDB | S4 | 98.5 | 36% | 0% | 0% | 0% | 0% | 1% | 63% |
| MariaDB | S5 | 37.2 | 86% | 7% | 2% | 0% | 3% | 1% | 1% |
| MySQL | S1 | 10.9 | 45% | 20% | 5% | 0% | 14% | 8% | 8% |
| MySQL | S2 | 5.1 | 33% | 52% | 3% | 0% | 5% | 3% | 4% |
| MySQL | S3 | 66.0 | 88% | 4% | 1% | 2% | 3% | 1% | 1% |
| MySQL | S4 | 111.6 | 41% | 0% | 0% | 0% | 0% | 1% | 58% |
| MySQL | S5 | 34.5 | 85% | 7% | 2% | 0% | 3% | 1% | 2% |
| PostgreSQL | S1 | 23.1 | 71% | 12% | 3% | 0% | 7% | 4% | 4% |
| PostgreSQL | S2 | 12.9 | 65% | 25% | 2% | 0% | 4% | 2% | 2% |
| PostgreSQL | S3 | 74.1 | 87% | 4% | 1% | 3% | 2% | 1% | 1% |
| PostgreSQL | S4 | 89.0 | 37% | 0% | 0% | 0% | 0% | 2% | 61% |
| PostgreSQL | S5 | 46.6 | 88% | 6% | 2% | 0% | 3% | 1% | 1% |
| SQLite | S1 | 67.9 | 87% | 6% | 2% | 0% | 3% | 1% | 2% |
| SQLite | S2 | 19.7 | 70% | 24% | 2% | 0% | 2% | 1% | 2% |
| SQLite | S3 | 140.8 | 92% | 3% | 1% | 2% | 1% | 1% | 1% |
| SQLite | S5 | 68.5 | 90% | 5% | 2% | 0% | 1% | 1% | 1% |

SQLite S4 is left out: parallel sessions wrote to the same file during that run, the numbers are not valid.
In S4 the `sql` category only covers statements that run through the wrapped connection inside the probe, the `other` share is the writer in PHP (command extraction, serializers, validation, change sets, events).

What the profile decides:

- SQL execution dominates S3 and S5 (84 to 92 percent on every engine) and S1 on PostgreSQL and SQLite (71 and 87 percent).
  Only a different statement shape helps there (R1, R3, A1, C1), not faster PHP.
- Hydration is 15 percent at most (S1 on MySQL and MariaDB) and 7 percent or less in every other cell.
  Compiled hydrators (R2) could save at most that share on a list, so R2 is not built.
  R3 (DTO projection, no `Entity` objects) gives the upper bound of what skipping the generic hydration and entity creation can win, and is measured instead.
- Reader PHP (building the SQL) is the biggest PHP share in S2 on MySQL and MariaDB (46 and 52 percent of a 5 ms call).
- Events are 1 to 8 percent, extensions are not a separate cost in this slice.
- S4 is 58 to 63 percent PHP in the writer, the rest is statements.

## Verified statement analysis

Counted from the statement list of the profile run (statements per call, the same on repeated runs).

- S4 on MySQL, MariaDB and SQLite runs 371 statements, on PostgreSQL 123.
  The difference is 248 single row `SELECT 1 as exists ...` lookups: 150 on `product_translation`, 100 on `product`.
- S3 runs the id statement, a separate `SELECT COUNT(*) FROM (<same query>)` and one statement per aggregation (min, max, terms) next to the association reads.

## Lever C1: exact total from a window count

Change: `DalV2/Read/WindowCountSearcher.php` is a copy of `Dbal/EntitySearcher.php` (DAL class copy).
When the criteria ask for an exact total with a limit and no score field, the id statement selects `COUNT(*) OVER() as __total` and the total is taken from the first row.
An empty page with an offset falls back to the old `COUNT(*)` statement, because no row carries the total then.
Verify: `--verify` equals the DAL on S1, S2, S3 and S5 on MySQL, MariaDB, PostgreSQL and SQLite.
BC: internal (searcher implementation, same `IdSearchResult`).

## Lever W1: write path

### W1a: why MySQL, MariaDB and SQLite run 250 more lookups than PostgreSQL

Cause, verified by logging the cache key in a copy of the gateway:

- `EntityWriteGateway::prefetch()` stores the existence of each primary key in the `PrimaryKeyBag` under the key `implode('_', $primaryKey)` of the decoded values (hex strings).
- `EntityWriteGateway::getCurrentState()` decodes the key it looks up with `$definition->getField($fieldName)`, but `$fieldName` is a storage name there (`version_id`, `product_id`, `language_id`, `product_version_id`).
  `getField()` finds fields by property name, so for every key that is not named the same in both (the version columns and the foreign key columns of the translation) it returns `null` and the value stays undecoded.
- On MySQL, MariaDB and SQLite an undecoded value is the 16 byte binary id, on PostgreSQL the id is already a hex string (`IdBinding`).
  So on PostgreSQL the key accidentally matches, on the others it never does, and `fetchFromDatabase()` runs one query per entity and language although the prefetch loaded them.
- The product lookups on the key `id_<binary version>` miss on the three binary engines (log: 100 `fetchFromDatabase` calls for the 50 creates and 50 updates, key `version_id` still binary).

Fix (`write=key`): decode with `getFields()->getByStorageName()` when the property lookup fails.
Result on S4: statements 371 to 121 on MySQL and MariaDB, output equals the DAL.
It is a bug in trunk, independent of the ORM question, see core findings.

Measured gains of C1 and W1 are in the lever table of the timing section.

## Lever A1: min and max fused into one statement

Change: `DalV2/Read/StatsFusionAggregator.php` (86 lines, a wrapper around the aggregator, no DAL class copy).
A `MinAggregation` and a `MaxAggregation` on the same field become one `StatsAggregation` that selects both, and the two results are filled from it.
Verify: equals the DAL on S1, S3 and S5 on all four engines.
Effect: the statement count of S3 goes from 7 to 6, S1 and S5 save no statement.
BC: internal, additive (no change to the criteria API).

## Lever R3: DTO projections through partial loading

Change: `DalV2/Projection/` (Path 23, Projector 105, four DTOs 121 lines, the scenario glue 203 lines).
A DTO names its source per constructor parameter with `#[Path('manufacturer.name')]`.
The projector turns the paths into `Criteria::addFields()`, runs the normal repository search and builds the DTO from the resulting `PartialEntity` objects.
Translated and inherited values come out resolved, because the DAL resolves them while loading.
There is no new SQL path: the same reader runs, it only selects the listed fields.

Verified findings while building it:

- A variant that inherits `prices` or other to-many associations from its parent only gets them in partial mode if `parentId` is among the requested fields.
  Without it the S2 projection returned an empty `prices` list.
  With `#[Path('parentId')]` in the DTO, S2 equals the DAL on all four engines.
  The inherited to-many fallback of `EntityReader` reads `parentId` from the loaded entity, so a projection of an inheritance aware entity has to include it.
  This is a trap for every partial read of a variant, independent of the ORM question, see core findings.
- Verify: `--verify` with `proj=1` equals the DAL on S1, S2, S3 and S5 on MySQL, MariaDB, PostgreSQL and SQLite.

BC: additive.
An existing criteria without `addFields()` behaves as before.

## Lever R1: read shape (join and batch)

R1 changes how the DAL reads a product page.
It has two options of `DalV2Implementation`, each a copy of the DAL classes (the DAL classes themselves are untouched).

- `shape=join` rewrites the derived-table translation subselects into direct `LEFT JOIN`s per language with `COALESCE`.
  `FlatTranslationQueryBuilder` (91 lines) overrides `getTranslationQueryBuilder()` of the DAL query builder, so reader and searcher both get it, plus 10 changed lines in `WindowCountSearcher` (the copy of `EntitySearcher`) to switch it on.
- `shape=batch` skips the depth-0 to-one joins of the product (manufacturer, unit, cover, tax, delivery time) and reads them afterwards with one `WHERE id IN (...)` statement per association.
  It is `ShapeEntityReader`, a copy of `EntityReader` with about 130 changed lines, of which about 100 are `isBatched()` and `loadBatchedToOne()`.
- `shape=join+batch` does both.

BC label: internal.
No public signature changes; the SQL text changes (the aliases of the derived translation tables disappear) and with `batch` the statement count of S1, S2, S3 and S5 goes from 4/5/7/4 to 8/10/11/8.
Partial loading, associations below the root, extensions, self references and to-one associations without a foreign key field on the entity are not batched and still use the joins.

The SQL was captured per engine with `sqllog=<file>` (a wrapper around the driver connection that writes SQL, parameters and timing as JSONL, `Capture/`), so the plans below run the exact statements the DAL sends (after the engine's translator).

### Verify

`shape=join`, `shape=batch` and `shape=join+batch` pass `--verify` for S1 to S5 on MySQL, MariaDB, PostgreSQL and SQLite.
The timing block repeated the verify for both shape configs with the levers on every engine (24 verify runs, all five scenarios equal to the DAL).

### Plans

Main read of S1 (S2, S3 and S5 show the same picture, see `scripts/orm-spike-r1-plans.sh`).
Plan nodes are counted per engine (MySQL `->` lines, MariaDB `table` blocks, PostgreSQL nodes, SQLite plan rows), so compare within an engine.
Execution is the top node's actual time on MySQL and MariaDB, `Execution Time` on PostgreSQL and a timed run of the statement on SQLite.
Median of 7 runs.

| Engine | Shape | S1 joins | derived tables | plan nodes | planning ms | execution ms |
|---|---|---|---|---|---|---|
| mysql | default | 19 | 6 | 56 | n/a | 0.443 |
| mysql | join | 19 | 0 | 56 | n/a | 0.355 |
| mysql | batch | 5 | 2 | 16 | n/a | 0.216 |
| mysql | join+batch | 5 | 0 | 16 | n/a | 0.243 |
| mariadb | default | 19 | 6 | 20 | 0.485 | 0.33 |
| mariadb | join | 19 | 0 | 20 | 0.299 | 0.336 |
| mariadb | batch | 5 | 2 | 6 | 0.349 | 0.306 |
| mariadb | join+batch | 5 | 0 | 6 | 0.132 | 0.172 |
| postgresql | default | 19 | 6 | 50 | 3.592 | 1.508 |
| postgresql | join | 19 | 0 | 52 | 3.948 | 1.957 |
| postgresql | batch | 5 | 2 | 11 | 0.718 | 0.358 |
| postgresql | join+batch | 5 | 0 | 11 | 0.707 | 0.414 |
| sqlite | default | 19 | 6 | 38 | n/a | 16.526 |
| sqlite | join | 19 | 0 | 20 | n/a | 1.292 |
| sqlite | batch | 5 | 2 | 12 | n/a | 14.672 |
| sqlite | join+batch | 5 | 0 | 6 | n/a | 0.658 |

- MySQL and MariaDB already merge the derived translation tables: `shape=join` leaves the plan the same size (56 and 20 nodes), execution does not move and MariaDB's optimizer time drops from 0.49 to 0.30 ms.
- PostgreSQL flattens them as well (50 against 52 nodes); `shape=join` does not shorten planning (3.6 ms against 3.9 ms, execution 1.5 against 2.0 ms).
- `shape=batch` shrinks the main statement from 19 to 5 joins and PostgreSQL planning from 3.6 to 0.7 ms; the four extra statements are narrow primary key reads.
- SQLite materializes each derived translation table (6 materialize steps in the plan); the flat join removes them, and the main read goes from 16.5 to 1.3 ms.

Planning share on PostgreSQL (`EXPLAIN (ANALYZE)` of every statement of one scenario run, sum of the median over 5 runs, without the plan cache of doc 22):

| Scenario | Planning ms | Execution ms | Planning share |
|---|---|---|---|
| S1 | 7.2 | 4.6 | 61 percent |
| S2 | 3.8 | 0.9 | 80 percent |
| S3 | 8.4 | 44.0 | 16 percent |
| S5 | 6.4 | 30.6 | 17 percent |

With `shape=join+batch` the planning sum drops to 4.5, 1.9, 6.1 and 3.4 ms.
These are server side numbers, the timings below include the PHP side.

### Detail read probe

The storefront product detail request of core finding 9 is not reproduced: the `orm-spike:bench` harness has the reads S1 to S5 but no storefront page request, and the page measurements of docs 22 and 25 come from the lane databases, which this work does not touch.
The S1 main read has the same structure (19 joins: parent self-join, to-one associations, 6 translation subqueries instead of 9) and is measured in its place; its PostgreSQL planning of 3.4 to 3.9 ms matches the 5 ms warm figure of the finding.

### Timings

One block under the lock letter R, other lanes stopped (48 containers), `--scenario=all --iterations=50 --warmup=5`, `APP_ENV=prod`, one `--output-dir` per engine and config (`/tmp/r1-results/orm-spike-r1/bench/<engine>/c<n>`).
The host load average stayed at 7.6 to 10.0 (1 minute) during the block even with the lanes stopped (start 9.99, MySQL 9.99, MariaDB 8.11, PostgreSQL 9.59, SQLite 7.63, end 8.53), so the noise note applies: "DAL v2 untouched" differs from the DAL by up to 20 percent here, and gains below that are not claimed.

MySQL 8.4, median ms (statements per run):

| Config | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| DAL | 12.5 (4) | 6.0 (5) | 57.3 (7) | 97.0 (371) | 30.2 (4) |
| DAL v2 default | 13.6 (4) | 7.0 (5) | 62.7 (7) | 120.6 (371) | 32.0 (4) |
| `shape=join` | 13.7 (4) | 7.1 (5) | 60.2 (7) | 95.3 (371) | 30.0 (4) |
| `shape=batch` | 11.9 (8) | 6.6 (10) | 59.1 (11) | 98.5 (371) | 29.4 (8) |
| `shape=join+batch` | 11.6 (8) | 6.1 (10) | 58.1 (11) | 98.5 (371) | 31.2 (8) |
| levers `count=window agg=stats write=key+upd proj=1` | 5.1 (2) | 2.6 (5) | 33.3 (4) | 57.4 (23) | 14.2 (2) |
| `shape=join+batch` with the levers | 7.3 (2) | 5.8 (5) | 33.9 (4) | 54.1 (23) | 13.3 (2) |

MariaDB, median ms (statements per run):

| Config | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| DAL | 10.8 (4) | 6.1 (5) | 44.4 (7) | 97.1 (371) | 30.3 (4) |
| DAL v2 default | 12.0 (4) | 7.6 (5) | 48.8 (7) | 106.9 (371) | 30.1 (4) |
| `shape=join` | 11.5 (4) | 6.5 (5) | 47.4 (7) | 101.8 (371) | 30.5 (4) |
| `shape=batch` | 10.7 (8) | 5.7 (10) | 43.0 (11) | 109.4 (371) | 33.8 (8) |
| `shape=join+batch` | 14.6 (8) | 7.8 (10) | 47.9 (11) | 114.0 (371) | 31.8 (8) |
| levers `count=window agg=stats write=key+upd proj=1` | 5.5 (2) | 2.9 (5) | 27.4 (4) | 59.0 (23) | 14.0 (2) |
| `shape=join+batch` with the levers | 3.8 (2) | 2.1 (5) | 22.1 (4) | 55.8 (23) | 15.3 (2) |

PostgreSQL, median ms (statements per run):

| Config | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| DAL | 22.5 (4) | 11.6 (5) | 60.8 (7) | 91.6 (123) | 43.5 (4) |
| DAL v2 default | 22.0 (4) | 14.0 (5) | 60.0 (7) | 82.8 (123) | 40.9 (4) |
| `shape=join` | 24.2 (4) | 14.0 (5) | 70.0 (7) | 83.8 (123) | 42.4 (4) |
| `shape=batch` | 18.8 (8) | 9.5 (10) | 59.5 (11) | 88.7 (123) | 35.1 (8) |
| `shape=join+batch` | 16.4 (8) | 9.0 (10) | 59.7 (11) | 83.9 (123) | 38.9 (8) |
| levers `count=window agg=stats write=key+upd proj=1` | 11.1 (2) | 6.2 (5) | 40.2 (4) | 88.1 (123) | 17.2 (2) |
| `shape=join+batch` with the levers | 9.9 (2) | 5.7 (5) | 36.3 (4) | 90.9 (123) | 20.1 (2) |

SQLite, median ms (statements per run):

| Config | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| DAL | 69.5 (4) | 18.5 (5) | 144.6 (7) | 376.4 (371) | 73.7 (4) |
| DAL v2 default | 64.0 (4) | 17.2 (5) | 124.6 (7) | 363.5 (371) | 62.6 (4) |
| `shape=join` | 35.0 (4) | 5.7 (5) | 102.9 (7) | 351.2 (371) | 38.9 (4) |
| `shape=batch` | 64.9 (8) | 18.1 (10) | 135.6 (11) | 374.8 (371) | 64.0 (8) |
| `shape=join+batch` | 35.6 (8) | 5.3 (10) | 101.9 (11) | 370.1 (371) | 38.7 (8) |
| levers `count=window agg=stats write=key+upd proj=1` | 34.6 (2) | 10.9 (5) | 69.0 (4) | 314.3 (23) | 23.6 (2) |
| `shape=join+batch` with the levers | 16.0 (2) | 1.5 (5) | 46.8 (4) | 323.3 (23) | 17.5 (2) |

Gain against DAL v2 default of the same block:

- MySQL and MariaDB: nothing outside the noise for `join`, `batch` or `join+batch` (all within 20 percent in both directions, MariaDB `join+batch` S1 is 22 percent slower).
- PostgreSQL: `batch` and `join+batch` lower S1 by 15 and 25 percent and S2 by 32 and 36 percent; S3 is unchanged and S5 moves 5 to 14 percent (inside the noise).
  `join` alone does nothing (S3 is 17 percent slower, inside the noise).
  This matches the planning share (S1 61 percent, S2 80 percent, S3 and S5 about 17 percent).
  It is measured without the plan cache; with the plan cache of doc 22 the planning part is mostly gone, so the PostgreSQL gain would be smaller, which was not measured here.
- SQLite: `join` and `join+batch` lower S1 by 45 percent, S2 by 67 percent, S3 by 17 percent (inside the noise) and S5 by 38 percent; `batch` alone does nothing.
- With the other levers on top (`join+batch` with levers against levers only): SQLite S1 34.6 to 16.0 ms, S2 10.9 to 1.5 ms, S3 69.0 to 46.8 ms, S5 23.6 to 17.5 ms; PostgreSQL S1 11.1 to 9.9 ms and S2 6.2 to 5.7 ms (inside the noise), S5 17.2 to 20.1 ms (slower, inside the noise); MySQL S1 and S2 are slower with the shape (7.3 against 5.1 and 5.8 against 2.6 ms) and MariaDB S1 is faster (3.8 against 5.5 ms), which contradicts the neutral results without levers, so I read them as noise of a 2 to 7 ms call.
- S4 does not read through R1 and does not move.

Reading: the statement shape only matters where the engine's planner does not already flatten the derived tables.
On MySQL and MariaDB it does not matter, on PostgreSQL only the batched read helps (through planning time) and on SQLite the flat join is the fix.
`shape=batch` costs four more statements per request; the saved planning pays for them on PostgreSQL only.

## Lever R2: compiled hydrators, not built

Hydration is at most 14.8 percent of the wall time (S1 on MariaDB) and at most 7 percent in all other cells of the profile table above.
Compiling hydrators cannot remove more than that share, so it was not built.

## SQL hygiene: core findings 2, 6, 14, 27

Checked in the code of `poc/orm-spike` (which contains the `poc/db-independent` work):

| Row | Topic | State on the branch |
|---|---|---|
| 2 | `ONLY_FULL_GROUP_BY` | Fixed for PostgreSQL only: `makeSelectValidForGroupBy()` wraps selects in `any_value()`, called in `EntityReader` and `EntitySearcher` only when the platform is PostgreSQL. `MySQLFactory` still removes `ONLY_FULL_GROUP_BY` from the session `sql_mode` on MySQL and MariaDB. |
| 6 | MySQL session variables for the per-parent limit | Fixed for PostgreSQL and SQLite through `SqlDialect::rowNumberPerPartition()`. `MySqlDialect` returns `null`, so MySQL and MariaDB still run `@n:=IF(...)` and `SET @n = 0, @c = null`. |
| 14 | NULL sort order | PostgreSQL emulates MySQL (`SqlDialect::sortDirectionWithMySqlNulls()`, `DESC NULLS LAST`, `ASC NULLS FIRST`). MySQL and MariaDB do not state the order, the DAL still relies on the MySQL default. |
| 27 | Untyped float and int binding | Not fixed in the DAL. SQLite is covered by the middleware `Sqlite/TextBindingStatement` (prepares again with `CAST(? AS REAL)` for float parameters). `SqlQueryParser` and `CriteriaQueryBuilder` still bind untyped. |

Not changed in DAL v2: these are fixes inside DAL classes and each is a core change, not a lever of this spike.

## DX results

### X1: attribute entities as the single source of truth

The core already has the attribute entity machinery (`Attribute/Entity`, `Field`, `PrimaryKey`, `OneToMany`, `ManyToOne`, `ManyToMany`, `Translations`, `Inherited`, `Version`, `ReferenceVersion`, `CustomFields`, `SearchRanking`, `ForeignKey`, `ListField`, `Serialized` and others) and compiles them into definitions in `AttributeEntityCompiler`.
The only registration is the service tag `shopware.entity` (one line per class in `dalv2.php`).
Two spike entities were written this way and run through the real repositories on all four engines: `Attr/SpikeNote.php` (31 lines) and `Attr/SpikePluginNote.php` (41 lines, with an association to `product`, a foreign key and a reference version).

Size of the classic definitions of the slice (lines, from the files; definition plus entity plus collection):

| Entity | Classic classes | Lines |
|---|---|---|
| `product_manufacturer` | Definition 73, Entity 105, Collection 38 | 216 |
| `product_manufacturer_translation` | 58, 89, 51 | 198 |
| `product_price` | 83, 78, 49 | 210 |
| `product_translation` | 76, 215, 51 | 342 |
| `product_category` | Definition 51 | 51 |
| `product` | 320, 1390, 30 | 1740 |

For comparison the existing attribute entity `MeasurementSystemEntity` (translations, one-to-many, custom fields) is 56 lines in one class.
The slice entities themselves were not rewritten as attribute classes: the real entity names cannot be registered twice, and spike copies on copied tables were not built.
So no line count is claimed for an attribute version of the slice.

What the attribute set cannot express for `product`, verified by reading `AttributeEntityCompiler`: its type map has no `ParentFkField`, `ParentAssociationField`, `ChildrenAssociationField`, `ChildCountField`, `ManyToManyIdField`, `VariantListingConfigField` and `NumberRangeField`, all of which `ProductDefinition` uses.
Entity extensions (the definition level extension point) have no attribute counterpart in the compiler either.
`Inherited`, `Version`, `ReferenceVersion`, `CustomFields` and `Translations` are available.

### X2: typed criteria

Existing PHPStan rules: `src/Core/DevOps/StaticAnalyze/PHPStan/Rules` has no rule that checks a `Criteria` field path (checked by listing the directory and searching it for criteria).
Prototype: `DalV2/Typed/FieldPathChecker.php` (79 lines) resolves a path such as `manufacturer.translations.name` against the registered definitions, through associations and translated fields.
Probe `fieldPaths` (command `orm-spike:dalv2-probes`): 7 valid paths accepted, 5 typos rejected with the failing segment named (for example `"nam" is not a field of product_manufacturer`), 1025 paths generated for `product` at depth 2.
The check runs on MariaDB and PostgreSQL (the check reads definitions only, no SQL).

Limits found:

- `Criteria` carries no entity type, so a PHPStan rule can only know the entity at a `->search($criteria)` call on a typed repository, not where the filter literal is written.
- Some paths exist only on a definition variant: `cheapestPrice` is a field of `SalesChannelProductDefinition`, not of `product`, and the checker correctly rejects it on `product`.
- A rule was not written, only the checker that such a rule would call.

### X3: the `spike_note` walkthrough

DAL v2 with an attribute entity (verified by probe `dx` on all four engines):

1. One class, `Attr/SpikeNote.php`: 31 lines with id, title and body, attributes only.
2. Table: the probe creates it with one `CREATE TABLE`; in a real plugin that is one migration like today.
3. Registration: one `shopware.entity` tag line, no definition, no collection, no repository class (the service `spike_note.repository` exists automatically).
4. CRUD through that repository: create, search, update, delete, with the entity class as a typed struct.
5. Classic DAL for comparison (existing small entity `Tag`, from the Doctrine doc): 253 lines in three classes plus a service definition.

The search returned instances of the attribute class `SpikeNote` itself.

## Probes of doc 29

Command: `orm-spike:dalv2-probes` (versioning, dx, pluginAssociation, fieldPaths) plus the S1 to S5 verify runs.
All run on MySQL, MariaDB, PostgreSQL and SQLite.

| Probe | Result | Detail | Changed by a lever |
|---|---|---|---|
| Translations with fallback | PASS | S1 and S2 verify equal the DAL, also with all levers and with `proj=1` | R3 resolves translated values through the DAL, no change in result |
| Variant inheritance | PASS | S1 and S2 verify | R3: `parentId` has to be requested for inherited to-many associations (see R3) |
| Versioning | PASS | `createVersion`, update in the draft, live 1 and draft 2, `merge`, live is 2 | none (the write levers are off in the probe) |
| Plugin adds an association (new table, new class) | PASS | `SpikePluginNote` with `product` association, filter on `product.id`, partial loading with `product.productNumber` equals the full entity | R3: partial loading works on a plugin entity |
| Plugin adds a field to a core entity (entity extension) | not exercised | needs a registered `EntityExtension`, which would change the DAL for the other lanes of the same instance | not applicable |
| App custom entity at runtime | not exercised | needs an app lifecycle with `custom_entity`, not part of the seeded data set | not applicable |
| Criteria from JSON | PASS | S5 verify (request criteria builder) on all engines, also with `proj=1` | R3 and C1 verified equal |
| Ids on four engines | PASS | all verify runs use the engine specific binding (`IdBinding`) | W1 key fix is a consequence of the binary id decoding (W1a) |

## Timings

Block: handoff V under `/tmp/wave8-timing.lock`, `orm-spike:bench --iterations=50 --warmup=5`, `APP_ENV=prod`, one scenario per run, per engine in the order DAL, DBAL, DAL v2 untouched, each lever alone, safe subset, all levers.
Other lanes stopped: yes (43 containers of other lanes stopped, restored afterwards, the lock removed).
Host load average at the start of each engine (1, 5, 15 minutes): MySQL 9.01 6.24 5.63, MariaDB 5.94 6.02 5.60, PostgreSQL 8.68 6.90 5.99, SQLite 10.13 8.29 6.68.
The 1 minute value contains the bench of the previous engine.
Noise: "DAL v2 untouched" runs the same code as the DAL and differs from it by up to 20 percent (MySQL S1: 11.33 against 9.08 ms), so differences below that are not claimed as gains.

Option sets: safe subset = `count=window agg=stats write=key+upd` (no projections, the result shape stays the DAL's); all levers = safe subset plus `proj=1`.
The subset was chosen before the measurement because projections change the result type.

Median / p95 in ms:

| Engine | Scenario | DAL | DBAL | DAL v2 untouched | DAL v2 safe subset | DAL v2 all levers |
|---|---|---|---|---|---|---|
| MySQL | S1 | 11.33 / 14.05 | 2.42 / 2.94 | 9.08 / 12.26 | 8.27 / 8.62 | 3.38 / 4.52 |
| MySQL | S2 | 6.19 / 7.74 | 0.49 / 0.58 | 4.96 / 5.88 | 4.47 / 4.95 | 1.84 / 2.12 |
| MySQL | S3 | 55.90 / 59.00 | 14.12 / 15.01 | 49.89 / 62.75 | 37.69 / 43.53 | 31.20 / 38.42 |
| MySQL | S4 | 81.62 / 115.98 | 6.12 / 7.11 | 88.55 / 112.24 | 53.97 / 68.54 | 54.36 / 62.14 |
| MySQL | S5 | 22.77 / 31.21 | 17.84 / 21.51 | 25.72 / 29.27 | 16.16 / 19.15 | 12.27 / 13.31 |
| MariaDB | S1 | 10.77 / 11.99 | 2.67 / 3.49 | 8.07 / 11.24 | 8.77 / 10.40 | 4.81 / 5.87 |
| MariaDB | S2 | 5.04 / 5.81 | 0.57 / 0.75 | 4.64 / 6.30 | 4.87 / 6.51 | 2.60 / 3.18 |
| MariaDB | S3 | 39.87 / 43.99 | 20.25 / 28.59 | 39.70 / 47.66 | 30.48 / 39.00 | 26.35 / 32.56 |
| MariaDB | S4 | 92.43 / 125.25 | 7.11 / 8.42 | 90.40 / 109.38 | 55.17 / 74.39 | 54.76 / 68.35 |
| MariaDB | S5 | 28.40 / 52.00 | 17.98 / 19.61 | 25.20 / 29.52 | 18.75 / 25.54 | 13.88 / 14.63 |
| PostgreSQL | S1 | 22.26 / 23.87 | 33.49 / 35.51 | 22.69 / 32.24 | 19.91 / 21.01 | 10.23 / 11.58 |
| PostgreSQL | S2 | 11.99 / 13.53 | 3.27 / 4.10 | 11.59 / 14.21 | 12.92 / 14.98 | 5.74 / 6.90 |
| PostgreSQL | S3 | 74.64 / 84.54 | 34.41 / 41.45 | 71.55 / 89.74 | 56.84 / 61.00 | 36.29 / 45.16 |
| PostgreSQL | S4 | 87.74 / 120.66 | 13.37 / 20.84 | 78.47 / 93.33 | 86.74 / 96.57 | 87.71 / 113.73 |
| PostgreSQL | S5 | 41.88 / 45.49 | 31.08 / 43.89 | 36.70 / 42.56 | 26.83 / 28.04 | 17.54 / 17.92 |
| SQLite | S1 | 63.92 / 85.46 | 20.17 / 22.37 | 61.46 / 63.97 | 45.71 / 48.37 | 37.63 / 44.88 |
| SQLite | S2 | 16.35 / 18.12 | 0.28 / 0.51 | 16.56 / 17.44 | 17.22 / 19.92 | 10.32 / 11.14 |
| SQLite | S3 | 133.69 / 180.37 | 18.49 / 20.03 | 129.22 / 137.48 | 78.12 / 83.38 | 70.72 / 75.48 |
| SQLite | S4 | 323.06 / 413.99 | 6.04 / 12.19 | 329.71 / 356.25 | 323.70 / 451.75 | 296.41 / 348.74 |
| SQLite | S5 | 64.57 / 68.29 | 13.03 / 13.79 | 61.49 / 67.48 | 44.97 / 55.77 | 22.54 / 23.51 |

Lever table (median ms, statements per call in brackets; `-` means the lever does not apply to that scenario):

| Engine | Scenario | DAL v2 untouched | C1 window count | A1 stats fusion | R3 projections | W1 key | W1 upd | W1 key+upd |
|---|---|---|---|---|---|---|---|---|
| MySQL | S1 | 9.08 (4) | 7.49 (3) | 8.42 (4) | 4.82 (3) | - | - | - |
| MySQL | S2 | 4.96 (5) | - | - | 2.70 (5) | - | - | - |
| MySQL | S3 | 49.89 (7) | 42.56 (6) | 42.00 (6) | 50.52 (6) | - | - | - |
| MySQL | S4 | 88.55 (371) | - | - | - | 60.60 (121) | 76.20 (273) | 49.33 (23) |
| MySQL | S5 | 25.72 (4) | 15.77 (3) | 25.61 (4) | 23.75 (3) | - | - | - |
| MariaDB | S1 | 8.07 (4) | 7.63 (3) | 7.38 (4) | 6.79 (3) | - | - | - |
| MariaDB | S2 | 4.64 (5) | - | - | 3.70 (5) | - | - | - |
| MariaDB | S3 | 39.70 (7) | 30.76 (6) | 31.71 (6) | 38.07 (6) | - | - | - |
| MariaDB | S4 | 90.40 (371) | - | - | - | 59.05 (121) | 83.62 (273) | 57.81 (23) |
| MariaDB | S5 | 25.20 (4) | 17.86 (3) | 28.90 (4) | 26.81 (3) | - | - | - |
| PostgreSQL | S1 | 22.69 (4) | 16.06 (3) | 20.03 (4) | 12.90 (3) | - | - | - |
| PostgreSQL | S2 | 11.59 (5) | - | - | 6.15 (5) | - | - | - |
| PostgreSQL | S3 | 71.55 (7) | 41.09 (6) | 61.75 (6) | 66.12 (6) | - | - | - |
| PostgreSQL | S4 | 78.47 (123) | - | - | - | 90.68 (123) | 98.28 (123) | 96.14 (123) |
| PostgreSQL | S5 | 36.70 (4) | 24.46 (3) | 41.94 (4) | 32.70 (3) | - | - | - |
| SQLite | S1 | 61.46 (4) | 45.09 (3) | 61.56 (4) | 50.44 (3) | - | - | - |
| SQLite | S2 | 16.56 (5) | - | - | 11.55 (5) | - | - | - |
| SQLite | S3 | 129.22 (7) | 108.41 (6) | 97.76 (6) | 121.15 (6) | - | - | - |
| SQLite | S4 | 329.71 (371) | - | - | - | 316.22 (121) | 315.56 (273) | 345.53 (23) |
| SQLite | S5 | 61.49 (4) | 41.91 (3) | 61.10 (4) | 44.46 (3) | - | - | - |

Reading the numbers:

- W1 on S4: key fix plus update batching take MySQL from 88.55 to 49.33 ms and MariaDB from 90.40 to 57.81 ms, statements 371 to 23.
  The key fix alone gives 60.60 and 59.05 ms (371 to 121 statements), the update batching alone 76.20 and 83.62 ms (371 to 273).
- W1 on PostgreSQL does nothing: statements stay at 123 and the median at 78 to 98 ms.
  The key bug does not exist there (W1a) and the unchanged statement count shows that the batched update did not engage there.
  The code fell back to per-row updates whenever a changed column on PostgreSQL was not an integer (`WriteGatewayV2` lines 586 to 590).
  Correction (doc 36): the reason given for that fallback, that PostgreSQL types an untyped `CASE` as text, is wrong.
  The PoC translator read the bare column reference in `ELSE "stock"` as a MySQL string literal and turned it into `ELSE 'stock'`; with table-qualified column references the batched update runs on PostgreSQL without casts.
- W1 on SQLite: statements go from 371 to 23, the median does not move (329.71 against 296.41 to 345.53 ms).
  The re-run profile of SQLite S4 shows 76.5 percent of the time in SQL, and the one `UPDATE product` statement (50 rows per run) accounts for 249.9 ms per run, about 5 ms per row.
  Why one row of that update costs 5 ms on SQLite was not found.
- C1 (window count) on S5: MySQL 25.72 to 15.77 ms, MariaDB 25.20 to 17.86, PostgreSQL 36.70 to 24.46, SQLite 61.49 to 41.91.
  S3: MySQL 49.89 to 42.56, MariaDB 39.70 to 30.76, PostgreSQL 71.55 to 41.09, SQLite 129.22 to 108.41.
- A1 (stats fusion) alone shows no gain outside the noise on S1 and S5 (statement count unchanged); on S3 the count drops by one statement.
- R3 (projections) on S1 and S2, the scenarios with real hydration and reader PHP share: MySQL S1 9.08 to 4.82 ms, S2 4.96 to 2.70; MariaDB S1 8.07 to 6.79, S2 4.64 to 3.70; PostgreSQL S1 22.69 to 12.90, S2 11.59 to 6.15; SQLite S1 61.46 to 50.44, S2 16.56 to 11.55.
  On S3 and S5 (SQL dominated) projections give nothing measurable.
- All levers against the DAL: S1 11.33 to 3.38 ms on MySQL (DBAL 2.42), S2 6.19 to 1.84 (DBAL 0.49), S5 22.77 to 12.27 (DBAL 17.84, below it), S3 55.90 to 31.20 (DBAL 14.12), S4 81.62 to 54.36 (DBAL 6.12).
  DAL v2 does not reach DBAL on S3 and S4.
  S4 remains 9 times DBAL on MySQL with 23 statements, so the rest is writer PHP and events (58 percent of S4 in the profile is writer PHP).

## Lever summary

| Lever | Gain | Lines | BC label | Rough effort for the core (estimate) |
|---|---|---|---|---|
| C1 window count | S3 and S5 about 15 to 45 percent on all four engines | 33 changed lines in a copy of `EntitySearcher` | internal | days, needs the count fallback tests per engine |
| A1 stats fusion | one statement less on S3, no measured gain | 86 | internal, additive | days |
| R3 projections | S1 and S2 about 15 to 50 percent, nothing on S3 and S5 | 128 for the mechanism, 121 for the DTOs | additive | one to two weeks to cover more entities and the `parentId` rule |
| W1a key fix | S4 on MySQL, MariaDB and SQLite 371 to 121 statements | about 5 lines in `getCurrentState` | internal bug fix | hours, plus a regression test |
| W1b update batching | S4 371 to 23 statements on MySQL and MariaDB, no effect on PostgreSQL and SQLite time | about 130 changed lines in a copy of the gateway | internal | one to two weeks (events, tests; no casts needed on PostgreSQL, doc 36) |
| R1 read shape | `join`: SQLite S1 45, S2 67, S5 38 percent, nothing on MySQL, MariaDB, PostgreSQL; `batch`: PostgreSQL S1 15 to 25, S2 32 to 36 percent, nothing on MySQL, MariaDB, SQLite | about 91 (flat join builder) plus about 130 (reader copy) plus 10 | internal | one to two weeks (translation join in `QueryBuilder`, to-one batching with its exceptions, tests per engine), judgement |
| R2 compiled hydrators | at most the hydration share (3 to 15 percent) | not built | internal | not justified by the profile |

The effort column is an estimate from the size of the changes, not a measurement.

## Follow-up from the final timing block (doc 34)

The final block in `docs/34-orm-spike-final-timings.md` measured DAL v2 next to both ORMs under one load state; the open items for DAL v2 it adds:

- Writes are the weak spot: DAL v2 with all levers is slower on S4 than optimized Doctrine and optimized Cycle on every engine (MySQL 57.49 against 43.48 and 52.29 ms, PostgreSQL 89.15 against 57.22 and 59.07 ms), although it sends 23 statements against about 350.
  Doc 35 gave the ORM and DBAL paths the same validation, write protection and written events as the DAL: the contract costs them a few ms and the gap stays, so the remaining cost is writer PHP (58 to 59 percent of S4 in the profile above; events alone are 1.1 to 1.5 percent).
- SQLite: Cycle writes the 50 products in 16.86 ms with 350 statements, DAL v2 needs 287.10 ms with 23, so the 5 ms per row of the `UPDATE product` above is not a property of SQLite itself; the cause is still not found and is the first thing to check (statement shape of the DAL update, the `TextBindingStatement` middleware, transaction handling).
- PostgreSQL: the batched update does not engage (123 statements, as the DAL).
  A spike run of the batched update on PostgreSQL failed with `column "stock" is of type integer but expression is of type text`.
  Correction (doc 36): this was not `CASE` typing but the PoC translator turning `ELSE "stock"` into the string `ELSE 'stock'`; with table-qualified column references the batched update engages on PostgreSQL without casts.
- Not exercised for DAL v2 and still open: the plugin field probe on a core entity and the app custom entity probe.

## What DAL v2 keeps solving and what it removes

Kept from the 2019 decision against an ORM (all verified by the probes): translations with fallback, variant inheritance, versioning with merge, plugin extension through new entities, `EntityWrittenEvent` and the criteria from JSON, on all four engines.
Removed or reduced: the per-entity classes for new entities (attribute entity, 31 lines for `spike_note`), the 250 lookups of the existing write path on three engines (a bug), one count statement per paginated search, and the hydration overhead of list and detail reads when a projection is used.
Not removed: field path typos in criteria (only the checker prototype), the gap to DBAL on S3 and S4, and the writer PHP share of S4.
