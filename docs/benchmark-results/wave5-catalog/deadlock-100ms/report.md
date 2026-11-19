### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median (min..max) | MySQL 8.4 median (min..max) | PostgreSQL median (min..max) |
|---|---|---|---|---|

### Latency, sequential requests, median (ms)

Median of the 5 per-run medians. Requests per run in the second column.

| Scenario | n | PostgreSQL | MariaDB |
|---|---|---|---|
| admin API bulk sync write (50 products) | 10 | 434.5 | 249.4 |

### Latency, sequential requests, p95 over all requests of all runs (ms)

| Scenario | PostgreSQL | MariaDB |
|---|---|---|
| admin API bulk sync write (50 products) | 505.4 | 299.4 |

### Latency, range of the 5 per-run medians (ms)

| Scenario | PostgreSQL | MariaDB |
|---|---|---|
| admin API bulk sync write (50 products) | 425.6..441.3 | 236.2..254.7 |

### Throughput, 4 parallel connections, median (requests per second)

| Scenario | PostgreSQL | MariaDB |
|---|---|---|
| admin API bulk sync write (50 products) | 5.9 | 12.2 |

### Throughput, range of the 5 runs (requests per second)

| Scenario | PostgreSQL | MariaDB |
|---|---|---|
| admin API bulk sync write (50 products) | 5.7..6.1 | 11.7..12.8 |

### Errors (responses other than 200, latency and throughput runs)

| Scenario | PostgreSQL | MariaDB | Probe pass |
|---|---|---|---|
| admin API bulk sync write (50 products) | 0 | 0 | 0 |

### Ratio of the median latency to MySQL 8.4 (same setting)

| Scenario |  | clear (ranges do not overlap) |
|---|---|
| admin API bulk sync write (50 products) |  |  |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| admin API bulk sync write (50 products) | 10 | 374 | 495.3 | 379.4 | 312.2 | 47.6 | 9.6 % | 21.5 | 4.3 % | 115.9 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| admin API bulk sync write (50 products) | 500.7 | 311.4 | 47.2 | 21.5 | 0.127 | 0.058 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| admin API bulk sync write (50 products) | 495.8 | 434.5 |
