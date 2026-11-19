### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|
| system:install --basic-setup (910 migrations) | 5 | 8.5 (8.2..9.5) | 20.5 (18.8..23.0) | 8.1 (7.7..9.6) |
| catalog upload, 6 templates (once) | 1 | 33.5 (33.5..33.5) | 32.5 (32.5..32.5) | 53.4 (53.4..53.4) |
| dal:refresh:index | 5 | 7.1 (7.0..7.9) | 9.8 (9.6..10.7) | 11.8 (11.4..12.1) |

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 97.4 | 103.3 | 253.5 | 221.1 | 96.7 | 101.2 | 215.7 |
| storefront listing with filter | 40 | 60.9 | 61.6 | 200.4 | 169.7 | 62.8 | 64.8 | 170.7 |
| storefront search | 40 | 72.7 | 80.8 | 258.5 | 235.7 | 74.9 | 77.7 | 219.0 |
| storefront product detail | 40 | 84.2 | 85.6 | 290.1 | 248.7 | 83.7 | 90.9 | 255.7 |
| store API product listing with aggregations | 60 | 33.2 | 36.3 | 54.2 | 32.0 | 26.2 | 27.3 | 28.1 |
| admin API product search with aggregations | 60 | 27.3 | 31.9 | 53.6 | 39.6 | 25.6 | 29.4 | 31.6 |
| admin API bulk sync write (50 products) | 10 | 332.0 | 387.8 | 571.8 | 580.3 | 325.1 | 394.7 | 529.4 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 138.4 | 154.0 | 327.4 | 275.8 | 138.5 | 140.0 | 299.8 |
| storefront listing with filter | 105.8 | 93.6 | 268.1 | 246.1 | 89.7 | 108.3 | 243.6 |
| storefront search | 133.1 | 131.0 | 367.7 | 308.9 | 152.3 | 127.8 | 300.0 |
| storefront product detail | 137.8 | 134.3 | 424.5 | 339.0 | 145.5 | 140.9 | 337.6 |
| store API product listing with aggregations | 67.3 | 68.3 | 100.8 | 69.1 | 52.3 | 55.9 | 62.2 |
| admin API product search with aggregations | 43.4 | 49.6 | 79.9 | 66.4 | 44.9 | 49.4 | 51.4 |
| admin API bulk sync write (50 products) | 501.9 | 637.0 | 1148.7 | 841.3 | 527.0 | 569.3 | 814.0 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 94.9..104.8 | 101.5..106.8 | 252.5..256.0 | 211.0..235.8 | 92.8..99.8 | 91.8..108.3 | 209.7..220.8 |
| storefront listing with filter | 55.1..77.0 | 55.7..65.2 | 186.6..215.8 | 161.4..172.0 | 57.6..68.6 | 59.0..70.3 | 161.5..177.8 |
| storefront search | 71.1..99.9 | 67.6..89.0 | 234.5..315.4 | 211.4..241.8 | 73.3..89.3 | 70.0..92.7 | 208.4..245.4 |
| storefront product detail | 74.9..99.9 | 79.6..95.5 | 270.7..320.8 | 239.8..266.8 | 76.0..100.4 | 76.3..93.7 | 225.3..269.0 |
| store API product listing with aggregations | 25.8..39.1 | 25.9..37.4 | 52.7..63.4 | 28.0..41.2 | 24.1..37.7 | 23.1..36.0 | 25.6..31.4 |
| admin API product search with aggregations | 24.4..33.8 | 29.7..33.3 | 46.3..55.7 | 38.8..42.0 | 23.7..29.6 | 24.5..38.1 | 29.7..37.7 |
| admin API bulk sync write (50 products) | 322.2..364.7 | 369.9..439.9 | 547.7..741.5 | 530.0..647.3 | 289.9..363.6 | 376.3..409.0 | 484.1..590.2 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 35.6 | 32.4 | 13.5 | 15.6 | 35.6 | 33.3 | 16.0 |
| storefront listing with filter | 56.5 | 53.0 | 16.6 | 18.4 | 49.2 | 49.3 | 19.2 |
| storefront search | 45.8 | 44.4 | 12.8 | 14.6 | 48.7 | 44.5 | 15.9 |
| storefront product detail | 39.8 | 35.2 | 11.7 | 14.2 | 38.6 | 40.3 | 13.7 |
| store API product listing with aggregations | 98.0 | 92.7 | 56.3 | 89.1 | 106.2 | 87.5 | 95.9 |
| admin API product search with aggregations | 131.8 | 116.6 | 68.3 | 101.9 | 131.6 | 124.2 | 120.8 |
| admin API bulk sync write (50 products) | 9.9 | 7.1 | 1.1 | 1.4 | 9.4 | 7.1 | 3.2 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 31.4..37.8 | 27.4..34.9 | 13.4..14.1 | 15.1..16.2 | 34.3..37.7 | 32.2..35.6 | 15.4..16.8 |
| storefront listing with filter | 50.5..59.8 | 39.4..61.7 | 15.6..17.3 | 17.1..20.5 | 39.5..58.8 | 42.0..58.3 | 18.7..20.2 |
| storefront search | 35.2..49.5 | 40.3..50.3 | 10.5..13.9 | 11.2..16.2 | 41.8..54.9 | 32.5..51.2 | 15.3..16.7 |
| storefront product detail | 32.6..41.8 | 25.5..37.2 | 11.2..12.2 | 13.7..14.4 | 34.7..43.0 | 36.1..41.9 | 13.0..14.5 |
| store API product listing with aggregations | 74.8..114.5 | 78.6..101.3 | 48.0..63.0 | 76.2..92.3 | 93.7..108.7 | 74.0..100.3 | 86.8..96.8 |
| admin API product search with aggregations | 101.3..136.5 | 104.1..119.7 | 62.9..74.7 | 91.6..102.9 | 120.2..142.4 | 111.2..125.6 | 105.3..122.4 |
| admin API bulk sync write (50 products) | 8.8..10.8 | 6.3..7.6 | 0.5..1.9 | 0.9..3.2 | 8.6..10.1 | 6.5..7.9 | 0.8..4.2 |

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
| storefront home | 0.94 | 2.46 | 2.14 | 0.96 | 2.13 | no, yes, yes, no, yes |
| storefront listing with filter | 0.99 | 3.25 | 2.75 | 0.97 | 2.64 | no, yes, yes, no, yes |
| storefront search | 0.90 | 3.20 | 2.92 | 0.96 | 2.82 | no, yes, yes, no, yes |
| storefront product detail | 0.98 | 3.39 | 2.91 | 0.92 | 2.81 | no, yes, yes, no, yes |
| store API product listing with aggregations | 0.92 | 1.49 | 0.88 | 0.96 | 1.03 | no, yes, no, no, no |
| admin API product search with aggregations | 0.86 | 1.68 | 1.24 | 0.87 | 1.08 | no, yes, yes, no, no |
| admin API bulk sync write (50 products) | 0.86 | 1.47 | 1.50 | 0.82 | 1.34 | yes, yes, yes, yes, yes |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 73 | 251.9 | 173.4 | 161.4 | 10.7 | 4.3 % | 1.4 | 0.6 % | 78.5 |
| storefront listing with filter | 40 | 63 | 187.4 | 137.0 | 130.0 | 6.4 | 3.4 % | 0.6 | 0.3 % | 50.4 |
| storefront search | 40 | 64 | 379.1 | 270.3 | 251.8 | 13.3 | 3.5 % | 1.8 | 0.5 % | 108.8 |
| storefront product detail | 40 | 82 | 286.0 | 212.4 | 192.3 | 18.7 | 6.5 % | 1.0 | 0.4 % | 73.5 |
| store API product listing with aggregations | 60 | 12 | 54.7 | 30.7 | 29.5 | 1.0 | 1.9 % | 0.2 | 0.3 % | 24.0 |
| admin API product search with aggregations | 60 | 14 | 53.5 | 28.9 | 26.9 | 1.8 | 3.3 % | 0.3 | 0.5 % | 24.6 |
| admin API bulk sync write (50 products) | 10 | 374 | 623.0 | 487.5 | 414.9 | 53.3 | 8.6 % | 22.3 | 3.6 % | 135.4 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 260.9 | 166.1 | 10.9 | 1.5 | 0.147 | 0.019 |
| storefront listing with filter | 197.2 | 134.7 | 6.8 | 0.7 | 0.102 | 0.010 |
| storefront search | 370.4 | 253.7 | 14.2 | 1.9 | 0.208 | 0.028 |
| storefront product detail | 305.1 | 203.5 | 19.8 | 1.1 | 0.228 | 0.013 |
| store API product listing with aggregations | 59.0 | 31.6 | 2.3 | 0.3 | 0.086 | 0.013 |
| admin API product search with aggregations | 55.1 | 26.5 | 1.9 | 0.3 | 0.125 | 0.019 |
| admin API bulk sync write (50 products) | 639.8 | 422.9 | 53.2 | 22.4 | 0.143 | 0.060 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 252.4 | 253.5 |
| storefront listing with filter | 187.9 | 200.4 |
| storefront search | 379.7 | 258.5 |
| storefront product detail | 286.3 | 290.1 |
| store API product listing with aggregations | 55.5 | 54.2 |
| admin API product search with aggregations | 54.2 | 53.6 |
| admin API bulk sync write (50 products) | 623.7 | 571.8 |
