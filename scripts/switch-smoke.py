#!/usr/bin/env python3
"""Smoke test against a Shopware web process, runs inside instance-web-1.
usage: python3 - BASE_URL ACCESS_KEY < switch-smoke.py
Prints one line per check: STEP|name|PASS/FAIL|milliseconds|detail
Exit code 1 when a check failed."""
import json, sys, time, uuid, urllib.request, urllib.error

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
CURRENCY = 'b7d2554b0ce847cd82f3ac9bd1c0dfca'
failed = 0
ctx = {}


def call(method, path, body=None, headers=None, raw=False):
    h = {'Accept': 'application/json'}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        code, text, hd = r.status, r.read().decode('utf-8', 'replace'), r.headers
    except urllib.error.HTTPError as e:
        code, text, hd = e.code, e.read().decode('utf-8', 'replace'), e.headers
    if raw:
        return code, text, hd
    try:
        return code, json.loads(text) if text.strip() else None, hd
    except ValueError:
        return code, text, hd


def err(body):
    if isinstance(body, dict) and body.get('errors'):
        e = body['errors'][0]
        return (e.get('code', '') + ' ' + (e.get('detail') or e.get('title') or ''))[:200].replace('|', '/').replace('\n', ' ')
    return str(body)[:120].replace('|', '/').replace('\n', ' ')


def step(name, fn):
    global failed
    t = time.time()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa
        ok, detail = False, 'exception ' + repr(e)[:200]
    ms = int((time.time() - t) * 1000)
    if not ok:
        failed += 1
    print('STEP|%s|%s|%d|%s' % (name, 'PASS' if ok else 'FAIL', ms, detail), flush=True)
    return ok


def storefront_home():
    c, b, _ = call('GET', '/', raw=True)
    return c == 200 and '<html' in b.lower(), 'http %d, %d bytes' % (c, len(b))


def storefront_listing():
    c, b, _ = call('POST', '/store-api/category', {'limit': 5}, {'sw-access-key': KEY})
    cats = [x for x in (b or {}).get('elements', []) if x.get('type') == 'page' and x.get('active')] if c == 200 else []
    if not cats:
        return False, 'no category, http %d %s' % (c, err(b))
    ctx['cat'] = cats[0]['id']
    c, b, _ = call('GET', '/navigation/' + cats[0]['id'], raw=True)
    return c == 200 and '<html' in b.lower(), 'http %d, %d bytes' % (c, len(b))


def storefront_search():
    c, b, _ = call('GET', '/search?search=a', raw=True)
    return c == 200, 'http %d, %d bytes' % (c, len(b))


def admin_token():
    c, b, _ = call('POST', '/api/oauth/token', {'grant_type': 'password', 'client_id': 'administration', 'scopes': 'write', 'username': 'admin', 'password': 'shopware'})
    if c == 200 and 'access_token' in b:
        ctx['token'] = b['access_token']
        return True, 'http 200'
    return False, 'http %d %s' % (c, err(b))


def api(method, path, body=None):
    return call(method, '/api' + path, body, {'Authorization': 'Bearer ' + ctx['token']})


def admin_read():
    c, b, _ = api('POST', '/search/product', {'limit': 5, 'total-count-mode': 1})
    if c != 200:
        return False, 'http %d %s' % (c, err(b))
    ctx['products'] = b.get('total')
    return True, 'total %s products' % b.get('total')


def product_write():
    c, b, _ = api('POST', '/search/tax', {'limit': 1})
    if c != 200 or not b['data']:
        return False, 'tax http %d %s' % (c, err(b))
    pid = uuid.uuid4().hex
    ctx['pid'] = pid
    price = [{'currencyId': CURRENCY, 'gross': 12.5, 'net': 10.5, 'linked': False}]
    c, b, _ = api('POST', '/product', {'id': pid, 'name': 'Switch test product', 'productNumber': 'SW-SWITCH-' + pid[:8], 'stock': 5, 'taxId': b['data'][0]['id'], 'price': price})
    if c not in (200, 204):
        return False, 'create http %d %s' % (c, err(b))
    c, b, _ = api('PATCH', '/product/' + pid, {'stock': 7, 'name': 'Switch test product changed'})
    if c not in (200, 204):
        return False, 'update http %d %s' % (c, err(b))
    c, b, _ = api('POST', '/search/product', {'ids': [pid]})
    ok = c == 200 and b['total'] == 1 and b['data'][0]['stock'] == 7
    return ok, 'create 204, update 204, read back ' + ('ok' if ok else 'http %d %s' % (c, err(b)))


def sync_api():
    pid = uuid.uuid4().hex
    c, b, _ = api('POST', '/_action/sync', [{'key': 'w', 'action': 'upsert', 'entity': 'tag', 'payload': [{'id': pid, 'name': 'switch-' + pid[:8]}]}, {'key': 'd', 'action': 'delete', 'entity': 'tag', 'payload': [{'id': pid}]}])
    return c == 200, 'http %d %s' % (c, '' if c == 200 else err(b))


def checkout():
    sw = {'sw-access-key': KEY}
    c, b, h = call('GET', '/store-api/context', None, sw)
    if c != 200:
        return False, 'context http %d %s' % (c, err(b))
    tok = h.get('sw-context-token')
    sw['sw-context-token'] = tok
    c, b, _ = call('POST', '/store-api/salutation', {'limit': 1}, sw)
    sal = b['elements'][0]['id']
    c, b, _ = call('POST', '/store-api/country', {'limit': 1, 'filter': [{'type': 'equals', 'field': 'active', 'value': True}, {'type': 'equals', 'field': 'shippingAvailable', 'value': True}]}, sw)
    country = b['elements'][0]['id']
    email = 'switch-%s@example.com' % uuid.uuid4().hex[:8]
    c, b, h = call('POST', '/store-api/account/register', {'guest': True, 'email': email, 'salutationId': sal, 'firstName': 'Switch', 'lastName': 'Test', 'storefrontUrl': BASE,
                   'billingAddress': {'countryId': country, 'street': 'Teststr. 1', 'zipcode': '12345', 'city': 'Testcity'}}, sw)
    if c != 200:
        return False, 'register http %d %s' % (c, err(b))
    sw['sw-context-token'] = h.get('sw-context-token') or tok
    c, b, _ = call('POST', '/store-api/product', {'limit': 10, 'filter': [{'type': 'range', 'field': 'availableStock', 'parameters': {'gt': 5}}, {'type': 'equals', 'field': 'childCount', 'value': 0}]}, sw)
    if c != 200 or not b['elements']:
        return False, 'product listing http %d %s' % (c, err(b))
    ids = [e['id'] for e in b['elements']]
    c, b, _ = call('POST', '/store-api/checkout/cart/line-item', {'items': [{'type': 'product', 'referencedId': ids[0], 'quantity': 1}]}, sw)
    if c != 200 or not b.get('lineItems'):
        errs = b.get('errors') if isinstance(b, dict) else None
        keys = [e.get('key') or e.get('message') for e in (errs.values() if isinstance(errs, dict) else errs or [])]
        return False, 'add line item http %d %s cart errors %s' % (c, err(b), keys)
    c, b, _ = call('POST', '/store-api/checkout/order', {}, sw)
    if c != 200:
        return False, 'order http %d %s' % (c, err(b))
    return True, 'order %s, total %s' % (b.get('orderNumber'), b.get('price', {}).get('totalPrice'))


step('storefront home', storefront_home)
step('storefront listing', storefront_listing)
step('storefront search', storefront_search)
if step('admin token', admin_token):
    step('admin product search', admin_read)
    step('admin product write', product_write)
    step('admin sync api', sync_api)
step('store api checkout', checkout)
sys.exit(1 if failed else 0)
