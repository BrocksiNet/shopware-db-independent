#!/usr/bin/env python3
"""Slices the statement logs of PostgreSQL (log_min_duration_statement=0) and MariaDB (slow log table, long_query_time=0)
by the request windows of capture-requests.py and prints one comparison table per scenario (markdown).

usage: capture-statements.py <dir>   with pg.log, maria-slow.tsv, pg-requests.tsv, mariadb-requests.tsv in <dir>
"""
import collections
import json
import re
import sys

d = sys.argv[1]
TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 12


def windows(path):
    out = {}
    for line in open(path):
        p = line.rstrip('\n').split('\t')
        out[p[0]] = (float(p[1]) - 0.02, float(p[2]) + 0.05, float(p[3]))
    return out


def tag(sql):
    m = re.match(r'\s*(?:/\*\s*(.*?)\s*\*/|--\s*(.*?)(?:\n|$))', sql, flags=re.S)
    return (m.group(1) or m.group(2)) if m else None


def norm(sql):
    t = tag(sql)
    if t and '::' in t:
        return t  # DAL comment, identical on both databases
    sql = re.sub(r'(?i)replace\(\s*([\w.]+)::text,\s*\'-\',\s*\'\'\s*\)', r'\1', sql)
    sql = re.sub(r'(?i)lower\(\s*hex\(\s*([\w.]+)\s*\)\s*\)', r'\1', sql)
    s = re.sub(r'/\*.*?\*/', '', sql, flags=re.S)
    s = s.replace('`', '').replace('"', '')
    s = re.sub(r"'(?:[^'\\]|\\.|'')*'", '?', s)
    s = re.sub(r'\b0x[0-9a-fA-F]+\b', '?', s)
    s = re.sub(r'\$\d+', '?', s)
    s = re.sub(r'\b\d+(\.\d+)?\b', '?', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    s = re.sub(r'\(\s*\?(\s*,\s*\?)+\s*\)', '(?)', s)
    s = re.sub(r'(::\w+( \w+)?)|(cast\(\? as \w+\))', '', s)
    return s


def label(sql):
    m = re.match(r'\s*/\*\s*(.*?)\s*\*/', sql, flags=re.S)
    c = m.group(1)[:40] + ' ' if m else ''
    s = re.sub(r'/\*.*?\*/', '', sql, flags=re.S).replace('`', '').replace('"', '')
    s = re.sub(r'\s+', ' ', s).strip()
    return (c + s)[:110]


# PostgreSQL log
import datetime
pg = []  # (epoch, pid, kind, ms, sql, params)
rec = None
head = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) UTC \[(\d+)\] (\w+):  (.*)$')
for line in open(f'{d}/pg.log', errors='replace'):
    m = head.match(line.rstrip('\n'))
    if m:
        if rec:
            pg.append(rec)
        ts = datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc).timestamp()
        rec = [ts, int(m.group(2)), m.group(3), m.group(4)]
    elif rec:
        rec[3] += '\n' + line.rstrip('\n')
if rec:
    pg.append(rec)
entries = []
last_params = {}
for ts, pid, lvl, msg in pg:
    if lvl == 'DETAIL' and msg.startswith('Parameters: ') and entries and entries[-1][1] == pid:
        entries[-1] = entries[-1][:5] + (msg[len('Parameters: '):],)
        continue
    m = re.match(r'duration: ([\d.]+) ms\s+(statement|parse|bind|execute)\s*(\S*?):\s?(.*)$', msg, flags=re.S)
    if m:
        kind = m.group(2)
        sql = m.group(4)
        dm = re.search(r'\nDETAIL:\s+parameters: (.*)$', sql, flags=re.S)
        params = None
        if dm:
            params = dm.group(1)
            sql = sql[:dm.start()]
        entries.append((ts, pid, kind, float(m.group(1)), sql, params))
# the log time stamp is written at the end of the statement
pg_by_scen = {}
pgw = windows(f'{d}/pg-requests.tsv')
for name, (a, b, ms) in pgw.items():
    calls = collections.OrderedDict()
    for ts, pid, kind, dur, sql, params in entries:
        if not (a <= ts <= b):
            continue
        key = norm(sql)
        e = calls.setdefault(key, {'label': label(sql), 'calls': 0, 'ms': 0.0, 'sql': sql, 'params': params})
        e['ms'] += dur
        if kind in ('execute', 'statement'):
            e['calls'] += 1
        if params:
            e['params'] = params
    pg_by_scen[name] = calls

# MariaDB slow log
rows = []
for line in open(f'{d}/maria-slow.tsv', errors='replace'):
    p = line.rstrip('\n').split('\t', 4)
    if len(p) < 5:
        continue
    rows.append((float(p[0]), float(p[1]) * 1000, int(p[2]), p[4].replace('\\\\n', '\n')))
maw = windows(f'{d}/mariadb-requests.tsv')
ma_by_scen = {}
for name, (a, b, ms) in maw.items():
    calls = collections.OrderedDict()
    for ts, dur, ex, sql in rows:
        if not (a <= ts <= b):  # slow log start_time is the start, not the end
            continue
        key = norm(sql)
        e = calls.setdefault(key, {'label': label(sql), 'calls': 0, 'ms': 0.0, 'rows': 0})
        e['calls'] += 1
        e['ms'] += dur
        e['rows'] += ex
    ma_by_scen[name] = calls

out = []
summary = []
for name in pgw:
    p, m = pg_by_scen[name], ma_by_scen[name]
    pn = sum(e['calls'] for e in p.values())
    mn = sum(e['calls'] for e in m.values())
    pt = sum(e['ms'] for e in p.values())
    mt = sum(e['ms'] for e in m.values())
    summary.append((name, pgw[name][2], maw[name][2], pn, mn, pt, mt, len(p), len(m)))
    out.append(f'\n### {name}\n')
    out.append('| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |')
    out.append('|---|---:|---:|---:|---:|')
    for key, e in sorted(p.items(), key=lambda kv: -kv[1]['ms'])[:TOP]:
        mm = m.get(key)
        out.append('| `%s` | %d | %.1f | %s | %s |' % (e['label'].replace('|', '/'), e['calls'], e['ms'], mm['calls'] if mm else '-', '%.1f' % mm['ms'] if mm else '-'))
    matched = sum(1 for k in p if k in m)
    out.append(f'\nUnique statements: PostgreSQL {len(p)}, MariaDB {len(m)}, same text after normalisation {matched}.')
    json.dump({'pg': p, 'maria': m}, open(f'{d}/{name.replace(" ", "-")}.json', 'w'), indent=1)

print('| Scenario | Request ms PG | Request ms MariaDB | PG statements | MariaDB statements | PG DB ms | MariaDB DB ms |')
print('|---|---:|---:|---:|---:|---:|---:|')
for s in summary:
    print('| %s | %.0f | %.0f | %d | %d | %.0f | %.0f |' % s[:7])
print('\n'.join(out))
