# Environment (phase 0, 2026-11-18)

## What runs

`sw-dev` lane `pg`, checkout in `instance/` (full clone of `shopware/shopware`,
trunk at `ae0190f5892`, branch `poc/postgresql`, remotes `origin` = upstream and
`fork` = `BrocksiNet/shopware`).

| Service | Image | Host port |
|---|---|---|
| web | `localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy` | 8110 (http://pg.localhost:8088) |
| database | `mariadb:10.11` | 3314 |
| postgres | `postgres:18-alpine` (PostgreSQL 18.7) | 5442 |
| adminer | `adminer` | 9088 |
| mailer | `axllent/mailpit` | 8033 |
| valkey | `valkey/valkey:alpine` | none |

Shopware is installed on MariaDB and still uses it (`DATABASE_URL` unchanged).
PostgreSQL runs next to it with user, password and database `shopware`. The web
container gets `POSTGRES_URL=pgsql://shopware:shopware@postgres:5432/shopware`.

Verified from inside the web container: PHP has `pdo_pgsql` and `pgsql`, a PDO
connection to `postgres:5432` works, and `SELECT uuidv7()` returns a value, so
PostgreSQL 18 can generate UUIDv7 ids natively.

## How it was set up

1. `sw-dev lane create pg --ref trunk --path <project>/instance --full-clone`
2. Web image: the dev image has no PostgreSQL driver. `environment/web.Dockerfile`
   describes the image:

   ```bash
   podman build -t localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy \
     -f docs/environment/web.Dockerfile docs/environment
   ```
3. `~/shopware-dev/instances/pg.yaml` (outside this repository) got the `image`
   override and `POSTGRES_URL` for `web`, the `postgres` service and the
   `postgres-data` volume.

## Switch test databases (wave 3)

The switch harness (`scripts/switch-db.sh`, results in `docs/12-switch-test.md`) installs Shopware from scratch on MySQL 8, MariaDB and PostgreSQL.
All three use the separate database `shopware_switch`, the lane database `shopware` is never touched.

MariaDB (`instance-database-1`) and PostgreSQL (`instance-postgres-1`) are the existing lane containers, they run without CPU or memory limits.
MySQL 8 runs as a fourth container on the same compose network (`instance_default`, alias `mysql`), also without limits, with the same server settings as the MariaDB service in `compose.yaml` (sql_mode, buffer pool 1 GB, `log_bin_trust_function_creators`, UTC):

```bash
podman run -d --name instance-mysql-1 --network instance_default --network-alias mysql \
  -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=shopware_switch -v instance_mysql-data:/var/lib/mysql \
  docker.io/library/mysql:8.4 \
  --sql_mode=STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION \
  --log_bin_trust_function_creators=1 --binlog_cache_size=16M --join_buffer_size=1024M \
  --innodb_log_file_size=128M --innodb_buffer_pool_size=1024M --innodb_buffer_pool_instances=1 \
  --group_concat_max_len=320000 --default-time-zone=+00:00 --max_binlog_size=512M --binlog_expire_logs_seconds=86400
```

It is not part of `compose.yaml` (that file belongs to the Shopware checkout), so `podman compose down` does not remove it.
Stop and remove it with `podman rm -f instance-mysql-1` (the volume `instance_mysql-data` stays).
Image: `mysql:8.4` (8.4.13 at the time of writing).

Connection URLs used by the script (passed with `podman exec -e DATABASE_URL=...`, the lane `.env` stays untouched):

| Database | `DATABASE_URL` | Port of the smoke web process |
|---|---|---|
| MySQL 8 | `mysql://root:root@mysql:3306/shopware_switch` | 8092 |
| MariaDB | `mysql://root:root@database:3306/shopware_switch` | 8093 |
| PostgreSQL | `pgsql://shopware:shopware@postgres:5432/shopware_switch` | 8094 |

How the smoke test runs without breaking the lane: a second web process `php -S 127.0.0.1:<port> -t public public/index.php` is started inside `instance-web-1` with its own `DATABASE_URL`, `APP_URL=http://localhost:<port>`, `APP_ENV=prod` and its own `APP_CACHE_DIR=/tmp/sw-switch-<db>` (so the compiled container and cache of the lane in `var/cache` are never reused or overwritten).
The Python smoke script runs inside the container and talks to that port, the lane keeps serving on http://pg.localhost:8088.
`framework:demodata` refuses to run outside `APP_ENV=prod`, therefore the whole harness runs in `prod`.

## Incident: Podman VM `/Users` mount hung (resolved)

On 2026-11-18, for at least 30 minutes, every read under `/Users` inside the
Podman VM blocked (`podman machine ssh "ls -d /Users"` stayed in uninterruptible
wait). While it lasted:

- `podman build` with a context under `/Users` hung without printing a step.
- `podman compose up -d --force-recreate web` hung at "Recreate"/"Creating",
  because the shared override bind-mounts
  `~/.local/share/phpactor/phpactor.phar` into `web`.

It cleared without a VM restart (uptime was unchanged). The cause is not
established. It was first seen after a `podman build` that used `/tmp` as build
context was started and aborted.

Afterwards the image was rebuilt from `environment/web.Dockerfile` (24 s), the
temporary `volumes: !override` workaround was removed from `pg.yaml`, and the
web container was recreated with `sw-dev compose recreate-web pg`.

Check if it happens again:

```bash
podman machine ssh "timeout 6 ls -d /Users >/dev/null; echo exit=\$?"   # 124 = hung
```
