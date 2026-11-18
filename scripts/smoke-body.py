import json
d = json.load(open('/tmp/smoke-body.json'))
if d.get('errors'):
    print(d['errors'][0].get('code'))
else:
    print(json.dumps({k: d[k] for k in sorted(d) if k in ('status', 'success', 'apiAlias')}))
