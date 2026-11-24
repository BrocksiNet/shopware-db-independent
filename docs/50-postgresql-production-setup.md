# 50 PostgreSQL in a production-like setup

Wave 10, handoff E.
Question: does Shopware on PostgreSQL work in the setup a production shop runs, not only on the lane (doc 46 "What is not proven", point 3, production part)?
Branch `poc/wave10`, PostgreSQL 18, MariaDB 11 as the reference, both with the same stack next to the lane.

## Verdict

PostgreSQL works in a production-like setup after six small fixes, all committed on `poc/wave10`.
With the fixes, the same functional run passes on PostgreSQL and on MariaDB: install, demo data, storefront walk to a placed order, admin product save, import of 1,000 products, `es:index` and storefront search through OpenSearch, scheduled tasks, two messenger workers, a streaming replica with TLS, and a PgBouncer transaction mode variant.
Four of the six fixes were PostgreSQL bugs that only a production setup shows (replica write routing, OpenSearch indexing SQL twice, the column case map in long-running workers), one was a core bug that only a worker hits (sitemap), one was missing replica and TLS support in `PostgreSQLFactory`.
Read-your-writes under replica lag fails the same way on both databases, so it is no PostgreSQL argument.
Two behaviours differ and must be documented: a failed statement aborts the whole transaction on PostgreSQL (MariaDB carries on), and the plan cache must be off behind PgBouncer.
Not proven: the sanity timings.
The podman VM stopped answering during the timing loop (see "Timings"), so this doc has only single runs; D has the commands.

Doc 46 point 3 (production part), proposed wording: "PostgreSQL runs the production setup (OpenSearch, replica, TLS, workers, PgBouncer) with the fixes of wave 10 E; speed in that setup is not measured."

## Setup

All containers are E's own (`instance-w10e-*`, network `instance_default`), database `w10e_shop`, OpenSearch prefix `rs_w10_e_`.
The lane's containers, indices and databases were not touched.

| Part | PostgreSQL | MariaDB |
|---|---|---|
| Primary | `instance-w10e-pg`, postgres:18, TLS on (own CA), `timezone=Europe/Berlin` on purpose so lost session state shows | `instance-w10e-mariadb`, TLS on, binlog for the replica |
| Replica | `instance-w10e-pgreplica`, `pg_basebackup -R`, streaming, `hot_standby=on`, TLS `verify-full` to the primary | `instance-w10e-mariadbreplica`, `read_only=ON`, user without `SUPER` |
| Pooler | `instance-w10e-pgbouncer`, PgBouncer 1.25.2, `pool_mode=transaction`, `max_prepared_statements=200`, TLS both sides | none (Shopware docs recommend ProxySQL, not tested) |
| Web | `instance-w10e-web-pg` (port 8191, primary plus replica), `instance-w10e-web-pgb` (port 8193, through PgBouncer) | `instance-w10e-web-my` (port 8192, primary plus replica) |
| Search | `instance-w10e-opensearch`, OpenSearch 2.19.7, 768 MB heap, prefixes `rs_w10_e_pg`, `rs_w10_e_my` | same node |

Every web container: `APP_ENV=prod`, `SHOPWARE_HTTP_CACHE_ENABLED=1`, php-fpm static 8 children, opcache without timestamp checks, `DATABASE_SSL_CA` set, `SHOPWARE_ES_ENABLED=1`, `SHOPWARE_ES_INDEXING_ENABLED=1`, `SHOPWARE_ES_THROW_EXCEPTION=1`, `SHOPWARE_ADMIN_WORKER_ENABLED=0`, two `messenger:consume async low_priority --time-limit=300 --memory-limit=512M` loops and one `scheduled-task:run` loop.
`APP_CACHE_DIR=/tmp/w10e` keeps the prod container cache inside the container: a prod `cache:clear` deletes every other `var/cache/prod_*` dir (`CacheClearer::cleanupOldContainerCacheDirectories`), which removed the lane's prod cache once (README signal).

Shopware docs used:

- Message queue: https://developer.shopware.com/docs/guides/hosting/infrastructure/message-queue.html ("If you have configured the cli-worker, you should turn off the admin worker", `enable_admin_worker: false`, `bin/console messenger:consume async low_priority`).
- Database cluster: https://developer.shopware.com/docs/guides/hosting/infrastructure/database-cluster.html (`DATABASE_REPLICA_x_URL`; on a write "the query is delegated to the primary server, and the current connection uses only the primary node for subsequent calls"; TLS through `DATABASE_SSL_*`; ProxySQL for pooling).
- Elasticsearch/OpenSearch: https://developer.shopware.com/docs/guides/hosting/infrastructure/elasticsearch/elasticsearch-setup.html (`SHOPWARE_ES_ENABLED`, `SHOPWARE_ES_INDEXING_ENABLED`, `SHOPWARE_ES_INDEX_PREFIX`, `SHOPWARE_ES_THROW_EXCEPTION`, `bin/console es:index`).
- Scheduled tasks: https://developer.shopware.com/docs/guides/hosting/infrastructure/scheduled-task.html (`scheduled-task:run`).

### Config values that differ from MySQL

| Setting | PostgreSQL | MySQL/MariaDB | Why |
|---|---|---|---|
| `DATABASE_URL` | `pgsql://…:5432/…` | `mysql://…:3306/…` | driver |
| `DATABASE_PERSISTENT_CONNECTION` | `1` direct, `0` behind PgBouncer | optional | a new PostgreSQL backend costs about 36 ms plus connect (doc 22); behind a pooler the pooler keeps the backends |
| `DATABASE_PLAN_CACHE` | `1` direct, unset behind PgBouncer | ignored | SQL-level `PREPARE` lives on one server connection, PgBouncer hands the next transaction another one (probe below) |
| `DATABASE_SSL_CA` and friends | same variables; `CA` gives `sslmode=verify-full`, `DATABASE_SSL_DONT_VERIFY_SERVER_CERT=1` gives `require`; `sslmode` in the URL wins | PDO MySQL attributes | libpq has no CA-only mode without `sslmode` (commit `12abc252e15`, 8 unit tests) |
| `DATABASE_REPLICA_0_URL` | same variable, needs `hot_standby=on` on the replica | same | – |
| `SHOPWARE_ADMIN_WORKER_ENABLED=0` | same | same | `config/packages/admin_worker.yaml` (gitignored, like a project's config), default on |
| Server `max_connections` | php-fpm children × web nodes + workers, or the pooler's `default_pool_size` | same idea, threads are cheaper | one process per backend |
| Server time zone | any; the session runs `SET TIME ZONE 'UTC'` | session `time_zone` | PgBouncer tracks `Timezone` per client (features page, footnote 1), the probe saw UTC 12 of 12 times across 2 server connections |
| PgBouncer `max_prepared_statements` | `> 0` (200 here) | – | protocol-level prepared statements through the pooler need it (PgBouncer feature map, https://www.pgbouncer.org/features.html); 12 of 12 native prepares worked in the probe |
| PgBouncer `ignore_startup_parameters` | `extra_float_digits,options` | – | pdo_pgsql sends them |

`instance/.env.pgsql.dist` now documents replica, TLS and the PgBouncer rule (`07a03ea7c89`).

## Functional run

Catalog: `framework:demodata` (not `read_store_large`), run in steps because one call fails on both databases with "Cannot get 3 elements, only 2 in array": `ProductGenerator::buildDownloads` asks for up to 3 download media, the media search finds 2 of the 7 private ones (`MediaVisibilityRestrictionSubscriber`).
Steps: `--media=200`; base data (10 categories, 10 manufacturers, 5 property groups, 20 customers, 5 rules, 10 tags); 20 × `--products=50`; 50 reviews, 2 streams, 2 promotions, 20 orders; `dal:refresh:index`.
Result: 1,000 parent products on both, 2,444 products with variants on PostgreSQL and 2,466 on MariaDB (random generator), plus 1,000 imported.

| Step | PostgreSQL | MariaDB |
|---|---|---|
| `system:install` | works, 22 s | works, 29 s |
| demo data (steps above) | works | works |
| `dal:refresh:index` | works | works |
| storefront walk (home, listing, search, detail, add to cart, cart, guest register, confirm, order) | works after `be901964bdb`, order created | works, order created |
| admin API product save and read back | works (204, read returns the new name and stock) | works |
| `import:entity` 1,000 products, profile `default_product` | works, 1,000 records, 63.0 s wall | works, 1,000 records, 50.2 s wall |
| `es:index --no-queue` | works after `3727203c817` and `e3262248e55`, 3,404 products indexed, 2.9 s | works, 3,426 products indexed, 2.1 s |
| storefront search through OpenSearch | works (`query_total` of the index rises with each search) | works |
| `sitemap:generate` and `SitemapMessage` in the worker | works after `f44b65f8764` | works |
| scheduled tasks | 28 of 29 ran, 27 `scheduled`, 2 `skipped`, 0 failed | same counts |
| admin worker off | `/api/_info/config` `enableAdminWorker: false` | same |

Both databases skip and run the same tasks, and both index 40 products fewer than the table holds (parents without `displayParent`), so the indexing SQL selects the same rows.

### Log errors, classified

| Error | Where | Class | State |
|---|---|---|---|
| `SQLSTATE[25006] cannot execute INSERT in a read-only transaction` on guest register | PG only, `IncrementSqlStorage::reserve()` | real product bug of the PostgreSQL port: the `INSERT … RETURNING` runs through `fetchOne()`, `PrimaryReadReplicaConnection` sends it to the replica | fixed `be901964bdb`, unit test |
| `function group_concat(jsonb) does not exist` in `es:index` | PG only, `SqlHelper::objectArray` | dialect gap (shim) | fixed `3727203c817` |
| `column "p.active" must appear in the GROUP BY clause` in `es:index` | PG only, `ElasticsearchProductDefinition` base and translation queries | behaviour difference (`GROUP BY`; product's key is `(id, version_id)`, so `p.id` alone does not cover the columns) | fixed `e3262248e55`, same groups on MySQL |
| 3,918 `Undefined array key "where"` warnings in one worker run | PG only, DBAL `PostgreSQLSchemaManager` index query through the translator | real product bug of the PostgreSQL port: a quoted lower case alias was renamed after an upper case keyword | fixed `2f10df5eb2e`, unit test |
| `UnknownAlias "`product`"` in `SitemapMessage` | PG; on MariaDB the message had not run before the fix, so no comparison | core bug: the query joins on a backtick alias the iterator does not use on PostgreSQL | fixed `f44b65f8764` |
| "Cannot get 3 elements, only 2 in array" | both | demo data generator, not database related | worked around by steps |
| "Cannot install service … APP_URL … could not be reached" | both | environment (container cannot reach its own published port) | ignored |
| "Disk full", podman "unable to open database file", MariaDB session start 500 at 19:48 UTC | both | environment: the VM disk ran full | binlogs purged, WAL limited |

The full log sweep after the last fixes (worker and scheduler logs of the final containers) could not be done: the VM stopped answering (see "Timings").

## Areas

### OpenSearch

| Check | Result |
|---|---|
| `es:index` from PostgreSQL | works with change `3727203c817` (jsonb `group_concat`) and `e3262248e55` (GROUP BY on every joined primary key); broken before with the two errors above |
| storefront search on OpenSearch | works on both |
| index content | 3,404 (PG) and 3,426 (MariaDB) products, equal to the products minus 40 hidden parents on each |
| existing databases | need the new aggregate from `mysql-compat.sql` (it runs at install), `psql -f` of the block or a reinstall |

### Replica

| Check | Result |
|---|---|
| `DATABASE_REPLICA_0_URL` on PostgreSQL | works with change `12abc252e15` (the factory built no `PrimaryReadReplicaConnection` before) |
| writes go to the primary | works with change `be901964bdb`; the one write through `fetchOne()` went to the replica; `grep RETURNING` finds no other such write in `src/` |
| walk and order with the replica in sync | works on both |
| replica paused (`pg_wal_replay_pause()`, MariaDB `STOP SLAVE SQL_THREAD`) | same failure on both: the cart page shows no item, guest register answers 500 (`InvalidCriteriaIdsException`), admin read after save returns the old name and stock |
| after resume | works again on both |

Read-your-writes across requests is not guaranteed on either database: Shopware switches to the primary only for the rest of the request that writes.
That is the documented behaviour, it is no PostgreSQL difference.

### SSL

| Check | Result |
|---|---|
| `DATABASE_SSL_CA` on PostgreSQL | works with change `12abc252e15`, every client backend on primary and replica shows `pg_stat_ssl.ssl = t`, TLSv1.3 |
| replica to primary, PgBouncer to server | `verify-full`, works |
| MariaDB with the same variable | works |

### Workers

| Check | PostgreSQL | MariaDB |
|---|---|---|
| two `messenger:consume async low_priority` plus `scheduled-task:run` | works | works |
| failed statement inside a transaction, next statement | broken by design: `SQLSTATE[25P02] In failed sql transaction` until rollback | carries on |
| `services_resetter` reset after that | does not roll back (nesting level stays 1), the next statement still fails until `rollBack()` | does not roll back either; later statements run inside the open transaction |
| killed backend (`pg_terminate_backend`, `KILL`) | the next statement fails with `ConnectionLost`, the one after it reconnects | same |
| messages left `delivered` when the disk ran full | 3 rows (`ProductIndexingMessage`, `IterateEntityIndexerMessage`) wait for the redeliver timeout | – |

A handler that catches a database error and goes on inside the same transaction breaks the rest of that transaction on PostgreSQL, and a leaked open transaction makes every later message of that worker fail until the worker restarts.
On MariaDB the same leak is silent: later messages run in a transaction that is never committed.
So the risk exists on both, PostgreSQL makes it visible; workers with `--time-limit` bound it on both.

### Pooler (PgBouncer, transaction mode)

Probe: one PDO client against PgBouncer next to five busy clients, so its transactions land on different server connections; control run directly against PostgreSQL.

| Check | Through PgBouncer | Direct |
|---|---|---|
| server connections seen by one client | 2 | 1 |
| `SET TIME ZONE 'UTC'` then `SHOW TIME ZONE`, 12 times | 12 × UTC (PgBouncer tracks `Timezone`) | 12 × UTC |
| protocol prepared statement, 12 executes | 12 ok (`max_prepared_statements=200`) | 12 ok |
| SQL `PREPARE`/`EXECUTE` (what `PlanCacheMiddleware` does), 12 executes | 2 ok, then `prepared statement "w10e_plan" does not exist` | 12 ok |
| session advisory lock held, other client tries | blocked 6 of 6, unlock by the holder works | same |
| `LISTEN`, then `NOTIFY` from another client | not received | received |

Shopware through PgBouncer (`DATABASE_PERSISTENT_CONNECTION=0`, no plan cache): the storefront walk places an order, the admin save reads back, and 16 queued indexer messages were consumed by the workers within 5 s.
The messenger transport does not depend on `LISTEN`: Symfony's `PostgreSqlConnection` waits `get_notify_timeout` (default 0 ms) and then polls the table anyway.
The session advisory lock held in the probe because the holding client did not commit in between; PgBouncer lists session-level advisory locks, `SET`, `LISTEN` and SQL `PREPARE` as "Never" in transaction pooling (https://www.pgbouncer.org/features.html).
Shopware's lock store defaults to `flock` (`LOCK_DSN`, `framework.yaml`), so it does not depend on advisory locks; a `LOCK_DSN` pointing at PostgreSQL would not be safe behind the pooler.
`SET foreign_key_checks = 0` becomes a session-level `set_config('session_replication_role', …)` (`DdlRewriter`), which would stay on a pooled server connection; only `CustomEntitySchemaUpdater` sends it at runtime, and only a superuser can set it.

| Setting | Works | Broken |
|---|---|---|
| PgBouncer, persistent off, plan cache off | yes | – |
| PgBouncer with `DATABASE_PLAN_CACHE=1` | – | `EXECUTE` hits server connections without the prepared plan |

## Timings

Other lanes stopped: no.
Single runs only, the sanity block did not finish.

| Measure | PostgreSQL | MariaDB |
|---|---|---|
| `import:entity` 1,000 products, wall | 63.0 s | 50.2 s |
| `es:index --no-queue`, indexing step | 2.9 s | 2.1 s |
| `system:install` | 22 s | 29 s |

The walk timing loop (5 warm-up plus 50 walks per variant, `timing.py`) was started at about 20:15 UTC and did not return; after it, the podman VM stopped answering (`podman ps`, `podman machine ssh` and every published port time out), the last reading before was 774 MB free disk and 2.1 GB available memory.
E did not restart the VM, that would stop the lane.

Commands for D (canonical block), all on E's containers:

```sh
# storefront walk, one JSON line per run
python3 /tmp/wave10-e/walk.py http://localhost:8191   # PostgreSQL, primary plus replica
python3 /tmp/wave10-e/walk.py http://localhost:8192   # MariaDB, primary plus replica
python3 /tmp/wave10-e/walk.py http://localhost:8193   # PostgreSQL through PgBouncer
# median and p95 per step: 5 warm-up, 50 runs
python3 /tmp/wave10-e/timing.py http://localhost:8191 50 5
# import of 1,000 products (the CSV holds new product numbers, copy a fresh one per run, see mkcsv.py)
podman exec instance-w10e-web-pg sh -c 'cd /var/www/html && time bin/console import:entity /tmp/import.csv "+1 day" --profile-technical-name=default_product -q'
podman exec instance-w10e-web-my sh -c 'cd /var/www/html && time bin/console import:entity /tmp/import.csv "+1 day" --profile-technical-name=default_product -q'
```

Stop the workers in the web containers first (they run in the same php containers), and record load average and free disk next to the numbers.

## Proposed change to E5.02

Do not edit the draft; proposal for the next revision:

- Title: "Production connection setup for PostgreSQL: persistent connections, plan cache, replicas, TLS and poolers".
- Add to the Technical TODO:
  - [ ] Support `DATABASE_REPLICA_*` and `DATABASE_SSL_*` in the PostgreSQL connection factory, same variables as MySQL (`DATABASE_SSL_CA` maps to `sslmode=verify-full`, `DATABASE_SSL_DONT_VERIFY_SERVER_CERT` to `require`, `sslmode` in the URL wins).
  - [ ] Route every write to the primary, also writes that return rows (`INSERT … RETURNING` through `fetchOne()`/`executeQuery()`); `PrimaryReadReplicaConnection` only switches on `executeStatement()`, `prepare()`, transactions and savepoints (DBAL 4.6, https://github.com/doctrine/dbal/blob/4.6.x/src/Connections/PrimaryReadReplicaConnection.php).
  - [ ] Document two supported setups: direct (`DATABASE_PERSISTENT_CONNECTION=1`, `DATABASE_PLAN_CACHE=1`, `max_connections` sized for php-fpm children × nodes) and PgBouncer transaction mode (`DATABASE_PERSISTENT_CONNECTION=0`, no plan cache, PgBouncer ≥ 1.21 with `max_prepared_statements > 0`, `ignore_startup_parameters=extra_float_digits,options`).
  - [ ] Document that a failed statement aborts the whole transaction on PostgreSQL, so code must not catch a database error and go on in the same transaction; reset or restart workers that leak a transaction.
- Replace "Measure PgBouncer 1.21 or newer with `max_prepared_statements`, which was not measured" with: functionally proven in wave 10 E (doc 50); speed through PgBouncer still not measured.
- Add finding rows 42 to 45 (below) to `findings`.

## Core findings

Rows added to `docs/core-findings.md`:

- `PrimaryReadReplicaConnection` routes only `executeStatement()`, `prepare()` and transactions to the primary, a write through `executeQuery()`/`fetchOne()` goes to the replica (robustness).
- A prod `cache:clear` deletes every other `var/cache/prod_*` dir, also the ones of other apps sharing `var/cache` (robustness).
- `ProductUrlProvider` joins on a hard-coded backtick alias instead of the iterator's FROM alias (portability).
- `ElasticsearchProductDefinition` groups by `p.id` while selecting other columns of `product` and of joined rows, valid only without `ONLY_FULL_GROUP_BY` (portability, like row 2).

## Fix commits on `poc/wave10`

| Commit | Change |
|---|---|
| `12abc252e15` | `feat(core)`: read replicas and `DATABASE_SSL_*` in `PostgreSQLFactory`, 8 unit tests |
| `2f10df5eb2e` | `fix(core)`: quoted lower case aliases stay out of the column case map, unit test |
| `f44b65f8764` | `fix(core)`: sitemap product query joins on the iterator's FROM alias |
| `be901964bdb` | `fix(core)`: number range `RETURNING` upsert on the primary, unit test |
| `3727203c817` | `fix(core)`: `group_concat(jsonb)` in `mysql-compat.sql` |
| `e3262248e55` | `fix(elasticsearch)`: product indexing GROUP BY lists every joined primary key |
| `07a03ea7c89` | `docs(core)`: `.env.pgsql.dist` for replica, TLS, PgBouncer |

All runs used the shared working tree of `poc/wave10`, including other handoffs' uncommitted changes at the time.

## Cleanup

E's containers and data are still there, because the VM stopped answering before cleanup.
Remove them when the VM answers again:

```sh
podman rm -f instance-w10e-pg instance-w10e-pgreplica instance-w10e-pgbouncer instance-w10e-mariadb instance-w10e-mariadbreplica \
  instance-w10e-web-pg instance-w10e-web-my instance-w10e-web-pgb instance-w10e-opensearch
podman volume prune -f   # anonymous volumes of the removed containers only, check the list first with: podman volume ls -f dangling=true
rm -rf instance/var/log/w10e-pg instance/var/log/w10e-my instance/var/log/w10e-pgb
rm -f instance/config/packages/admin_worker.yaml   # only if nobody else wants the switch
```

The database `w10e_shop` and the OpenSearch indices `rs_w10_e_*` live only in these containers and go with them.
Helper files: `/tmp/wave10-e/` (walk, timing, admin, import CSV, probes, certificates).
