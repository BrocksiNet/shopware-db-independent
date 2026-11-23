---
id: E4.06
type: Story
template: story.yaml
title: "Public dialect service for extensions and a shopware-cli check"
parent: E4
related: [E4.01, E4.02, E4.03]
findings: []
status: filed
upstream: "https://github.com/shopware/shopware/issues/23323"
---

## User story

As an extension developer, I would like a public dialect service and an early warning for MySQL-only SQL, so that my extension keeps working when the core supports another database.

## Acceptance criteria

- The dialect service of the core is public API, with documented methods and a deprecation policy.
- The developer documentation shows how to replace common MySQL-only constructs in an extension: backtick quoting, `INSERT IGNORE`, `ON DUPLICATE KEY UPDATE`, `GROUP_CONCAT`, JSON functions and manual id conversion.
- `shopware-cli` has a check that lists the statements of an extension that rely on MySQL-only constructs, with the file and line.
- The check is advisory and does not fail a build by default.

## Research notes (not for upstream)

- Source: `docs/27-final-report.md` (plugin impact, `shopware-cli` check); `docs/28-plugin-sql-inventory.md`.
- Plugin scan (store mirror of 2026-10-02, 3,747 plugins, 625 apps without PHP or SQL):
  - 1,701 plugins (1,692 with no raw SQL plus 9 with no PHP) are not affected.
  - 2,045 plugins (54.6 percent) contain raw SQL.
  - 477 (12.7 percent) would be handled by the translator shim, 1,122 (29.9 percent) have MySQL-only DDL, 354 (9.4 percent) use constructs the shim has no rule for.
  - Gaps without a shim rule: `information_schema` in 219 plugins, date difference functions in 77, JSON functions in 77.
  - Constructs counted: backticks 1756, `HEX` 632, `LOWER(HEX)` 569, JSON 513, `INSERT IGNORE` 205, `ON DUPLICATE KEY` 152, `information_schema` 258.
- Method limits: regex scan over tokenized PHP, SQL built by concatenation is seen only in parts, 36 plugins plus 6 were checked by hand; the numbers are an estimate.
- Trunk has no public dialect service; this issue depends on E4.01.
- The `shopware-cli` repository is separate; this draft needs a matching issue there.
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Trunk c6ef9571261 still has no dialect service (`grep -rli 'SqlDialect' src` is empty).
