# 51 Timing reliability and canonical block (Wave 10 D)

Status: 2026-11-25, wave 10 handoff D.
Branch: `poc/wave10` in `instance/` (up to `0ed724decae`, which adds `--option` passthrough to `read-store:load` and `read-store:load-worker`).
Runner: `scripts/wave10-paired.py`.
Archived per-block summaries and cache-window logs: `docs/benchmark-results/wave10-d/`.

## Verdict

Doc 46 "What is not proven", point 4 ("every timing comes from one developer machine; differences below about 10 % are not reliable"): **proven with limits**.

- It is still **one developer machine** (Apple M4 Pro inside a Podman AppleHV VM); no second machine was available, so absolute numbers remain host-specific.
- The old rule of thumb ("below ~10 % is unreliable") is replaced by **measured A/A noise and paired AB/BA 95 % bootstrap confidence intervals** across all headline comparisons with other `sw-dev` lanes stopped.
- Measured A/A noise floors (maximum deviation of the 95 % CI from 1.000× across 10 paired AB/BA rounds):
  - CLI `orm-spike:bench` S1: **±1.7 %** on SQLite (in-process, no container IPC), **±3.8 %** on MySQL with explicit vCPU pinning, **±5.7 % to ±8.2 %** unpinned on PostgreSQL / MariaDB / MySQL.
  - Full HTTP storefront (PHP-FPM + Caddy + MariaDB, `bench_mariadb`): **±9.7 % to ±11.8 %** on `p50` (`detail` −9.8 %, `listing` −9.7 %, `home` −11.8 %). That confirms the earlier ~10 % floor for full-stack HTTP storefront runs on this host, while paired CLI runs resolve differences down to ~4–8 %.
- Every architectural conclusion of doc 46 **holds**, with two important refinements:
  1. **Doc 38's "DAL v2 does not change storefront reads at 150k" (measured without levers) does not hold**: with the wave 8 levers (`count=window agg=stats write=key+upd proj=1`), DAL v2 cuts 150k latency by 20–54 % (`S1` 0.583×, `S2` 0.464×, `S3` 0.617×, `R3b` 0.804×) and lifts c=8 throughput by +24 % (`14.1 → 17.4 req/s`). However, it still saturates ~8 MySQL cores (`120 s` CPU in 15 s) and remains **43× slower** than O1a (`756 req/s`), so the architectural conclusion that DAL v2 cannot replace OpenSearch at 150k **holds**.
  2. **OpenSearch HTTP cache window (`docs/44`) is a real defect under `refresh=false`**: synchronous projection alone leaves OpenSearch's 1 s `refresh_interval` open. Immediate Store API listings returned the old name in **9 of 10** trials, and immediate Storefront `/navigation/{cat}` requests after cache invalidation **poisoned Shopware's HTTP cache** with stale product names (next to a fresh MySQL SEO URL in the same `<a>` tag) past `+1.3 s` in **5 of 5** trials (`1.4–1.9 ms` cache hits). Explicit `_refresh` (10.0 ms median) or `refresh=wait_for` (857 ms median on 1 shard, 1 s interval) reduced stale reads and cache poisoning to **0**.

---

## 1. Host, VM, thermal state, and pinning

### Hardware and runtime

- **Host**: Apple M4 Pro, 14 cores (10 performance + 4 efficiency), 48 GiB RAM, macOS 26.7.3 (Build 25G342).
- **Thermal state** (`pmset -g therm` before and during runs): no thermal or performance warning recorded.
- **Podman VM** (`podman-machine-default`, AppleHV / vfkit): 8 vCPUs (`0-7`), 16,384 MiB RAM, 100 GiB disk, Linux `6.17.7-300.fc43.aarch64`. No `cpufreq` governor is exposed inside the AppleHV guest (`/sys/devices/system/cpu/cpu0/cpufreq` absent).
- **Isolation**: all other `sw-dev` lanes were stopped (`6-5`, `6-6`, `6-7`, `6-8`, `commercial`, `frankenphp`, `varnish`, plus `trunk` and `sfcheck` paused under `/tmp/wave10-timing.lock` for the duration of the block). Only the target stack ran; VM free RAM stayed 5–11 GiB with 0 swap.
- **Container limits**: default VM limits (8 vCPUs / 16 GiB) for CLI and read-store blocks; `4 CPUs / 4 GiB` on `instance-postgres-1` and `instance-database-1` during the Step 3a HTTP benchmark to match `docs/13`.

### Container CPU pinning on rootless Podman

`podman update --cpuset-cpus` fails on this VM (`crun update` exit 1: controller `cpuset` is not delegated under `/sys/fs/cgroup/user.slice/user-502.slice/cgroup.subtree_control`, which delegates only `cpu io memory pids`).
Direct process-level vCPU pinning (`taskset -apc 4-7 <mysqld_pid>` on the VM + `os.sched_setaffinity(0, {0,1,2,3})` around the PHP process) **does** work and narrowed the MySQL S1 A/A 95 % CI width from **11.4 %** (`[0.968, 1.082]`, unpinned at host load 8.0–9.7) to **6.3 %** (`[0.962, 1.025]`, pinned at host load 5.4–5.8). Both pinning and lower concurrent host load contributed; affinity was restored to `0-7` after the test.

### A/A noise measurements (10 paired AB/BA rounds)

Same binary and workload run twice (`A1` vs `A2`), alternating `AB` / `BA` per round. DB CLI runs use `orm-spike:bench --impl=dal --scenario=S1 --iterations=50 --warmup=5` on `orm_spike` (5k products); HTTP storefront runs use 20 requests/round (+ 1 warm-up) per route against `mariadb` (`bench_mariadb`, `SHOPWARE_HTTP_CACHE_ENABLED=0`).

| Workload | A1 median (min..max) | A2 median (min..max) | Ratio A2/A1 | 95 % CI (ratio of medians) | 95 % CI (median of paired ratios) | Max CI dev from 1.0 |
|---|---:|---:|---:|---|---|---:|
| SQLite S1 (in-process CLI) | 60.29 ms (58.18..60.87) | 60.42 ms (57.27..61.23) | 1.002× | `[0.983, 1.008]` | `[0.985, 1.009]` | **±1.7 %** |
| MySQL S1 (pinned 0-3 / 4-7) | 10.76 ms (10.09..12.12) | 10.62 ms (10.43..11.15) | 0.987× | `[0.962, 1.025]` | `[0.959, 1.029]` | **±3.8 %** |
| PostgreSQL S1 (unpinned) | 20.87 ms (20.05..21.66) | 20.99 ms (19.26..21.97) | 1.006× | `[0.943, 1.034]` | `[0.955, 1.030]` | **±5.7 %** |
| MariaDB S1 (unpinned) | 10.57 ms (9.94..11.05) | 10.50 ms (9.60..13.16) | 0.993× | `[0.934, 1.018]` | `[0.943, 1.019]` | **±6.6 %** |
| MySQL S1 (unpinned) | 11.09 ms (10.11..12.37) | 11.31 ms (10.45..12.59) | 1.020× | `[0.968, 1.082]` | `[0.959, 1.087]` | **±8.2 %** |
| HTTP storefront `listing` (MariaDB) | 63.40 ms (57.33..72.06) | 60.98 ms (58.97..70.56) | 0.962× | `[0.903, 1.028]` | `[0.914, 1.035]` | **±9.7 %** |
| HTTP storefront `detail` (MariaDB) | 88.21 ms (79.28..102.5) | 83.36 ms (78.28..98.67) | 0.945× | `[0.902, 1.023]` | `[0.893, 1.035]` | **±9.8 %** |
| HTTP storefront `home` (MariaDB) | 103.2 ms (96.34..111.5) | 96.60 ms (94.04..121.0) | 0.936× | `[0.882, 0.994]` | `[0.890, 1.006]` | **±11.8 %** |

---

## 2. Method (`scripts/wave10-paired.py`)

Every comparison in Section 3 was executed with `scripts/wave10-paired.py`:

- **Pairing and alternation**: 10 rounds (`n = 10`), alternating execution order `AB` on odd rounds and `BA` on even rounds to cancel thermal drift and linear background load trends.
- **Per-round statistic**: median of the round's iterations (or throughput / cgroup CPU over the 15 s load window for R5).
- **Uncertainty**: deterministic paired bootstrap (`B = 10,000` resamples of the 10 `(a_i, b_i)` pairs, `seed = 42`), reporting both the 95 % percentile CI of `median(B) / median(A)` (primary column below) and `median(b_i / a_i)` (robust under transient host load spikes; shown in notes and `.summary.json`).
- **Reproducibility**: `python3 scripts/wave10-paired.py run --rounds 10 --parser <orm-spike|read-store|walk-e|json-kv> --label-a ... --cmd-a ... --label-b ... --cmd-b ... --out <jsonl> --summary-json <json>`, plus offline `analyze <jsonl>`.

Verdict rules for Section 3:
- **`holds`**: 95 % CI excludes 1.0 in the claimed direction and is consistent with the prior headline magnitude.
- **`holds smaller`**: 95 % CI excludes 1.0 in the claimed direction, but the measured effect is clearly smaller than previously claimed (or smaller gap than previously claimed).
- **`does not hold`**: 95 % CI contradicts the prior claim (or crosses 1.0 where a difference was claimed, or shows a real difference where "no change" was claimed).

---

## 3. Canonical block results

### 3a. PostgreSQL vs MariaDB (`bench_pg` vs `bench_mariadb`, catalog dataset)

Same harness (`scripts/benchmark.sh` snapshot `0ed724decae`, `bench_pg` / `bench_mariadb` with 1,840 products / 503 categories / 8 sales channels, `4 CPUs / 4 GiB` DB container limits, equal DB memory settings, `VACUUM (FULL, ANALYZE)` / `ANALYZE TABLE` before the block). Each round ran 20 sequential requests (+ 1 warm-up) per storefront route and 5 bulk sync upserts (50 products each); parallel bulk sync ran 12 requests with 4 workers per round.

| Comparison & scenario | Baseline claim (`docs/13` w6/w7) | MariaDB median (min..max) | PostgreSQL median (min..max) | Ratio PG / MariaDB | 95 % CI (ratio of med) | Verdict |
|---|---|---:|---:|---:|---|---|
| New conn: `storefront home` | 1.54–1.71× | 100.2 ms (97.7..107.8) | 163.1 ms (152.0..170.4) | **1.629×** | `[1.558, 1.695]` | **holds** |
| New conn: `storefront listing` | 1.80–1.85× | 61.49 ms (58.0..66.7) | 111.7 ms (106.3..126.8) | **1.816×** | `[1.763, 1.883]` | **holds** |
| New conn: `storefront detail` | 1.84–2.03× | 83.56 ms (78.1..86.3) | 154.1 ms (146.3..174.6) | **1.845×** | `[1.796, 2.059]` | **holds** |
| New conn: `storefront search` (with interleaved bulk sync) | 2.02–2.20× | 71.91 ms (68.6..81.1) | 175.6 ms (131.9..225.7) | **2.442×** | `[1.804, 3.084]` | **holds** (wider; see note) |
| New conn: `bulk sync` (50 products, seq) | 2.15–2.18× | 272.1 ms (250.6..292.7) | 559.2 ms (516.3..654.0) | **2.055×** | `[1.940, 2.239]` | **holds** |
| Persistent + plan cache: `storefront home` | 1.13–1.19× | 99.67 ms (93.0..114.4) | 115.6 ms (108.3..130.8) | **1.160×** | `[1.073, 1.242]` | **holds** |
| Persistent + plan cache: `storefront listing` | 1.10–1.12× | 62.65 ms (55.9..77.3) | 70.93 ms (64.9..76.2) | **1.132×** | `[1.060, 1.177]` | **holds** |
| Persistent + plan cache: `storefront detail` | 1.40–1.61× | 81.96 ms (77.5..94.7) | 102.9 ms (96.2..111.8) | **1.255×** | `[1.176, 1.331]` | **holds smaller** (closer to MariaDB) |
| Persistent + plan cache: `storefront search` (clean, post-VACUUM) | 1.35–1.63× | 79.31 ms (66.6..148.3) | 108.4 ms (84.7..161.0) | **1.366×** (paired 1.302×) | `[0.900, 1.551]` (paired `[1.216, 1.374]`) | **holds** |
| Persistent + plan cache: `bulk sync` (50 products, seq) | 1.91–1.97× | 280.6 ms (265.4..355.1) | 506.5 ms (449.3..660.3) | **1.805×** | `[1.681, 1.844]` | **holds** |
| Persistent + plan cache: `bulk sync` (c=4, rps, 0 errors) | 0.32× (3.7 vs 11.7/s) | 10.89 req/s (8.95..11.69) | 3.74 req/s (2.92..4.69) | **0.344×** | `[0.283, 0.384]` | **holds** |

**Note on `storefront search` bloat**: when 50-product bulk sync upserts ran inside the same round as `search`, PostgreSQL `search` started at 92.8 ms in round 1 (right after `VACUUM ANALYZE`) and degraded to 244.3 ms by round 10 (`2.438×`, CI `[1.754, 3.407]`) due to dead-tuple growth on `product_search_keyword` before autovacuum caught up. A clean read-only 10-round check immediately after `VACUUM ANALYZE` gave a paired median ratio of **1.302×** (paired 95 % CI `[1.216, 1.374]`; ratio of medians 1.366× with a wide unpaired CI `[0.900, 1.551]` because both engines experienced a shared host load spike in rounds 6–9). Overall PostgreSQL storefront with persistent connections + plan cache sits at **1.13× to 1.30×** of MariaDB (`1.13–1.37×` incl. ratio-of-medians search), slightly tighter than doc 46's `1.13× to 1.46×`.

### 3b. DAL vs DAL v2 (all wave 8 levers) on `orm_spike` (5k products, MySQL)

Commands: `orm-spike:bench --impl=dal` vs `--impl=dalv2 --option count=window --option agg=stats --option write=key+upd --option proj=1` (50 iters + 5 warm-up per round × 10 AB/BA rounds; `--verify` OK on S1, S2, S3, S5).

| Scenario | Baseline claim (`docs/34`) | DAL median (min..max) | DAL v2 median (min..max) | Stmts | Ratio DAL v2 / DAL | 95 % CI | Verdict |
|---|---|---:|---:|---:|---:|---|---|
| S1 (listing) | 0.30× (3.3× faster) | 10.82 ms (9.04..11.65) | 4.77 ms (3.72..5.36) | 4 → 2 | **0.441×** (2.27× faster) | `[0.411, 0.520]` | **holds smaller** |
| S2 (detail) | 0.41× (2.4× faster) | 5.54 ms (4.60..6.13) | 2.33 ms (1.92..2.77) | 5 → 5 | **0.420×** (2.38× faster) | `[0.380, 0.483]` | **holds** |
| S3 (filtered + aggs) | 0.58× (1.7× faster) | 58.81 ms (54.20..64.32) | 34.44 ms (31.00..36.10) | 7 → 4 | **0.586×** (1.71× faster) | `[0.559, 0.622]` | **holds** |
| S5 (bulk write / search-like) | 0.50× (2.0× faster) | 29.93 ms (28.40..32.33) | 14.00 ms (12.56..15.01) | 4 → 2 | **0.468×** (2.14× faster) | `[0.451, 0.483]` | **holds** |

### 3c. DAL vs DAL v2 (with wave 8 levers) on `read_store_large` (150k products, MySQL)

Wave 9 ran `dalv2` without `--option` (`docs/38` "Correction: O0b ran without levers"). Here DAL v2 ran with the full lever set (`count=window agg=stats write=key+upd proj=1`), `--verify` OK on S1, S2, S3, R3b, R4. Fast scenarios (`S2`, `R4`): 50 iters + 5 warm-up/round; slow scenarios (`S1`, `S3`, `R3b`): 5 iters + 2 warm-up/round (50 measured iters total); R5: `read-store:load --concurrency=8 --duration=15s` with the new `--option` passthrough (`0ed724decae`).

| Scenario / Metric | Baseline claim (`docs/38` without levers) | DAL median (min..max) | DAL v2 + levers median (min..max) | Stmts | Ratio DAL v2 / DAL | 95 % CI | Verdict |
|---|---|---:|---:|---:|---:|---|---|
| S2 / R1 (detail) | "no change" (~1.11×) | 5.14 ms (4.74..6.39) | 2.39 ms (1.99..2.96) | 5 → 5 | **0.464×** | `[0.410, 0.553]` | **does not hold** (2.15× faster) |
| S1 / R2 (listing) | "no change" (~1.07×) | 115.6 ms (104.2..123.4) | 67.38 ms (59.4..81.5) | 4 → 2 | **0.583×** | `[0.548, 0.641]` | **does not hold** (1.72× faster) |
| S3 (filters + aggs) | "no change" (~1.07×) | 2,517 ms (2,420..2,680) | 1,553 ms (1,489..1,908) | 7 → 4 | **0.617×** | `[0.595, 0.635]` | **does not hold** (1.62× faster) |
| R3b (word search) | "no change" (~1.08×) | 1,076 ms (1,007..1,193) | 865.2 ms (779..962) | 9 → 7 | **0.804×** | `[0.761, 0.832]` | **does not hold** (1.24× faster) |
| R4 (batch of 24) | "no change" (~1.09×) | 11.02 ms (9.39..11.66) | 10.89 ms (9.45..12.12) | 5 → 5 | **0.988×** | `[0.880, 1.064]` | **holds** (no change) |
| R5 c=8 throughput | "no change" (10.3 vs 10.4/s) | 14.05 req/s (12.8..14.1) | 17.45 req/s (16.5..18.0) | 5.3 → 4.2 | **1.242×** | `[1.223, 1.285]` | **does not hold** (+24 %) |
| R5 c=8 overall p50 | — | 163.5 ms (150.5..183.1) | 81.65 ms (75.3..86.2) | — | **0.499×** | `[0.482, 0.525]` | — |
| R5 c=8 MySQL CPU (15 s) | ~8 cores saturated | 125.0 s (121.4..127.8) | 120.0 s (118.5..123.3) | — | **0.960×** | `[0.947, 0.972]` | **holds** (still CPU-saturated) |

**Architectural takeaway**: the statement "DAL v2 does not change storefront reads at 150k" is **disproven** — levers deliver 1.24× to 2.15× faster reads and +24 % c=8 throughput at 150k. The **architectural conclusion** that DAL v2 cannot substitute for OpenSearch at 150k **holds**: at 17.4 req/s and 120 s of MySQL CPU in 15 s (8 saturated cores, R3b p50 = 1.95 s), it is still 43× below O1a (`756 req/s`, 2.44 s MySQL CPU).

### 3d. OpenSearch HTTP cache window (`docs/44` "HTTP cache interaction")

Tested on `orm_spike` with synchronous projection (`READ_STORE_PROJECTOR_STORES=opensearch-source`, `READ_STORE_PROJECTOR_MODE=sync`, `SHOPWARE_ES_SOURCE_DOCUMENT=1`, `SHOPWARE_HTTP_CACHE_ENABLED=1`, `rs_w10_o1a_orm_spike__product`, 1 shard, `refresh_interval=1s`). Raw logs: `docs/benchmark-results/wave10-d/3d-cache-window.jsonl` and `3d-http-cache-poison.jsonl`.

1. **Store API listing (`GET /store-api/product-listing/{cat}?order=name-asc&limit=24&p=1`, 10 trials per mode)**:
   - **`refresh=false` (default)**: **9 of 10** immediate requests after `product.repository->update()` returned the **old** product name (only 1 trial happened to cross OpenSearch's 1 s background refresh tick).
   - **Explicit `_refresh` after sync write**: **0 of 10** stale responses; `_refresh` call latency **10.0 ms** median (not safe under high concurrent write volume because every call forces a segment flush).
   - **Real OpenSearch `refresh=wait_for`** (10 staggered single-doc index calls against the 1-shard index with `refresh_interval=1s`): **0 of 10** stale responses; write latency **857 ms** median (range `844.5..1,037.0 ms`).
2. **Storefront HTTP cache poisoning (`GET /navigation/{cat}?order=name-asc`, immediate `CacheInvalidator::invalidate(..., true)` after write, 5 trials per mode)**:
   - **`refresh=false` (default)**: **5 of 5** trials rendered a **mixed/stale response** — the product's SEO URL came fresh from MySQL (`…-NEW`), while the product title, image alt, card name, and analytics JSON in the very same `<a>` element came stale from OpenSearch `_source` (`…-OLD`). Shopware's `HttpCacheKernel` stored that stale page, and a second request **1.3 s later** (past OpenSearch's 1 s refresh) served the **poisoned HTTP cache hit** (`1.44..1.91 ms`) still containing `…-OLD` in **5 of 5** trials.
   - **Explicit refresh before cache invalidation**: **0 of 5** immediate stale pages and **0 of 5** poisoned HTTP cache entries (`1.31..1.70 ms` cache hits all contained `…-NEW` only).

**Verdict**: the concern in `docs/44` **holds** (confirmed as a real HTTP cache poisoning bug when cache invalidation fires faster than OpenSearch's `refresh_interval`). Mitigations for E6.02/E6.04: either keep Shopware's delayed HTTP cache invalidation delay strictly larger than OpenSearch's `refresh_interval` (default 1 s, e.g. `>= 2–5 s`), or trigger cache invalidation from an OpenSearch post-refresh / async projector worker rather than synchronously on the write request, or use `refresh=wait_for` only on low-frequency admin writes (accepting up to `refresh_interval` write latency).

### 3e. O1 vs O1a vs `store-w10-opensearch-valkey` (5k and 150k)

Exact commands from doc 47 (`A`), 10 paired AB/BA rounds each (30 iters/round for latency; 15 s at c=8 for R5 load with MySQL cgroup `cpu.stat` `usage_usec`).

#### O1 vs O1a on `read_store_large` (150k products)

| Metric | Baseline (`docs/47`) | O1 median (min..max) | O1a median (min..max) | Stmts | Ratio O1a / O1 | 95 % CI | Verdict |
|---|---|---:|---:|---:|---:|---|---|
| S2 / R1 (detail) | 0.44× (7.4 → 3.3 ms) | 7.64 ms (7.21..10.78) | 3.37 ms (2.54..4.81) | 4 → 1 | **0.440×** | `[0.379, 0.491]` | **holds** |
| S1 / R2 (listing) | 0.67× (11.1 → 7.4 ms) | 10.88 ms (9.77..12.61) | 7.19 ms (6.78..8.99) | 2 → 0 | **0.661×** | `[0.654, 0.785]` | **holds** |
| R3b (word search) | 0.89× (24.4 → 21.8 ms) | 24.66 ms (22.94..30.44) | 22.02 ms (19.90..25.48) | 2 → 0 | **0.893×** | `[0.811, 0.996]` | **holds** |
| R4 (batch of 24) | 0.66× (13.4 → 8.8 ms) | 14.41 ms (12.16..17.59) | 9.32 ms (8.21..12.20) | 4 → 1 | **0.646×** | `[0.582, 0.776]` | **holds** |
| R5 c=8 throughput | 1.50× (512 → 768/s) | 532.0 req/s (511.2..580.5) | 756.1 req/s (675.3..842.3) | 2.7 → 0.5 | **1.421×** | `[1.318, 1.484]` | **holds** |
| R5 c=8 MySQL CPU (15 s) | −85 % (0.15×) | 15.07 s (14.94..15.47) | 2.44 s (2.31..2.48) | — | **0.162×** (−83.8 %) | `[0.156, 0.163]` | **holds** |
| R5 c=8 R1 / R2 / R3b p50 | — | 8.95 / 13.1 / 28.85 ms | 3.90 / 8.90 / 24.65 ms | — | 0.436× / 0.679× / 0.854× | `[0.411,0.461]` / `[0.664,0.731]` / `[0.828,0.916]` | **holds** |

#### O1 vs O1a and O1a vs `store-w10-opensearch-valkey` on `orm_spike` (5k products)

| Comparison & metric | Baseline (`docs/47`) | A median (min..max) | B median (min..max) | Stmts | Ratio B / A | 95 % CI | Verdict |
|---|---|---:|---:|---:|---:|---|---|
| O1 → O1a: S2 / R1 | 0.41× | 8.34 ms (6.75..12.63) | 3.46 ms (2.50..5.15) | 4 → 1 | **0.415×** | `[0.326, 0.450]` | **holds** |
| O1 → O1a: S1 / R2 | 0.70× | 10.05 ms (7.80..12.29) | 6.92 ms (6.26..8.02) | 2 → 0 | **0.688×** | `[0.579, 0.731]` | **holds** |
| O1 → O1a: R3b | 0.75× | 13.75 ms (11.18..19.69) | 10.34 ms (8.91..14.75) | 2 → 0 | **0.752×** | `[0.683, 0.809]` | **holds** |
| O1 → O1a: R4 | 0.68× | 13.37 ms (13.12..16.12) | 9.03 ms (7.83..9.90) | 4 → 1 | **0.676×** | `[0.607, 0.711]` | **holds** |
| O1 → O1a: R5 c=8 rps | 1.85× | 733.0 req/s (661..825) | 1,354 req/s (1,207..1,528) | 2.7 → 0.5 | **1.847×** | `[1.704, 1.954]` | **holds** |
| O1 → O1a: R5 c=8 MySQL CPU | −82 % | 18.32 s (17.86..18.73) | 3.38 s (3.34..3.47) | — | **0.185×** (−81.5 %) | `[0.182, 0.189]` | **holds** |
| O1a → composed: S2 / R1 | 0.04× (Valkey) | 3.95 ms (2.28..5.05) | 0.155 ms (0.12..0.36) | 1 → 0 | **0.039×** | `[0.030, 0.050]` | **holds** |
| O1a → composed: R4 (mget 24) | 0.09× (Valkey) | 9.34 ms (8.14..10.51) | 0.82 ms (0.57..1.61) | 1 → 0 | **0.088×** | `[0.080, 0.095]` | **holds** |
| O1a → composed: S1 / R2 | ~tie | 7.39 ms (6.48..10.47) | 6.45 ms (5.58..8.51) | 0 → 0 | **0.873×** | `[0.773, 1.022]` | **holds** (within noise) |
| O1a → composed: R3b (standalone) | ~2.3× slower | 10.46 ms (8.70..13.09) | 23.88 ms (21.55..35.13) | 0 → 2 | **2.283×** | `[1.920, 2.536]` | **holds** |
| O1a → composed: R5 c=8 rps | ~0.54× (SQL keyword) | 1,392 req/s (1,227..1,513) | 753.0 req/s (715.5..764.5) | 0.5 → 0.4 | **0.541×** | `[0.514, 0.559]` | **holds** |
| O1a → composed: R5 c=8 MySQL CPU | ~22× higher | 3.30 s (3.05..3.36) | 73.63 s (70.02..75.90) | — | **22.347×** | `[21.506, 23.049]` | **holds** |

### 3f. Production-like storefront walk (`docs/50`, E's setup)

Full 10-step customer journey (`home → listing → search → detail → add_to_cart → cart → register_page → register_guest → confirm → order`) with HTTP cache, OpenSearch, primary + read replica, TLS, and background workers stopped. Each round ran `/tmp/wave10-e/timing.py <url> 5 1` (5 measured walks + 1 warm-up per round × 10 AB/BA rounds = 50 measured walks per stack; **0 failures** across all 200 measured walks).

#### MariaDB (primary + replica) vs PostgreSQL direct (primary + replica, persistent + plan cache)

| Step | Baseline (`docs/50`) | MariaDB median (min..max) | PG direct median (min..max) | Ratio PG / MariaDB | 95 % CI | Verdict |
|---|---|---:|---:|---:|---|---|
| `home` (cached) | ~1.0× | 23.0 ms (22..28) | 23.0 ms (22..30) | **1.000×** | `[0.979, 1.022]` | **holds** |
| `listing` (cached) | ~1.0× | 14.0 ms (13..19) | 14.0 ms (14..18) | **1.000×** | `[0.903, 1.000]` | **holds** |
| `detail` (cached) | ~1.0× | 11.0 ms (11..15) | 11.5 ms (11..15) | **1.045×** | `[1.000, 1.091]` | **holds** |
| `search` (OpenSearch) | ~1.0× | 32.0 ms (30..56) | 33.0 ms (31..56) | **1.031×** | `[1.000, 1.061]` | **holds** |
| `register_page` | ~1.1× | 68.5 ms (65..111) | 75.0 ms (72..129) | **1.095×** | `[1.043, 1.131]` | **holds** |
| `cart` | ~1.1× | 82.0 ms (80..135) | 91.0 ms (86..168) | **1.110×** | `[1.048, 1.159]` | **holds** |
| `register_guest` / `confirm` | ~1.16× | 106.0 ms (102..205) | 123.0 ms (112..292) | **1.160×** | `[1.093, 1.219]` | **holds** |
| `add_to_cart` | ~1.18× | 132.5 ms (126..248) | 157.0 ms (149..310) | **1.185×** | `[1.104, 1.246]` | **holds** |
| `order` | ~1.35× | 166.5 ms (160..321) | 228.5 ms (208..367) | **1.372×** | `[1.162, 1.426]` | **holds** |
| **Full walk total** | ~1.19× | **636.5 ms** (613..1,113) | **749.5 ms** (720..1,521) | **1.178×** | `[1.088, 1.227]` | **holds** |

#### PostgreSQL direct (persistent + plan cache) vs PostgreSQL via PgBouncer 1.26.1 (transaction mode, non-persistent)

Previously unmeasured in doc 50 (E5.02 open item). All 100 measured walks completed with 0 failures.

| Step | PG direct median (min..max) | PG + PgBouncer median (min..max) | Ratio PgB / direct | 95 % CI |
|---|---:|---:|---:|---|
| `home` / `listing` / `detail` (cached) | 24.0 / 15.0 / 12.0 ms | 28.5 / 20.0 / 17.0 ms | 1.188× / 1.333× / 1.417× | `[1.120,1.229]` / `[1.267,1.367]` / `[1.333,1.478]` |
| `search` (OpenSearch) | 35.0 ms (32..38) | 41.5 ms (36..51) | **1.186×** | `[1.113, 1.235]` |
| `add_to_cart` | 158.5 ms (143..184) | 203.5 ms (180..225) | **1.284×** | `[1.164, 1.419]` |
| `register_guest` / `confirm` | 132.5 ms (117..146) | 171.0 ms (141..186) | **1.291×** | `[1.112, 1.482]` |
| `order` | 226.0 ms (203..244) | 285.0 ms (245..312) | **1.261×** | `[1.121, 1.387]` |
| **Full walk total** | **771.0 ms** (726..844) | **1,012 ms** (861..1,066) | **1.312×** | `[1.128, 1.384]` |

PgBouncer in transaction mode adds ~4–5 ms per cached read (new non-persistent connection to PgBouncer per PHP request) and 26–29 % on checkout writes (no PHP-side plan cache), putting total walk latency at ~1.31× direct PostgreSQL (~1.55× MariaDB) with 0 errors.

---

## 4. Second machine

Per the wave 10 decision (`handoffs/wave10/README.md`), no second machine was used. Every number in this document still comes from one developer host (Apple M4 Pro, Podman AppleHV VM), now with measured A/A noise floors and paired AB/BA 95 % bootstrap confidence intervals rather than an unmeasured "~10 % rule of thumb". Any upstream performance budget for E5 or E6 should still be verified on target Linux bare-metal / cloud hardware before release.
