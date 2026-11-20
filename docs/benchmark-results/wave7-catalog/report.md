### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 94.9 | 99.0 | 145.6 | 125.1 | 93.9 | 94.4 | 125.0 | 106.4 |
| storefront listing with filter | 40 | 56.4 | 59.9 | 101.0 | 78.5 | 54.8 | 54.9 | 69.0 | 62.3 |
| storefront search | 40 | 80.4 | 79.6 | 148.3 | 113.2 | 72.6 | 74.1 | 100.0 | 106.1 |
| storefront product detail | 40 | 80.3 | 78.7 | 150.5 | 120.5 | 78.4 | 77.0 | 109.9 | 112.9 |
| store API product listing with aggregations | 60 | 21.3 | 21.6 | 38.3 | 24.5 | 21.1 | 22.6 | 19.0 | 19.5 |
| admin API product search with aggregations | 60 | 22.7 | 23.7 | 45.5 | 29.4 | 23.5 | 23.4 | 25.0 | 23.9 |
| admin API bulk sync write (50 products) | 10 | 263.7 | 371.2 | 520.3 | 557.2 | 263.4 | 312.7 | 503.9 | 496.3 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 129.7 | 136.3 | 192.4 | 162.3 | 112.3 | 141.8 | 170.9 | 151.7 |
| storefront listing with filter | 79.2 | 76.9 | 125.3 | 104.3 | 70.2 | 70.4 | 93.8 | 98.5 |
| storefront search | 108.9 | 98.6 | 180.8 | 148.3 | 106.6 | 133.6 | 170.6 | 201.1 |
| storefront product detail | 141.5 | 217.3 | 191.7 | 151.3 | 117.7 | 104.6 | 170.9 | 174.7 |
| store API product listing with aggregations | 41.7 | 40.9 | 72.4 | 57.2 | 43.6 | 45.5 | 49.1 | 47.4 |
| admin API product search with aggregations | 42.9 | 51.3 | 61.5 | 44.4 | 42.5 | 45.1 | 51.6 | 45.1 |
| admin API bulk sync write (50 products) | 458.2 | 833.7 | 1370.3 | 1775.7 | 915.9 | 1049.4 | 1427.1 | 615.3 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 87.2..110.3 | 85.4..105.6 | 137.8..158.0 | 116.2..135.0 | 84.9..104.8 | 85.0..130.5 | 107.4..163.3 | 101.0..118.0 |
| storefront listing with filter | 50.2..69.0 | 52.0..65.5 | 92.3..108.9 | 74.7..83.8 | 50.0..64.3 | 50.4..61.7 | 63.1..89.0 | 58.0..80.0 |
| storefront search | 61.1..86.6 | 63.8..81.1 | 133.1..158.9 | 103.8..129.0 | 66.9..80.4 | 64.3..119.3 | 86.4..153.6 | 87.5..179.7 |
| storefront product detail | 77.0..133.7 | 73.7..182.4 | 131.5..157.8 | 115.7..139.7 | 73.4..99.7 | 69.8..91.6 | 100.2..131.1 | 97.0..153.3 |
| store API product listing with aggregations | 19.8..25.5 | 21.0..24.0 | 35.0..46.4 | 23.1..28.6 | 20.1..27.5 | 19.6..29.4 | 17.7..22.1 | 18.1..24.0 |
| admin API product search with aggregations | 22.0..38.9 | 22.1..43.2 | 39.2..58.5 | 26.5..43.0 | 22.4..39.6 | 21.8..42.4 | 22.4..45.3 | 22.2..43.2 |
| admin API bulk sync write (50 products) | 253.5..428.0 | 297.5..551.0 | 485.4..1258.9 | 513.1..1702.2 | 257.2..791.9 | 306.6..758.9 | 453.1..970.1 | 443.9..558.7 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 40.5 | 38.2 | 24.7 | 29.5 | 40.8 | 39.5 | 31.3 | 38.4 |
| storefront listing with filter | 58.1 | 61.0 | 34.0 | 42.1 | 60.1 | 61.0 | 47.7 | 56.3 |
| storefront search | 51.7 | 49.3 | 27.8 | 32.6 | 53.0 | 51.1 | 36.2 | 38.8 |
| storefront product detail | 48.0 | 48.6 | 26.1 | 31.6 | 48.7 | 48.2 | 34.2 | 35.6 |
| store API product listing with aggregations | 104.2 | 97.9 | 66.5 | 91.2 | 99.4 | 93.9 | 105.0 | 109.5 |
| admin API product search with aggregations | 149.1 | 136.1 | 90.1 | 131.3 | 149.3 | 137.6 | 151.7 | 152.0 |
| admin API bulk sync write (50 products) | 11.7 | 9.0 | 3.7 | 3.5 | 12.4 | 9.0 | 3.7 | 3.8 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 38.7..40.8 | 35.7..39.3 | 23.5..25.3 | 28.4..30.1 | 38.0..41.2 | 35.5..39.8 | 29.9..32.1 | 36.4..38.6 |
| storefront listing with filter | 55.3..61.5 | 57.4..62.2 | 32.1..35.8 | 39.8..43.5 | 56.4..61.2 | 58.1..62.3 | 46.8..48.5 | 50.8..58.8 |
| storefront search | 44.0..54.1 | 40.9..51.8 | 24.7..28.3 | 31.7..34.6 | 52.5..56.3 | 46.4..53.2 | 35.1..37.8 | 36.9..39.4 |
| storefront product detail | 43.0..48.9 | 45.8..49.2 | 25.1..26.6 | 30.9..32.4 | 46.4..49.1 | 47.5..49.3 | 33.2..34.8 | 31.6..36.5 |
| store API product listing with aggregations | 93.0..111.1 | 89.0..105.8 | 56.3..71.3 | 82.2..96.3 | 78.4..116.1 | 80.9..110.7 | 89.3..109.0 | 91.8..118.8 |
| admin API product search with aggregations | 143.7..149.6 | 129.7..137.8 | 89.7..90.4 | 129.1..131.9 | 145.2..151.5 | 131.2..138.5 | 144.8..152.8 | 147.7..152.3 |
| admin API bulk sync write (50 products) | 10.5..12.4 | 7.6..9.7 | 3.1..3.9 | 3.2..3.9 | 10.1..12.7 | 8.5..9.4 | 3.3..4.1 | 3.6..4.4 |

### Errors (responses other than 200, latency and throughput runs)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache | Probe pass |
|---|---|---|---|---|---|---|---|---|---|
| storefront home | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront listing with filter | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront search | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| storefront product detail | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| store API product listing with aggregations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| admin API product search with aggregations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| admin API bulk sync write (50 products) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Ratio of the median latency to MySQL 8.4 (same setting)

| Scenario | MariaDB / MySQL 8.4 | PostgreSQL / MySQL 8.4 | PostgreSQL + PgBouncer / MySQL 8.4 | MariaDB persistent / MySQL 8.4 persistent | PostgreSQL persistent / MySQL 8.4 persistent | clear (ranges do not overlap) |
|---|---|---|---|---|---|---|
| storefront home | 0.96 | 1.47 | 1.26 | 1.00 | 1.32 | no, yes, yes, no, no |
| storefront listing with filter | 0.94 | 1.68 | 1.31 | 1.00 | 1.26 | no, yes, yes, no, yes |
| storefront search | 1.01 | 1.86 | 1.42 | 0.98 | 1.35 | no, yes, yes, no, no |
| storefront product detail | 1.02 | 1.91 | 1.53 | 1.02 | 1.43 | no, no, no, no, yes |
| store API product listing with aggregations | 0.99 | 1.78 | 1.14 | 0.94 | 0.84 | no, yes, no, no, no |
| admin API product search with aggregations | 0.96 | 1.92 | 1.24 | 1.00 | 1.07 | no, no, no, no, no |
| admin API bulk sync write (50 products) | 0.71 | 1.40 | 1.50 | 0.84 | 1.61 | no, no, no, no, no |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 73 | 137.8 | 70.2 | 67.0 | 2.0 | 1.4 % | 1.2 | 0.9 % | 67.5 |
| storefront listing with filter | 40 | 63 | 121.6 | 60.5 | 57.3 | 2.3 | 1.9 % | 0.8 | 0.7 % | 61.1 |
| storefront search | 40 | 64 | 169.4 | 99.3 | 93.2 | 4.3 | 2.5 % | 1.2 | 0.7 % | 70.2 |
| storefront product detail | 40 | 82 | 134.7 | 71.3 | 67.7 | 2.5 | 1.9 % | 0.9 | 0.7 % | 63.4 |
| store API product listing with aggregations | 60 | 12 | 44.1 | 24.5 | 23.9 | 0.5 | 1.1 % | 0.2 | 0.3 % | 19.6 |
| admin API product search with aggregations | 60 | 14 | 52.4 | 24.6 | 23.8 | 0.6 | 1.1 % | 0.3 | 0.6 % | 27.7 |
| admin API bulk sync write (50 products) | 10 | 394 | 558.5 | 450.2 | 396.4 | 33.0 | 5.9 % | 21.6 | 3.9 % | 108.3 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 140.1 | 68.0 | 2.1 | 1.2 | 0.027 | 0.016 |
| storefront listing with filter | 124.0 | 58.6 | 2.3 | 0.8 | 0.037 | 0.013 |
| storefront search | 179.1 | 97.7 | 4.7 | 1.3 | 0.067 | 0.019 |
| storefront product detail | 137.1 | 68.8 | 2.6 | 0.9 | 0.031 | 0.011 |
| store API product listing with aggregations | 57.4 | 30.6 | 0.7 | 0.3 | 0.041 | 0.013 |
| admin API product search with aggregations | 55.2 | 25.3 | 0.6 | 0.4 | 0.040 | 0.022 |
| admin API bulk sync write (50 products) | 567.5 | 398.9 | 34.1 | 21.4 | 0.084 | 0.055 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 138.1 | 145.6 |
| storefront listing with filter | 121.9 | 101.0 |
| storefront search | 169.8 | 148.3 |
| storefront product detail | 135.0 | 150.5 |
| store API product listing with aggregations | 44.7 | 38.3 |
| admin API product search with aggregations | 53.4 | 45.5 |
| admin API bulk sync write (50 products) | 558.9 | 520.3 |
