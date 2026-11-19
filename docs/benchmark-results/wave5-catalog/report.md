### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 102.5 | 106.3 | 181.3 | 149.4 | 103.9 | 105.8 | 140.3 |
| storefront listing with filter | 40 | 63.7 | 63.6 | 118.4 | 94.7 | 60.8 | 62.2 | 83.8 |
| storefront search | 40 | 77.5 | 78.1 | 149.0 | 115.1 | 74.1 | 76.6 | 106.4 |
| storefront product detail | 40 | 77.3 | 76.6 | 155.2 | 131.8 | 75.5 | 73.8 | 123.6 |
| store API product listing with aggregations | 60 | 22.6 | 20.5 | 38.3 | 24.9 | 20.2 | 19.5 | 21.4 |
| admin API product search with aggregations | 60 | 21.3 | 21.7 | 39.7 | 26.2 | 20.2 | 20.0 | 24.3 |
| admin API bulk sync write (50 products) | 10 | 249.0 | 300.8 | 427.1 | 430.8 | 248.7 | 293.7 | 398.3 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 139.3 | 148.6 | 227.3 | 188.6 | 142.9 | 149.7 | 183.6 |
| storefront listing with filter | 85.1 | 80.7 | 149.1 | 121.7 | 79.5 | 79.4 | 107.0 |
| storefront search | 97.7 | 97.2 | 179.9 | 158.6 | 97.8 | 95.6 | 139.6 |
| storefront product detail | 105.5 | 103.0 | 201.0 | 169.3 | 102.9 | 98.6 | 164.7 |
| store API product listing with aggregations | 39.5 | 37.5 | 77.9 | 54.7 | 43.3 | 36.7 | 60.5 |
| admin API product search with aggregations | 29.6 | 30.6 | 46.6 | 35.2 | 28.7 | 27.9 | 33.4 |
| admin API bulk sync write (50 products) | 342.4 | 367.0 | 503.1 | 508.2 | 287.6 | 364.8 | 463.8 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 92.9..115.5 | 95.7..114.3 | 175.4..187.0 | 142.0..153.5 | 98.9..120.2 | 102.6..110.5 | 133.3..150.2 |
| storefront listing with filter | 61.9..70.7 | 60.1..68.6 | 110.2..121.6 | 86.2..98.1 | 59.6..62.6 | 59.0..65.3 | 78.6..88.6 |
| storefront search | 67.4..78.8 | 72.2..81.8 | 138.9..153.0 | 113.2..123.1 | 65.6..78.4 | 72.1..79.2 | 105.8..116.0 |
| storefront product detail | 72.6..78.7 | 71.5..79.1 | 146.1..162.6 | 123.4..135.3 | 72.9..77.9 | 69.6..78.3 | 118.2..125.4 |
| store API product listing with aggregations | 18.3..26.5 | 19.5..21.9 | 36.3..43.2 | 21.5..27.4 | 17.5..30.9 | 18.6..22.5 | 18.0..26.3 |
| admin API product search with aggregations | 20.8..21.9 | 21.3..22.2 | 39.4..40.0 | 26.1..27.0 | 20.0..24.4 | 19.9..22.4 | 23.4..24.5 |
| admin API bulk sync write (50 products) | 238.4..268.1 | 283.1..312.9 | 420.1..443.4 | 423.5..445.8 | 235.7..261.3 | 280.8..303.4 | 390.0..409.3 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 35.0 | 31.6 | 20.6 | 23.2 | 35.2 | 33.1 | 25.3 |
| storefront listing with filter | 52.0 | 53.8 | 28.3 | 36.3 | 53.0 | 57.6 | 39.4 |
| storefront search | 52.9 | 48.6 | 26.0 | 31.8 | 53.8 | 50.4 | 34.5 |
| storefront product detail | 47.3 | 45.7 | 21.9 | 26.6 | 47.9 | 47.4 | 28.8 |
| store API product listing with aggregations | 119.5 | 114.3 | 68.1 | 98.4 | 119.5 | 118.4 | 111.4 |
| admin API product search with aggregations | 150.4 | 129.5 | 79.6 | 124.6 | 152.8 | 138.3 | 137.9 |
| admin API bulk sync write (50 products) | 12.1 | 9.6 | 1.6 | 3.0 | 11.9 | 9.2 | 1.0 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 33.6..36.9 | 28.6..35.5 | 18.1..20.9 | 21.8..24.3 | 31.0..38.4 | 31.3..37.2 | 25.0..27.7 |
| storefront listing with filter | 51.6..55.7 | 52.1..58.8 | 27.7..29.5 | 35.2..42.2 | 49.8..56.1 | 49.4..62.2 | 38.4..42.9 |
| storefront search | 45.5..54.9 | 45.2..52.0 | 24.8..27.1 | 27.9..32.3 | 46.7..57.1 | 45.6..53.9 | 32.1..35.4 |
| storefront product detail | 45.5..48.6 | 45.3..48.4 | 21.6..23.4 | 25.6..27.1 | 46.9..48.6 | 43.2..49.3 | 27.5..29.6 |
| store API product listing with aggregations | 115.0..121.3 | 107.4..117.5 | 64.8..70.1 | 94.7..101.3 | 115.1..122.1 | 113.2..119.6 | 102.2..112.1 |
| admin API product search with aggregations | 120.7..151.2 | 121.2..138.6 | 71.0..85.0 | 114.7..125.7 | 141.2..155.2 | 132.2..140.8 | 125.2..139.3 |
| admin API bulk sync write (50 products) | 11.6..12.5 | 8.4..9.7 | 1.0..2.5 | 0.6..4.3 | 11.8..12.4 | 8.9..9.6 | 0.6..1.6 |

### Errors (responses other than 200, latency and throughput runs)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | Probe pass |
|---|---|---|---|---|---|---|---|---|
| storefront home | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront listing with filter | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront search | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront product detail | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| store API product listing with aggregations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| admin API product search with aggregations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| admin API bulk sync write (50 products) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Ratio of the median latency to MySQL 8.4 (same setting)

| Scenario | MariaDB / MySQL 8.4 | PostgreSQL / MySQL 8.4 | PostgreSQL + PgBouncer / MySQL 8.4 | MariaDB persistent / MySQL 8.4 persistent | PostgreSQL persistent / MySQL 8.4 persistent | clear (ranges do not overlap) |
|---|---|---|---|---|---|---|
| storefront home | 0.96 | 1.71 | 1.40 | 0.98 | 1.33 | no, yes, yes, no, yes |
| storefront listing with filter | 1.00 | 1.86 | 1.49 | 0.98 | 1.35 | no, yes, yes, no, yes |
| storefront search | 0.99 | 1.91 | 1.47 | 0.97 | 1.39 | no, yes, yes, no, yes |
| storefront product detail | 1.01 | 2.03 | 1.72 | 1.02 | 1.67 | no, yes, yes, no, yes |
| store API product listing with aggregations | 1.10 | 1.87 | 1.21 | 1.03 | 1.10 | no, yes, no, no, no |
| admin API product search with aggregations | 0.98 | 1.83 | 1.21 | 1.01 | 1.21 | no, yes, yes, no, yes |
| admin API bulk sync write (50 products) | 0.83 | 1.42 | 1.43 | 0.85 | 1.36 | yes, yes, yes, yes, yes |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 73 | 188.4 | 100.3 | 87.4 | 11.4 | 6.1 % | 1.5 | 0.8 % | 88.1 |
| storefront listing with filter | 40 | 63 | 119.9 | 62.1 | 54.5 | 6.8 | 5.7 % | 0.7 | 0.6 % | 57.8 |
| storefront search | 40 | 64 | 131.9 | 76.1 | 65.2 | 9.7 | 7.4 % | 0.8 | 0.6 % | 55.8 |
| storefront product detail | 40 | 82 | 149.0 | 86.1 | 67.1 | 17.6 | 11.8 % | 0.9 | 0.6 % | 63.0 |
| store API product listing with aggregations | 60 | 12 | 35.8 | 19.8 | 19.0 | 0.8 | 2.2 % | 0.1 | 0.3 % | 16.0 |
| admin API product search with aggregations | 60 | 14 | 41.5 | 20.4 | 18.6 | 1.6 | 3.8 % | 0.2 | 0.5 % | 21.0 |
| admin API bulk sync write (50 products) | 10 | 374 | 492.4 | 378.5 | 310.4 | 47.6 | 9.7 % | 21.6 | 4.4 % | 113.9 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 196.3 | 92.1 | 11.8 | 1.6 | 0.156 | 0.021 |
| storefront listing with filter | 120.8 | 55.0 | 7.0 | 0.7 | 0.108 | 0.012 |
| storefront search | 135.1 | 67.3 | 9.9 | 0.9 | 0.152 | 0.013 |
| storefront product detail | 152.8 | 68.9 | 18.1 | 0.9 | 0.215 | 0.010 |
| store API product listing with aggregations | 48.6 | 25.3 | 2.0 | 0.2 | 0.066 | 0.009 |
| admin API product search with aggregations | 42.3 | 18.4 | 1.7 | 0.2 | 0.112 | 0.016 |
| admin API bulk sync write (50 products) | 497.4 | 313.2 | 46.8 | 21.4 | 0.127 | 0.058 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 188.8 | 181.3 |
| storefront listing with filter | 120.4 | 118.4 |
| storefront search | 132.3 | 149.0 |
| storefront product detail | 149.4 | 155.2 |
| store API product listing with aggregations | 36.4 | 38.3 |
| admin API product search with aggregations | 42.0 | 39.7 |
| admin API bulk sync write (50 products) | 492.9 | 427.1 |
