# Issues for the Shopware core

This folder turns the core work found by the experiment into issue drafts for [shopware/shopware](https://github.com/shopware/shopware).
Each file is one issue, written so that it can be copied into the matching upstream issue template.

## Structure

- One folder per epic, `E<n>-<slug>/`.
- `00-epic.md` is the epic, every other file is a sub-issue of it.
- File names are `<nn>-<slug>.md`; the issue id used in this folder is `E<n>.<nn>` (for example `E3.01`).

Every file starts with front matter:

```yaml
id: E3.01
type: Bug            # Epic, Story, Bug, Improvement or Task (upstream issue types)
template: bug_report.yml   # upstream template in .github/ISSUE_TEMPLATE/
title: "..."         # upstream title
parent: E3           # epic id, empty for epics
related: [E1.04]     # other drafts in this folder
findings: [31]       # rows of docs/core-findings.md
status: draft        # draft, reproduced, ready, filed
upstream: ""         # full URL once filed
```

The headings of the body are the field labels of the upstream template, in the template's order:

| Type | Template | Headings |
|---|---|---|
| Epic | `epic.yaml` | Problem we must solve, WHY we need to solve it, Solution to the problem, WHO benefits, Accessibility, WHERE will we do it, Out of scope, Acceptance criteria |
| Story | `story.yaml` | User story, Acceptance criteria |
| Bug | `bug_report.yml` | Shopware Version, Affected area / extension, Actual behaviour, Expected behaviour, How to reproduce |
| Improvement, Task | `technical_todo.yaml` | Technical TODO (Task for docs, spikes, decisions) |

After the template headings, `## Research notes (not for upstream)` holds links into this repository, measurements by engine and the PoC branch.
This repository is private, so nothing above that heading may rely on it: numbers, file paths and code references in the upstream part are stated in full.

Status values:

- **draft**: written from the docs, not checked against current trunk.
- **reproduced**: checked on a trunk commit (named in the file), with a test or a measurement.
- **ready**: reproduced and reviewed, can be filed.
- **filed**: the `upstream` field holds the issue URL.

Filing anything upstream needs an explicit OK.

## Epics

| Epic | Topic | Sub-issues | Upstream |
|---|---|---|---|
| [E1](E1-mysql-robustness/00-epic.md) | Robustness on MySQL and MariaDB: stop relying on lenient MySQL behaviour | 12 | [#23287](https://github.com/shopware/shopware/issues/23287) |
| [E2](E2-performance/00-epic.md) | (Story) Write and search performance on every database | 3 | [#23300](https://github.com/shopware/shopware/issues/23300) |
| [E3](E3-dal-v2/00-epic.md) | DAL v2: keep the DAL and improve it | 12 | [#23304](https://github.com/shopware/shopware/issues/23304) |
| [E4](E4-database-abstraction/00-epic.md) | Database abstraction groundwork: dialect, id binding, neutral migrations | 6 | [#23317](https://github.com/shopware/shopware/issues/23317) |
| [E5](E5-postgresql/00-epic.md) | PostgreSQL as an experimental second database | 5 | not filed yet |

E1, E2 and E3 help MySQL and MariaDB alone and need no decision about PostgreSQL.
E4 is phase 1 and 2 of the integration plan in `docs/27-final-report.md`, E5 is phase 3; E5 depends on a go decision.

## Sub-issues

| Id | Type | Title | Findings | Status |
|---|---|---|---|---|
| [E1.01](E1-mysql-robustness/01-group-by-natural-sorting.md) | Bug | Natural sorting in a grouped query sorts by a non-aggregated column | 1 | [filed](https://github.com/shopware/shopware/issues/23288) |
| [E1.02](E1-mysql-robustness/02-only-full-group-by.md) | Improvement | Make DAL selects valid under `ONLY_FULL_GROUP_BY` and stop changing `sql_mode` | 2 | [filed](https://github.com/shopware/shopware/issues/23289) |
| [E1.03](E1-mysql-robustness/03-having-alias-and-states-updater.md) | Improvement | Remove the select alias in `HAVING`, the unqualified `id` and the partial `GROUP BY` of `StatesUpdater` | 3, 4 | [filed](https://github.com/shopware/shopware/issues/23290) |
| [E1.04](E1-mysql-robustness/04-row-number-per-partition.md) | Improvement | Replace session variable row counting with `ROW_NUMBER() OVER (PARTITION BY ...)` | 6 | [filed](https://github.com/shopware/shopware/issues/23291) |
| [E1.05](E1-mysql-robustness/05-savepoints-after-failed-statements.md) | Improvement | Do not continue a transaction after a failed statement without a savepoint | 5 | [filed](https://github.com/shopware/shopware/issues/23292) |
| [E1.06](E1-mysql-robustness/06-multi-insert-duplicate-keys.md) | Improvement | Merge rows with the same key in `MultiInsertQueryQueue` | 12 | [filed](https://github.com/shopware/shopware/issues/23293) |
| [E1.07](E1-mysql-robustness/07-explicit-null-order.md) | Improvement | State the NULL order of `FieldSorting` in the SQL | 14, 22 | [filed](https://github.com/shopware/shopware/issues/23294) |
| [E1.08](E1-mysql-robustness/08-price-accessor-scale.md) | Improvement | Make scale and arithmetic of the price accessor explicit | 13 | [filed](https://github.com/shopware/shopware/issues/23295) |
| [E1.09](E1-mysql-robustness/09-accent-insensitive-search.md) | Task | Decide and test whether string filters are accent-insensitive | 18 | [filed](https://github.com/shopware/shopware/issues/23296) |
| [E1.10](E1-mysql-robustness/10-lock-validator-row-count.md) | Improvement | `LockValidator` uses `rowCount()` after a SELECT | 25 | [filed](https://github.com/shopware/shopware/issues/23297) |
| [E1.11](E1-mysql-robustness/11-typed-numeric-parameters.md) | Improvement | Bind numeric criteria parameters with their type | 27 | [filed](https://github.com/shopware/shopware/issues/23298) |
| [E1.12](E1-mysql-robustness/12-custom-field-date-filter-cast.md) | Improvement | Date custom field filters cast the column but not the value | 28 | [filed](https://github.com/shopware/shopware/issues/23299) |
| [E2.01](E2-performance/01-batch-product-indexer-updates.md) | Improvement | Batch the single row `UPDATE product` statements of the product indexer updaters | 29 | [filed](https://github.com/shopware/shopware/issues/23301) |
| [E2.02](E2-performance/02-indexer-row-order-deadlocks.md) | Improvement | One fixed row order in the product indexer updaters against deadlocks | 10 | [filed](https://github.com/shopware/shopware/issues/23302) |
| [E2.03](E2-performance/03-search-keyword-score-once.md) | Improvement | Compute the search keyword score once per search request | 23, 24 | [filed](https://github.com/shopware/shopware/issues/23303) |
| [E3.01](E3-dal-v2/01-write-gateway-primary-key-decode.md) | Bug | `EntityWriteGateway` misses the prefetched existence state for storage named primary keys | 31 | [filed](https://github.com/shopware/shopware/issues/23305) |
| [E3.02](E3-dal-v2/02-window-count-total.md) | Improvement | Return the exact total of a paginated search with a window count | 32 | [filed](https://github.com/shopware/shopware/issues/23306) |
| [E3.03](E3-dal-v2/03-fuse-min-max-stats.md) | Improvement | Fuse min and max aggregations of one field into one statement | | [filed](https://github.com/shopware/shopware/issues/23307) |
| [E3.04](E3-dal-v2/04-batched-entity-updates.md) | Improvement | Batch update commands of one entity in the write gateway | 29 | [filed](https://github.com/shopware/shopware/issues/23308) |
| [E3.05](E3-dal-v2/05-profile-write-path.md) | Task | Profile the DAL write path | | [filed](https://github.com/shopware/shopware/issues/23309) |
| [E3.06](E3-dal-v2/06-partial-read-inherited-to-many.md) | Bug | Partial read of a variant returns an empty inherited to-many association | 33 | [filed](https://github.com/shopware/shopware/issues/23310) |
| [E3.07](E3-dal-v2/07-dto-projections.md) | Story | Read into typed DTO projections through partial loading | 33 | [filed](https://github.com/shopware/shopware/issues/23311) |
| [E3.08](E3-dal-v2/08-read-shape.md) | Task | Decide on the read shape options join and batch | | [filed](https://github.com/shopware/shopware/issues/23312) |
| [E3.09](E3-dal-v2/09-typed-criteria-field-paths.md) | Story | Check criteria field paths with PHPStan | | [filed](https://github.com/shopware/shopware/issues/23313) |
| [E3.10](E3-dal-v2/10-attribute-entity-compiler-gaps.md) | Story | Close the attribute entity compiler gaps | | [filed](https://github.com/shopware/shopware/issues/23314) |
| [E3.11](E3-dal-v2/11-classic-definitions-to-attributes.md) | Task | Decide whether classic definitions move to attribute entities | | [filed](https://github.com/shopware/shopware/issues/23315) |
| [E3.12](E3-dal-v2/12-extension-probes.md) | Task | Verify plugin fields and app custom entities on the DAL v2 changes | | [filed](https://github.com/shopware/shopware/issues/23316) |
| [E4.01](E4-database-abstraction/01-sql-dialect-service.md) | Story | `SqlDialect` service with the MySQL implementation | 8 | [filed](https://github.com/shopware/shopware/issues/23318) |
| [E4.02](E4-database-abstraction/02-hex-id-binding.md) | Story | Hex ids above the connection, binding in one place | 7 | [filed](https://github.com/shopware/shopware/issues/23319) |
| [E4.03](E4-database-abstraction/03-neutral-migration-api.md) | Story | Database-neutral migration API for new migrations | 8 | [filed](https://github.com/shopware/shopware/issues/23320) |
| [E4.04](E4-database-abstraction/04-custom-entity-ddl-platform.md) | Improvement | Fixed DDL platform for custom entity schema updates | 20 | [filed](https://github.com/shopware/shopware/issues/23321) |
| [E4.05](E4-database-abstraction/05-portable-test-sql.md) | Improvement | Remove MySQL-only SQL from tests | 15, 21, 26 | [filed](https://github.com/shopware/shopware/issues/23322) |
| [E4.06](E4-database-abstraction/06-extension-dialect-and-cli-check.md) | Story | Public dialect service for extensions and a `shopware-cli` check | | [filed](https://github.com/shopware/shopware/issues/23323) |
| [E5.01](E5-postgresql/01-postgresql-driver.md) | Story | PostgreSQL dialect, connection factory and translator shim behind a flag | 30 | draft |
| [E5.02](E5-postgresql/02-connection-setup.md) | Improvement | Persistent connections and a plan cache for PostgreSQL | 11, 16 | draft |
| [E5.03](E5-postgresql/03-string-filter-semantics.md) | Task | Decide the string filter semantics on PostgreSQL | 17 | draft |
| [E5.04](E5-postgresql/04-sort-indexes-null-order.md) | Improvement | Sort indexes with the NULL order the DAL emits | 19 | draft |
| [E5.05](E5-postgresql/05-nightly-ci.md) | Task | Nightly CI with the DAL and integration suites on PostgreSQL | | draft |

## Findings without an issue

- 9 (19 joins in the product detail read): with the plan cache the remaining planning time does not justify splitting the statement (`docs/22`).

Every other row of `docs/core-findings.md` maps to an issue above.
New findings go into `docs/core-findings.md` first and then into an issue here.
