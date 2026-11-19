### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|---|
| storefront home | 30 | 83.2 | 85.2 | 149.1 |
| storefront listing with filter | 40 | 51.2 | 50.4 | 97.7 |
| storefront search | 40 | 60.6 | 62.2 | 119.3 |
| storefront product detail | 40 | 71.0 | 70.9 | 142.9 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| storefront home | 114.6 | 105.4 | 195.3 |
| storefront listing with filter | 63.6 | 66.3 | 133.9 |
| storefront search | 85.8 | 81.3 | 149.8 |
| storefront product detail | 97.8 | 101.1 | 183.3 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| storefront home | 82.5..85.3 | 84.7..85.4 | 148.0..153.8 |
| storefront listing with filter | 50.6..52.3 | 50.3..51.3 | 95.8..100.9 |
| storefront search | 58.9..63.7 | 59.8..62.9 | 116.1..122.2 |
| storefront product detail | 70.4..72.9 | 70.4..74.2 | 141.2..152.0 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| storefront home | 39.9 | 37.9 | 22.3 |
| storefront listing with filter | 63.0 | 62.8 | 33.4 |
| storefront search | 53.2 | 51.8 | 26.9 |
| storefront product detail | 47.4 | 47.8 | 22.3 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| storefront home | 39.2..40.6 | 34.6..39.0 | 20.3..23.0 |
| storefront listing with filter | 62.5..64.5 | 60.0..65.1 | 31.6..34.5 |
| storefront search | 51.6..54.6 | 50.1..52.5 | 25.3..28.2 |
| storefront product detail | 46.4..48.0 | 42.4..49.0 | 21.7..22.9 |

### Errors (responses other than 200, latency and throughput runs)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | Probe pass |
|---|---|---|---|---|
| storefront home | 0 | 0 | 0 | 0 |
| storefront listing with filter | 0 | 0 | 0 | 0 |
| storefront search | 0 | 0 | 0 | 0 |
| storefront product detail | 0 | 0 | 0 | 0 |

### Ratio of the median latency to MySQL 8.4 (same setting)

| Scenario | MariaDB / MySQL 8.4 | PostgreSQL / MySQL 8.4 | clear (ranges do not overlap) |
|---|---|---|---|
| storefront home | 0.98 | 1.75 | no, yes |
| storefront listing with filter | 1.01 | 1.94 | no, yes |
| storefront search | 0.97 | 1.92 | no, yes |
| storefront product detail | 1.00 | 2.02 | no, yes |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 73 | 149.6 | 82.5 | 71.2 | 9.9 | 6.6 % | 1.2 | 0.8 % | 67.1 |
| storefront listing with filter | 40 | 63 | 98.5 | 52.4 | 45.5 | 6.2 | 6.2 % | 0.6 | 0.6 % | 46.0 |
| storefront search | 40 | 64 | 120.6 | 70.4 | 60.2 | 9.1 | 7.6 % | 0.8 | 0.6 % | 50.2 |
| storefront product detail | 40 | 82 | 147.2 | 84.0 | 66.3 | 17.2 | 11.7 % | 0.8 | 0.6 % | 63.2 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 155.2 | 73.1 | 10.2 | 1.2 | 0.136 | 0.016 |
| storefront listing with filter | 104.1 | 47.9 | 6.5 | 0.6 | 0.098 | 0.009 |
| storefront search | 125.6 | 63.1 | 9.6 | 0.8 | 0.143 | 0.012 |
| storefront product detail | 152.1 | 68.9 | 17.7 | 0.9 | 0.210 | 0.010 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 150.0 | 149.1 |
| storefront listing with filter | 98.8 | 97.7 |
| storefront search | 120.9 | 119.3 |
| storefront product detail | 147.5 | 142.9 |
