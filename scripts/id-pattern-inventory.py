#!/usr/bin/env python3
"""Classifies binary uuid helper call sites in the Shopware checkout by pattern.
usage: scripts/id-pattern-inventory.py [path to instance (default: instance)] [--examples N]
Scope: src/**/*.php; Migration and tests listed separately. Line based, so counts are per line hit.
"""
import re, sys, os, collections

root = 'instance'
ex_n = 0
args = sys.argv[1:]
while args:
    a = args.pop(0)
    if a == '--examples':
        ex_n = int(args.pop(0))
    else:
        root = a

PATTERNS = [
    # (name, regex) first match wins per hit, a line can hit several patterns (all counted)
    ('param_in_array_value', re.compile(r"=>\s*Uuid::fromHexToBytes\(")),
    ('setParameter_bytes', re.compile(r"setParameter\([^;]*Uuid::fromHexToBytes\(")),
    ('callable_fromHexToBytes', re.compile(r"Uuid::fromHexToBytes\(\.\.\.\)|'Uuid::fromHexToBytes'|Uuid::class\s*,\s*'fromHexToBytes'")),
    ('list_fromHexToBytesList', re.compile(r"Uuid::fromHexToBytesList\(")),
    ('array_param_type_binary', re.compile(r"ArrayParameterType::BINARY|Connection::PARAM_STR_ARRAY\s*\)\s*;\s*//\s*binary")),
    ('result_fromBytesToHex', re.compile(r"Uuid::fromBytesToHex\(")),
    ('result_fromBytesToHexList', re.compile(r"Uuid::fromBytesToHexList\(")),
    ('sql_lower_hex', re.compile(r"LOWER\(\s*HEX\(", re.I)),
    ('sql_unhex', re.compile(r"UNHEX\(", re.I)),
    ('other_fromHexToBytes', re.compile(r"Uuid::fromHexToBytes\(")),
]
SPECIFIC_FIRST = ['param_in_array_value', 'setParameter_bytes', 'callable_fromHexToBytes']

def scope(path):
    if '/Migration/' in path: return 'migration'
    return 'src'

counts = collections.defaultdict(lambda: collections.Counter())
files = collections.defaultdict(lambda: collections.defaultdict(set))
allfiles = collections.defaultdict(set)
examples = collections.defaultdict(list)
for d, _, fs in os.walk(os.path.join(root, 'src')):
    for f in fs:
        if not f.endswith('.php'): continue
        p = os.path.join(d, f)
        sc = scope(p)
        for i, line in enumerate(open(p, encoding='utf8', errors='ignore'), 1):
            hit = False
            fh_done = False
            for name, rx in PATTERNS:
                if not rx.search(line): continue
                # other_fromHexToBytes only when no specific bytes pattern matched
                if name == 'other_fromHexToBytes' and fh_done: continue
                if name in SPECIFIC_FIRST: fh_done = True
                counts[sc][name] += len(rx.findall(line)) if name != 'other_fromHexToBytes' else 1
                files[sc][name].add(p)
                allfiles[sc].add(p)
                if len(examples[(sc, name)]) < ex_n:
                    examples[(sc, name)].append(f'{p}:{i}: {line.strip()[:110]}')

for sc in ('src', 'migration'):
    print(f'## {sc}: {len(allfiles[sc])} files')
    for name, _ in PATTERNS:
        if counts[sc][name]:
            print(f'{name:28} hits {counts[sc][name]:5}  files {len(files[sc][name]):4}')
    for name, _ in PATTERNS:
        for e in examples[(sc, name)]: print('  ex', name, e)
