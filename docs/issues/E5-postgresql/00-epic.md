---
id: E5
type: Epic
template: epic.yaml
title: "PostgreSQL as an experimental second database"
parent: ""
related: [E4]
findings: [11, 16, 17, 19, 30, 34]
status: draft
upstream: ""
---

## Problem we must solve

Shopware 6 runs on MySQL and MariaDB only.
Shops whose hosting or IT standard is PostgreSQL cannot use it.

## WHY we need to solve it

A proof of concept showed that the same Shopware code installs and runs on MySQL 8.4, MariaDB 10.11 and PostgreSQL 18, with the 910 migrations of a default install running on PostgreSQL and producing the same tables, columns, indexes and constraints as a reference converted from the installed MariaDB schema.
What it costs is known: a dialect per database, hex ids above the connection, a translator shim for old migrations and extension SQL, a recommended connection setup, and decisions on behaviour that MySQL users get without asking.
Whether to offer it is a business decision (cloud, managed databases, enterprise demand against the CI and support cost of a further database) that this epic waits for.

## Solution to the problem

After epic E4 (dialect, id binding, neutral migrations):

- PostgreSQL dialect, connection factory, PostgreSQL-only indexes, MySQL compatibility functions and the translator shim, behind a flag (E5.01).
- Recommended connection setup: persistent connections + plan cache or PgBouncer ≥ 1.21 (transaction mode), read replicas (`DATABASE_REPLICA_*`), and TLS (`DATABASE_SSL_*`) (E5.02).
- Decision on the semantics of string filters on PostgreSQL (E5.03).
- Sort indexes with the NULL order the DAL emits (E5.04).
- Nightly CI with the DAL and integration suites on PostgreSQL (E5.05).

## WHO benefits

Merchants and agencies that run on managed PostgreSQL, hosting partners, enterprise customers with a PostgreSQL standard.

## Accessibility

Backend-only work required

## WHERE will we do it

Core platform: connection setup, dialect, DAL, migrations; CI; developer and hosting documentation.

## Out of scope

- Official support with a CI matrix on every PR and a performance budget (a later phase).
- SQLite (optional, after epic E4).

## Acceptance criteria

- Go decision recorded (RFC or ADR).
- The full integration suite is green on PostgreSQL in nightly CI.
- Storefront response times on PostgreSQL within an agreed factor of MySQL.

## Research notes (not for upstream)

- Core developer feedback (2026-11-23): not worth the effort; benchmarks favouring PostgreSQL are mostly synthetic, ports from MySQL or MariaDB were reported to get slower, and the ecosystem is MySQL-based. Recorded as a risk in `docs/27-final-report.md`; it weighs on the go decision this epic depends on.
- Source: `docs/27-final-report.md` (TL;DR, "Required core changes" rows 6 and 7, phase 3, risks), `docs/core-findings.md` rows 11, 16, 17, 19, 30, and 42 to 50, `docs/22`, `docs/23`, `docs/49` (non-DAL suites: 386 → 90 PG-only failures across 8,072 tests, 98.9 % pass rate), `docs/50` (production setup: replicas, TLS, OpenSearch, workers, PgBouncer), `docs/51` (canonical paired CIs: uncached storefront 1.13–1.30× MariaDB, production walk 1.18× MariaDB, PgBouncer 1.31× direct PG, bulk write 1.81× seq / 0.34× c=4 rps).
- Known risk: write and import performance on PostgreSQL is about 1.8–2.1× MariaDB (`docs/27`, `docs/51`).
- Branch `poc/wave10` (fork `BrocksiNet/shopware`) holds the latest working implementation.
