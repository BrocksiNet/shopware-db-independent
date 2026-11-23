# Wave 8 V: DAL v2, the DAL kept and improved

Handoff V of wave 8.
Question: how far do targeted changes to the existing DAL get, measured on the same slice and the same four databases as Doctrine (doc 31) and Cycle?
Harness and scenarios S1 to S5: [docs/30](30-orm-spike-baseline.md).
Candidate description: [docs/29](29-orm-alternatives.md), section "Candidate 3: DAL v2".

Code: `instance/src/Core/Framework/OrmSpike/DalV2/` on the instance branch `poc/orm-spike`.
No DAL class was edited.
Where a lever needs a changed DAL class the class is copied into `DalV2/` and named as a copy below.

## Status

This document is written lever by lever.
Sections marked "pending" are filled in when the lever is built and measured.

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
  The difference is 248 single row `SELECT 1 as exists ...` lookups: 150 on `product_translation`, 100 on `product` (and a few on other tables).
- S3 runs the id statement, a separate `SELECT COUNT(*) FROM (<same query>)` and one statement per aggregation (min, max, terms) next to the association reads.

## Lever C1: exact total from a window count

pending measurements.

Change: `DalV2/Read/WindowCountSearcher.php` is a copy of `Dbal/EntitySearcher.php` (DAL class copy).
When the criteria ask for an exact total with a limit and no score field, the id statement selects `COUNT(*) OVER() as __total` and the total is taken from the first row.
An empty page with an offset falls back to the old `COUNT(*)` statement, because no row carries the total then.
Verify: `--verify` equals the DAL on S1, S2, S3 and S5 on MySQL, MariaDB, PostgreSQL and SQLite.
BC: internal (searcher implementation, same `IdSearchResult`).

## Lever W1: write path

pending measurements.

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
