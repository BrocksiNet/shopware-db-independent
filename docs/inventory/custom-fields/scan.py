#!/usr/bin/env python3
"""Count custom field sets and custom fields that store plugins and apps ship (wave 10, handoff B, docs/48).

Usage: python3 -I scan.py <mirror>/plugins/shopware6 <out-dir>

Plugins: static scan of PHP files (vendor/, node_modules/, .git and test directories skipped, files above 3 MB skipped).
A PHP file is a "custom field file" when it mentions custom_field_set, customFieldSet, CustomFieldSet or CustomFieldTypes.
In such files, every `'type' => CustomFieldTypes::X` or `'type' => '<known custom field type>'` counts as one field
when its array also has a `'name' =>` key and is not the `'config'` array of a field (that one repeats the type),
every `'relations' =>` as one set, and a set targets products when the file has
`'entityName' => 'product'` or `ProductDefinition::ENTITY_NAME` next to a relations key.
Raw SQL inserts into `custom_field` are flagged per plugin, not counted as fields.

Apps: manifest.xml `<custom-fields><custom-field-set>`, each child of `<fields>` is one field,
`<related-entities>` tells whether the set targets products.

The scan reads the mirror only and executes nothing from it.
"""
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

SKIP_DIRS = {'vendor', 'node_modules', '.git', 'tests', 'Tests', 'test', 'Test'}
MAX_BYTES = 3 * 1024 * 1024

KNOWN_TYPES = {
    'bool', 'checkbox', 'colorpicker', 'date', 'datetime', 'entity', 'float', 'int', 'json',
    'number', 'price', 'html', 'media', 'select', 'switch', 'text',
}

RE_FILE = re.compile(r'custom_field_set|customFieldSet|CustomFieldSet|CustomFieldTypes')
RE_TYPE_CONST = re.compile(r"""['"]type['"]\s*=>\s*CustomFieldTypes::([A-Z_]+)""")
RE_TYPE_STR = re.compile(r"""['"]type['"]\s*=>\s*['"]([a-z]+)['"]""")
RE_RELATIONS = re.compile(r"""['"]relations['"]\s*=>""")
RE_PRODUCT_REL = re.compile(
    r"""['"]entityName['"]\s*=>\s*(['"]product['"]|ProductDefinition::ENTITY_NAME)"""
)
RE_CONFIG_KEY = re.compile(r"""['"]config['"]\s*=>\s*(array\s*)?$""")
RE_NAME_KEY = re.compile(r"""['"]name['"]\s*=>""")


def is_field_definition(src, pos):
    """True when the `'type' =>` at pos sits in an array that has a `'name' =>` key and is not the `'config'` array of a field."""
    depth = 0
    start = -1
    i = pos - 1
    while i >= 0:
        ch = src[i]
        if ch in ')]':
            depth += 1
        elif ch in '([':
            if depth == 0:
                start = i
                break
            depth -= 1
        i -= 1
    if start < 0:
        return False
    if RE_CONFIG_KEY.search(src[max(0, start - 40):start]):
        return False
    depth = 0
    end = len(src)
    i = pos
    while i < len(src):
        ch = src[i]
        if ch in '([':
            depth += 1
        elif ch in ')]':
            if depth == 0:
                end = i
                break
            depth -= 1
        i += 1
    return RE_NAME_KEY.search(src[start:end]) is not None


RE_SQL_INSERT = re.compile(r'INSERT\s+(IGNORE\s+)?INTO\s+`?custom_field`?\s*[(\s]', re.IGNORECASE)


def scan_plugin(path):
    fields = 0
    sets = 0
    product_sets = 0
    types = {}
    sql_insert = False
    cf_files = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith('.php'):
                continue
            full = os.path.join(root, name)
            try:
                if os.path.getsize(full) > MAX_BYTES:
                    continue
                with open(full, 'r', encoding='utf-8', errors='replace') as fh:
                    src = fh.read()
            except OSError:
                continue
            if RE_SQL_INSERT.search(src):
                sql_insert = True
            if not RE_FILE.search(src):
                continue
            file_fields = 0
            for m in RE_TYPE_CONST.finditer(src):
                if not is_field_definition(src, m.start()):
                    continue
                file_fields += 1
                t = m.group(1).lower()
                types[t] = types.get(t, 0) + 1
            for m in RE_TYPE_STR.finditer(src):
                t = m.group(1)
                if t in KNOWN_TYPES and is_field_definition(src, m.start()):
                    file_fields += 1
                    types[t] = types.get(t, 0) + 1
            rel = len(RE_RELATIONS.findall(src))
            if file_fields == 0 and rel == 0:
                continue
            cf_files += 1
            fields += file_fields
            sets += rel
            product_sets += min(rel, len(RE_PRODUCT_REL.findall(src)))
    return fields, sets, product_sets, types, sql_insert, cf_files


def local(tag):
    return tag.rsplit('}', 1)[-1]


def scan_app(manifest):
    try:
        tree = ET.parse(manifest)
    except ET.ParseError:
        return None
    fields = 0
    product_fields = 0
    sets = 0
    product_sets = 0
    types = {}
    for el in tree.iter():
        if local(el.tag) != 'custom-field-set':
            continue
        sets += 1
        is_product = False
        set_fields = 0
        for child in el:
            if local(child.tag) == 'related-entities':
                is_product = any(local(e.tag) == 'product' for e in child)
            if local(child.tag) == 'fields':
                for f in child:
                    if not isinstance(f.tag, str):
                        continue
                    set_fields += 1
                    t = local(f.tag)
                    types[t] = types.get(t, 0) + 1
        fields += set_fields
        if is_product:
            product_sets += 1
            product_fields += set_fields
    return fields, sets, product_sets, product_fields, types


def pct(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return s[k]


def summary(values):
    nz = [v for v in values if v > 0]
    return {
        'with_any': len(nz),
        'total': sum(nz),
        'p50': pct(nz, 50),
        'p90': pct(nz, 90),
        'p99': pct(nz, 99),
        'max': max(nz) if nz else 0,
    }


def main():
    base = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    os.makedirs(out, exist_ok=True)

    plugin_rows = []
    plugin_types = {}
    pdir = os.path.join(base, 'plugin')
    for name in sorted(os.listdir(pdir)):
        path = os.path.join(pdir, name)
        if not os.path.isdir(path):
            continue
        fields, sets, product_sets, types, sql_insert, cf_files = scan_plugin(path)
        for t, c in types.items():
            plugin_types[t] = plugin_types.get(t, 0) + c
        plugin_rows.append([name, fields, sets, product_sets, int(sql_insert), cf_files])

    app_rows = []
    app_types = {}
    adir = os.path.join(base, 'app')
    for name in sorted(os.listdir(adir)):
        manifest = os.path.join(adir, name, 'manifest.xml')
        if not os.path.isfile(manifest):
            continue
        res = scan_app(manifest)
        if res is None:
            app_rows.append([name, -1, -1, -1, -1])
            continue
        fields, sets, product_sets, product_fields, types = res
        for t, c in types.items():
            app_types[t] = app_types.get(t, 0) + c
        app_rows.append([name, fields, sets, product_sets, product_fields])

    with open(os.path.join(out, 'plugins.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['plugin', 'fields', 'sets', 'product_sets', 'sql_insert_custom_field', 'custom_field_files'])
        w.writerows(plugin_rows)
    with open(os.path.join(out, 'apps.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['app', 'fields', 'sets', 'product_sets', 'product_fields'])
        w.writerows(app_rows)

    pf = [r[1] for r in plugin_rows]
    meta = {
        'plugins': len(plugin_rows),
        'plugin_fields': summary(pf),
        'plugin_sets': summary([r[2] for r in plugin_rows]),
        'plugins_with_product_set': sum(1 for r in plugin_rows if r[3] > 0),
        'plugin_fields_in_plugins_with_product_set': summary([r[1] for r in plugin_rows if r[3] > 0]),
        'plugins_sql_insert_custom_field': sum(r[4] for r in plugin_rows),
        'plugin_types': dict(sorted(plugin_types.items(), key=lambda kv: -kv[1])),
        'apps': len(app_rows),
        'apps_unparsable': sum(1 for r in app_rows if r[1] < 0),
        'app_fields': summary([r[1] for r in app_rows if r[1] >= 0]),
        'app_sets': summary([r[2] for r in app_rows if r[2] >= 0]),
        'apps_with_product_set': sum(1 for r in app_rows if r[3] > 0),
        'app_product_fields': summary([r[4] for r in app_rows if r[4] >= 0]),
        'app_types': dict(sorted(app_types.items(), key=lambda kv: -kv[1])),
    }
    with open(os.path.join(out, 'meta.json'), 'w') as fh:
        json.dump(meta, fh, indent=1)
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
