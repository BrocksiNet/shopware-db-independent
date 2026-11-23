---
id: E3
type: Epic
template: epic.yaml
title: "DAL v2: keep the DAL and make it faster and typed"
parent: ""
related: [E1, E2]
findings: [31, 32, 33]
status: checked
upstream: ""
---

## Problem we must solve

The DAL is the public data API of the core, of every plugin and of every app, and it is measurably slower than hand-written SQL: a product listing, detail, search, bulk write and criteria-from-JSON scenario take 1.5 to 12.6 times as long as hand-written DBAL on MySQL.
Its write path sends one existence lookup per row although it prefetches them, a paginated search with an exact total runs the query twice, and new entities need about 250 lines in three classes plus a service definition.
Field paths in criteria are strings, so typos only fail at run time.

## WHY we need to solve it

The question whether to replace the DAL with an ORM was answered with a proof of concept that compared the DAL, hand-written DBAL, Doctrine ORM 3.8, Cycle ORM 2.19 and an improved DAL on MySQL, MariaDB, PostgreSQL and SQLite:

- Neither ORM provides translations with fallback, variant inheritance, versioning with merge or the written events; every probe passed only with hand-written code, and Doctrine fails a plugin field on a core entity.
- Both ORMs write one statement per row.
- A full replacement is estimated at 100 to 230 person-weeks and breaks every plugin and app.
- An improved DAL kept every DAL feature and was 1.7 to 3.3 times faster than today's DAL on the read scenarios on MySQL, MariaDB and PostgreSQL.

Keeping the DAL is therefore only a good answer if the improvements are made.

## Solution to the problem

Internal changes first, in the order of measured gain per effort, then additive API:

1. Fix the existence lookup of the write gateway (E3.01).
2. Exact total from a window count (E3.02), fused min and max statistics (E3.03).
3. Batched updates in the write gateway and a profile of the remaining writer cost (E3.04, E3.05).
4. Read shape decision (E3.08).
5. Additive API: DTO projections with partial loading (E3.06, E3.07), typed criteria field paths (E3.09), attribute entities that can express every field type (E3.10).
6. Optional and breaking, decided separately: classic definitions to attribute entities (E3.11).

The SQL hygiene items that are part of this work (`ONLY_FULL_GROUP_BY`, row numbering, NULL order, typed parameters) are tracked in epic E1.

## WHO benefits

Developers of the core, plugins and apps (faster DAL, typed reads, less boilerplate for new entities), merchants (faster listing, detail, search and imports).

## Accessibility

Backend-only work required

## WHERE will we do it

Core platform: `Framework/DataAbstractionLayer` (`EntityWriteGateway`, `EntitySearcher`, `EntityAggregator`, `EntityReader`, `Criteria`, attribute entity compiler), PHPStan rules of the core.

## Out of scope

- Replacing the DAL with an ORM, or running an ORM underneath the DAL API: rejected by the proof of concept, no gain shown.
- Compiled hydrators: hydration is 15 percent of a call at most in the profile, not worth it.
- Changes to the public DAL API other than additive ones, except E3.11 after a separate decision.

## Acceptance criteria

- The five benchmark scenarios (listing, detail, search, bulk write of 50 products, criteria from JSON) are measured on MySQL and MariaDB before and after each sub-issue, with statement counts.
- Every internal change keeps the full integration suite green and the output of the scenarios identical.
- No public API break outside E3.11.

## Research notes (not for upstream)

- Checked statically against trunk c6ef9571261 (2026-11-23).
- Source: `docs/29-orm-alternatives.md` "Conclusion" (recommendation, lever order, effort 11 to 27 person-weeks without a break), `docs/33-orm-spike-dal-v2.md` (levers, profile, open items), `docs/34-orm-spike-final-timings.md` (one timing block, nine configurations, four engines).
- "1.5 to 12.6 times": DAL against DBAL on MySQL in doc 34, S5 28.24/19.47 = 1.45 to S4 90.11/7.16 = 12.6. "1.7 to 3.3 times": doc 29 conclusion.
- The spike code is on the local instance branch `poc/orm-spike` (last commit `7878aa3e709`).
