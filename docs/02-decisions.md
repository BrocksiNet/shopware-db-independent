# Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-11-18 | Base is current trunk, changed as needed. Merging mitelg's `feat/open-api-dto-generator` or other helpful branches is allowed. | Experimental project, no upstream constraints. |
| 2026-11-18 | Ids are native `uuid` on PostgreSQL. | That is what a real port would use; `bytea` would only mirror MySQL's `binary(16)`. |
| 2026-11-18 | No plugins, no commercial. Open source core only. | Keeps the proof of concept bounded. |
| 2026-11-18 | Layout: `README.md`, `docs/`, `instance/`, `review/`. | See README. |
| 2026-11-18 | Two git repositories: this research repository, and `instance/` as a clone of `shopware/shopware` on branch `poc/postgresql`. | Research docs and core changes have different histories; the core branch stays mergeable with trunk and can go to a fork as one branch. |
| 2026-11-18 | Fresh installs on PostgreSQL run the real migrations, translated automatically (also for future migrations), instead of shipping a converted schema. | Long term solution; a schema check against PostgreSQL catches new migrations that do not translate. |
