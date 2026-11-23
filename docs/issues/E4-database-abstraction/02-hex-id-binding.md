---
id: E4.02
type: Story
template: story.yaml
title: "Hex ids above the connection, binding in one place"
parent: E4
related: [E4.01, E4.06, E3.01]
findings: [7]
status: filed
upstream: "https://github.com/shopware/shopware/issues/23319"
---

## User story

As a core or extension developer, I would like to pass ids as hex strings to the database layer, so that I do not convert between hex and 16 byte binary by hand in every query.

## Acceptance criteria

- One component turns a hex id, or a list of hex ids, into the value and the parameter type the connection needs: 16 bytes on MySQL and MariaDB.
  It also covers the opposite direction for results and the text form of an id column in a select.
- Core code outside migrations uses this component and no longer calls `Uuid::fromHexToBytes`, `Uuid::fromBytesToHex`, `UNHEX()`, `LOWER(HEX())` or `ArrayParameterType::BINARY` for ids.
- A Rector rule rewrites the common call sites (bytes in parameters, id lists, result to hex), and the rule is published for extensions.
- Manual id conversion is deprecated for extensions, with the replacement named in the deprecation.
- Untyped binary parameters (an id passed to `setParameter()` without a type) no longer exist in core code.
- Existing migrations stay as they are.
- MySQL and MariaDB suites stay green and there is no measurable performance regression.

Design notes that came out of a proof of concept:

- A custom DBAL type is not enough, because DBAL expands list parameters only for `ArrayParameterType`; a static facade with `value()`, `values()`, `type()`, `listType()`, `toHex()`, `toHexList()` and `text()` covers lists.
- Rector rewrote 80 percent of the hits in the files with manual conversion; bytes and parameters 97 percent, `LOWER(HEX())` 44 percent, `UNHEX` none.
  Heredoc SQL and callers that receive bytes from other code need manual work.

## Research notes (not for upstream)

- Finding: `docs/core-findings.md` row 7; `docs/15` (id spike), `docs/20` (untyped callers), `docs/27` ("Required core changes" row 3, phase 1).
- Base numbers (`docs/04`): 715 `BINARY(16)` columns (691 named `id` or `*_id`), 63 composite foreign keys with a version column, 309 non-migration files with manual conversion by the wide pattern.
- Trunk `e9e18ef0e7b`, counted by me: 314 non-migration PHP files under `src` match `Uuid::fromHexToBytes|Uuid::fromBytesToHex|LOWER\(HEX|UNHEX\(|ArrayParameterType::BINARY|ParameterType::BINARY`.
  The base of the proof of concept had 309, so the pattern has grown by 5 files.
- Pattern inventory on the base (`docs/15`): bytes in array parameters 251 hits in 121 files, `setParameter` with bytes 62 in 37, id lists 138 in 75, `ArrayParameterType::BINARY` 174 in 98, result to hex 186 in 88, `LOWER(HEX())` 372 in 144, other `fromHexToBytes` 86 in 46, `UNHEX` 14 in 8.
  Rector: 250 files changed, 204 complete; 29 hits in 21 files receive bytes from callers.
- Converted path: 8 files, codec conversions per 9 request flow from 85 to 0, `IdBinding::value` 44 ns against 100 ns; the gain per request is not measurable, the gain is architectural.
- Untyped binary callers (`docs/20`): safe on MySQL, but a random 16 byte value is valid UTF-8 about 1 in 11,000 times, which matters when a driver guesses the codec.
  Callers listed there: `SearchKeywordUpdater:212/230`, `SystemConfigService:304`, `UserConfigController:128`.
- The proof of concept class is `IdBinding`, a static facade, with a Rector rule `BinaryUuidToIdBindingRector`.
- Related bug: E3.01 is an example of a manual conversion bug (decode by property name).
- Checked statically against trunk c6ef9571261 (2026-11-23).
- Recount on trunk c6ef9571261: `grep -rlE 'Uuid::fromHexToBytes|Uuid::fromBytesToHex|LOWER\(HEX|UNHEX\(|ArrayParameterType::BINARY|ParameterType::BINARY' src --include='*.php' | grep -v '/Migration/' | wc -l` gives 314, unchanged.
- The caller line numbers above come from the proof of concept base and were not re-checked; `UserConfigController` is not at `src/Core/Framework/Api/Controller/` on trunk.
