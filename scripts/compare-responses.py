import importlib.util, re, sys, hashlib
spec = importlib.util.spec_from_file_location('bl', '/tmp/bench/benchmark-load.py'); bl = importlib.util.module_from_spec(spec); spec.loader.exec_module(bl)
bl.CATALOG = True
A, B = bl.STACKS[sys.argv[1]], bl.STACKS[sys.argv[2]]
d = bl.discover(A); d['auth']['Authorization'] = 'Bearer ' + bl.token(A)
sc = bl.scenarios(d, 3)
strip = [(re.compile(rb'(csrf|token|nonce)[^"\'<>\s]{0,40}["\']?\s*[:=]\s*["\'][^"\']*["\']', re.I), b'T'), (re.compile(rb'\b[A-Za-z0-9_-]{40,}\b'), b'L'), (re.compile(rb'(?<=-)\d{6,10}\b'), b'N')]
def norm(p):
    for r, t in strip: p = r.sub(t, p)
    return p
ca, cb = bl.Client(A), bl.Client(B)
for name in ('storefront home', 'storefront listing with filter', 'storefront search', 'storefront product detail'):
    n, b = sc[name]; same = diff = 0; ex = None
    for i in range(0, 12):
        m, p, body, h = b(i)
        sa, _, pa = ca.request(m, p, body, h); sb, _, pb = cb.request(m, p, body, h)
        na, nb = norm(pa), norm(pb)
        if sa == sb and na == nb: same += 1
        else:
            diff += 1; ex = (i, p, sa, sb, len(na), len(nb))
    print(name, 'same', same, 'diff', diff, ex)
