# ORM spike: final timings

One timing block for all nine configurations on all four databases, produced unattended by `scripts/orm-spike-final-block.sh`, tables by `scripts/orm-spike-final-tables.py`.

## Conditions

Block of 2026-11-23, handoff E1, `APP_ENV=prod`, warm cache, 5 warm-up and 50 measured iterations per scenario, `--scenario=all`, PHP 8.4.17.
Other lanes stopped: yes (46 containers, restarted afterwards, lock removed).
Host load average (1, 5, 15 min) at the start of each engine: mysql 16.36, 11.83, 9.34; mariadb 12.48, 11.59, 9.48; postgresql 7.59, 10.24, 9.23; sqlite 7.27, 9.05, 8.90.
Load at the end of the block: 7.53, 7.58, 8.16.
The load is high for a block with stopped lanes and falls during the run, so MySQL (first engine) was measured under the highest load; compare implementations within an engine, not engines with each other.
Every configuration ran in its own `--output-dir` and the `--verify` run (1 iteration, separate call) came first.
Configurations: `dal`, `dbal`, `doctrine` (`mode=idiomatic`, `mode=optimized`), `cycle` (`variant=idiomatic`, `variant=optimized`), `dalv2` (no options; `count=window agg=stats write=key+upd`; those plus `proj=1`).
The option keys were checked against the code (`DoctrineImplementation`, `CycleImplementation`, `DalV2Implementation`).
The harness names the MariaDB result file `mysql-<impl>.json` because the `SqlDialect` name reports `mysql` there; the server behind the `mariadb` runs is MariaDB 10.11.16 (`instance-database-1`).
Raw JSON: `/var/www/html/var/orm-spike-e1/` inside `instance-web-1` (not versioned).

## Results

### mysql

Medians in ms, statements per iteration, peak memory in MB; ratio = median / dal median.

| implementation | S1 ms | S1 stmts | S1 MB | S1 x dal | S2 ms | S2 stmts | S2 MB | S2 x dal | S3 ms | S3 stmts | S3 MB | S3 x dal | S4 ms | S4 stmts | S4 MB | S4 x dal | S5 ms | S5 stmts | S5 MB | S5 x dal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dal | 12.42 | 4 | 41 | 1.00 | 4.60 | 5 | 50 | 1.00 | 56.67 | 7 | 51 | 1.00 | 90.11 | 371 | 58 | 1.00 | 28.24 | 4 | 57 | 1.00 |
| dbal | 2.21 | 1 | 25 | 0.18 | 0.55 | 4 | 25 | 0.12 | 20.29 | 3 | 25 | 0.36 | 7.16 | 5 | 25 | 0.08 | 19.47 | 1 | 25 | 0.69 |
| doctrine idiomatic | 10.52 | 32 | 32 | 0.85 | 2.35 | 15 | 30 | 0.51 | 30.81 | 45 | 32 | 0.54 | 55.37 | 450 | 32 | 0.61 | 18.35 | 22 | 32 | 0.65 |
| doctrine optimized | 2.83 | 1 | 27 | 0.23 | 0.78 | 4 | 27 | 0.17 | 20.23 | 3 | 27 | 0.36 | 43.48 | 351 | 32 | 0.48 | 23.78 | 1 | 29 | 0.84 |
| cycle idiomatic | 7.71 | 13 | 32 | 0.62 | 3.62 | 18 | 31 | 0.79 | 47.44 | 11 | 32 | 0.84 | 44.69 | 350 | 33 | 0.50 | 13.42 | 4 | 32 | 0.48 |
| cycle optimized | 6.14 | 13 | 32 | 0.49 | 2.98 | 18 | 31 | 0.65 | 48.80 | 11 | 32 | 0.86 | 52.29 | 350 | 32 | 0.58 | 12.54 | 4 | 32 | 0.44 |
| dalv2 default | 11.11 | 4 | 41 | 0.89 | 6.16 | 5 | 51 | 1.34 | 60.85 | 7 | 51 | 1.07 | 100.98 | 371 | 58 | 1.12 | 29.98 | 4 | 57 | 1.06 |
| dalv2 count=window agg=stats write=key+upd | 10.41 | 3 | 41 | 0.84 | 5.75 | 5 | 51 | 1.25 | 39.68 | 5 | 51 | 0.70 | 53.39 | 23 | 58 | 0.59 | 17.41 | 3 | 57 | 0.62 |
| dalv2 all levers (+proj=1) | 3.78 | 2 | 39 | 0.30 | 1.90 | 5 | 39 | 0.41 | 32.67 | 4 | 39 | 0.58 | 57.49 | 23 | 50 | 0.64 | 14.11 | 2 | 48 | 0.50 |

### mariadb

Medians in ms, statements per iteration, peak memory in MB; ratio = median / dal median.

| implementation | S1 ms | S1 stmts | S1 MB | S1 x dal | S2 ms | S2 stmts | S2 MB | S2 x dal | S3 ms | S3 stmts | S3 MB | S3 x dal | S4 ms | S4 stmts | S4 MB | S4 x dal | S5 ms | S5 stmts | S5 MB | S5 x dal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dal | 11.91 | 4 | 41 | 1.00 | 6.26 | 5 | 51 | 1.00 | 41.72 | 7 | 51 | 1.00 | 94.01 | 371 | 58 | 1.00 | 29.33 | 4 | 57 | 1.00 |
| dbal | 2.68 | 1 | 25 | 0.23 | 0.56 | 4 | 25 | 0.09 | 23.21 | 3 | 25 | 0.56 | 6.22 | 5 | 25 | 0.07 | 18.83 | 1 | 25 | 0.64 |
| doctrine idiomatic | 17.30 | 32 | 32 | 1.45 | 1.88 | 15 | 30 | 0.30 | 39.55 | 45 | 32 | 0.95 | 53.64 | 450 | 32 | 0.57 | 21.57 | 22 | 32 | 0.74 |
| doctrine optimized | 2.97 | 1 | 27 | 0.25 | 0.77 | 4 | 27 | 0.12 | 23.01 | 3 | 27 | 0.55 | 41.59 | 351 | 32 | 0.44 | 21.65 | 1 | 29 | 0.74 |
| cycle idiomatic | 6.57 | 13 | 32 | 0.55 | 3.20 | 18 | 31 | 0.51 | 32.49 | 11 | 32 | 0.78 | 42.69 | 350 | 33 | 0.45 | 13.79 | 4 | 32 | 0.47 |
| cycle optimized | 4.49 | 13 | 32 | 0.38 | 2.34 | 18 | 31 | 0.37 | 29.24 | 11 | 32 | 0.70 | 41.68 | 350 | 32 | 0.44 | 12.65 | 4 | 32 | 0.43 |
| dalv2 default | 9.77 | 4 | 41 | 0.82 | 5.20 | 5 | 51 | 0.83 | 44.20 | 7 | 51 | 1.06 | 97.50 | 371 | 58 | 1.04 | 29.50 | 4 | 57 | 1.01 |
| dalv2 count=window agg=stats write=key+upd | 9.28 | 3 | 41 | 0.78 | 5.39 | 5 | 51 | 0.86 | 27.90 | 5 | 51 | 0.67 | 54.09 | 23 | 58 | 0.58 | 18.17 | 3 | 57 | 0.62 |
| dalv2 all levers (+proj=1) | 4.48 | 2 | 39 | 0.38 | 2.52 | 5 | 39 | 0.40 | 23.83 | 4 | 39 | 0.57 | 54.87 | 23 | 50 | 0.58 | 14.51 | 2 | 48 | 0.49 |

### postgresql

Medians in ms, statements per iteration, peak memory in MB; ratio = median / dal median.

| implementation | S1 ms | S1 stmts | S1 MB | S1 x dal | S2 ms | S2 stmts | S2 MB | S2 x dal | S3 ms | S3 stmts | S3 MB | S3 x dal | S4 ms | S4 stmts | S4 MB | S4 x dal | S5 ms | S5 stmts | S5 MB | S5 x dal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dal | 21.35 | 4 | 41 | 1.00 | 12.07 | 5 | 51 | 1.00 | 68.39 | 7 | 52 | 1.00 | 84.65 | 123 | 59 | 1.00 | 41.24 | 4 | 58 | 1.00 |
| dbal | 33.34 | 1 | 25 | 1.56 | 2.98 | 4 | 25 | 0.25 | 34.64 | 3 | 25 | 0.51 | 12.72 | 5 | 26 | 0.15 | 28.48 | 1 | 25 | 0.69 |
| doctrine idiomatic | 51.90 | 32 | 32 | 2.43 | 5.80 | 15 | 30 | 0.48 | 59.33 | 45 | 32 | 0.87 | 75.39 | 450 | 33 | 0.89 | 57.90 | 22 | 34 | 1.40 |
| doctrine optimized | 31.88 | 1 | 27 | 1.49 | 4.57 | 4 | 28 | 0.38 | 36.23 | 3 | 28 | 0.53 | 57.22 | 351 | 32 | 0.68 | 23.35 | 1 | 29 | 0.57 |
| cycle idiomatic | 12.34 | 13 | 32 | 0.58 | 4.27 | 18 | 32 | 0.35 | 41.64 | 11 | 32 | 0.61 | 57.22 | 350 | 33 | 0.68 | 32.05 | 4 | 33 | 0.78 |
| cycle optimized | 11.03 | 13 | 32 | 0.52 | 4.02 | 18 | 32 | 0.33 | 40.82 | 11 | 33 | 0.60 | 59.07 | 350 | 33 | 0.70 | 32.91 | 4 | 33 | 0.80 |
| dalv2 default | 21.14 | 4 | 41 | 0.99 | 12.33 | 5 | 51 | 1.02 | 62.61 | 7 | 52 | 0.92 | 85.36 | 123 | 59 | 1.01 | 42.80 | 4 | 58 | 1.04 |
| dalv2 count=window agg=stats write=key+upd | 18.96 | 3 | 42 | 0.89 | 12.17 | 5 | 51 | 1.01 | 46.92 | 5 | 52 | 0.69 | 85.80 | 123 | 59 | 1.01 | 26.66 | 3 | 58 | 0.65 |
| dalv2 all levers (+proj=1) | 10.05 | 2 | 39 | 0.47 | 5.61 | 5 | 40 | 0.47 | 35.57 | 4 | 40 | 0.52 | 89.15 | 123 | 50 | 1.05 | 17.33 | 2 | 49 | 0.42 |

### sqlite

Medians in ms, statements per iteration, peak memory in MB; ratio = median / dal median.

| implementation | S1 ms | S1 stmts | S1 MB | S1 x dal | S2 ms | S2 stmts | S2 MB | S2 x dal | S3 ms | S3 stmts | S3 MB | S3 x dal | S4 ms | S4 stmts | S4 MB | S4 x dal | S5 ms | S5 stmts | S5 MB | S5 x dal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dal | 62.34 | 4 | 41 | 1.00 | 17.02 | 5 | 51 | 1.00 | 130.22 | 7 | 52 | 1.00 | 339.01 | 371 | 59 | 1.00 | 62.44 | 4 | 57 | 1.00 |
| dbal | 19.03 | 1 | 25 | 0.31 | 0.27 | 4 | 25 | 0.02 | 17.42 | 3 | 25 | 0.13 | 5.81 | 5 | 26 | 0.02 | 12.63 | 1 | 25 | 0.20 |
| doctrine idiomatic | 36.63 | 32 | 33 | 0.59 | 1.01 | 15 | 31 | 0.06 | 28.28 | 45 | 33 | 0.22 | 319.29 | 450 | 34 | 0.94 | 12.74 | 22 | 34 | 0.20 |
| doctrine optimized | 19.72 | 1 | 29 | 0.32 | 0.44 | 4 | 29 | 0.03 | 18.53 | 3 | 29 | 0.14 | 125.83 | 351 | 33 | 0.37 | 13.63 | 1 | 30 | 0.22 |
| cycle idiomatic | 6.97 | 13 | 34 | 0.11 | 1.85 | 18 | 33 | 0.11 | 24.86 | 11 | 34 | 0.19 | 17.05 | 350 | 34 | 0.05 | 9.60 | 4 | 34 | 0.15 |
| cycle optimized | 5.34 | 13 | 34 | 0.09 | 1.14 | 18 | 33 | 0.07 | 23.10 | 11 | 34 | 0.18 | 16.86 | 350 | 34 | 0.05 | 8.98 | 4 | 34 | 0.14 |
| dalv2 default | 62.06 | 4 | 42 | 1.00 | 17.36 | 5 | 51 | 1.02 | 129.52 | 7 | 52 | 0.99 | 339.27 | 371 | 59 | 1.00 | 62.52 | 4 | 57 | 1.00 |
| dalv2 count=window agg=stats write=key+upd | 45.99 | 3 | 42 | 0.74 | 17.20 | 5 | 51 | 1.01 | 79.35 | 5 | 52 | 0.61 | 298.29 | 23 | 59 | 0.88 | 42.24 | 3 | 58 | 0.68 |
| dalv2 all levers (+proj=1) | 33.46 | 2 | 40 | 0.54 | 10.08 | 5 | 40 | 0.59 | 67.84 | 4 | 40 | 0.52 | 287.10 | 23 | 51 | 0.85 | 22.47 | 2 | 49 | 0.36 |

### Verify (against dal, 1 iteration)

| engine | implementation | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|---|
| mysql | dbal | OK | OK | OK | OK | OK |
| mysql | doctrine idiomatic | OK | OK | OK | OK | OK |
| mysql | doctrine optimized | OK | OK | OK | OK | OK |
| mysql | cycle idiomatic | OK | OK | OK | OK | OK |
| mysql | cycle optimized | OK | OK | OK | OK | OK |
| mysql | dalv2 default | OK | OK | OK | OK | OK |
| mysql | dalv2 count=window agg=stats write=key+upd | OK | OK | OK | OK | OK |
| mysql | dalv2 all levers (+proj=1) | OK | OK | OK | OK | OK |
| mariadb | dbal | OK | OK | OK | OK | OK |
| mariadb | doctrine idiomatic | OK | OK | OK | OK | OK |
| mariadb | doctrine optimized | OK | OK | OK | OK | OK |
| mariadb | cycle idiomatic | OK | OK | OK | OK | OK |
| mariadb | cycle optimized | OK | OK | OK | OK | OK |
| mariadb | dalv2 default | OK | OK | OK | OK | OK |
| mariadb | dalv2 count=window agg=stats write=key+upd | OK | OK | OK | OK | OK |
| mariadb | dalv2 all levers (+proj=1) | OK | OK | OK | OK | OK |
| postgresql | dbal | OK | OK | OK | OK | OK |
| postgresql | doctrine idiomatic | OK | OK | OK | OK | OK |
| postgresql | doctrine optimized | OK | OK | OK | OK | OK |
| postgresql | cycle idiomatic | OK | OK | OK | OK | OK |
| postgresql | cycle optimized | OK | OK | OK | OK | OK |
| postgresql | dalv2 default | OK | OK | OK | OK | OK |
| postgresql | dalv2 count=window agg=stats write=key+upd | OK | OK | OK | OK | OK |
| postgresql | dalv2 all levers (+proj=1) | OK | OK | OK | OK | OK |
| sqlite | dbal | OK | OK | OK | OK | OK |
| sqlite | doctrine idiomatic | OK | OK | OK | OK | OK |
| sqlite | doctrine optimized | OK | OK | OK | OK | OK |
| sqlite | cycle idiomatic | OK | OK | OK | OK | OK |
| sqlite | cycle optimized | OK | OK | OK | OK | OK |
| sqlite | dalv2 default | OK | OK | OK | OK | OK |
| sqlite | dalv2 count=window agg=stats write=key+upd | OK | OK | OK | OK | OK |
| sqlite | dalv2 all levers (+proj=1) | OK | OK | OK | OK | OK |

### Cold cache (cache:clear --no-warmup, then one S2 call, wall time in seconds, median of 5)

Wall time includes `podman exec`, kernel boot and cache build; warm = same call right after.

| engine | implementation | cold s | warm s | cold - warm s | cold min-max s | rc |
|---|---|---|---|---|---|---|
| mysql | dal | 1.76 | 0.29 | 1.47 | 0.34-2.16 | 0 |
| mysql | dbal | 1.04 | 0.21 | 0.83 | 0.21-1.05 | 0 |
| mysql | doctrine | 1.10 | 0.23 | 0.87 | 0.23-1.14 | 0 |
| mysql | cycle | 1.04 | 0.23 | 0.81 | 0.24-1.13 | 0 |
| mysql | dalv2 | 1.56 | 0.28 | 1.29 | 0.50-1.87 | 0 |
| mariadb | dal | 1.61 | 0.29 | 1.32 | 1.51-2.00 | 0 |
| mariadb | dbal | 1.04 | 0.22 | 0.83 | 0.21-1.15 | 0 |
| mariadb | doctrine | 1.06 | 0.23 | 0.83 | 0.23-1.16 | 0 |
| mariadb | cycle | 1.06 | 0.22 | 0.84 | 0.22-1.20 | 0 |
| mariadb | dalv2 | 1.69 | 0.29 | 1.40 | 1.57-1.75 | 0 |
| postgresql | dal | 1.71 | 0.33 | 1.37 | 1.66-1.86 | 0 |
| postgresql | dbal | 1.10 | 0.24 | 0.85 | 0.24-1.18 | 0 |
| postgresql | doctrine | 1.12 | 0.27 | 0.85 | 0.27-1.16 | 0 |
| postgresql | cycle | 1.09 | 0.25 | 0.83 | 0.26-1.10 | 0 |
| postgresql | dalv2 | 1.76 | 0.33 | 1.43 | 1.67-1.91 | 0 |
| sqlite | dal | 1.59 | 0.30 | 1.29 | 0.31-1.72 | 0 |
| sqlite | dbal | 1.03 | 0.23 | 0.81 | 0.22-1.06 | 0 |
| sqlite | doctrine | 1.07 | 0.25 | 0.82 | 0.24-1.11 | 0 |
| sqlite | cycle | 1.06 | 0.23 | 0.83 | 0.23-1.12 | 0 |
| sqlite | dalv2 | 1.59 | 0.30 | 1.29 | 0.47-1.59 | 0 |

### Failed cells

None.

## Notes

All 32 verify cells (8 non-dal configurations times 4 engines, S1 to S5) pass against the DAL.
No benchmark cell failed, so no cell was rerun.
The first attempt of the cold-cache measurement used plain `cache:clear`, which warms the cache again, so cold and warm were equal; it was discarded and rerun with `cache:clear --no-warmup`, 5 repetitions per cell, in a second lock (load at its start 5.11, 6.66, 7.69).
Single cold calls vary: some of the 5 repetitions on MySQL and SQLite show warm-like times (see min to max), the median is the number to use.
The cold cost is about 1.0 s for DBAL, Doctrine and Cycle and about 1.6 to 1.8 s for the DAL and DAL v2, each including about 0.2 to 0.3 s of `podman exec` and kernel boot.

## PostgreSQL S1: why hand-written DBAL is slower than the DAL

In this block S1 on PostgreSQL takes 33.34 ms with DBAL, 21.35 ms with the DAL and 11.03 to 12.34 ms with Cycle.
The DBAL query was captured with `scripts/orm-spike-explain-s1.php` (spy on `fetchAllAssociative`, parameters inlined) and run with `EXPLAIN (ANALYZE, BUFFERS)` in `orm_spike`.
Run in `psql` it takes about 27.6 ms steady state (5 runs: 42.2 first, then 28.9, 27.7, 27.6, 27.7), so the time is spent in the database, not in PHP.
The plan starts with a hash left join of `product p` and its parent `pp` over 5000 rows each (two sequential scans), then 5 index-driven translation joins, and produces 4750 rows before the category filter.
The category condition is an `EXISTS` that the planner executes as a semi join after those joins, reducing 4750 rows to 220 (and 200 after the remaining filters), so all translation, manufacturer and cover joins run for about 4750 rows instead of for the 24 on the page.
The manufacturer translation joins use `COALESCE(p.product_manufacturer_id, pp.product_manufacturer_id)` in their join condition, which cannot be an index condition: they nested-loop over `product_manufacturer_translation` and drop 105678 and 142500 rows through the join filter.
The planner estimates 1 to 25 rows at the joins where it gets 4750 to 220, and a `WindowAgg` computes the total count over the full 200 rows before the top-N sort (59878 shared buffer hits in total).
This is the plan of one single statement that does the filtering, joining, counting and sorting together.
The DAL runs four statements for S1 (id query, count, hydration of the page, prices), counted by the harness.
Its SQL could not be captured in full, because `pg_stat_activity` cuts the text at 1023 characters and `podman logs` does not work here, so no DAL plan was taken.
A sampling of `pg_stat_activity` over 250 iterations (1 ms interval, first 1023 characters only) caught the DBAL main statement 2113 times, about 8.5 samples per iteration, and the DAL id query 681 times plus its count query 200 times, about 3.5 samples per iteration.
That fits a DAL query that finds the 24 ids first and fetches the rest only for them, but this is the sampling result, not a plan comparison.
