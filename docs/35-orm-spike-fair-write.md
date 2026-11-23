# ORM spike: fair write comparison (S4)

Doc 34 compares the DAL with DBAL, Doctrine and Cycle for S4, the bulk write of 50 products.
The DAL does more than the ORM code in that comparison: it validates, checks write protection and dispatches written events.
This document adds "full" variants of DBAL, Doctrine idiomatic, Doctrine optimized, Cycle idiomatic and Cycle optimized that do the same work, and measures them next to the unchanged bare variants.
Code: instance branch `poc/orm-spike`, commit `19d1ef5867e`.
Timing script: `scripts/orm-spike-fair-block.sh`.

## Contract

A full variant has to do the following for the S4 write set, otherwise it is not counted as equivalent.

1. Validation before any write, the whole batch is rejected on the first invalid product.
   The rules are the constraints of the field serializers for the S4 fields: uuid fields (`id`, `taxId`, `currencyId`, `languageId`, category ids, `salesChannelId`) must be valid uuids and not blank, `productNumber` and the translation `name` must be strings, not blank after trim and at most 255 characters, `stock` must be an int, `gross` and `net` must be numeric, `visibility` must be one of 10, 20, 30.
2. The write-protection check of the DAL: every property that is set is checked against the `WriteProtected` flag of the field definition and the scope of the context.
3. One `EntityWrittenEvent` per written entity, collected in an `EntityWrittenContainerEvent` and dispatched through the Shopware event dispatcher in system scope, with the same entity names, primary keys, payloads and existence data as the DAL.
   S4 dispatches two containers, one for the create and one for the stock update.
4. Indexers stay disabled and the live version is used, as in the bare variants.

## What each variant does

The bare variants are unchanged.
The full variants are switched on with `--option full=1`.

| Variant | Validation | Write protection | Events |
|---|---|---|---|
| dal | the DAL (field serializers) | the DAL | the DAL |
| dbal full | `WriteContract::plain()`, plain PHP checks, before the transaction | `WriteContract::assertWritable()` on the row values, before the transaction | both containers built by `WrittenEvents` and dispatched after the commit |
| doctrine full (idiomatic, optimized) | Symfony Validator on the entities, attribute constraints (including the `HexUuid` constraint that reuses the Shopware `UuidValidator`), before the flush | `assertWritable()` on the public properties of every entity | create container after the first flush, update container after the stock update |
| cycle full (idiomatic, optimized) | the same attribute constraints on the Cycle entities, before `run()` | the same | the same |

Doctrine runs the checks inside a guard that clears the entity manager when a check fails, so the failed entities are not flushed later; Cycle needs none.
In both ORMs the checks run before the first statement, so a rejected batch has written nothing.
New code lives in `OrmSpike/Fair/` (`WriteContract`, `WrittenEvents`, `WrittenProduct`, `WriteRejected`, `Constraint/HexUuid`, `FairCheckCommand`) and `OrmSpike/DependencyInjection/fair.php`.

## Equivalence proofs

The command is `orm-spike:fair-check` (`--mode=events|reject|all`), run on all four engines against the `orm_spike` databases.
`--verify` was run for every full variant (scenario all, 1 iteration) on all four engines.

| Engine | `--verify` for the 5 full variants | event comparison (5 variants against dal) | rejection matrix | write protection |
|---|---|---|---|---|
| mysql | S1 to S5 OK | identical | as expected | same as dal |
| mariadb | S1 to S5 OK | identical | as expected | same as dal |
| postgresql | S1 to S5 OK | identical | as expected | same as dal |
| sqlite | S1 to S5 OK | identical | as expected | same as dal |

The `--verify` column is the exit code 0 of every run, with S4 reported as `OK (<impl> equals dal)` in the log.
The check output of the last run is in `/tmp/fair/check-<engine>.txt` (not versioned).

### Events (proof c)

A listener on `EntityWrittenContainerEvent` records the containers of one S4 run per implementation.
For the DAL and each full variant the same two containers arrive: the first with product 50, product_translation 100, product_visibility 50, product_category 100 and category 50 results, the second with product 50 and product_translation 50 results.
Compared per result: entity name, operation, primary key, payload, existence (exists, state, child flags), event class, order of the events and error count.
The comparison reports "identical" for all five variants on all four engines.

Normalized before comparing, so these are not proven equal:

- Date values are compared by class and time zone only, not by value.
- The DAL generates random ids for `product_visibility`, so those ids are replaced by a marker and the visibility is identified by its product id.
- Binary strings are compared as hex.
- On PostgreSQL the DAL puts the primary key columns into `EntityExistence::getState()` of updated rows (`id`, `version_id`), the other engines do not.
  Only the keys `exists`, `parent_id` and `parent` of the state are compared.
  A subscriber that reads the state would see that difference, none of the Shopware code read for this spike does.

### Rejection (proof b)

Each case below is written through the DAL and through each full variant, then the rows of the write set are counted in `product`, `product_translation`, `product_category` and `product_visibility`.
Cases marked product 25 change only the 26th product of the 50, so the batch must be rejected as a whole.

| Case | Expected | Result on all four engines, dal and 5 full variants |
|---|---|---|
| valid write set (control) | written | written, 300 rows |
| taxId blank | rejected | rejected, 0 rows |
| taxId not a uuid | rejected | rejected, 0 rows |
| productNumber of 256 characters (product 25) | rejected | rejected, 0 rows |
| productNumber blank (product 25) | rejected | rejected, 0 rows |
| translation name blank (product 25) | rejected | rejected, 0 rows |
| translation name of 256 characters (product 25) | rejected | rejected, 0 rows |
| product id not a uuid (product 25) | rejected | rejected, 0 rows |
| category id not a uuid (product 25) | rejected | rejected, 0 rows |
| currencyId not a uuid | rejected | rejected, 0 rows |
| salesChannelId not a uuid | rejected | rejected, 0 rows |

Write protection was compared with the DAL for five field and scope combinations: `product.availableStock` in system and user scope (both rejected), `product_translation.descriptionTeaser` in system scope (allowed) and user scope (rejected), `product.stock` in user scope (allowed).
`WriteContract::assertWritable()` gave the same answer as the DAL in all five on all four engines.

## Not equivalent

- A blank `languageId` is not rejected by the DAL: it wrote 250 of 300 rows on all four engines.
  All full variants reject it with 0 rows.
  This case is informational and not part of the pass criteria, the full variants are stricter than the DAL here.
- The validation covers the S4 fields only.
  Other constraints of the DAL (other fields, unique checks, foreign key existence beyond the database constraints) are not reimplemented.
  The 11 cases above are a matrix, not a proof for every possible payload.
- Events are built by hand in `WrittenEvents` to mirror the DAL for this write set.
  Equal for S4 as run here, no claim for other write sets.
- Write protection was compared for five combinations.

## Conditions

Two complete runs of the same block, run 1 from 12:30 to 12:43 and run 2 from 12:47 to 13:00 on 2026-11-23, `APP_ENV=prod`, warm cache, 5 warm-up and 50 measured iterations, `--scenario=S4`, verify (1 iteration, separate call) before the timed runs, one `--output-dir` per configuration, PHP 8.4.17.
All other lanes stopped (48 containers, restarted afterwards, lock removed).
Host load average (1, 5, 15 min) at the start of each engine, run 1: mysql 8.03, 9.92, 11.48; mariadb 8.11, 9.73, 11.32; postgresql 5.66, 8.29, 10.55; sqlite 6.39, 7.91, 10.15.
Run 2: mysql 6.22, 6.72, 8.21; mariadb 4.74, 6.21, 7.93; postgresql 4.73, 5.66, 7.50; sqlite 6.36, 5.86, 7.36.
The load is high for a block with stopped lanes, so compare implementations within an engine and look at both runs.
Configurations 1 to 14 in the order of the tables, options as in doc 34 plus `full=1` for the full variants.
Raw JSON: `/var/www/html/var/orm-spike-fair-bench/` and `/var/www/html/var/orm-spike-fair-bench-2/` inside `instance-web-1`, copies in `/tmp/fair-first/fair-results/` and `/tmp/fair-results-2/` (not versioned).
The profile section used 60 measured iterations after 5 warm-up calls and is not part of the timing block.

## Results

Median ms of S4, the ratio is the median divided by the dal median of the same run, statements per iteration (identical in both runs for every cell), peak memory in MB of run 1.

### mysql

| implementation | ms run 1 | x dal run 1 | ms run 2 | x dal run 2 | statements | MB (run 1) |
|---|---|---|---|---|---|---|
| dal | 86.89 | 1.00 | 81.82 | 1.00 | 371 | 46 |
| dalv2 default | 89.66 | 1.03 | 80.28 | 0.98 | 371 | 47 |
| dalv2 count=window agg=stats write=key+upd | 52.09 | 0.60 | 46.51 | 0.57 | 23 | 47 |
| dalv2 all levers (+proj=1) | 55.47 | 0.64 | 46.85 | 0.57 | 23 | 47 |
| dbal bare | 6.98 | 0.08 | 5.45 | 0.07 | 5 | 26 |
| dbal full | 8.99 | 0.10 | 7.53 | 0.09 | 9 | 39 |
| doctrine idiomatic bare | 53.22 | 0.61 | 45.58 | 0.56 | 450 | 33 |
| doctrine idiomatic full | 77.93 | 0.90 | 46.41 | 0.57 | 454 | 45 |
| doctrine optimized bare | 41.27 | 0.47 | 39.58 | 0.48 | 351 | 33 |
| doctrine optimized full | 47.63 | 0.55 | 34.37 | 0.42 | 355 | 46 |
| cycle idiomatic bare | 45.78 | 0.53 | 32.71 | 0.40 | 350 | 34 |
| cycle idiomatic full | 44.14 | 0.51 | 36.19 | 0.44 | 354 | 46 |
| cycle optimized bare | 39.00 | 0.45 | 34.51 | 0.42 | 350 | 34 |
| cycle optimized full | 40.52 | 0.47 | 38.55 | 0.47 | 354 | 46 |

### mariadb

| implementation | ms run 1 | x dal run 1 | ms run 2 | x dal run 2 | statements | MB (run 1) |
|---|---|---|---|---|---|---|
| dal | 98.68 | 1.00 | 87.96 | 1.00 | 371 | 46 |
| dalv2 default | 92.94 | 0.94 | 94.66 | 1.08 | 371 | 47 |
| dalv2 count=window agg=stats write=key+upd | 53.74 | 0.54 | 52.18 | 0.59 | 23 | 47 |
| dalv2 all levers (+proj=1) | 53.60 | 0.54 | 49.81 | 0.57 | 23 | 47 |
| dbal bare | 6.19 | 0.06 | 6.19 | 0.07 | 5 | 26 |
| dbal full | 8.15 | 0.08 | 8.37 | 0.10 | 9 | 39 |
| doctrine idiomatic bare | 60.36 | 0.61 | 56.46 | 0.64 | 450 | 33 |
| doctrine idiomatic full | 59.54 | 0.60 | 56.52 | 0.64 | 454 | 45 |
| doctrine optimized bare | 43.72 | 0.44 | 39.83 | 0.45 | 351 | 33 |
| doctrine optimized full | 49.16 | 0.50 | 46.61 | 0.53 | 355 | 46 |
| cycle idiomatic bare | 45.49 | 0.46 | 43.90 | 0.50 | 350 | 34 |
| cycle idiomatic full | 54.15 | 0.55 | 50.71 | 0.58 | 354 | 46 |
| cycle optimized bare | 44.16 | 0.45 | 53.46 | 0.61 | 350 | 34 |
| cycle optimized full | 53.86 | 0.55 | 55.24 | 0.63 | 354 | 46 |

### postgresql

| implementation | ms run 1 | x dal run 1 | ms run 2 | x dal run 2 | statements | MB (run 1) |
|---|---|---|---|---|---|---|
| dal | 82.80 | 1.00 | 84.72 | 1.00 | 123 | 47 |
| dalv2 default | 87.98 | 1.06 | 77.70 | 0.92 | 123 | 47 |
| dalv2 count=window agg=stats write=key+upd | 85.12 | 1.03 | 81.62 | 0.96 | 123 | 47 |
| dalv2 all levers (+proj=1) | 87.77 | 1.06 | 84.81 | 1.00 | 123 | 47 |
| dbal bare | 11.74 | 0.14 | 12.54 | 0.15 | 5 | 28 |
| dbal full | 14.88 | 0.18 | 15.66 | 0.18 | 9 | 39 |
| doctrine idiomatic bare | 75.80 | 0.92 | 76.26 | 0.90 | 450 | 34 |
| doctrine idiomatic full | 82.98 | 1.00 | 77.74 | 0.92 | 454 | 46 |
| doctrine optimized bare | 57.70 | 0.70 | 57.76 | 0.68 | 351 | 34 |
| doctrine optimized full | 64.80 | 0.78 | 62.73 | 0.74 | 355 | 46 |
| cycle idiomatic bare | 54.75 | 0.66 | 62.43 | 0.74 | 350 | 35 |
| cycle idiomatic full | 68.88 | 0.83 | 63.27 | 0.75 | 354 | 47 |
| cycle optimized bare | 61.82 | 0.75 | 60.50 | 0.71 | 350 | 35 |
| cycle optimized full | 63.00 | 0.76 | 64.03 | 0.76 | 354 | 47 |

### sqlite

| implementation | ms run 1 | x dal run 1 | ms run 2 | x dal run 2 | statements | MB (run 1) |
|---|---|---|---|---|---|---|
| dal | 328.79 | 1.00 | 330.31 | 1.00 | 371 | 47 |
| dalv2 default | 309.89 | 0.94 | 301.62 | 0.91 | 371 | 47 |
| dalv2 count=window agg=stats write=key+upd | 301.02 | 0.92 | 292.18 | 0.88 | 23 | 47 |
| dalv2 all levers (+proj=1) | 291.22 | 0.89 | 288.70 | 0.87 | 23 | 47 |
| dbal bare | 5.97 | 0.02 | 5.87 | 0.02 | 5 | 28 |
| dbal full | 8.05 | 0.02 | 7.66 | 0.02 | 9 | 39 |
| doctrine idiomatic bare | 199.57 | 0.61 | 196.36 | 0.59 | 450 | 33 |
| doctrine idiomatic full | 207.69 | 0.63 | 194.02 | 0.59 | 454 | 46 |
| doctrine optimized bare | 124.23 | 0.38 | 121.94 | 0.37 | 351 | 34 |
| doctrine optimized full | 132.05 | 0.40 | 126.46 | 0.38 | 355 | 46 |
| cycle idiomatic bare | 16.56 | 0.05 | 16.45 | 0.05 | 350 | 35 |
| cycle idiomatic full | 21.75 | 0.07 | 20.71 | 0.06 | 354 | 47 |
| cycle optimized bare | 17.36 | 0.05 | 16.00 | 0.05 | 350 | 35 |
| cycle optimized full | 21.27 | 0.06 | 21.13 | 0.06 | 354 | 47 |


## What the full contract costs

Full minus bare median in ms, run 1 / run 2.

| implementation | mysql | mariadb | postgresql | sqlite |
|---|---|---|---|---|
| dbal | +2.0 / +2.1 | +2.0 / +2.2 | +3.1 / +3.1 | +2.1 / +1.8 |
| doctrine idiomatic | +24.7 / +0.8 | -0.8 / +0.1 | +7.2 / +1.5 | +8.1 / -2.3 |
| doctrine optimized | +6.4 / -5.2 | +5.4 / +6.8 | +7.1 / +5.0 | +7.8 / +4.5 |
| cycle idiomatic | -1.6 / +3.5 | +8.7 / +6.8 | +14.1 / +0.8 | +5.2 / +4.3 |
| cycle optimized | +1.5 / +4.0 | +9.7 / +1.8 | +1.2 / +3.5 | +3.9 / +5.1 |


DBAL full costs 1.8 to 3.1 ms more than bare on every engine in both runs, it moves from 5 to 9 statements and from 26-28 to 39 MB.
For Doctrine and Cycle the difference ranges from -5.2 to +24.7 ms and changes sign between runs in several cells, so it is within the noise of this host and no cell is lower than bare in both runs.
Every full variant shows 4 more statements than its bare variant (5 to 9, 450 to 454, 351 to 355, 350 to 354, on all four engines).
The MySQL general log of one `dbal` full run shows two webhook lookup selects (columns `webhookId`, `webhookName`, `eventName`) after the commit, which the bare variant does not issue.
That is the only extra work seen in the log and not a second write path, the cause was only checked for DBAL full on MySQL.
Memory grows by 11 to 13 MB for every full variant because the validator and the event classes are loaded.

## DAL v2 S4 profile split

Method as in doc 33: `hrtime` probes, `--option profile=1 --option profile_skip=5`, 60 measured calls, exclusive-time stack.
The wall time is inflated by the probes and only the shares are used.

| engine | wall ms (profile mode) | sql | events | rest (writer PHP incl. validation, serializers) |
|---|---|---|---|---|
| mysql | 102.7 | 39.6% (40.6 ms) | 1.1% (1.16 ms) | 59.3% (60.9 ms) |
| mariadb | 101.5 | 39.6% (40.2 ms) | 1.1% (1.15 ms) | 59.2% (60.1 ms) |
| postgresql | 90.0 | 38.4% (34.6 ms) | 1.5% (1.33 ms) | 60.1% (54.1 ms) |
| sqlite | 354.8 | 76.3% (270.8 ms) | 0.4% (1.30 ms) | 23.3% (82.6 ms) |


The events share of the DAL is 0.4 to 1.5 percent (1.2 to 1.3 ms) on every engine, it is the whole dispatcher time including the webhook lookup listeners.
Validation is not a probe category of the profile, it is part of "rest" (writer PHP: command extraction, serializers, validation, change sets), so a validation share of the DAL is not measured here.
The cost of validation, write protection and events in the ORM paths is the full minus bare difference above, which includes the webhook lookups.

## Conclusion

With the contract in place the ORM variants stay faster than the DAL on MySQL, MariaDB and SQLite, and are close to the DAL on PostgreSQL for Doctrine idiomatic.
Ratio ranges to dal over both runs: MySQL doctrine idiomatic 0.57 to 0.90, doctrine optimized 0.42 to 0.55, cycle idiomatic 0.44 to 0.51, cycle optimized 0.47; MariaDB 0.50 to 0.64 for all four; PostgreSQL doctrine idiomatic 0.92 to 1.00, doctrine optimized 0.74 to 0.78, cycle 0.75 to 0.83; SQLite doctrine idiomatic 0.59 to 0.63, doctrine optimized 0.38 to 0.40, cycle 0.06 to 0.07.
The measured cost of the contract in the ORM variants (about 2 to 3 ms for DBAL, up to about 10 ms for Doctrine and Cycle outside the noisy cells) is small next to the DAL median of 82 to 99 ms (330 ms on SQLite).
DBAL full is 0.02 to 0.18 of the DAL.
DAL v2 with the write levers (`write=key+upd`) reaches 0.54 to 0.64 on MySQL and MariaDB with 23 statements instead of 371, 0.87 to 0.89 on SQLite and no gain on PostgreSQL, where the statement count stays 123.
So the fair comparison does not change the ranking against today's DAL: the contract costs the ORM variants a few ms, and the gap to the DAL stays.
Against DAL v2 with the write levers it narrows the picture by engine (medians run 1 / run 2):

- MariaDB: DAL v2 53.74 / 52.18 ms is level with the ORM full variants (doctrine optimized 49.16 / 46.61, cycle idiomatic 54.15 / 50.71, cycle optimized 53.86 / 55.24, doctrine idiomatic 59.54 / 56.52).
- MySQL: DAL v2 52.09 / 46.51 ms is 4 to 12 ms behind the fastest ORM full variant (cycle optimized 40.52 in run 1, doctrine optimized 34.37 in run 2) and ahead of doctrine idiomatic full in run 1 (77.93).
- PostgreSQL: DAL v2 85.12 / 81.62 ms is level with doctrine idiomatic full (82.98 / 77.74) and about 20 ms behind the other ORM full variants (62.73 to 68.88), because the batched update does not engage there.
- SQLite: DAL v2 301.02 / 292.18 ms stays far behind (doctrine optimized full 132.05 / 126.46, cycle full about 21); the profile above puts 76 percent of it in SQL, so the cause is the statements, not validation or events.

The remaining write gap of DAL v2 is therefore not validation and events (events are 1.1 to 1.5 percent of its S4 time); it is writer PHP on MySQL, the missing batched update on PostgreSQL and the SQL cost on SQLite.
