### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|
| system:install --basic-setup (910 migrations) | 5 | 8.0 (7.6..8.8) | 18.3 (17.9..20.5) | 6.5 (6.3..7.5) |
| framework:demodata (once) | 1 | 24.0 (24.0..24.0) | 27.3 (27.3..27.3) | 32.6 (32.6..32.6) |
| dal:refresh:index | 5 | 9.5 (8.1..10.0) | 12.5 (11.8..13.2) | 15.6 (13.6..31.2) |

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 207.2 | 248.0 | 294.4 | 261.0 | 210.0 | 245.8 | 254.3 |
| storefront listing with filter | 40 | 128.4 | 147.7 | 199.9 | 182.6 | 126.1 | 152.0 | 160.3 |
| storefront search | 40 | 133.5 | 160.9 | 257.4 | 220.6 | 137.2 | 150.9 | 215.8 |
| storefront product detail | 40 | 138.2 | 155.5 | 215.2 | 206.5 | 137.3 | 163.7 | 176.2 |
| store API product listing with aggregations | 60 | 47.6 | 44.6 | 81.5 | 60.7 | 47.9 | 48.2 | 56.4 |
| admin API product search with aggregations | 60 | 28.6 | 32.9 | 51.1 | 36.2 | 29.1 | 30.5 | 33.0 |
| admin API bulk sync write (50 products) | 10 | 204.3 | 258.1 | 378.1 | 369.6 | 194.7 | 269.4 | 355.5 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 283.6 | 336.3 | 371.2 | 336.5 | 292.6 | 318.9 | 337.2 |
| storefront listing with filter | 185.3 | 267.8 | 328.6 | 284.5 | 196.0 | 248.6 | 219.2 |
| storefront search | 219.9 | 332.8 | 396.2 | 372.4 | 232.2 | 251.9 | 332.1 |
| storefront product detail | 261.5 | 263.8 | 337.6 | 385.1 | 246.4 | 386.7 | 273.7 |
| store API product listing with aggregations | 82.5 | 93.3 | 123.7 | 107.5 | 82.7 | 91.8 | 109.0 |
| admin API product search with aggregations | 35.4 | 45.0 | 67.8 | 48.9 | 46.8 | 40.0 | 46.5 |
| admin API bulk sync write (50 products) | 343.7 | 484.5 | 602.7 | 521.5 | 287.0 | 421.5 | 530.0 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 202.7..222.5 | 245.8..268.5 | 277.1..301.5 | 254.2..271.4 | 200.3..216.7 | 239.1..263.8 | 252.4..270.6 |
| storefront listing with filter | 114.2..139.1 | 129.3..178.5 | 162.4..228.1 | 157.0..194.6 | 113.1..157.1 | 136.5..169.4 | 152.7..172.3 |
| storefront search | 113.9..156.5 | 139.4..194.5 | 251.7..284.4 | 208.1..263.2 | 122.2..151.2 | 134.4..173.9 | 201.3..252.2 |
| storefront product detail | 119.3..152.4 | 133.4..168.4 | 201.4..226.1 | 180.5..212.1 | 115.1..146.6 | 135.0..190.4 | 167.8..187.7 |
| store API product listing with aggregations | 45.6..53.1 | 42.6..56.8 | 79.2..93.3 | 57.7..67.1 | 44.7..50.3 | 40.6..53.6 | 52.9..76.1 |
| admin API product search with aggregations | 28.2..30.1 | 30.9..37.6 | 49.1..57.9 | 34.6..41.2 | 27.7..31.2 | 30.2..30.7 | 32.1..35.0 |
| admin API bulk sync write (50 products) | 175.8..266.1 | 252.7..319.4 | 316.6..401.0 | 322.2..444.1 | 189.3..204.5 | 229.5..278.9 | 320.2..421.2 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 14.1 | 11.3 | 11.5 | 12.8 | 14.2 | 11.5 | 12.5 |
| storefront listing with filter | 26.4 | 20.8 | 15.6 | 18.6 | 25.3 | 23.1 | 20.7 |
| storefront search | 23.0 | 19.5 | 11.4 | 15.1 | 23.3 | 21.0 | 14.3 |
| storefront product detail | 23.4 | 20.3 | 15.9 | 16.6 | 25.1 | 18.7 | 21.6 |
| store API product listing with aggregations | 70.0 | 57.4 | 38.8 | 49.1 | 71.5 | 59.9 | 49.5 |
| admin API product search with aggregations | 103.3 | 87.8 | 57.3 | 90.0 | 104.2 | 98.0 | 94.7 |
| admin API bulk sync write (50 products) | 17.7 | 11.4 | 6.9 | 8.1 | 18.2 | 11.4 | 7.9 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 13.4..14.2 | 10.0..12.0 | 11.3..12.1 | 12.3..13.2 | 13.1..14.7 | 10.0..11.9 | 11.6..13.5 |
| storefront listing with filter | 23.8..26.8 | 19.8..24.2 | 12.3..17.1 | 18.2..19.9 | 22.8..28.5 | 17.2..24.1 | 16.4..22.3 |
| storefront search | 21.5..26.8 | 16.1..20.4 | 10.8..12.8 | 11.0..15.5 | 20.5..25.7 | 15.4..22.5 | 11.2..15.3 |
| storefront product detail | 22.9..28.4 | 15.8..24.4 | 14.1..17.4 | 14.1..17.0 | 16.2..26.7 | 16.2..21.9 | 17.1..24.4 |
| store API product listing with aggregations | 67.1..73.6 | 57.1..61.7 | 38.0..40.4 | 45.0..50.8 | 46.0..73.5 | 55.2..61.5 | 40.5..52.7 |
| admin API product search with aggregations | 89.2..115.5 | 62.0..90.5 | 50.5..61.9 | 72.5..95.1 | 87.6..117.5 | 86.5..100.3 | 89.9..107.6 |
| admin API bulk sync write (50 products) | 15.5..18.0 | 10.1..11.8 | 6.6..8.2 | 7.2..8.8 | 16.8..18.5 | 10.7..12.2 | 7.0..8.3 |

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
| storefront home | 0.84 | 1.19 | 1.05 | 0.85 | 1.03 | yes, yes, no, yes, no |
| storefront listing with filter | 0.87 | 1.35 | 1.24 | 0.83 | 1.05 | no, no, no, no, no |
| storefront search | 0.83 | 1.60 | 1.37 | 0.91 | 1.43 | no, yes, yes, no, yes |
| storefront product detail | 0.89 | 1.38 | 1.33 | 0.84 | 1.08 | no, yes, yes, no, no |
| store API product listing with aggregations | 1.07 | 1.82 | 1.36 | 0.99 | 1.17 | no, yes, yes, no, no |
| admin API product search with aggregations | 0.87 | 1.56 | 1.10 | 0.95 | 1.08 | yes, yes, no, no, yes |
| admin API bulk sync write (50 products) | 0.79 | 1.47 | 1.43 | 0.72 | 1.32 | no, no, yes, yes, yes |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 62 | 304.6 | 178.3 | 163.0 | 11.9 | 3.9 % | 3.6 | 1.2 % | 126.3 |
| storefront listing with filter | 40 | 59 | 250.9 | 102.3 | 86.7 | 11.0 | 4.4 % | 3.1 | 1.2 % | 148.6 |
| storefront search | 40 | 56 | 285.8 | 159.3 | 144.9 | 12.4 | 4.3 % | 2.9 | 1.0 % | 126.5 |
| storefront product detail | 40 | 63 | 230.7 | 102.0 | 83.0 | 17.0 | 7.4 % | 2.6 | 1.1 % | 128.7 |
| store API product listing with aggregations | 60 | 19 | 85.9 | 49.8 | 45.2 | 4.0 | 4.7 % | 0.5 | 0.5 % | 36.1 |
| admin API product search with aggregations | 60 | 15 | 60.4 | 30.3 | 28.2 | 1.9 | 3.1 % | 0.3 | 0.6 % | 30.0 |
| admin API bulk sync write (50 products) | 10 | 239 | 398.2 | 297.0 | 249.1 | 36.0 | 9.0 % | 12.5 | 3.1 % | 101.3 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 324.1 | 174.3 | 12.3 | 3.7 | 0.192 | 0.059 |
| storefront listing with filter | 274.1 | 91.0 | 11.7 | 3.3 | 0.187 | 0.053 |
| storefront search | 315.4 | 151.2 | 12.6 | 3.0 | 0.222 | 0.052 |
| storefront product detail | 246.6 | 87.3 | 17.3 | 2.6 | 0.269 | 0.041 |
| store API product listing with aggregations | 96.6 | 56.1 | 4.2 | 0.5 | 0.212 | 0.025 |
| admin API product search with aggregations | 65.4 | 30.1 | 2.1 | 0.4 | 0.126 | 0.022 |
| admin API bulk sync write (50 products) | 408.6 | 262.3 | 37.3 | 13.1 | 0.151 | 0.052 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 304.7 | 294.4 |
| storefront listing with filter | 251.2 | 199.9 |
| storefront search | 286.1 | 257.4 |
| storefront product detail | 231.2 | 215.2 |
| store API product listing with aggregations | 86.8 | 81.5 |
| admin API product search with aggregations | 61.0 | 51.1 |
| admin API bulk sync write (50 products) | 399.2 | 378.1 |
