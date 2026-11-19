#!/usr/bin/env python3
"""Markdown tables from a results directory of scripts/benchmark.sh (results.json from run, install-times.txt from prepare).

usage: python3 scripts/benchmark-report.py [results-dir]
Stacks are columns, scenarios are rows.
A difference between two stacks counts as clear when the ranges of their 5 per-run medians do not overlap.
"""
import json
import statistics
import sys
from collections import defaultdict

d = sys.argv[1] if len(sys.argv) > 1 else 'docs/benchmark-results'
LABEL = {'mariadb': 'MariaDB', 'mysql': 'MySQL 8.4', 'pg': 'PostgreSQL', 'pgbouncer': 'PostgreSQL + PgBouncer',
         'mariadb-persistent': 'MariaDB persistent', 'mysql-persistent': 'MySQL 8.4 persistent', 'pg-persistent': 'PostgreSQL persistent'}


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def ms(x):
    if x is None:
        return 'n/a'
    return f'{x:.1f}'


print('### Install, demo data and indexing (seconds, wall time of the console command)\n')
times = defaultdict(list)
for line in open(f'{d}/install-times.txt'):
    kind, db, _, secs = line.split()
    times[(kind, db)].append(float(secs))
dbs = ('mariadb', 'mysql', 'pg')
print('| Step | Runs | ' + ' | '.join(f'{LABEL[k]} median (min..max)' for k in dbs) + ' |')
print('|---|---|' + '---|' * len(dbs))
for kind, label in (('install', 'system:install --basic-setup (910 migrations)'), ('demodata', 'framework:demodata (once)'), ('catalog', 'catalog upload, 6 templates (once)'), ('index', 'dal:refresh:index')):
    cells = []
    if not any(times[(kind, k)] for k in dbs):
        continue
    for k in dbs:
        a = times[(kind, k)]
        if not a:
            cells.append('-')
            continue
        cells.append(f'{statistics.median(a):.1f} ({min(a):.1f}..{max(a):.1f})')
    print(f'| {label} | {len(times[(kind, "mariadb")])} | ' + ' | '.join(cells) + ' |')

r = json.load(open(f'{d}/results.json'))
stacks = r['stacks']
heads = ' | '.join(LABEL[k] for k in stacks)
sep = '|---|' + '---|' * len(stacks)


def lat(s, k):
    if not any(s['latency'][k]):
        return None
    runs = [statistics.median(x) * 1000 for x in s['latency'][k] if x]
    allv = [v * 1000 for x in s['latency'][k] for v in x]
    return statistics.median(runs), pct(allv, 0.95), min(runs), max(runs)


print('\n### Latency, sequential requests, median (ms)\n')
print(f'Median of the 5 per-run medians. Requests per run in the second column.\n')
print(f'| Scenario | n | {heads} |')
print(sep.replace('|---|', '|---|---|', 1))
for name, s in r['scenarios'].items():
    print(f'| {name} | {s["n"]} | ' + ' | '.join(ms((lat(s, k) or [None])[0]) for k in stacks) + ' |')

print('\n### Latency, sequential requests, p95 over all requests of all runs (ms)\n')
print(f'| Scenario | {heads} |')
print(sep)
for name, s in r['scenarios'].items():
    print(f'| {name} | ' + ' | '.join(ms((lat(s, k) or [None] * 4)[1]) for k in stacks) + ' |')

print('\n### Latency, range of the 5 per-run medians (ms)\n')
print(f'| Scenario | {heads} |')
print(sep)
for name, s in r['scenarios'].items():
    print(f'| {name} | ' + ' | '.join((f'{ms(lat(s, k)[2])}..{ms(lat(s, k)[3])}' if lat(s, k) else 'n/a') for k in stacks) + ' |')

print('\n### Throughput, 4 parallel connections, median (requests per second)\n')
print(f'| Scenario | {heads} |')
print(sep)
for name, s in r['scenarios'].items():
    if not any(s['throughput'].get(k) for k in stacks):
        continue
    print(f'| {name} | ' + ' | '.join(f'{statistics.median(s["throughput"][k]):.1f}' for k in stacks) + ' |')

print('\n### Throughput, range of the 5 runs (requests per second)\n')
print(f'| Scenario | {heads} |')
print(sep)
for name, s in r['scenarios'].items():
    if not any(s['throughput'].get(k) for k in stacks):
        continue
    print(f'| {name} | ' + ' | '.join(f'{min(s["throughput"][k]):.1f}..{max(s["throughput"][k]):.1f}' for k in stacks) + ' |')

print('\n### Errors (responses other than 200, latency and throughput runs)\n')
print(f'| Scenario | {heads} | Probe pass |')
print(sep + '---|')
for name, s in r['scenarios'].items():
    print(f'| {name} | ' + ' | '.join(str(s['errors'][k]) for k in stacks) + f' | {s.get("probes", {}).get("errors", "-")} |')

print('\n### Ratio of the median latency to MySQL 8.4 (same setting)\n')
pairs = [('mariadb', 'mysql'), ('pg', 'mysql'), ('pgbouncer', 'mysql'), ('mariadb-persistent', 'mysql-persistent'), ('pg-persistent', 'mysql-persistent')]
pairs = [(a, b) for a, b in pairs if a in stacks and b in stacks]
print('| Scenario | ' + ' | '.join(f'{LABEL[a]} / {LABEL[b]}' for a, b in pairs) + ' | clear (ranges do not overlap) |')
print('|---|' + '---|' * (len(pairs) + 1))
for name, s in r['scenarios'].items():
    cells, clears = [], []
    for a, b in pairs:
        x, y = lat(s, a), lat(s, b)
        if not x or not y:
            cells.append('n/a')
            clears.append('n/a')
            continue
        cells.append(f'{x[0] / y[0]:.2f}')
        clears.append('yes' if (x[2] > y[3] or y[2] > x[3]) else 'no')
    print(f'| {name} | ' + ' | '.join(cells) + ' | ' + ', '.join(clears) + ' |')

if any('probes' in s for s in r['scenarios'].values()):
    print('\n### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)\n')
    print('driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).\n')
    print('| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for name, s in r['scenarios'].items():
        p = s.get('probes', {})
        if 'wall_ms' not in p:
            continue
        w, drv, tr, co, tot = (p[k]['median'] for k in ('wall_ms', 'driver_ms', 'translator_ms', 'codec_ms', 'db_layers_ms'))
        print(f'| {name} | {p["requests"]} | {p["statements_median"]:.0f} | {ms(w)} | {ms(tot)} | {ms(drv)} | {ms(tr)} | {100 * tr / w:.1f} % | {ms(co)} | {100 * co / w:.1f} % | {ms(w - tot)} |')
    print('\nMean instead of median:\n')
    print('| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |')
    print('|---|---|---|---|---|---|---|')
    for name, s in r['scenarios'].items():
        p = s.get('probes', {})
        if 'wall_ms' not in p:
            continue
        st = p['statements_median'] or 1
        print(f'| {name} | {ms(p["wall_ms"]["mean"])} | {ms(p["driver_ms"]["mean"])} | {ms(p["translator_ms"]["mean"])} | {ms(p["codec_ms"]["mean"])} | {p["translator_ms"]["median"] / st:.3f} | {p["codec_ms"]["median"] / st:.3f} |')
    print('\nLatency in the probe pass (client side, median, includes the probe overhead itself):\n')
    print('| Scenario | Probe pass | PostgreSQL without probes |')
    print('|---|---|---|')
    for name, s in r['scenarios'].items():
        if 'probes' not in s:
            continue
        pp = s['probes']['latency_median_ms']
        base = (lat(s, 'pg') or [None])[0] if 'pg' in stacks else None
        print(f'| {name} | {ms(pp)} | {ms(base)} |')
