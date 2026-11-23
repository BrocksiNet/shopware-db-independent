#!/usr/bin/env python3
"""Markdown tables for the final timing block (docs/34).
usage: orm-spike-final-tables.py [results-dir=/tmp/e1-results/orm-spike-e1] [run-dir=/tmp/e1-run]
"""
import glob, json, os, re, sys

res = sys.argv[1] if len(sys.argv) > 1 else '/tmp/e1-results/orm-spike-e1'
run = sys.argv[2] if len(sys.argv) > 2 else '/tmp/e1-run'
ENGINES = ['mysql', 'mariadb', 'postgresql', 'sqlite']
CONFIGS = [
    ('dal', 'dal'), ('dbal', 'dbal'),
    ('doctrine', 'doctrine idiomatic'), ('doctrine', 'doctrine optimized'),
    ('cycle', 'cycle idiomatic'), ('cycle', 'cycle optimized'),
    ('dalv2', 'dalv2 default'),
    ('dalv2', 'dalv2 count=window agg=stats write=key+upd'),
    ('dalv2', 'dalv2 all levers (+proj=1)'),
]
SC = ['S1', 'S2', 'S3', 'S4', 'S5']


def load(path):
    # the harness names the file after the SqlDialect, which reports `mysql` for MariaDB too
    try:
        if not os.path.exists(path):
            path = glob.glob(os.path.dirname(path) + '/*.json')[0]
        return json.load(open(path))
    except Exception:
        return None


def cell(d, s):
    return (d or {}).get('scenarios', {}).get(s)


failed = []
for eng in ENGINES:
    print(f'### {eng}\n')
    print('Medians in ms, statements per iteration, peak memory in MB; ratio = median / dal median.\n')
    print('| implementation | ' + ' | '.join(f'{s} ms | {s} stmts | {s} MB | {s} x dal' for s in SC) + ' |')
    print('|---|' + '---|' * (4 * len(SC)))
    dal = load(f'{res}/bench/{eng}/c1/{eng}-dal.json')
    for i, (impl, label) in enumerate(CONFIGS, 1):
        d = load(f'{res}/bench/{eng}/c{i}/{eng}-{impl}.json')
        row = [label]
        for s in SC:
            c, b = cell(d, s), cell(dal, s)
            if not c or c.get('status') != 'ok':
                err = (c or {}).get('error') or (c or {}).get('status') or 'missing'
                failed.append(f'{eng} {label} {s}: {str(err)[:160]}')
                row += ['FAIL', '-', '-', '-']
                continue
            ratio = f"{c['medianMs'] / b['medianMs']:.2f}" if b and b.get('status') == 'ok' else '-'
            stm = c['statementsMedian'] if c.get('statementsCounted') else 'n/a'
            row += [f"{c['medianMs']:.2f}", str(stm), f"{c['peakMemoryMb']:.0f}", ratio]
        print('| ' + ' | '.join(row) + ' |')
    print()

print('### Verify (against dal, 1 iteration)\n')
print('| engine | implementation | S1 | S2 | S3 | S4 | S5 |')
print('|---|---|---|---|---|---|---|')
for eng in ENGINES:
    for i, (impl, label) in enumerate(CONFIGS, 1):
        if impl == 'dal':
            continue
        try:
            txt = open(f'{run}/calls/{eng}-c{i}-verify.log').read()
        except OSError:
            txt = ''
        r = {}
        for m in re.finditer(r'^(S\d): (\w+)(.*)$', txt, re.M):
            r[m.group(1)] = m.group(2) if m.group(2) == 'OK' else (m.group(2) + m.group(3)).strip()[:80]
        for s in SC:
            if r.get(s) != 'OK':
                failed.append(f'verify {eng} {label} {s}: {r.get(s, "no output")}')
        print(f'| {eng} | {label} | ' + ' | '.join(r.get(s, 'none') for s in SC) + ' |')
print()

print('### Cold cache (cache:clear --no-warmup, then one S2 call, wall time in seconds, median of 5)\n')
print('Wall time includes `podman exec`, kernel boot and cache build; warm = same call right after.\n')
print('| engine | implementation | cold s | warm s | cold - warm s | cold min-max s | rc |')
print('|---|---|---|---|---|---|---|')
import statistics
rows = {}
try:
    for line in open(f'{run}/cold.txt'):
        e, im, rc, cold, warm = line.split()
        rows.setdefault((e, im), []).append((int(rc), float(cold), float(warm)))
    for (e, im), v in rows.items():
        c = statistics.median(x[1] for x in v)
        w = statistics.median(x[2] for x in v)
        cs = [x[1] for x in v]
        print(f'| {e} | {im} | {c:.2f} | {w:.2f} | {c - w:.2f} | {min(cs):.2f}-{max(cs):.2f} | {max(x[0] for x in v)} |')
except OSError:
    print('| no data | | | | | | |')
print()
print('### Failed cells\n')
print('\n'.join(f'- {f}' for f in failed) if failed else 'None.')
