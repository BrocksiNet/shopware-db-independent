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
