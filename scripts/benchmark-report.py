#!/usr/bin/env python3
"""Markdown tables from docs/benchmark-results/ (results.json from scripts/benchmark.sh run, install-times.txt from prepare).

usage: python3 scripts/benchmark-report.py [results-dir]
A difference counts as clear when the ranges of the per-run medians of both databases do not overlap (5 alternating runs).
"""
import json
import statistics
import sys
from collections import defaultdict

d = sys.argv[1] if len(sys.argv) > 1 else 'docs/benchmark-results'


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def ms(x):
    return f'{x:.1f}'


print('## Install, demo data and indexing (seconds, wall time of the console command)\n')
times = defaultdict(list)
for line in open(f'{d}/install-times.txt'):
    kind, db, _, secs = line.split()
    times[(kind, db)].append(float(secs))
print('| Step | Runs | MariaDB median | MariaDB min..max | PostgreSQL median | PostgreSQL min..max | PostgreSQL / MariaDB |')
print('|---|---|---|---|---|---|---|')
for kind, label in (('install', 'system:install --basic-setup (910 migrations)'), ('demodata', 'framework:demodata (once)'), ('index', 'dal:refresh:index')):
    a, b = times[(kind, 'mariadb')], times[(kind, 'pg')]
    print(f'| {label} | {len(a)} | {statistics.median(a):.1f} | {min(a):.1f}..{max(a):.1f} | {statistics.median(b):.1f} | {min(b):.1f}..{max(b):.1f} | {statistics.median(b) / statistics.median(a):.2f} |')

r = json.load(open(f'{d}/results.json'))
print('\n## Latency, sequential requests (milliseconds)\n')
print('Median of the per-run medians, p95 over all requests of all runs, range of the per-run medians. Ratio is PostgreSQL / MariaDB.\n')
print('| Scenario | Requests per run | MariaDB median | MariaDB p95 | MariaDB run medians | PostgreSQL median | PostgreSQL p95 | PostgreSQL run medians | Ratio | Clear |')
print('|---|---|---|---|---|---|---|---|---|---|')
for name, s in r['scenarios'].items():
    cells = {}
    for k in ('mariadb', 'pg'):
        runs = [statistics.median(x) * 1000 for x in s['latency'][k]]
        allv = [v * 1000 for x in s['latency'][k] for v in x]
        cells[k] = (statistics.median(runs), pct(allv, 0.95), min(runs), max(runs))
    m, p = cells['mariadb'], cells['pg']
    clear = 'yes' if (p[2] > m[3] or m[2] > p[3]) else 'no, overlap'
    print(f'| {name} | {s["n"]} | {ms(m[0])} | {ms(m[1])} | {ms(m[2])}..{ms(m[3])} | {ms(p[0])} | {ms(p[1])} | {ms(p[2])}..{ms(p[3])} | {p[0] / m[0]:.2f} | {clear} |')

print('\n## Throughput, 4 parallel connections (requests per second)\n')
print('| Scenario | MariaDB median | MariaDB run range | PostgreSQL median | PostgreSQL run range | Ratio | Clear |')
print('|---|---|---|---|---|---|---|')
for name, s in r['scenarios'].items():
    m, p = s['throughput']['mariadb'], s['throughput']['pg']
    if not m:
        continue
    clear = 'yes' if (min(p) > max(m) or min(m) > max(p)) else 'no, overlap'
    print(f'| {name} | {statistics.median(m):.1f} | {min(m):.1f}..{max(m):.1f} | {statistics.median(p):.1f} | {min(p):.1f}..{max(p):.1f} | {statistics.median(p) / statistics.median(m):.2f} | {clear} |')

print('\n## Errors (responses other than 200, all runs)\n')
print('| Scenario | MariaDB | PostgreSQL | Probe pass |')
print('|---|---|---|---|')
for name, s in r['scenarios'].items():
    print(f'| {name} | {s["errors"]["mariadb"]} | {s["errors"]["pg"]} | {s["probes"].get("errors", "-")} |')

print('\n## Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)\n')
print('driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).\n')
print('| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for name, s in r['scenarios'].items():
    p = s['probes']
    if 'wall_ms' not in p:
        continue
    w, drv, tr, co, tot = (p[k]['median'] for k in ('wall_ms', 'driver_ms', 'translator_ms', 'codec_ms', 'db_layers_ms'))
    print(f'| {name} | {p["requests"]} | {p["statements_median"]:.0f} | {ms(w)} | {ms(tot)} | {ms(drv)} | {ms(tr)} | {100 * tr / w:.1f} % | {ms(co)} | {100 * co / w:.1f} % | {ms(w - tot)} |')
print('\nMean instead of median:\n')
print('| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |')
print('|---|---|---|---|---|---|---|')
for name, s in r['scenarios'].items():
    p = s['probes']
    if 'wall_ms' not in p:
        continue
    st = p['statements_median'] or 1
    print(f'| {name} | {ms(p["wall_ms"]["mean"])} | {ms(p["driver_ms"]["mean"])} | {ms(p["translator_ms"]["mean"])} | {ms(p["codec_ms"]["mean"])} | {p["translator_ms"]["median"] / st:.3f} | {p["codec_ms"]["median"] / st:.3f} |')
print('\nLatency in the probe pass (client side, median, includes the probe overhead itself):\n')
print('| Scenario | Probe pass | PostgreSQL without probes |')
print('|---|---|---|')
for name, s in r['scenarios'].items():
    pp = s['probes']['latency_median_ms']
    base = statistics.median(statistics.median(x) * 1000 for x in s['latency']['pg'])
    print(f'| {name} | {ms(pp)} | {ms(base)} |')
