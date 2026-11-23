---
id: E4.03
type: Story
template: story.yaml
title: "Database-neutral migration API for new migrations"
parent: E4
related: [E4.01, E4.04, E5.01]
findings: [8]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23320"
---

## User story

As a core or extension developer, I would like to write a migration without MySQL DDL, so that the same migration runs on every database the core supports.

## Acceptance criteria

- New core migrations can create and alter tables, columns, indexes and foreign keys through a neutral API, for example the DBAL schema objects or a helper on `MigrationStep`.
- The API covers an id column type, so that migrations no longer spell `BINARY(16)` for ids.
- Existing migrations keep running unchanged on MySQL and MariaDB.
- A CI check compares the schema produced by the migrations with the expected schema.
- The API is documented for extension developers, with one example migration.

Open question: how far the API reaches, because data migrations with raw SQL still need the dialect (E4.01).

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 8 (910 migrations are MySQL DDL); plan in `docs/10` ("Migrations") and `docs/27` (phase 2).
- Trunk `e9e18ef0e7b`: 919 `Migration*.php` files under `src/Core/Migration/V6_*`, so the base of the docs (910) has grown by 9.
- Decision in `docs/10`: history stays MySQL SQL, executed through a translator shim on other databases; new migrations use a portable API (DBAL Schema or a helper); a schema check in CI.
  The shim is part of E5.01, not of this issue.
- Open question from `docs/10`: how far a portable migration API goes.
- Plugin side (`docs/28`, a scan of 3,747 plugins of a store mirror from 2026-10-02): 1,389 plugins have MySQL-only DDL in 7,505 migration classes, `BINARY(16)` appears in 1,376.
  The scan is a regex over tokenized PHP, SQL built by concatenation is seen only in part; treat the numbers as an estimate.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Recount on trunk c6ef9571261: `find src/Core/Migration -name 'Migration*.php' -path '*V6_*' | wc -l` gives 919, unchanged.
