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
   describes the image. It was actually produced with the equivalent
   run-and-commit, because `podman build` hung (see below):

   ```bash
   podman run --name pgsql-ext-build --user root --entrypoint sh \
     ghcr.io/shopware/docker-dev:php8.4-node24-caddy \
     -c 'install-php-extensions pdo_pgsql pgsql'
   podman commit --change 'USER www-data' --change 'ENTRYPOINT ["/entrypoint"]' \
     --change 'CMD ["/usr/bin/supervisord","-c","/etc/supervisord.conf"]' \
     pgsql-ext-build localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy
   ```
3. `~/shopware-dev/instances/pg.yaml` (outside this repository) got the `image`
   override and `POSTGRES_URL` for `web`, the `postgres` service and the
   `postgres-data` volume.

## Known problem: Podman VM `/Users` mount hangs

On 2026-11-18 every read under `/Users` inside the Podman VM blocked (`ls -d
/Users` stays in uninterruptible wait). Effects:

- `podman build` with a context under `/Users` hangs without output.
- Compose cannot create a container that bind-mounts a host path. The shared
  override mounts `~/.local/share/phpactor/phpactor.phar` into `web`.

Workaround in `pg.yaml`: `volumes: !override` for `web`, keeping only the
`shopware-src` volume. The lane has no phpactor until that block is removed.
Source sync is unaffected, it runs through Mutagen and a named volume.

The cause is not established. A `podman machine` restart is the expected fix; it
stops the containers of every lane, so it has not been done.
