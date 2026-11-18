#!/usr/bin/env python3
"""Compares the catalog (columns, indexes, constraints) of a PostgreSQL database with the expected catalog.

usage: compare-schema.py check  <database>   compares the database with expected-catalog.json, exit code 1 on a difference
       compare-schema.py update <database>   writes expected-catalog.json from the database (the lane schema, created by mysql-to-pg-ddl.py)

Index and constraint names are not compared, they are shortened and prefixed by the table, only their definitions are.
Column order is not compared.
"""
import collections
import json
import os
import subprocess
import sys

CONTAINER = os.environ.get('PG_CONTAINER', 'instance-postgres-1')
USER = os.environ.get('PG_USER', 'shopware')
EXPECTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expected-catalog.json')

QUERIES = {
    'columns': r"""select c.relname, a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull::text,
    regexp_replace(coalesce(pg_get_expr(d.adbin,d.adrelid),''),'\s+',' ','g'), a.attgenerated::text, coalesce(co.collname,'')
    from pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace
    left join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
    left join pg_collation co on co.oid=a.attcollation and a.attcollation<>100
    where n.nspname='public' and c.relkind='r' and a.attnum>0 and not a.attisdropped order by 1,2""",
    'indexes': r"""select tablename, regexp_replace(indexdef,'INDEX \S+ ON','INDEX ON') from pg_indexes where schemaname='public' order by 1,2""",
    'constraints': r"""select c.relname, o.contype::text, regexp_replace(pg_get_constraintdef(o.oid),'\s+',' ','g')
    from pg_constraint o join pg_class c on c.oid=o.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' order by 1,2,3""",
}


def query(database, sql):
    result = subprocess.run(['podman', 'exec', CONTAINER, 'psql', '-U', USER, '-d', database, '-AtF', '\t', '-c', sql], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit('psql failed: ' + result.stderr)
    return [line.split('\t') for line in result.stdout.splitlines()]


def catalog(database):
    return {name: query(database, sql) for name, sql in QUERIES.items()}


def compare(expected, actual):
    differences = 0
    columns_expected = {(r[0], r[1]): r[2:] for r in expected['columns']}
    columns_actual = {(r[0], r[1]): r[2:] for r in actual['columns']}
    print('columns: expected %d, actual %d' % (len(columns_expected), len(columns_actual)))
    for key in sorted(set(columns_expected) - set(columns_actual)):
        print('  missing column', key)
        differences += 1
    for key in sorted(set(columns_actual) - set(columns_expected)):
        print('  unexpected column', key)
        differences += 1
    for key in sorted(set(columns_expected) & set(columns_actual)):
        if columns_expected[key] != columns_actual[key]:
            print('  column differs', key, 'expected', columns_expected[key], 'actual', columns_actual[key])
            differences += 1
    for name in ('indexes', 'constraints'):
        left = collections.Counter(map(tuple, expected[name]))
        right = collections.Counter(map(tuple, actual[name]))
        print('%s: expected %d, actual %d' % (name, sum(left.values()), sum(right.values())))
        for key in sorted(left - right):
            print('  missing', name[:-1], key)
            differences += 1
        for key in sorted(right - left):
            print('  unexpected', name[:-1], key)
            differences += 1
    return differences


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('check', 'update'):
        sys.exit(__doc__)
    actual = catalog(sys.argv[2])
    if sys.argv[1] == 'update':
        with open(EXPECTED, 'w') as handle:
            json.dump(actual, handle, indent=1)
            handle.write('\n')
        print('written', EXPECTED)
        return
    with open(EXPECTED) as handle:
        expected = json.load(handle)
    differences = compare(expected, actual)
    print('%d differences' % differences)
    sys.exit(1 if differences else 0)


main()
