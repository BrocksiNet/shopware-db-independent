# Read store baseline (wave 9, handoff P)

Handoff P of wave 9: branch, engine containers, dataset, harness extension and the O0 / O0b / O1 baselines for the read store research (`docs/38-read-store-plan.md`).

## Branch

`poc/read-store` exists in `instance/`.
It was created by the orchestrator from `poc/orm-spike` at `46a47f1a7c9` with a clean tree and is checked out.
All wave 9 code goes there.
Handoff K may create its folders under `src/Core/Framework/ReadStore/` now (branch ready).

## Engine containers

Both containers are defined in the lane override `~/shopware-dev/instances/pg.yaml` (sw-dev mechanism, section "wave 9 read store"), started with `podman compose up -d opensearch mongodb web` in `instance/`.

| Container | Image | Digest | Limits |
|---|---|---|---|
| `instance-opensearch-1` | `opensearchproject/opensearch:2` (2.19.7, Lucene 9.12.3), security plugin disabled as in `compose.yaml` | `sha256:d89333b6bd4a13b9a95aef7f373c0a6e73440f59bc0d8d1460f9b347289ed0ef` | 8 CPUs / 16 GiB, JVM heap `-Xms4g -Xmx4g` (set in pg.yaml) |
| `instance-mongodb-1` | `mongo:8` (8.3.17) | `sha256:747773029b84309981a3624a1af64ffc8c4d792283cc0834f26fe01fc6d28b34` | 8 CPUs / 16 GiB |
| `instance-web-1` | `localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy` rebuilt with `mongodb` | image id `d0d0d0f5959e` (`sha256:54c51f408eb15dcb062a539d2d24f6f30040d8cfeaa3e1b25f6e6a65caa478e2` local digest) | unchanged |

The shared override `shared.podman-mutagen.yaml` puts `opensearch` behind the compose profile `opensearch`; `pg.yaml` resets it with `profiles: !reset []` so the lane always starts it.
Volumes `opensearch-data` and `mongodb-data` are new (named volumes of the compose project `instance`).
Reachable from `instance-web-1` as `http://opensearch:9200` (`OPENSEARCH_URL` is set by the upstream compose file) and `mongodb://mongodb:27017`.

## PHP extension and composer

`docs/environment/web.Dockerfile` now runs `install-php-extensions pdo_pgsql pgsql mongodb`.
Steps (no hand-patching of the running container):

1. `cd docs/environment && podman build -t localhost/shopware-docker-dev-pgsql:php8.4-node24-caddy -f web.Dockerfile .`
2. `cd instance && podman compose up -d opensearch mongodb web` (recreates `instance-web-1`; the code lives in the named volume `instance_shopware-src`, so `vendor/` and the synced tree stay).
3. The mutagen session `shopware-pg` lost its beta side on the recreate (`Connecting to beta`), `mutagen sync resume shopware-pg` brought it back to `Watching for changes`.

Result: `php -r 'echo phpversion("mongodb");'` prints `2.5.8`.
`composer require mongodb/mongodb` installed `mongodb/mongodb` 2.5.1 (`^2.5` in `composer.json`, commit `7819b64`).
`composer.lock` is in `.gitignore` of the checkout (line `/composer.lock`), so it cannot be committed; the version above is what `composer.json` resolves to today.
