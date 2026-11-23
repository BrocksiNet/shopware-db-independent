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
    try:
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

print('### Cold cache (clear, then one S2 call, wall time in seconds)\n')
print('Wall time includes `podman exec`, kernel boot and cache build; warm = same call right after.\n')
print('| engine | implementation | cold s | warm s | cold - warm s | rc |')
print('|---|---|---|---|---|---|')
try:
    for line in open(f'{run}/cold.txt'):
        e, im, rc, cold, warm = line.split()
        print(f'| {e} | {im} | {float(cold):.2f} | {float(warm):.2f} | {float(cold) - float(warm):.2f} | {rc} |')
except OSError:
    print('| no data | | | | | |')
print()
print('### Failed cells\n')
print('\n'.join(f'- {f}' for f in failed) if failed else 'None.')
