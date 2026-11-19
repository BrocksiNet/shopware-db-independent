#!/usr/bin/env python3
"""Sync write load for docs/19-postgresql-parallel-writes.md, runs in the web container (standard library only).

Uses the payload of the benchmark scenario "admin API bulk sync write (50 products)" from benchmark-load.py
(copied next to this file as benchmark_load.py).

usage: parallel-writes.py PORT [--seq N] [--par N] [--workers 4] [--repeats 3] [--payload stock|description|both] [--overlap]
Prints one JSON line per measurement: sequential median latency, parallel requests per second, status codes.
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark_load as b  # noqa: E402

CACHE = '/tmp/benchb/disc-%d.json'


def load(port):
    f = CACHE % port
    if os.path.exists(f):
        return json.load(open(f))
    b.CATALOG = True
    d = b.discover(port)
    json.dump({'products': d['products']}, open(f, 'w'))
    return {'products': d['products']}


def build(prods, i, payload, size):
    ids = [prods[(i * size + k) % len(prods)] for k in range(size)]
    rows = []
    for k, pid in enumerate(ids):
        row = {'id': pid}
        if payload in ('stock', 'both'):
            row['stock'] = 100 + (i + k) % 900
        if payload in ('description', 'both'):
            row['description'] = f'benchmark write {i} {k}'
        rows.append(row)
    return {'write-product': {'entity': 'product', 'action': 'upsert', 'payload': rows}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seq', type=int, default=10)
    ap.add_argument('--par', type=int, default=20)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--payload', default='both')
    ap.add_argument('--size', type=int, default=50)
    ap.add_argument('--start', type=int, default=20000)
    ap.add_argument('--nowrap', action='store_true', help='parallel ordinals 0..par-1, so no two requests share a product while par*size <= number of products')
    ap.add_argument('--dedupe', action='store_true', help='drop the products that appear in several channels, so concurrent requests rarely share a row')
    ap.add_argument('--same', action='store_true', help='all requests write the same products (worst case overlap)')
    a = ap.parse_args()
    prods = load(a.port)['products']  # the benchmark list holds two products six times each (visible in all 6 channels)
    if a.dedupe:
        prods = list(dict.fromkeys(prods))
    auth = {'Authorization': 'Bearer ' + b.token(a.port)}
    statuses = {}

    def one(c, i):
        body = build(prods, 0 if a.same else i, a.payload, a.size)
        st, t, pl = c.request('POST', '/api/_action/sync', body, auth)
        statuses[st] = statuses.get(st, 0) + 1
        if st >= 300 and 'err' not in statuses:
            statuses['err'] = pl[:400].decode('utf8', 'replace')
        return t

    c = b.Client(a.port)
    for i in range(3):
        one(c, 900 + i)
    seq_med, par = [], []
    for r in range(a.repeats):
        if a.seq:
            lat = [one(c, a.start + r * 1000 + i) for i in range(a.seq)]
            seq_med.append(statistics.median(lat) * 1000)
        if a.par:
            counter = {'n': 0}
            lock = threading.Lock()
            lats = []

            def work():
                cl = b.Client(a.port)
                while True:
                    with lock:
                        i = counter['n']
                        counter['n'] += 1
                    if i >= a.par:
                        return
                    lats.append(one(cl, i if a.nowrap else a.start + 500 + r * 1000 + i))
            ths = [threading.Thread(target=work) for _ in range(a.workers)]
            t0 = time.perf_counter()
            [t.start() for t in ths]
            [t.join() for t in ths]
            par.append(a.par / (time.perf_counter() - t0))
    print(json.dumps({'dedupe': a.dedupe, 'port': a.port, 'payload': a.payload, 'size': a.size, 'workers': a.workers,
                      'seq_median_ms': [round(x, 1) for x in seq_med], 'par_rps': [round(x, 2) for x in par],
                      'par_rps_median': round(statistics.median(par), 2) if par else None,
                      'statuses': statuses}))


if __name__ == '__main__':
    main()
