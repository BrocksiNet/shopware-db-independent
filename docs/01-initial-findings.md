# Initial findings (2026-11-18)

Measured with regex file counts on a local checkout at `a7facd873c5` (a branch
off trunk of the same day). Treat the numbers as orders of magnitude; phase 1
replaces them with reproducible scripts run against `instance/`.

## Where the database coupling sits

- `src` has 7362 PHP files.
- The DAL has four storage interfaces: `EntityReaderInterface`,
  `EntitySearcherInterface`, `EntityAggregatorInterface`,
  `EntityWriteGatewayInterface`. 29 of its 474 files import
  `Doctrine\DBAL\Connection`.
- 1410 files import `Doctrine\DBAL\Connection`: 952 in `Migration` directories,
  458 elsewhere.
- The 458 by area: `Core/Framework` 146, `Core/Content` 102, `Core/Checkout` 59,
  `Core/System` 56, `Elasticsearch/Admin` 17, `Core/Test` 12, `Storefront/Theme`
  9, `Storefront/Framework` 9, `Core/Maintenance` 7, rest below 7 each.
- 926 migration classes (`Migration/V6_*`).

## MySQL-specific constructs (files containing them)

| Construct | Files |
|---|---|
| Backtick-quoted identifiers after FROM/JOIN/INTO/UPDATE/TABLE | 678 |
| `Uuid::fromHexToBytes` / `fromBytesToHex` | 340 |
| `JSON_*` functions | 176 |
| `HEX(` / `UNHEX(` | 174 |
| `MultiInsertQueryQueue` / `RetryableQuery` | 50 |
| `IFNULL(` / `IF(` | 34 |
| `GROUP_CONCAT` | 24 |
| `REPLACE INTO` | 15 |
| `INSERT IGNORE` | 14 |
| `GENERATED ALWAYS` / `VIRTUAL` | 13 |
| `ON DUPLICATE KEY` | 12 |
| `CREATE TRIGGER` | 8 |
| `FOREIGN_KEY_CHECKS` / `@@` variables | 3 |

## Connection and environment

- `src/Core/Framework/Adapter/Database/MySQLFactory.php` hardcodes
  `'driver' => 'pdo_mysql'` and an init command that sets
  `@@session.time_zone`, `@@session.group_concat_max_len` and
  `@@session.sql_mode`.
- `composer.json` requires `ext-pdo_mysql`, `doctrine/dbal ~4.4.0`,
  `symfony/serializer ~7.4.0`. `symfony/object-mapper` is not a dependency.
- The dev image `ghcr.io/shopware/docker-dev:php8.4-node24-caddy` ships
  `pdo_mysql` and `pdo_sqlite`, no `pdo_pgsql`.

## The DTO pull request

https://github.com/shopware/shopware/pull/17858 (mitelg, draft, 281 files,
branch `feat/open-api-dto-generator`) generates request and response DTOs from
the OpenAPI schema (`OpenApiDtoGenerator`, `OpenApiDtoGenerationCommand`).

- Its DTO contract (`src/Core/Framework/Api/OpenApi/AGENTS.md`) requires DTOs to
  stay mutable so extension events can adjust them, and keeps optional fields
  uninitialized.
- Its example `AccountNewsletterRecipientV2Route` returns a
  `ReadNewsletterRecipientStatusResponse` DTO but still builds a `Criteria` and
  calls a `SalesChannelRepository`.

Conclusion: the pull request types the API boundary. It does not decouple
storage. It is the upper half of the layer this project needs; the lower half
(a storage port below the route) is missing.

Related: https://github.com/shopware/shopware/pull/15487 (patzick, draft)
generates DTOs with the external `@shopware/api-gen` tool.
