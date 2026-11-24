---
id: E6.06
type: Improvement
template: technical_todo.yaml
title: "Defer old-generation deletion past max query timeout in blue/green read-store swap"
parent: E6
related: [E6.01, E6.02, E6.03]
findings: []
status: draft
upstream: ""
---

## Technical TODO

Under concurrent mixed load (`c=4`, 12 s) during a live blue/green `read-store:rebuild`, pointer-based storage engines that immediately drop the previous generation inside `swap()` kill in-flight queries that resolved the old generation pointer milliseconds before the swap:

- Observed on `MongoDbStorage::swap()`: 1 of 5,226 concurrent requests failed with `Executor error during aggregate command on namespace: rs_readstore.rs_<oldGen> :: caused by :: collection dropped`.
- `OpenSearchStorage::swap()` should also delay `indices.delete($old)` past the configured search timeout, and `ValkeyStorage::swap()` should set a short TTL (e.g. 60–300 s) on old generation keys rather than deleting synchronously.

Tasks:
1. Change `Storage::swap()` contract so dropping the previous generation is deferred (TTL, delayed cleanup job, or GC at the start of the next rebuild once `age > max_query_timeout`).
2. Add a single retry on `NamespaceNotFound` / missing-generation error after re-reading `liveGeneration()`.
3. Cover with a concurrent load + rebuild integration test asserting 0 errors and 0 empty reads across the swap.

## Research notes (not for upstream)

- Evidence: `docs/45-read-store-consistency.md` (Section 4.1, blue/green rebuild under concurrent `c=4` load).
