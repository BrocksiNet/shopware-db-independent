#!/usr/bin/env python3
"""Load generator for scripts/benchmark.sh, runs inside the web container (standard library only).

Stacks (same code snapshot, same Host header, own php-fpm pool and caddy, see STACKS):
  one stack per database and setting, for example mariadb, mysql, pg, pgbouncer (pg through PgBouncer), *-persistent (DATABASE_PERSISTENT_CONNECTION=1)
  pg-timing is pg with the timing probes, only used for the translator pass

Per scenario:
  latency   RUNS runs of N sequential requests per stack, the order of the stacks rotates per run
  throughput RUNS runs of 2N requests with 4 parallel connections per stack
  probes    translator pass on pgtime: per request time in the driver, in the translator layer and in the id codec layer

Every request URL differs from every other one of the same scenario (page, filter, category, product, search term),
so the object cache does not answer the repeated requests. The ordinals are the same for both databases,
but the generated ids and names differ (demodata is random).
"""
import argparse
import http.client
import json
import os
import statistics
import threading
import time

HOST = '127.0.0.1:8101'
STACKS = {'mariadb': 8101, 'mysql': 8104, 'pg': 8102, 'pgbouncer': 8105,
          'mariadb-persistent': 8106, 'mysql-persistent': 8107, 'pg-persistent': 8108, 'pg-timing': 8103}
# the data of a stack: the stacks of one database share its demo data
DATABASE = {'mariadb': 'mariadb', 'mariadb-persistent': 'mariadb', 'mysql': 'mysql', 'mysql-persistent': 'mysql',
            'pg': 'pg', 'pgbouncer': 'pg', 'pg-persistent': 'pg', 'pg-timing': 'pg'}
DEFAULT_STACKS = 'mariadb,mysql,pg,pgbouncer,mariadb-persistent,mysql-persistent,pg-persistent'
TIMING_FILE = '/tmp/bench/timing.jsonl'


class Client:
    def __init__(self, port):
        self.port = port
        self.conn = None

    def request(self, method, path, body=None, headers=None):
        h = {'Host': HOST, 'Accept': 'application/json, text/html'}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body)
            h['Content-Type'] = 'application/json'
        start = time.perf_counter()
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=300)
                self.conn.request(method, path, body=data, headers=h)
                resp = self.conn.getresponse()
                payload = resp.read()
                break
            except (http.client.HTTPException, OSError):
                self.conn = None
                if attempt:
                    raise
        return resp.status, time.perf_counter() - start, payload


def token(port):
    status, _, payload = Client(port).request('POST', '/api/oauth/token', {
        'grant_type': 'password', 'client_id': 'administration', 'scopes': 'write', 'username': 'admin', 'password': 'shopware'})
    assert status == 200, payload[:300]
    return json.loads(payload)['access_token']


def discover(port):
    """Ids and names of one database, found through the admin API."""
    c = Client(port)
    auth = {'Authorization': 'Bearer ' + token(port)}

    def search(entity, criteria):
        status, _, payload = c.request('POST', '/api/search/' + entity, criteria, auth)
        assert status == 200, (entity, payload[:300])
        return json.loads(payload)['data']

    sc = search('sales-channel', {'filter': [{'type': 'equals', 'field': 'type.name', 'value': 'Storefront'}], 'limit': 1})[0]
    products = search('product', {'filter': [{'type': 'equals', 'field': 'parentId', 'value': None}, {'type': 'equals', 'field': 'active', 'value': True}],
                                  'sort': [{'field': 'productNumber'}], 'limit': 500, 'includes': {'product': ['id', 'name']}})
    categories = search('category', {'filter': [{'type': 'equals', 'field': 'type', 'value': 'page'},
                                                {'type': 'not', 'operator': 'and', 'queries': [{'type': 'equals', 'field': 'products.id', 'value': None}]}],
                                     'sort': [{'field': 'id'}], 'limit': 100, 'includes': {'category': ['id']}})

    def seo(route, ids):
        rows = search('seo-url', {'filter': [{'type': 'equals', 'field': 'routeName', 'value': route}, {'type': 'equals', 'field': 'isCanonical', 'value': True},
                                             {'type': 'equals', 'field': 'salesChannelId', 'value': sc['id']}, {'type': 'equalsAny', 'field': 'foreignKey', 'value': '|'.join(ids)}],
                                  'limit': 500, 'includes': {'seo_url': ['foreignKey', 'seoPathInfo']}})
        return {r['foreignKey']: '/' + r['seoPathInfo'] for r in rows}

    # the storefront answers /navigation/<id> and /detail/<id> with a redirect to the SEO url, the benchmark requests the SEO url
    product_urls = seo('frontend.detail.page', [p['id'] for p in products])
    category_urls = seo('frontend.navigation.page', [x['id'] for x in categories])
    manufacturers = search('product-manufacturer', {'limit': 100, 'includes': {'product_manufacturer': ['id']}})
    words = sorted({w.lower() for p in products for w in (p['name'] or '').split() if len(w) > 4 and w.isalpha() and w.isascii()})
    return {
        'accessKey': sc['accessKey'],
        'auth': auth,
        'products': [p['id'] for p in products],
        'categories': [x['id'] for x in categories if x['id'] in category_urls],
        'product_urls': product_urls,
        'category_urls': category_urls,
        'manufacturers': [m['id'] for m in manufacturers],
        'words': words,
    }


def scenarios(d, runs):
    """name -> (n, builder(i) -> (method, path, body, headers)). i is the ordinal of the request inside the scenario, unique per request."""
    store = {'sw-access-key': d['accessKey']}
    auth = d['auth']
    cats, manus, prods, words = d['categories'], d['manufacturers'], d['products'], d['words']
    if not cats:
        raise SystemExit('no category with products found')

    def listing(i):
        cat = cats[i % len(cats)]
        manu = manus[(i * 7 + 3) % len(manus)]
        order = ('price-asc', 'price-desc', 'name-asc', 'name-desc')[i % 4]
        q = f'?order={order}&manufacturer={manu}&min-price=1'  # always page 1, a page beyond the last one is a cheap redirect
        return 'GET', d['category_urls'][cat] + q, None, {}

    def search(i):
        return 'GET', '/search?search=' + words[(i * 7) % len(words)] + '', None, {}

    urls = [d['product_urls'][p] for p in prods if p in d['product_urls']]

    def detail(i):
        return 'GET', urls[i % len(urls)], None, {}

    def store_listing(i):
        body = {'limit': 24, 'p': 1 + i % 20, 'total-count-mode': 1, 'order': ('name-asc', 'price-asc')[i % 2],
                'filter': [{'type': 'equals', 'field': 'manufacturerId', 'value': manus[i % len(manus)]}] if i % 3 else [],
                'aggregations': [
                    {'name': 'manufacturer', 'type': 'entity', 'field': 'manufacturerId', 'definition': 'product_manufacturer'},
                    {'name': 'price-max', 'type': 'max', 'field': 'cheapestPrice'},
                    {'name': 'properties', 'type': 'terms', 'field': 'properties.id'},
                    {'name': 'rating', 'type': 'max', 'field': 'ratingAverage'},
                ],
                'associations': {'cover': {'associations': {'media': {}}}}}
        return 'POST', '/store-api/product', body, store

    def admin_search(i):
        body = {'limit': 25, 'page': 1 + i % 40, 'total-count-mode': 1, 'sort': [{'field': ('name', 'productNumber', 'stock')[i % 3], 'order': 'ASC'}],
                'filter': [{'type': 'range', 'field': 'stock', 'parameters': {'gte': i % 5}}],
                'associations': {'manufacturer': {}, 'cover': {'associations': {'media': {}}}, 'prices': {}},
                'aggregations': [
                    {'name': 'by-manufacturer', 'type': 'terms', 'field': 'manufacturerId'},
                    {'name': 'avg-stock', 'type': 'avg', 'field': 'stock'},
                    {'name': 'stats-stock', 'type': 'stats', 'field': 'stock'},
                    {'name': 'by-tax', 'type': 'terms', 'field': 'taxId'},
                ]}
        return 'POST', '/api/search/product', body, auth

    def sync(i):
        ids = [prods[(i * 50 + k) % len(prods)] for k in range(50)]
        payload = [{'id': pid, 'stock': 100 + (i + k) % 900, 'description': f'benchmark write {i} {k}'} for k, pid in enumerate(ids)]
        body = {'write-product': {'entity': 'product', 'action': 'upsert', 'payload': payload}}
        return 'POST', '/api/_action/sync', body, auth

    return {
        'storefront home': (30, lambda i: ('GET', '/', None, {})),
        'storefront listing with filter': (40, listing),
        'storefront search': (40, search),
        'storefront product detail': (40, detail),
        'store API product listing with aggregations': (60, store_listing),
        'admin API product search with aggregations': (60, admin_search),
        'admin API bulk sync write (50 products)': (10, sync),
    }


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def measure_sequential(port, builder, start, n):
    c = Client(port)
    lat, errors = [], 0
    for i in range(start, start + n):
        method, path, body, headers = builder(i)
        status, secs, _ = c.request(method, path, body, headers)
        if status != 200:
            errors += 1
        else:
            lat.append(secs)
    return lat, errors


def measure_parallel(port, builder, start, n, workers=4):
    counter = {'next': start}
    lock = threading.Lock()
    errors = [0]

    def work():
        c = Client(port)
        while True:
            with lock:
                i = counter['next']
                if i >= start + n:
                    return
                counter['next'] += 1
            method, path, body, headers = builder(i)
            status, _, _ = c.request(method, path, body, headers)
            if status != 200:
                errors[0] += 1

    threads = [threading.Thread(target=work) for _ in range(workers)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return n / (time.perf_counter() - t0), errors[0]


def probe_pass(d_pg, name, n, builder_factory):
    """Translator pass: requests on the pg-timing stack, sums per probe from the timing file."""
    builder = builder_factory
    c = Client(STACKS['pg-timing'])
    for i in range(5):
        c.request(*builder(1000 + i))
    time.sleep(0.5)
    open(TIMING_FILE, 'w').close()
    lat, errors = [], 0
    for i in range(n):
        status, secs, _ = c.request(*builder(2000 + i))
        lat.append(secs)
        errors += status != 200
    time.sleep(0.5)
    rows = [json.loads(line) for line in open(TIMING_FILE) if line.strip()]
    rows = [r for r in rows if not r['uri'].startswith('/api/oauth')]
    out = {'errors': errors, 'requests': len(rows), 'latency_median_ms': statistics.median(lat) * 1000}
    if not rows:
        return out
    for key, fn in (
        ('wall_ms', lambda r: r['wall_ns']),
        ('driver_ms', lambda r: r['probes']['driver']['ns']),
        ('translator_ms', lambda r: r['probes']['translated']['ns'] - r['probes']['driver']['ns']),
        ('codec_ms', lambda r: r['probes']['codec']['ns'] - r['probes']['translated']['ns']),
        ('db_layers_ms', lambda r: r['probes']['codec']['ns']),
    ):
        vals = [fn(r) / 1e6 for r in rows]
        out[key] = {'median': statistics.median(vals), 'mean': statistics.mean(vals), 'p95': pct(vals, 0.95)}
    out['statements_median'] = statistics.median(r['probes']['codec']['stmts'] for r in rows)
    out['driver_calls_median'] = statistics.median(r['probes']['codec']['calls'] for r in rows)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--out', default='/tmp/bench/results.json')
    ap.add_argument('--only', default='', help='substring of a scenario name')
    ap.add_argument('--stacks', default=DEFAULT_STACKS, help='comma separated stack names')
    ap.add_argument('--no-throughput', action='store_true')
    ap.add_argument('--no-probes', action='store_true')
    ap.add_argument('--merge', action='store_true', help='keep the scenarios already in --out, run only the missing ones')
    a = ap.parse_args()
    names = a.stacks.split(',')

    dbs = sorted({DATABASE[k] for k in names} | {'pg'})
    first_stack = {db: next(k for k in (*names, 'pg') if DATABASE[k] == db) for db in dbs}
    disc = {db: discover(STACKS[first_stack[db]]) for db in dbs}
    scen = {db: scenarios(disc[db], a.runs) for db in dbs}
    result = {'runs': a.runs, 'host': HOST, 'stacks': names, 'scenarios': {}, 'counts': {}}
    result['counts'] = {db: {x: len(disc[db][x]) for x in ('products', 'categories', 'manufacturers', 'words')} for db in dbs}

    if a.merge and os.path.exists(a.out):
        result['scenarios'] = json.load(open(a.out))['scenarios']

    for name in scen[dbs[0]]:
        if (a.only and a.only not in name) or name in result['scenarios']:
            continue
        # the admin token lives 10 minutes
        for db in dbs:
            disc[db]['auth']['Authorization'] = 'Bearer ' + token(STACKS[first_stack[db]])
        n = scen[dbs[0]][name][0]
        res = {'n': n, 'latency': {k: [] for k in names}, 'errors': {k: 0 for k in names}, 'throughput': {k: [] for k in names}}
        print('==', name, flush=True)
        for k in names:  # warm up: opcache, container, connection, first object cache entries
            measure_sequential(STACKS[k], scen[DATABASE[k]][name][1], 5000, 8)
        for run in range(a.runs):
            r = run % len(names)
            order = names[r:] + names[:r]
            for k in order:
                lat, err = measure_sequential(STACKS[k], scen[DATABASE[k]][name][1], run * n, n)
                res['latency'][k].append(lat)
                res['errors'][k] += err
            print('  latency run', run + 1, {k: round(statistics.median(res['latency'][k][-1]) * 1000, 1) for k in order}, flush=True)
        if not a.no_throughput:
            for run in range(a.runs):
                r = run % len(names)
                order = names[r:] + names[:r]
                for k in order:
                    rps, err = measure_parallel(STACKS[k], scen[DATABASE[k]][name][1], 10000 + run * 2 * n, 2 * n)
                    res['throughput'][k].append(rps)
                    res['errors'][k] += err
                print('  throughput run', run + 1, {k: round(res['throughput'][k][-1], 2) for k in order}, flush=True)
        if not a.no_probes:
            res['probes'] = probe_pass(disc['pg'], name, n, scen['pg'][name][1])
            print('  probes', json.dumps(res['probes'])[:300], flush=True)
        result['scenarios'][name] = res
        json.dump(result, open(a.out, 'w'))


if __name__ == '__main__':
    main()
