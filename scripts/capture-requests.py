#!/usr/bin/env python3
"""Sends one request per storefront scenario to a benchmark stack with printed epoch windows, runs in the web container.

usage: capture-requests.py <stack> [ordinal] [warm-up requests]
Prints one line per scenario: name, start epoch, end epoch, milliseconds, status.
The statement logs of the database are sliced by these windows (scripts/capture-statements.py).
The stack is warmed with the same scenario first (other ordinals), the captured request is a fresh url like in the benchmark.
"""
import importlib.util
import sys
import time

spec = importlib.util.spec_from_file_location('bl', '/tmp/bench/benchmark-load.py')
bl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bl)

stack = sys.argv[1]
ordinal = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
warm = int(sys.argv[3]) if len(sys.argv) > 3 else 8
bl.CATALOG = True
port = bl.STACKS[stack]
disc = bl.discover(port)
scen = bl.scenarios(disc, 1)
only = ['storefront home', 'storefront listing with filter', 'storefront search', 'storefront product detail']
for name in only:
    n, builder = scen[name]
    bl.measure_sequential(port, builder, 5000, warm)  # warm up
    time.sleep(1)
    method, path, body, headers = builder(ordinal)
    c = bl.Client(port)
    t0 = time.time()
    status, secs, payload = c.request(method, path, body, headers)
    t1 = time.time()
    print(f'{name}\t{t0:.3f}\t{t1:.3f}\t{secs * 1000:.1f}\t{status}\t{len(payload)}\t{path}', flush=True)
    time.sleep(1)
