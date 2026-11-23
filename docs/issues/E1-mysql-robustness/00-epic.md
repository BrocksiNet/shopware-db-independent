---
id: E1
type: Epic
template: epic.yaml
title: "DAL and core SQL: stop relying on lenient MySQL behaviour"
parent: ""
related: [E3, E4]
findings: [1, 2, 3, 4, 5, 6, 12, 13, 14, 18, 22, 25, 27, 28]
status: checked
upstream: ""
---

## Problem we must solve

Parts of the DAL and of core SQL only return correct or stable results because MySQL and MariaDB are lenient.
The core switches `ONLY_FULL_GROUP_BY` off for every session (`MySQLFactory`), selects non-aggregated columns under `GROUP BY`, refers to select aliases in `HAVING`, counts rows with session variables that MySQL 8 deprecates, never states a NULL order, binds numbers untyped, decides on `rowCount()` after a SELECT and continues a transaction after a statement failed on purpose.
Some of these already give arbitrary or wrong results on MySQL today, for example a natural sort in a grouped query that sorts by the value of an arbitrary row.

## WHY we need to solve it

- Results that depend on server leniency are bugs waiting for a server upgrade, a different `sql_mode` or a different engine.
- MySQL 8 deprecates setting user variables inside expressions; the DAL uses that in `EntityReader`.
- Behaviour such as NULL order and accent-insensitive matching is not documented or tested, so nobody can say whether it is intended.
- Every item here is a prerequisite for running the core on any second database, and none of them needs a decision about one.

## Solution to the problem

Fix the items one by one as normal, non-breaking changes in minors (sub-issues E1.01 to E1.12):
valid `GROUP BY` and `HAVING`, `ROW_NUMBER() OVER (PARTITION BY ...)`, explicit NULL order, explicit scale and casts, typed parameters, `fetchOne()` instead of `rowCount()`, savepoints around statements that are expected to fail, merged duplicate keys in multi-row upserts.
All of them were implemented and run on MySQL 8.4, MariaDB 10.11, PostgreSQL 18 and SQLite in a proof of concept.

## WHO benefits

Developers of the core and of extensions (stable, documented DAL behaviour), merchants (stable search and sort results), hosting partners (no session `sql_mode` override).

## Accessibility

Backend-only work required

## WHERE will we do it

Core platform: `Framework/DataAbstractionLayer` (`CriteriaQueryBuilder`, `EntityReader`, `EntitySearcher`, `EntityAggregator`, `SqlQueryParser`, price and custom field accessor builders, `MultiInsertQueryQueue`, `LockValidator`), `MySQLFactory`, `Content/Product/DataAbstractionLayer/StatesUpdater.php`, the sales channel context persister.

## Out of scope

- Support for a second database (E4 and a later PostgreSQL epic).
- Performance work (E2 and E3).

## Acceptance criteria

- The core runs with the server default `sql_mode` (including `ONLY_FULL_GROUP_BY`) and `MySQLFactory` no longer changes it.
- No user variable assignment inside expressions remains in the DAL.
- The NULL order of `FieldSorting` and the accent sensitivity of string filters are documented and covered by tests.
- The full integration suite is green on MySQL and MariaDB after each sub-issue.

## Research notes (not for upstream)

- Source: `docs/core-findings.md` rows 1 to 6, 12 to 14, 18, 22, 25, 27, 28; `docs/27-final-report.md` "Required core changes" row 1, integration phase 1.
- Checked statically against trunk c6ef9571261 (2026-11-23).
