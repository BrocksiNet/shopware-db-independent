# Presentation Review (`presentations/` vs. `docs/` & External Readability)

## Resolution map — 25 November 2026

The review below describes the previous 23-slide architecture deck and 35-slide findings deck. The revised output has **15 architecture slides and 25 engineering slides**, organized by topic. Original observations remain below for traceability.

| Review item | Resolution in the revised decks |
| --- | --- |
| 1.1 Overwritten notes and duplicate source | Removed the stale overwrite and duplicate append. Architecture 5 retains the source-hydration warning and event responsibilities. Per-slide sources also deduplicate by URL. |
| 1.2 Batching semantics, tests and rerun | Engineering 13 distinguishes changing a key from repeating its unchanged WHERE value. Engineering 15 links tests at `46a47f1a7c9`, reports 7 tests / 19 assertions per engine, and shows the final 27/29-statement rerun with all four medians. Removed the stale rebenchmark warning. |
| 1.3 Projection timing | Engineering 11 uses the paired 5k listing result, 10.82 to 4.77 ms, ratio 0.441 and CI [0.411, 0.520]. Combined optimizations remain explicit. |
| 1.4 Recorded deadlocks | Engineering 20 uses 31 to 0 and the recorded throughput change. Sources distinguish the concurrent run from the separate sequential cost profile. |
| 1.5 Stale notes and backlog | Both cover notes match the new order. Engineering 25 includes source hydration, replica writes, stock and binary binding. The prototype is built; production hardening remains. |
| 1.6 Operational omissions and cleanup | Architecture 10 notes include uncached storefront and bulk-write gaps. README uses a plain Python rebuild command. Removed the obsolete Wave 9 preview. Manifest titles normalize whitespace and list only displayed excerpts. |
| Bridge from the video | Architecture 2 explains why 150k products motivated the work and defines the two search paths. |
| Internal jargon and errata | Covers, launcher and chapter titles use architecture concepts. Research codes and errata stay in source records or contextual notes. Concurrency is spelled out in the main comparison. |
| Chronological context switching | Architecture follows motivation, design, evidence and decisions. Engineering has three continuous chapters: OpenSearch (2–8), DAL (9–16), PostgreSQL and cross-engine bugs (17–25). |
| Side experiments | Architecture 12 introduces the newsletter port as a separate route-design experiment. Engineering 8 introduces the standalone store prototypes before the MongoDB lifecycle race. |
| Duplicate detail | Headline comparisons and measurement method live in architecture. PHP, SQL, detailed mapping/cache probes and suite breakdowns live in engineering, with chapter links between decks. |

The engineering cover includes its chapter map, so it does not need a separate agenda slide. Related prefetch, partial-read and consistency examples are combined to retain the substance within 40 slides. Earlier named links to merged slides remain aliases; former code-deck headline/method links redirect to their architecture counterparts.

Browser review covered all 40 slides, code highlighting, source and note drawers, chapter navigation, merged anchors and return to slide 1. Pinned source/doc targets and local links were checked against the repository snapshots. These checks validate the presentations; the recorded Shopware benchmarks and integration suites were not rerun.

---

## Original review

Reviewed against `docs/` (snapshot `ce36f6c`), `video/build.py` (the assumed viewer baseline), and the pinned `instance/` commits (`c8c6866ac19`, `91b22d0abbb`, `0ed724decae`).

## TL;DR

- **Technical accuracy of Wave 10 evidence is very high.** Generated HTML and `sources.json` match `build.py` byte-for-byte, all 24 pinned code excerpts and GitHub links resolve cleanly, and every Wave 10 metric matches `docs/46`–`docs/51` and the raw `wave10-d/*.summary.json` files.
- **There are 1 build bug and 4 factual/outdated mismatches** in the earlier slides (`live-parts` overwritten speaker notes + duplicate source, superseded batch-update test counts & rebenchmark warning, superseded 5k S1 projection timing vs. `docs/51`, `45` vs. `31` recorded deadlocks, and stale Wave 8/9 speaker notes).
- **For an external viewer who only watched the video, the structure is hard to follow.** Both decks read like an internal Wave 10 changelog/errata memo layered in reverse chronological order on top of Wave 8/9 decks. They open with undefined jargon (`O1a`, `Wave 10`, `doc 51`, `Walkthrough with Jonas`), correct Wave 9 claims the viewer never saw, switch topics 10+ times in `core-findings.html`, and duplicate 6 topics across 58 slides.

---

## Part 1 — Factual & Technical Findings Against `docs/`

### 1.1 Build bug: overwritten speaker notes & duplicate source (`architecture.html` #8 `live-parts`)

In `presentations/build.py:664-675`, leftover patch lines right after the rewritten `base[6]` slide undo the Wave 10 update:

- Line 673: dead no-op `.replace('Keep live calculation and checkout validation.', ...)` (string no longer exists in `base[6]['body']`).
- Line 674: **overwrites `base[6]['notes']`** — replacing Wave 10's explicit warning *"Do not present that guard as new O1a behaviour: O1a preserves existing OpenSearch queries"* with the older note *"Preserve rounding guards and explicit SQL fallback."*
- Line 675: appends `docs/47-o1a-source-hydration.md` a **second time** to slide 8's Sources sidebar (`presentations/sources.json:883-897`).

**Fix:** Delete lines 673–675 in `presentations/build.py` and rebuild.

### 1.2 Outdated batching status (`core-findings.html` #26 `unique`, #28 `batch-tests`, `README.md:47`)

- **Current slides / README:**
  - Slide 28 (`build.py:353-357`) says `5 tests / 16 assertions on each of four engines` and warns *"Timings in docs 33–36 predate these correctness changes. Rebenchmark the final implementation before quoting a current gain."* (`presentations/README.md:47` repeats this.)
  - Slide 26 (`build.py:349`) says *"updates touching any primary-key or unique-index column stay single-row."*
- **What `docs/35`, `docs/36`, and `docs/37` actually record:**
  - Commit `46a47f1a7c9` (right after pinned `CORE_REF = c8c6866ac19`) fixed a bug where repeating unchanged key columns (`product_id`/`version_id`) blocked all S4 batching, expanding the suite to **7 tests / 19 assertions** across all four engines (`docs/37-review-round-2.md:64`).
  - The rule is updates **changing** a primary-key or unique-index column (`docs/37-review-round-2.md:36-37`), not merely containing one.
  - S4 **was rebenchmarked** after review round 2 (`docs/35-orm-spike-fair-write.md:230-327`, `docs/36-dal-v2-batched-update-postgresql.md:84-90`): **27 statements** on MySQL (`46.57 ms`, `0.56×` DAL), MariaDB (`48.52 ms`, `0.56×`), SQLite (`276.55 ms`, `0.83×`), and **29 statements** on PostgreSQL (`69.29 ms`, `0.85×` DAL), with 4 `SAVEPOINT`/`RELEASE SAVEPOINT` statements and no measurable latency penalty.

### 1.3 Superseded 5k S1 projection timing (`core-findings.html` #23 `projection`)

- **Current slide (`build.py:323`):** Quotes `docs/34` MySQL S1 listing `12.42 to 3.78 ms` (`0.30×`) with all levers + projection.
- **Canonical update in `docs/51-timing-reliability.md` (§3b):** Remeasured that exact paired MySQL 5k S1 comparison as **`10.82 to 4.77 ms` (`0.441×`, 95% CI `[0.411, 0.520]`)** with verdict **`holds smaller`** than doc 34's `0.30×`. Because `index.html` and `README.md` declare doc 51 as the canonical timing source, slide 23 should reflect doc 51 (or explicitly note the narrower paired result).

### 1.4 "Recorded run" deadlock count mismatch (`core-findings.html` #29 `locks`)

- **Current slide (`build.py:362`):** *"The recorded run moved from 45 deadlocks to 0, with added sequential write cost."*
- **What `docs/19-postgresql-parallel-writes.md:142-151` actually says:** The **recorded** table moved from **31 deadlocks to 0** (`1.59 → 3.09 req/s`), whereas `45` was *"the first session's informal check … not recorded."* (`docs/core-findings.md` row 10 also carried `45`, which is where the slide likely pulled it from.) Also, the `~40 ms` sequential write cost cited in the speaker note comes from `docs/26` / `docs/summary.md`, not `docs/19`.

### 1.5 Stale Wave 8 / Wave 9 speaker notes & outdated summary slide (`core-findings.html` #1, #34)

- **Slide 1 (`findings`, `build.py:301`):** Speaker note still describes the old Wave 8 order (*"The main route covers key decoding, reads, batching and semantics. The final slides contain smaller findings and the source map"*), whereas Wave 10 now leads (slides 3–15) and those topics are chapter 3 (slides 20–33).
- **Slide 34 (`priorities`, `build.py:385, 600, 890`):**
  - The speaker note still contains the concatenated Wave 9 line *"The larger-read bottleneck needs the O1+ experiment"* — directly contradicting Wave 10 (and slide 15's own note: *"Do not repeat the former 'build O1a' next step"*).
  - The slide body still lists only the Wave 8 DAL backlog (missing O1a/E6 and Wave 10 core bugs like replica `RETURNING` writes, stock `SET` order, and `BlobField` binary binding).

### 1.6 Minor omissions & housekeeping

- **`architecture.html` #20 (`postgresql-stack`):** Reports the cached + OpenSearch customer walk (`1.178×` MariaDB) and PgBouncer (`1.312×`), but omits `docs/51` §3a's uncached storefront (`1.13–1.30×`) and bulk-write (`1.81×` sequential / `0.34×` at `c=4`) gap — worth mentioning in speaker notes so the write caveat stays visible.
- **`presentations/README.md:70`:** Rebuild command leaks a local shell wrapper (`rtk proxy python3 presentations/build.py` instead of `python3 presentations/build.py`).
- **`presentations/previews/wave9-findings.jpg`:** Leftover 28-slide Wave 9 screenshot sitting next to the current 35-slide `wave10-findings.jpg`.
- **`presentations/sources.json:1162`:** Double/trailing space in `"What the experiment  found in core "` from `<br>` / `<span>` tag stripping in `build.py:916`.
- **Handled better than `docs/` itself (worth noting):** The slides correctly use Shopware's configured `50,000` OpenSearch field limit from `docs/48` (where `docs/46:150` still cited the default `1,000`), correctly state `50 findings` (where `docs/46:175` still says `40`), and avoid hardcoding the mismatched PgBouncer patch version (`1.25.2` in `docs/50` vs. `1.26.1` in `docs/46`/`docs/51`).

---

## Part 2 — Structure & External-Audience Review

### 2.1 The gap between what the video taught and where the decks start

Checking `video/build.py` shows exactly what an external viewer knows coming into `presentations/`:

| Known from the video (Waves 1–8) | Assumed on Slide 1 of `presentations/` (not in the video) |
| --- | --- |
| Question 1: Can Shopware run on PostgreSQL / SQLite? (Yes: 910 migrations, 804 DAL tests, 1.1–1.5× storefront on PG, bulk writes 2× slower) | **What happened after Wave 8** (large-catalog 150k read-store research in Waves 9–10) |
| Question 2: Should we replace the DAL with an ORM or raw SQL? (No: keep DAL, improve it via DAL v2; 34 core findings) | **What `O1` and `O1a` mean** — used in the first sentence of `index.html` and `architecture.html` #1 without ever being formally defined |
| High-level concepts (DAL, PostgreSQL, SQLite, migrations, DAL v2) | Internal shorthand: **`Wave 9`**, **`Wave 10`**, **`doc 51`**, **`doc 34`**, **`E5`/`E6`**, **`S1`–`S4`**, **`R3b`/`R4`/`R5`**, **`c=8`**, **`rs_document`**, **`_mget`** |
| Clean narrative arc (problem → experiment → numbers → verdict) | **Internal errata** (*"Do not repeat the wave 9 claim that DAL v2 has no effect at 150k"*, *"The O1a gate is closed"*) referencing a prior Wave 9 draft the viewer never saw |
| General external audience | Personalization (`Walkthrough with Jonas` on `index.html` and `core-findings.html` #1) |

### 2.2 Six specific structural & comprehension issues

1. **No bridge from the video ("Wait, why are we suddenly talking about OpenSearch?")**
   The video ended with *"Keep the DAL, make it better."* Opening Slide 1 with *"O1a is now built and measured. The read/write split holds..."* leaves an external reader wondering what problem triggered a read/write split and why OpenSearch is suddenly the main subject. One missing framing sentence (*"The video tested 5k products in SQL. Next we asked: what breaks at 150k products, and how far can OpenSearch + DAL v2 take storefront reads?"*) would unlock the entire presentation.

2. **Undefined internal codenames in titles and headlines**
   - `O1` / `O1a` appear in slide titles (`O1a changes hydration...`, `The O1a gate is closed`, `O1a removes SQL hydration...`) before the reader is told `O1` = current OpenSearch ID lookup + SQL hydration and `O1a` = embedding the product document in OpenSearch `_source` to skip SQL hydration.
   - `Wave 9` / `Wave 10` / `doc 51` / `E5` / `E6` are project-tracking artifacts, not architecture concepts. Putting them in cover titles and chapter headings makes the deck feel like an internal status update rather than a self-contained technical story.
   - Workload codes (`S1`, `S2`, `S4`, `R3b`, `R4`, `R5`, `c=8`) appear in tables and notes without a legend.

3. **Reverse-chronological layering causes heavy context switching**
   Because `build.py` prepended Wave 10 and Wave 9 chapters onto the original Wave 8 deck, both decks move **backwards in time** instead of **forwards in understanding**:
   - **`architecture.html` (23 slides):** Jumps straight into O1a `_source` hydration and custom-field byte extrapolations (#2–#9) → drops back to DAL dialect / ID binding / compatibility shim / newsletter port / DAL v2 (#10–#19) → abruptly jumps back to Wave 10 PostgreSQL operational results (#20) and A/A timing methodology (#21) → decisions (#22).
   - **`core-findings.html` (35 slides):** Switches domain **10+ times** because slides are grouped by *when* they were found (Wave 10 → Wave 9 → Waves 1–8) rather than *what subsystem* they affect:
     > Read-store (#3) → DAL v2 (#4) → Read-store (#5–#7) → **PostgreSQL** (#8–#11) → **Read-store** (#12) → **Methodology** (#13) → **PostgreSQL** (#14) → Mixed gates (#15) → **Read-store + MongoDB** (#16–#19) → **DAL v2** (#20–#28) → **PostgreSQL** (#29–#30) → **DAL v2** (#31) → **PostgreSQL** (#32) → Misc (#33).

4. **Internal errata placed in headline slots**
   Slide 4 of `core-findings.html` and the cover/launcher notes spend prominent space correcting an earlier Wave 9 benchmark mistake (*"The old wave 9 DAL v2 run omitted the levers"*). For someone who never saw Wave 9, this creates confusion instead of clarity. Just state the true, current comparison once: *"At 150k products, DAL v2 improves SQL reads by 1.24–2.16×, yet OpenSearch is still ~43× faster on mixed storefront load."* (Keep the Wave 9 erratum in a footnote or speaker note for insiders.)

5. **Unintroduced side-characters**
   - **`MongoDbStorage.php` (`core-findings.html` #18):** MongoDB suddenly appears on slide 18 with no prior mention that MongoDB was prototyped as an alternative standalone read store. An external viewer has no context for why MongoDB is in a Shopware/PostgreSQL/OpenSearch deck.
   - **Newsletter storage port (`architecture.html` #16–#17):** Jumps from PostgreSQL SQL compatibility shims (#15) straight into `NewsletterSubscribeRoute` without framing it as *"a concrete small-slice proof of decoupling a route from the DAL, and how public entity events constrain DTO boundaries."*

6. **Heavy duplication across two decks (58 slides total)**
   Six core topics appear in **both** `architecture.html` and `core-findings.html` with overlapping tables/metrics:
   - O1a throughput, MySQL CPU & parity (`arch` #9 vs. `core` #3, #15)
   - Custom-field / `_source` size limits (`arch` #5 vs. `core` #7)
   - Partial `_update` erasing unstored fields (`arch` #6 vs. `core` #6)
   - PostgreSQL stack & `386 → 90` suite failures (`arch` #20 vs. `core` #14)
   - Paired AB/BA + A/A timing reliability (`arch` #21 vs. `core` #13)
   - Projection / DTOs (`arch` #18 vs. `core` #23)

   Meanwhile, `architecture.html` is too detailed in places for a high-level walkthrough (custom-field extrapolation tables, PHP interface code) while `core-findings.html` mixes architecture methodology, PostgreSQL bugs, OpenSearch bugs, and DAL optimizations in one chronological stream.

---

## Part 3 — Suggested Easier Structure

### Core design principles for an external-friendly deck

1. **Start where the video ended.** Open with a 1-slide recap (*"In the video: PostgreSQL works & we keep the DAL. Since then we tested three real-world stress tests: 150k-catalog storefront reads, full non-DAL PostgreSQL suites + production stack, and paired benchmark reliability."*).
2. **Organize by topic / question, never by wave number.** Remove `Wave 9`, `Wave 10`, `doc 51`, `E5/E6`, and `Jonas` from titles and body copy (keep doc/commit links in the `S` Sources drawer for traceability).
3. **Replace codenames with plain English.**
   - `O1` → **Current OpenSearch path** (OpenSearch IDs + SQL hydration)
   - `O1a` → **OpenSearch `_source` hydration** (product document in `_source`, no SQL hydration)
   - `S1`/`S2`/`S4`/`R3b`/`R5`/`c=8` → **Listing**, **Detail**, **50-product bulk write**, **Word search**, **Mixed storefront (8 concurrent clients)**
4. **State the current truth directly.** Drop Wave 9 self-corrections from slide headlines; put historical errata in speaker notes or a single methodology footnote.
5. **Separate "The Story & Decisions" from "The Engineering Deep-Dive"** cleanly so neither deck repeats the other.

---

### Recommended Two-Deck Structure (38–40 slides total, zero chronological whiplash)

#### Deck 1 — **The Story & Architecture** (~16 slides · 20–25 min live walkthrough)
*For anyone who watched the video — architects, engineering leads, or external contributors.*

| # | Proposed Slide | Plain-English Goal | Maps from current slides |
| --- | --- | --- | --- |
| 01 | **Title: Beyond the Video — Scaling Reads, Hardening the DAL & PostgreSQL** | Clean cover + 4-part agenda; no wave/doc jargon | `arch` #1 |
| 02 | **Where the video left off — and the 3 new questions** | Bridge slide: Video proved PostgreSQL + "keep DAL" at 5k. New questions: (1) How do reads scale at 150k? (2) Does PostgreSQL hold up across all 8,072 integration tests & a prod stack? (3) Which core bugs & DAL improvements pay off today? | **New bridge slide** |
| 03 | **Why 150k products change the read story** | Show DAL vs. DAL v2 vs. OpenSearch at 150k side by side in one chart/table: DAL v2 cuts SQL reads by ~2×, yet OpenSearch is still ~43× faster on mixed storefront load | `core` #4 (reframed without Wave 9 errata) |
| 04 | **The idea: hydrate products directly from OpenSearch `_source`** | Side-by-side diagram: *Current path* (OpenSearch IDs → SQL hydration → events) vs. *New path* (OpenSearch hits carry product document → hydrate → events; SQL only as counted fallback) | `arch` #2 + #3 merged |
| 05 | **What goes in the document vs. what stays live** | One-document-per-product context maps + clear split: prices/purchase limits stay live via loaded events; stock & query membership come from the index; checkout always validates against SQL | `arch` #4 + #8 merged |
| 06 | **Measured payoff at 150k products** | Headline paired results: `50/50` Store API parity, `1.42×` mixed throughput (`532 → 756 req/s`), `−84%` MySQL CPU, `−34%` listing latency, `−56%` detail latency | `arch` #9 + `core` #3 merged |
| 07 | **Three production constraints we uncovered** | One crisp synthesis slide covering the 3 real limits: (1) full re-index required (partial `_update` erases unstored fields), (2) payload/custom-field byte budgets (`0.42 → 53.5 GB`), (3) refresh-before-HTTP-cache-invalidation to prevent stale-cache poisoning | `arch` #5 + #6 + `core` #12 summarized |
| 08 | **How PostgreSQL fits without a rewrite** | The 3 clean boundaries (`SqlDialect`, `IdBinding`, compatibility shim) + connection/dialect split — connects directly back to the video's Question 1 | `arch` #10 + #12 + #13 + #14 + #15 distilled into 2 slides (#8–#9) |
| 09 | **PostgreSQL beyond DAL: 8,072 tests & a production-like stack** | Integration suite progress (`386 → 90` PG-only failures across 5 suites), prod walk (`1.18×` MariaDB, PgBouncer `1.31×`, 200 walks / 0 failures), and the remaining gaps (bulk writes `1.81×`, CustomEntity DDL, collations) | `arch` #20 + `core` #14 merged |
| 10 | **Improving the DAL without breaking plugins** | How DAL v2 sits behind `EntityRepository` & `Criteria` (window totals, projection/DTOs, key fix, safe batching) + the Newsletter route lesson on where public entity events cap decoupling | `arch` #16 + #17 + #18 + #19 distilled into 2 slides (#10–#11) |
| 11 | **How we trust the numbers (measurement discipline)** | 1 slide on paired AB/BA rounds, 95% bootstrap CIs, and A/A noise floors (`±1.7%` CLI to `±11.8%` HTTP) — explains *why* every headline number in the deck is trustworthy | `arch` #21 |
| 12 | **What to do next: 3 concrete decisions** | (1) Productize `_source` hydration with write/cache/size guards, (2) Cherry-pick safe DAL & core bug fixes now (zero breaking change), (3) Decide PostgreSQL support scope (replica/stock/blob fixes + remaining 90 tests) | `arch` #22 |
| 13 | **Reading map & deep-dive links** | Links into Deck 2 by topic (Read Store / DAL / PostgreSQL) + research docs | `arch` #23 |

*(Slides #8–#11 expand cleanly to ~15–16 slides total when keeping the code/diagram breathing room.)*

#### Deck 2 — **Engineering Deep-Dive: Code & Core Findings** (~22–24 slides · grouped strictly by subsystem)
*For core engineers who want the actual PHP/SQL bugs, trade-offs, and benchmarks — jump straight to whichever chapter you care about.*

- **Cover & Subsystem Map (2 slides):** 3 clear chapters instead of 3 chronological waves:
  1. **Chapter 1 — Read Store & OpenSearch Hydration (7 slides)**
     - `SourceDocumentEntityReader` & buffer lifecycle (`core` #5)
     - Route SQL accounting: why removing product SQL still leaves surrounding route queries (`core` #17)
     - Partial `_update` erasing unstored search fields (`core` #6)
     - Custom-field mapping vs. `_source` payload growth (`core` #7)
     - HTTP cache poisoning & refresh ordering (`core` #12)
     - Variant sibling expansion & DAL keyword aggregation over-count (`core` #16, #19)
     - Storage port contract & generation-swap safety — briefly introducing the standalone-store prototypes (incl. MongoDB) *before* showing the cursor-drop bug (`arch` #7 + `core` #18)
  2. **Chapter 2 — DAL Performance & Write Semantics (8 slides)**
     - Key-name mismatch defeating prefetch cache (`core` #20 + #21)
     - Window totals (`COUNT(*) OVER()`) (`core` #22)
     - Field projection / DTOs + inherited-association bug (updated with `docs/51` `0.441×` paired result) (`core` #23 + #24)
     - Batched updates: SQL shape, unique-constraint ordering, savepoint failure attribution, and **updated** `7 tests / 19 assertions` + post-review-round-2 timings (`core` #25–#28)
     - Write profiler breakdown (`core` #31)
  3. **Chapter 3 — PostgreSQL & Cross-Engine Core Bugs (7 slides)**
     - `INSERT … RETURNING` routed to read replica (`core` #8)
     - `UPDATE` right-hand-side assignment order in `StockStorage` (`core` #9)
     - `BlobField` binary parameter binding (`core` #10)
     - Parallel indexer lock ordering (fixing `31` vs. `45` recorded deadlocks) (`core` #29)
     - Per-connection result-type caching (`core` #32)
     - Database defaults & smaller portability fixes (`NULL` order, collations, `GROUP BY`, `rowCount()`, default sorting, cache cleanup) (`core` #11, #30, #33)
     - Full integration suite breakdown (`386 → 90`) & prioritized core worklist (`core` #14, #34 updated, #35)

---

### Quick-Win Option (If You Don't Want a Full Reorg Right Now)

If you want to keep the current two-deck layout and fix the biggest pain points with minimal effort:

1. **Fix the factual bugs first:**
   - Remove the 3 stale patch lines on `build.py:673-675` (`live-parts` notes + duplicate source).
   - Update `core-findings` #26 & #28 (and `README.md:47`) to `7 tests / 19 assertions`, "changing" key columns, and the post-review-round-2 rebenchmark from `docs/35`–`docs/37`.
   - Update `core-findings` #23 with `docs/51`'s paired `0.441×` (`10.82 → 4.77 ms`) result.
   - Correct `core-findings` #29 from `45` to `31` for the recorded run.
   - Update stale speaker notes on `core-findings` #1 and #34 (and refresh #34's body beyond Wave 8).
   - Clean up `README.md:70` (`rtk proxy`), `previews/wave9-findings.jpg`, and the double space in `sources.json:1162`.
2. **Add a 1-slide "Since the video" bridge + glossary right after Slide 1 of `architecture.html`** that explicitly defines *OpenSearch `_source` hydration (O1a)* vs. *current OpenSearch + SQL (O1)* and explains why 150k reads motivated the work after the video.
3. **De-jargonize `index.html` and Slide 1 of both decks:** Remove `Walkthrough with Jonas`, `through wave 10`, and Wave 9 errata from titles/intros; add a 1-line context note on `core-findings` #18 explaining why MongoDB is shown.
4. **Regroup `core-findings.html` by subsystem** (Read Store / DAL / PostgreSQL) instead of Wave 10 / Wave 9 / Wave 8 so readers stop bouncing back and forth across topics.
