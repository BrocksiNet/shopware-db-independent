import subprocess, re, statistics
def run(sql):
    out = subprocess.run(['podman','exec','instance-postgres-1','psql','-U','shopware','-d','w6d_scratch','-Atq','-c',sql],capture_output=True,text=True).stdout
    return out
def ms(q, n=5):
    ts=[]
    for _ in range(n):
        o = run('EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) ' + q)
        m = re.search(r'Execution Time: ([\d.]+)', o); ts.append(float(m.group(1)))
    plan = [l for l in o.splitlines() if 'Scan' in l][0].strip()[:70]
    return statistics.median(ts), plan
sets = ", ".join("'SW%d'" % (i*997) for i in range(1, 11))
cases = {
 'equals': ("num = 'SW99700'", "lower(num) COLLATE ucs_basic = 'sw99700'"),
 'equalsAny (10)': (f"num IN ({sets})", f"lower(num) COLLATE ucs_basic IN ({sets.lower()})"),
 'prefix': ("name LIKE 'Product 0a1%'", "lower(name) COLLATE ucs_basic LIKE 'product 0a1%'"),
 'contains': ("name LIKE '%Müller%'", "lower(name) COLLATE ucs_basic LIKE '%müller%'"),
}
import sys
phase = sys.argv[1]
for k,(a,b) in cases.items():
    q = lambda w: f'SELECT id FROM t WHERE {w}'
    if phase == 'before': print(k, 'ci', *ms(q(a)))
    else: print(k, 'lower', *ms(q(b)))
