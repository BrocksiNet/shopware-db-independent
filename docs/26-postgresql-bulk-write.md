# PostgreSQL bulk write, wave 7 W

Scenario: "admin API bulk sync write (50 products)", `POST /api/_action/sync`, `DATASET=catalog`, sequential, databases `bench_mariadb` and `bench_pg`.

## Measurement state

- Other sw-dev lanes stopped during every timing block (about 46 containers, started again after each block, 75 s settle time).
- Host load average at block start was between 13 and 49 (the host is shared), so absolute numbers drift by up to 40 percent between blocks.
- PostgreSQL ran with its default settings (`shared_buffers` 128 MB), `scripts/benchmark.sh settings` was not applied; wave 6 numbers used the tuned settings.
- The trigram index `product_search_keyword.idx.pg_keyword_trgm` (created by handoff R) did not exist in any of the runs below.
- `bench_pg` was vacuumed with `VACUUM (FULL, ANALYZE)` before the paired runs (the product table had grown to 577 MB of heap for 1,735 live rows through dead tuples; the bloat comes back within about 100 bulk requests).
- Only paired, alternating runs on the same stack set with swapped positions are used for comparisons between commits; sequential single-commit runs differed by more than the effects searched for.

## Baseline

| Run | MariaDB ms | PG ms | PG persistent ms | Host load | Other lanes stopped |
|---|---|---|---|---|---|
| first baseline, 7 runs | 390.0 | 856.5 | 701.9 | 24 to 49 | yes |
| second run, 7 runs | 415.4 | 708.3 | 767.3 | high | yes |
| quiet paired runs (pairs 3 and 4) | 289 | 466 to 639 | n/a | 13 to 16 | yes |

Wave 6 reported 555.3 ms on PG and 254.2 ms on MariaDB with the lanes running and tuned PG settings.
Stopping the lanes did not make the run reproducibly faster here: the drift between blocks (MariaDB 289 to 415 ms) is larger than any lane effect.
The ratio PG/MariaDB in the quiet runs is 1.6 to 2.2.

## What grew since wave 5 (`f6a37fd183f` to `03e1d43300f`)

Paired alternating runs, medians in ms, A and B positions swapped in the second line of each pair.

| Step | Result | Meaning |
|---|---|---|
| `f6a37fd183f` against `03e1d43300f` | 626 vs 704, swapped 543 vs 612 | +69 to +78 ms in total |
| `87783e92dad`, `a3770fd3f5e`, `ccda386febb`, `028d4c97a54`, `7517df9090b` against `f6a37fd183f` | 484 vs 466, swapped 479 vs 499 | about 0 ms |
| `38f1d41ac6c` (lock order) against `7517df9090b` | +26 and +54 (noisy) | about +40 ms |
| `03e1d43300f` against `38f1d41ac6c` (includes `e0e6f3d3fae`) | +32 and +11 | about +20 ms, the two commits were not separated |

The wave 5 commit itself measures 480 to 626 ms now, against 427 ms in wave 5.
So about 60 ms of the 128 ms growth (427 to 555 ms) is database state or host (table bloat, settings, load) and about 60 ms is code: roughly 40 ms lock order plus 20 ms in `e0e6f3d3fae` and `03e1d43300f`.

## Cause of the lock order cost

`ProductIndexer::withProductRowLocks` wraps the updaters in a transaction and runs `SELECT ... FOR UPDATE` on the products, their children and parents (PG only).
Experiments in a temporary worktree (all local, removed):

| Variant | Result against `38f1d41ac6c` |
|---|---|
| no lock, no transaction | about 40 ms faster (650 vs 619 reversed: 610 vs 557) |
| transaction kept, `FOR UPDATE` select removed | about 0 ms difference |
| `pg_advisory_xact_lock` on sorted hashed ids instead of `FOR UPDATE` | +52 ms in one order, 37 ms faster swapped, net about 0 |

Verified: the cost comes with the row lock statement, not with the transaction wrapper.
The server time of the lock statement is only about 1.6 ms, so the mechanism (hypothesis: tuple lock writes and the effect on the following updates of the same rows) is not verified.
Advisory locks give no measurable gain, so no code was changed.
Parallel check for the advisory variant: 0 deadlocks in 3 runs with and 3 without `--dedupe` (4.4, 3.46, 5.99 rps with `--dedupe`, 4.12, 3.67, 3.14 without) against 0 deadlocks for `38f1d41ac6c` in the same session (3.92, 2.3, 5.27 and 3.62, 3.53, 2.56).
These parallel numbers are noisy and below the wave 6 figures of `docs/19` (3.97 and 5.99 rps) only because of the host load.

## Split of one request

One request captured with `log_min_duration_statement=0` on PG and the slow log (`long_query_time=0`) on MariaDB, a single 50 product sync.
Logging inflates both numbers (684.7 ms on PG, 335.8 ms on MariaDB).
Host load at capture time about 15, other lanes stopped: yes.

| Part | PG | MariaDB |
|---|---|---|
| statements | 831 | 906 |
| server time (parse, bind, execute) | 404 ms | 284 ms |
| time outside the database (round trips, PDO, translator, codec, PHP) | about 280 ms | about 52 ms |

A probe pass with `TimingMiddleware` (10 requests, PG): wall 821 ms, driver 562 ms, translator 64 ms, id codec 27 ms, 393 statements per request in the probe stack, 25,883 driver calls.

Server time per phase, phases classified by statement text (approximate), ms PG against MariaDB:

| Phase | PG | MariaDB |
|---|---|---|
| category tree | 102 | 64 |
| other product reads | 97 | 47 |
| search keywords | 49 | 41 |
| invalidation and messenger | 31 | 24 |
| write commands | 20 | 13 |
| display group | 18 | 14 |
| cheapest price | 16 | 13 |
| rating | 15 | 34 |
| media and cover | 16 | 4.5 |
| inheritance and options | 12 | 3 |
| SEO urls | 8.5 | 13 |
| stream mapping | 8 | 3 |
| stock | 5.5 | 3.5 |
| transaction | 4.3 | 7.6 |

475 `UPDATE product` statements per request on both databases (158 `category_tree`, 50 DAL write, 50 `cheapest_price`, 87 `display_group`, 41 `rating_average`), 188 ms on PG against 117 ms on MariaDB.
Only 7 percent of these updates were HOT on PG (18 indexes on `product`).
Setting `fillfactor=70` raised HOT to 46 percent but the timing effect was small (ratio 2.04 against 2.09), so it was reset.

## Causes, verified or not

- Verified: the excess on PG is spread over many small statements, no single statement dominates.
- Verified: about 280 ms per request is spent outside the database on PG against about 52 ms on MariaDB (counts of statements are equal, so this is per statement overhead: unnamed parse and bind per statement, translator and codec).
- Verified: the lock order costs about 40 ms, the cost sits in the `FOR UPDATE` statement.
- Not verified: why a 1.6 ms statement costs 40 ms.
- Table bloat on `bench_pg` is a measurement hazard: the same commit moved by about 60 ms with it.

## Fixes

None applied.
The only candidate (advisory locks) showed no gain.

## What is left

- Reduce statement counts of the updaters (475 `UPDATE product` per request, one per product and updater), this is a core change that helps every database: see `docs/core-findings.md`.
- `VariantListingUpdater` and `VariantListingIndexer` (87 `display_group` updates) belong to handoff L, not touched.
- Per-statement client overhead on PG (translator 64 ms, codec 27 ms, unnamed parse per statement) is the main gap and belongs to the translator and plan cache work.
- A wall time split per indexer through `Profiler::trace` was prepared but not run.
- Settings reset: `log_min_duration_statement` reset, MariaDB slow log off with `long_query_time=10`, `fillfactor` reset, database containers at 8 CPUs and 16 GiB.
