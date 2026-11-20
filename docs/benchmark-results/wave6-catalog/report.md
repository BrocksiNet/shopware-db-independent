### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 95.1 | 95.3 | 162.9 | 135.2 | 96.1 | 97.0 | 131.7 | 114.3 |
| storefront listing with filter | 40 | 57.5 | 61.3 | 106.5 | 86.0 | 59.5 | 56.4 | 70.9 | 66.8 |
| storefront search | 40 | 59.5 | 61.5 | 130.7 | 107.0 | 59.4 | 62.1 | 99.5 | 97.1 |
| storefront product detail | 40 | 73.8 | 73.5 | 149.8 | 121.6 | 70.9 | 70.3 | 121.0 | 114.1 |
| store API product listing with aggregations | 60 | 22.8 | 23.1 | 40.7 | 28.6 | 28.2 | 23.8 | 20.3 | 22.6 |
| admin API product search with aggregations | 60 | 22.2 | 23.1 | 41.0 | 27.9 | 21.5 | 22.4 | 24.9 | 25.0 |
| admin API bulk sync write (50 products) | 10 | 254.2 | 307.9 | 555.3 | 565.9 | 251.7 | 307.2 | 510.6 | 497.0 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 134.0 | 127.0 | 219.2 | 180.1 | 131.4 | 130.2 | 188.8 | 168.5 |
| storefront listing with filter | 79.7 | 87.1 | 146.6 | 119.7 | 75.8 | 74.1 | 97.3 | 96.3 |
| storefront search | 76.0 | 81.6 | 163.3 | 135.7 | 86.1 | 78.7 | 125.5 | 126.1 |
| storefront product detail | 102.3 | 107.6 | 188.3 | 149.5 | 99.9 | 88.3 | 162.8 | 157.7 |
| store API product listing with aggregations | 51.6 | 54.1 | 78.2 | 71.0 | 52.0 | 53.0 | 57.3 | 59.2 |
| admin API product search with aggregations | 30.9 | 32.4 | 58.2 | 37.2 | 29.8 | 33.3 | 34.3 | 33.7 |
| admin API bulk sync write (50 products) | 355.2 | 390.0 | 611.6 | 723.2 | 369.7 | 404.4 | 621.2 | 576.7 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 83.9..107.8 | 88.4..97.0 | 151.6..165.4 | 128.5..142.1 | 86.9..96.8 | 88.3..101.4 | 120.2..142.9 | 100.3..124.5 |
| storefront listing with filter | 52.1..59.4 | 51.6..68.1 | 102.7..117.7 | 76.4..87.1 | 50.5..64.3 | 50.5..59.8 | 69.6..79.2 | 60.2..75.5 |
| storefront search | 59.4..63.9 | 60.1..65.8 | 125.8..132.2 | 101.8..107.6 | 58.3..64.3 | 59.7..63.3 | 97.6..101.0 | 95.1..98.0 |
| storefront product detail | 72.4..75.4 | 71.8..77.9 | 143.5..152.7 | 117.3..127.4 | 69.6..73.0 | 68.9..72.2 | 114.7..141.0 | 110.3..119.4 |
| store API product listing with aggregations | 21.3..29.8 | 21.5..35.5 | 38.2..45.8 | 26.3..40.7 | 19.2..29.7 | 21.8..27.7 | 19.5..23.2 | 18.7..24.2 |
| admin API product search with aggregations | 21.4..23.2 | 22.4..24.9 | 40.4..41.9 | 27.0..28.5 | 20.9..25.6 | 21.5..27.8 | 24.1..25.4 | 24.1..25.8 |
| admin API bulk sync write (50 products) | 238.5..281.6 | 293.4..333.4 | 514.3..563.8 | 536.9..583.4 | 242.5..272.2 | 302.1..320.5 | 478.2..533.4 | 470.2..532.4 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 36.6 | 34.1 | 21.6 | 25.3 | 36.4 | 35.0 | 27.0 | 31.0 |
| storefront listing with filter | 60.5 | 61.1 | 32.3 | 41.7 | 61.8 | 64.1 | 44.4 | 52.0 |
| storefront search | 55.3 | 52.3 | 25.0 | 29.6 | 55.7 | 52.2 | 32.3 | 33.5 |
| storefront product detail | 45.5 | 45.3 | 22.7 | 26.8 | 47.1 | 44.4 | 28.1 | 29.3 |
| store API product listing with aggregations | 110.8 | 110.0 | 68.5 | 94.3 | 118.9 | 110.4 | 108.8 | 114.2 |
| admin API product search with aggregations | 140.5 | 134.0 | 78.0 | 115.8 | 143.7 | 140.1 | 138.5 | 130.0 |
| admin API bulk sync write (50 products) | 11.5 | 8.9 | 3.8 | 3.7 | 12.0 | 9.1 | 3.8 | 3.6 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent | PostgreSQL persistent + plan cache |
|---|---|---|---|---|---|---|---|---|
| storefront home | 34.7..38.7 | 32.7..36.2 | 19.0..22.9 | 22.8..26.9 | 35.1..38.3 | 30.2..36.4 | 23.3..28.3 | 27.8..34.0 |
| storefront listing with filter | 54.3..64.3 | 58.9..62.6 | 29.2..35.0 | 38.8..43.7 | 56.9..66.1 | 55.1..65.4 | 42.3..47.0 | 47.6..53.2 |
| storefront search | 50.8..55.6 | 51.3..53.7 | 24.5..25.2 | 28.4..30.4 | 51.7..56.6 | 41.1..52.7 | 29.3..32.5 | 33.2..34.0 |
| storefront product detail | 42.4..47.8 | 43.1..47.8 | 21.7..23.2 | 26.4..27.8 | 44.5..48.7 | 42.7..47.7 | 24.1..29.2 | 26.9..29.8 |
| store API product listing with aggregations | 101.2..114.8 | 99.8..113.6 | 67.0..69.7 | 92.7..97.1 | 109.7..122.5 | 102.8..117.2 | 103.7..110.0 | 110.3..115.9 |
| admin API product search with aggregations | 134.5..144.2 | 127.4..137.5 | 71.8..86.7 | 111.7..124.5 | 138.0..152.4 | 134.7..140.8 | 119.5..141.4 | 118.1..132.9 |
| admin API bulk sync write (50 products) | 10.2..11.8 | 8.0..9.3 | 3.2..4.2 | 2.9..3.7 | 11.5..12.6 | 8.8..9.3 | 2.9..4.0 | 2.9..4.1 |

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
| storefront home | 1.00 | 1.71 | 1.42 | 0.99 | 1.36 | no, yes, yes, no, yes |
| storefront listing with filter | 0.94 | 1.74 | 1.40 | 1.05 | 1.26 | no, yes, yes, no, yes |
| storefront search | 0.97 | 2.13 | 1.74 | 0.96 | 1.60 | no, yes, yes, no, yes |
| storefront product detail | 1.00 | 2.04 | 1.66 | 1.01 | 1.72 | no, yes, yes, no, yes |
| store API product listing with aggregations | 0.99 | 1.76 | 1.24 | 1.19 | 0.86 | no, yes, no, no, no |
| admin API product search with aggregations | 0.96 | 1.77 | 1.21 | 0.96 | 1.11 | no, yes, yes, no, no |
| admin API bulk sync write (50 products) | 0.83 | 1.80 | 1.84 | 0.82 | 1.66 | yes, yes, yes, yes, yes |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 73 | 150.1 | 80.0 | 68.7 | 10.2 | 6.8 % | 1.2 | 0.8 % | 70.0 |
| storefront listing with filter | 40 | 63 | 101.6 | 52.6 | 45.6 | 6.4 | 6.3 % | 0.6 | 0.6 % | 49.0 |
| storefront search | 40 | 64 | 131.8 | 79.8 | 69.6 | 9.7 | 7.3 % | 0.8 | 0.6 % | 52.0 |
| storefront product detail | 40 | 82 | 161.7 | 92.1 | 72.9 | 18.3 | 11.3 % | 0.9 | 0.6 % | 69.6 |
| store API product listing with aggregations | 60 | 12 | 56.2 | 30.2 | 28.7 | 1.2 | 2.1 % | 0.2 | 0.3 % | 26.0 |
| admin API product search with aggregations | 60 | 14 | 40.6 | 20.7 | 19.0 | 1.6 | 3.9 % | 0.2 | 0.5 % | 19.9 |
| admin API bulk sync write (50 products) | 10 | 394 | 603.9 | 490.7 | 422.4 | 48.5 | 8.0 % | 21.9 | 3.6 % | 113.2 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 155.5 | 70.4 | 10.6 | 1.3 | 0.140 | 0.017 |
| storefront listing with filter | 105.2 | 47.0 | 6.6 | 0.6 | 0.101 | 0.010 |
| storefront search | 140.6 | 74.4 | 10.1 | 0.8 | 0.151 | 0.012 |
| storefront product detail | 167.0 | 75.0 | 19.0 | 0.9 | 0.223 | 0.011 |
| store API product listing with aggregations | 58.0 | 29.4 | 2.3 | 0.2 | 0.100 | 0.014 |
| admin API product search with aggregations | 41.9 | 18.2 | 1.7 | 0.2 | 0.113 | 0.016 |
| admin API bulk sync write (50 products) | 617.6 | 428.8 | 48.4 | 21.9 | 0.123 | 0.056 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 150.4 | 162.9 |
| storefront listing with filter | 101.9 | 106.5 |
| storefront search | 132.1 | 130.7 |
| storefront product detail | 162.4 | 149.8 |
| store API product listing with aggregations | 56.8 | 40.7 |
| admin API product search with aggregations | 41.0 | 41.0 |
| admin API bulk sync write (50 products) | 604.6 | 555.3 |
