import re,os,subprocess,sys
root='<repo>/instance/src'
names={}
pat1=re.compile(r"const\s+ENTITY_NAME\s*=\s*'([^']+)'")
pat2=re.compile(r"function getEntityName\(\)\s*:\s*string\s*\{\s*return\s+'([^']+)';",re.S)
for d,_,fs in os.walk(root):
    if '/Test' in d or '/node_modules' in d: continue
    for f in fs:
        if not f.endswith('.php'): continue
        p=os.path.join(d,f)
        s=open(p,errors='ignore').read()
        if 'EntityDefinition' not in s and 'ENTITY_NAME' not in s: continue
        for m in pat1.finditer(s): names.setdefault(m.group(1),set()).add(p[len(root)+1:])
        for m in pat2.finditer(s): names.setdefault(m.group(1),set()).add(p[len(root)+1:])
tables=[l.strip() for l in subprocess.check_output(['podman','exec','instance-database-1','mariadb','-uroot','-proot','shopware','-N','-e',"select table_name from information_schema.tables where table_schema='shopware' order by 1"]).decode().splitlines()]
ts=set(tables)
print('entity names found',len(names),'tables',len(tables))
print('TABLES WITHOUT DEFINITION:'); 
for t in tables:
    if t not in names: print(' ',t)
print('ENTITY NAMES WITHOUT TABLE:')
for n in sorted(names):
    if n not in ts: print(' ',n,sorted(names[n])[:2])
