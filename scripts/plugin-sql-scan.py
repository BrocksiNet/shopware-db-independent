#!/usr/bin/env python3
"""Inventory of MySQL-specific SQL in Shopware 6 store plugins.

Usage: python3 scripts/plugin-sql-scan.py <plugin-root> [outdir] [--hits FILE] [--strings FILE]

  <plugin-root>  directory with one directory per plugin (store mirror .../shopware6/plugin)
  outdir         default docs/inventory/plugins
  --hits FILE    optional TSV with every construct hit (plugin, file, line, construct, source line)
  --strings FILE optional JSONL with SQL strings that contain a construct (for translator tests)

Writes into outdir: plugins.csv (one row per plugin) and meta.json (totals, buckets, construct table).

Reuses the tokenizer and construct patterns of docs/inventory/raw-sql/scan.py (imported, not changed).
Method per plugin: walk the directory, skip vendor/, node_modules/, tests/ and files above 3 MB, tokenise every
.php file (comments, strings, code), match SQL constructs in string literals of files that touch the database and
PHP-side constructs (binary uuid helpers, QueryBuilder, execute/fetch calls) in code. .sql files are matched as one string.
The bucket rule is documented in docs/28-plugin-sql-inventory.md and implemented in classify() below.
"""
import csv, importlib.util, json, os, re, sys
from collections import Counter
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, '..', 'docs', 'inventory', 'raw-sql', 'scan.py')
spec = importlib.util.spec_from_file_location('coresql_scan', SCAN)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # scan.py has a __main__ guard, importing does not run it

SKIP_DIRS = {'vendor', 'node_modules', '.git', 'tests', 'Tests', 'test'}
MAX_BYTES = 3 * 1024 * 1024

# ---------------------------------------------------------------- what the translator shim covers
# Verified by reading instance/src/Core/Framework/Adapter/Database/PostgreSQL/ (see docs/28).
# Constructs handled by the shim: syntax in MySQLToPostgreSQLTranslator (backticks, <=>, 0x literals, REGEXP,
# CAST AS UNSIGNED, CONCAT, INTERVAL, GROUP_CONCAT SEPARATOR, JSON_OBJECT/ARRAY, @@foreign_key_checks etc.),
# UpsertRewriter (ON DUPLICATE KEY, INSERT IGNORE, REPLACE INTO), InsertSetRewriter, Update/DeleteRewriter,
# ShowRewriter (COLUMNS, INDEX, TABLES), InformationSchemaRewriter (columns, tables), DdlRewriter and the functions
# of mysql-compat.sql (if, ifnull, hex, unhex, date_format, date_add/sub, now, group_concat, substring_index,
# rand, uuid, sha, quarter, json_*).
HANDLED = {
    'backtick_ident', 'hex_fn', 'unhex_fn', 'lower_hex', 'group_concat', 'group_concat_separator', 'on_dup_key',
    'replace_into', 'insert_ignore', 'ifnull', 'if_fn', 'date_format', 'now_fn', 'date_add', 'date_sub',
    'interval_kw', 'concat_fn', 'concat_ws', 'regexp', 'null_safe_eq', 'fk_checks', 'for_update', 'skip_locked',
    'truncate', 'cast_unsigned', 'uuid_fn', 'substring_index', 'rand_fn', 'multi_table_dml', 'insert_set',
    'order_by_null', 'values_fn', 'hex_literal_0x', 'dq_string_literal',
}
# handled only for some arguments, decided per match in classify_hit()
PARTIAL = {'json_fn', 'at_at_var', 'show_stmt', 'information_schema', 'collate', 'ddl_keywords'}
JSON_COMPAT = {'JSON_EXTRACT', 'JSON_UNQUOTE', 'JSON_OBJECT', 'JSON_ARRAY', 'JSON_CONTAINS', 'JSON_CONTAINS_PATH',
               'JSON_LENGTH', 'JSON_QUOTE', 'JSON_REMOVE', 'JSON_SET', 'JSON_TYPE', 'JSON_VALID', 'JSON_ARRAY_APPEND',
               'JSON_ARRAYAGG', 'JSON_VALUE'}  # the last two are native in PostgreSQL 17+, accepted by 18.7 (semantics not compared)
# every other construct of scan.py has no rule in the shim (find_in_set, match_against, last_insert_id, straight_join,
# index_hint, lock_in_share, user_var, table_maint, sql_calc_found_rows, date_diff_fns, field_fn, misc_fns, div_mod_kw,
# date_part_fns, cast_datetime, cast_char_binary, unix_timestamp, limit_offset_comma, json_arrow)
# Constructs that are valid or common on PostgreSQL as well, they do not count as "MySQL-specific hits".
WEAK = {'now_fn', 'concat_fn', 'concat_ws', 'for_update', 'skip_locked', 'truncate', 'interval_kw',
        'cast_datetime', 'values_fn', 'order_by_null', 'lower_hex'}

# DDL markers that exist only in MySQL (matched in DDL strings: CREATE / ALTER / DROP / RENAME)
DDL = [
    ('ddl_binary16', r'\b(?:VAR)?BINARY\s*\(\s*\d+\s*\)'),
    ('ddl_engine', r'\bENGINE\s*='),
    ('ddl_charset', r'\bCHARSET\s*=|\bCHARACTER\s+SET\b'),
    ('ddl_collate', r'\bCOLLATE\s*=?\s*utf8'),
    ('ddl_auto_increment', r'\bAUTO_INCREMENT\b'),
    ('ddl_unsigned', r'\bUNSIGNED\b'),
    ('ddl_alter_modify_change', r'\bALTER\s+TABLE\b[^;]*?\b(?:MODIFY|CHANGE)\b'),
    ('ddl_on_update_ts', r'\bON\s+UPDATE\s+CURRENT_TIMESTAMP\b'),
    ('ddl_json_check', r'\bJSON_VALID\s*\('),
    ('ddl_after_first', r'\bALTER\s+TABLE\b[^;]*?\b(?:AFTER|FIRST)\b'),
    ('ddl_backtick', r'`'),
    ('ddl_inline_key', r'(?m)^\s*(?:UNIQUE\s+|FULLTEXT\s+)?KEY\s+`?\w+`?\s*\('),
    ('ddl_fulltext', r'\bFULLTEXT\b'),
    ('ddl_drop_fk_index', r'\bDROP\s+(?:FOREIGN\s+KEY|INDEX)\b'),
    ('ddl_mysql_types', r'\b(?:TINYINT|MEDIUMINT|LONGTEXT|MEDIUMTEXT|LONGBLOB|MEDIUMBLOB|TINYTEXT|DATETIME\s*\(\s*\d\s*\)|ENUM\s*\()'),
]
DDL_RE = [(n, re.compile(p, re.I)) for n, p in DDL]
DDL_START = re.compile(r'^\s*(?:CREATE|ALTER|DROP|RENAME)\s+(?:UNIQUE\s+|TEMPORARY\s+)?(?:TABLE|INDEX|DATABASE|VIEW|TRIGGER|FUNCTION|PROCEDURE|SCHEMA)?', re.I)
DDL_START2 = re.compile(r'^\s*(?:CREATE\s+(?:UNIQUE\s+|TEMPORARY\s+)?(?:TABLE|INDEX|VIEW|TRIGGER)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX|TRIGGER|VIEW)|RENAME\s+TABLE)\b', re.I)

EXTRA_PHP = [
    ('mysqli_direct', re.compile(r'\bnew\s+\\?mysqli\b|\bmysqli_\w+\s*\(|\bmysql_(?:connect|query)\s*\(')),
    ('migration_class', re.compile(r'\bextends\s+(?:\\?[\w\\]*\\)?MigrationStep\b')),
    ('dal_use', re.compile(r'\bDataAbstractionLayer\\|\bEntityRepository\b|\bEntityDefinition\b|\bCriteria\b')),
    ('conn_ref', re.compile(r'Doctrine\\DBAL\\(?:Connection|Driver|Query|Statement)|\bDoctrine\\DBAL\b')),
    ('exec_strict', re.compile(r'->(?:executeQuery|executeStatement|executeUpdate|executeCacheQuery|fetchAllAssociative|fetchAllAssociativeIndexed|fetchAllKeyValue|fetchAllNumeric|fetchAssociative|fetchFirstColumn|fetchNumeric|fetchOne|iterateAssociative|iterateKeyValue|iterateColumn)\s*\(')),
    ('exec_loose', re.compile(r'->(?:prepare|exec)\s*\(')),
]
ENCODED = re.compile(r'ionCube|sg_load\(|<\?php //0[0-9a-f]{3}|@dezend|zend_loader|\$__[A-Za-z0-9]{6,}\s*=\s*base64_decode', re.I)

# constructs found by hand while checking plugins (not in scan.py)
EXTRA_SQL = [
    ('hex_literal_0x', re.compile(r'(?<![\w])0x[0-9a-fA-F]{32}(?![0-9A-Za-z_])')),
    ('dq_string_literal', re.compile(r'(?:=|<>|!=|\bLIKE|\bIN\s*\(|\bTHEN|\bELSE|\bSET\s+\w+\s*=)\s*"[^"`\n]*"', re.I)),
]
# date_part_fns and field_fn match prose such as "3 day(s)" when case insensitive, they only count in upper case here
CASE_SENSITIVE = {'date_part_fns', 'field_fn'}
# cast_datetime of scan.py also matches the alias "AS date", only CAST(x AS DATETIME) is invalid on PostgreSQL
OVERRIDE = {'cast_datetime': re.compile(r'\bAS\s+DATETIME(?:\s*\(\s*\d\s*\))?\s*\)', re.I)}
SQL_RE = [(n, OVERRIDE.get(n) or (re.compile(rx.pattern) if n in CASE_SENSITIVE else rx)) for n, rx in S.SQL_RE] + EXTRA_SQL
SQL_NAMES = [n for n, _ in SQL_RE]
PHP_NAMES = [n for n, _ in S.PHP_RE]
SHOW_OK = re.compile(r'SHOW\s+(?:FULL\s+)?(?:COLUMNS|INDEX|INDEXES|KEYS|TABLES)\b', re.I)
INFO_AFTER = re.compile(r'[`"]?\s*\.\s*[`"]?(\w+)', re.I)
AT_OK = re.compile(r'@@(?:(?:SESSION|GLOBAL)\.)?(?:foreign_key_checks|unique_checks|sql_mode|version)\b', re.I)


def classify_hit(name, m, text):
    """True if the shim has a rule for this match. Returns None for constructs outside HANDLED and PARTIAL."""
    if name in HANDLED and name != 'multi_table_dml':
        return True, name
    if name == 'json_fn':
        fn = m.group(0).split('(')[0].strip().upper()
        return fn in JSON_COMPAT, 'json:' + fn
    if name == 'at_at_var':
        return bool(AT_OK.match(m.group(0))), 'var:' + m.group(0)
    if name == 'show_stmt':
        return bool(SHOW_OK.match(text, m.start())), 'show:' + m.group(0).upper()
    if name == 'information_schema':
        t = INFO_AFTER.match(text, m.end())
        tbl = t.group(1).lower() if t else '?'
        # InformationSchemaRewriter::matches() needs the unquoted form information_schema.columns|tables after the translator,
        # a backtick quoted schema or table name becomes "information_schema"."COLUMNS" and is not rewritten (checked in the instance)
        quoted = text[m.start() - 1:m.start()] in ('`', '"') or bool(re.match(r'[`"]?\s*\.\s*[`"]', text[m.end():m.end() + 12]))
        if tbl in ('columns', 'tables') and quoted:
            return False, 'info_schema_quoted:' + tbl
        if 'table_catalog' in text.lower():
            return False, 'info_schema:table_catalog'
        return tbl in ('columns', 'tables'), 'info_schema:' + tbl
    if name == 'multi_table_dml' and not (re.match(r'\s*UPDATE\b', text, re.I) and text.rstrip().endswith(';')):
        return True, 'multi_table_dml'
    if name == 'multi_table_dml':
        return False, 'update_join_trailing_semicolon'  # UpdateRewriter appends FROM after the semicolon (checked in the instance)
    if name == 'misc_fns' and m.group(0).upper().startswith('MD5'):
        return True, 'md5'  # md5() exists in PostgreSQL
    if name == 'date_part_fns' and m.group(0).upper().startswith('QUARTER'):
        return True, 'quarter'  # defined in mysql-compat.sql
    return False, name


def walk(root):
    """Yield (relpath, abspath, kind) for php and sql files outside skipped dirs; count vendor php separately."""
    vendor_php = 0
    vendor_doctrine = False
    for dp, dns, fns in os.walk(root):
        keep = []
        for d in dns:
            if d in SKIP_DIRS:
                if d == 'vendor':
                    for vp, _, vf in os.walk(os.path.join(dp, d)):
                        vendor_php += sum(1 for f in vf if f.endswith('.php'))
                        if '/doctrine/' in vp.replace(os.sep, '/') + '/':
                            vendor_doctrine = True
                continue
            keep.append(d)
        dns[:] = keep
        for f in fns:
            if f.endswith('.php') or f.endswith('.sql'):
                yield os.path.join(dp, f), vendor_php, vendor_doctrine
    yield None, vendor_php, vendor_doctrine


def scan_plugin(args):
    name, root, want_hits, want_strings = args
    base = os.path.join(root, name)
    c = Counter()
    hits = []
    strings_out = []
    handled_names = Counter()
    unhandled_names = Counter()
    ddl_names = Counter()
    mig = Counter()
    vendor_php = 0
    vendor_doctrine = False
    for path, vendor_php, vendor_doctrine in walk(base):
        if path is None:
            break
        rel = os.path.relpath(path, base)
        try:
            if os.path.getsize(path) > MAX_BYTES:
                c['oversize_files'] += 1
                continue
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
        except OSError:
            c['unreadable_files'] += 1
            continue
        if path.endswith('.sql'):
            c['sql_files'] += 1
            file_hits_scan(rel, src, [(1, src)], None, c, hits, handled_names, unhandled_names, ddl_names, mig, strings_out,
                           name, True, want_hits, want_strings)
            continue
        c['php_files'] += 1
        if ENCODED.search(src[:4000]):
            c['encoded_files'] += 1
            continue
        code, strings = S.tokenize(src)
        code = re.sub(r'(?m)^[ \t]*use\s[^;\n]*;', lambda m: ' ' * len(m.group(0)), code)
        raw_code = src  # for conn_ref: use statements are blanked in code, check the source with strings blanked
        php = Counter()
        for n, rx in S.PHP_RE:
            php[n] = len(rx.findall(code))
        ex = {n: len(rx.findall(code)) for n, rx in EXTRA_PHP}
        conn_ref = ex['conn_ref'] > 0 or bool(re.search(r'^\s*use\s+Doctrine\\DBAL\b', src, re.M))
        is_mig = ex['migration_class'] > 0
        sql_literals = 0
        for sl, content in strings:
            text = content
            if S.SQL_START.match(text) and len(text) >= 12 and S.SQL_BODY.search(text):
                sql_literals += 1
        touches_db = ex['exec_strict'] > 0 or php['qb_calls'] > 0 or (conn_ref and (ex['exec_loose'] > 0 or sql_literals > 0))
        if touches_db:
            c['db_files'] += 1
        if ex['exec_strict'] > 0 or (conn_ref and ex['exec_loose'] > 0):
            c['exec_files'] += 1
        if php['qb_calls'] > 0:
            c['qb_files'] += 1
        if conn_ref:
            c['conn_ref_files'] += 1
        if ex['dal_use'] > 0:
            c['dal_files'] += 1
        if ex['mysqli_direct'] > 0:
            c['mysqli_files'] += 1
            unhandled_names['mysqli_direct'] += 1
        for k in S.PHP_SPECIFIC:
            c[k] += php[k] if touches_db else 0
            if not touches_db and php[k]:
                c[k + '_outside_db_files'] += php[k]
        for k in ('multi_insert_queue', 'retryable'):
            c[k] += php[k]
        c['exec_calls'] += php['exec_calls']
        c['qb_calls'] += php['qb_calls']
        if is_mig:
            mig['classes'] += 1
        if touches_db:
            c['sql_strings'] += sql_literals
            file_hits_scan(rel, src, strings, code, c, hits, handled_names, unhandled_names, ddl_names, mig, strings_out,
                           name, False, want_hits, want_strings, is_mig=is_mig, touches_db=touches_db)
        elif is_mig:
            pass
    c['vendor_php_files'] = vendor_php
    c['vendor_doctrine'] = int(vendor_doctrine)
    return name, c, hits, handled_names, unhandled_names, ddl_names, mig, strings_out


def file_hits_scan(rel, src, strings, code, c, hits, handled_names, unhandled_names, ddl_names, mig, strings_out,
                   plugin, is_sql_file, want_hits, want_strings, is_mig=False, touches_db=True):
    lines = src.split('\n')
    file_ddl = False
    file_ddl_mysql = False
    file_has_dml = False
    file_unhandled = False
    file_handled = False
    for sl, content in strings:
        text = content.replace("\\'", "'").replace('\\"', '"')
        is_ddl = bool(DDL_START2.match(text)) or (is_sql_file and bool(re.search(r'\b(?:CREATE|ALTER)\s+TABLE\b', text, re.I)))
        string_hit = False
        if is_ddl:
            file_ddl = True
            c['ddl_strings'] += 1
            for n, rx in DDL_RE:
                k = len(rx.findall(text))
                if k:
                    ddl_names[n] += k
                    file_ddl_mysql = True
        elif S.SQL_START.match(text) or is_sql_file:
            file_has_dml = True
        # DDL fragments in strings that do not start with CREATE/ALTER (concatenated or heredoc pieces): ENGINE=, COLLATE for
        # a column type, AUTO_INCREMENT next to a column type. They are DDL markers, not DML constructs. A column named auto_increment
        # (information_schema.tables) is neither.
        frag = (not is_ddl) and bool(re.search(r'\bENGINE\s*=|\bCOLLATE\s*=|\b(?:VAR)?CHAR\s*\(\d+\)|\b(?:TINY|BIG|SMALL|MEDIUM)?INT(?:EGER)?\b\s*(?:\(\d+\))?\s+(?:UNSIGNED|NOT\s+NULL|NULL|AUTO_INCREMENT)|\bNOT\s+NULL\b|\bLONGTEXT\b', text, re.I))
        if frag:
            for n, rx in DDL_RE:
                k = len(rx.findall(text))
                if k:
                    ddl_names[n] += k
                    file_ddl_mysql = True
        for n, rx in SQL_RE:
            if (is_ddl or frag) and n in ('collate', 'ddl_keywords'):
                continue
            if n == 'ddl_keywords':
                continue  # outside DDL and without a column type it is a column name such as auto_increment
            for m in rx.finditer(text):
                string_hit = True
                c[n] += 1
                if n == 'json_fn':
                    c['jsonfn_' + m.group(0).split('(')[0].strip().upper()] += 1
                if n in HANDLED and n != 'multi_table_dml':
                    ok, tag = True, n
                else:
                    ok, tag = classify_hit(n, m, text)
                if ok:
                    handled_names[tag] += 1
                    file_handled = True
                else:
                    unhandled_names[tag] += 1
                    file_unhandled = True
                if want_hits:
                    ln = sl + content.count('\n', 0, min(m.start(), len(content)))
                    hits.append((plugin, rel, ln, n, 'H' if ok else 'E', lines[ln - 1].strip()[:200] if ln - 1 < len(lines) else ''))
        if want_strings and string_hit and len(text) < 1500:
            strings_out.append({'plugin': plugin, 'file': rel, 'line': sl, 'ddl': is_ddl, 'sql': text})
    if code is not None:
        pass
    if is_mig:
        if file_ddl or file_has_dml:
            mig['classes_with_sql'] += 1
        if file_ddl:
            mig['classes_with_ddl'] += 1
        if file_ddl_mysql:
            mig['classes_with_mysql_ddl'] += 1
        if file_unhandled:
            mig['classes_with_unhandled_dml'] += 1
    if file_ddl:
        c['files_with_ddl'] += 1
    if file_ddl_mysql:
        c['files_with_mysql_ddl'] += 1


def classify(r):
    """Bucket of a plugin row. Order matters: the highest risk wins."""
    if r['php_files'] == 0:
        return 'a_no_php'
    if r['raw_sql_files'] == 0 and r['sql_files'] == 0 and r['mysqli_files'] == 0:
        return 'b_php_no_raw_sql'
    if r['unhandled_total'] > 0:
        return 'e_unhandled_construct'
    if r['ddl_mysql_total'] > 0:
        return 'd_mysql_ddl'
    if r['handled_specific_total'] > 0 or r['uuid_php_total'] > 0:
        return 'c_shim_handles'
    return 'c0_raw_sql_no_mysql_construct'


def main():
    argv = [a for a in sys.argv[1:]]
    opts = {}
    for key in ('--hits', '--strings'):
        if key in argv:
            i = argv.index(key)
            opts[key] = argv[i + 1]
            del argv[i:i + 2]
    if not argv:
        sys.exit(__doc__)
    root = os.path.abspath(argv[0])
    out = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.join(HERE, '..', 'docs', 'inventory', 'plugins')
    os.makedirs(out, exist_ok=True)
    names = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    jobs = [(n, root, '--hits' in opts, '--strings' in opts) for n in names]
    with Pool() as pool:
        results = pool.map(scan_plugin, jobs, chunksize=8)
    sql_cols = [n for n in SQL_NAMES]
    jfn = sorted({k for _, c, *_ in results for k in c if k.startswith('jsonfn_')})
    ddl_cols = [n for n, _ in DDL]
    php_cols = ['uuid_fromHexToBytes', 'uuid_fromBytesToHex', 'uuid_randomBytes', 'array_param_binary']
    rows = []
    hit_rows = []
    str_rows = []
    for name, c, hits, handled, unhandled, ddl_names, mig, strs in results:
        r = {'plugin': name}
        for k in ('php_files', 'vendor_php_files', 'vendor_doctrine', 'encoded_files', 'sql_files', 'oversize_files',
                  'db_files', 'exec_files', 'qb_files', 'conn_ref_files', 'dal_files', 'mysqli_files', 'sql_strings',
                  'ddl_strings', 'files_with_ddl', 'files_with_mysql_ddl'):
            r[k] = c[k]
        r['raw_sql_files'] = c['db_files']
        r['migration_classes'] = mig['classes']
        r['migration_classes_with_sql'] = mig['classes_with_sql']
        r['migration_classes_with_ddl'] = mig['classes_with_ddl']
        r['migration_classes_with_mysql_ddl'] = mig['classes_with_mysql_ddl']
        r['migration_classes_with_unhandled_dml'] = mig['classes_with_unhandled_dml']
        for k in sql_cols + jfn:
            r[k] = c[k]
        for k in ddl_cols:
            r[k] = ddl_names[k]
        for k in php_cols:
            r[k] = c[k]
        r['uuid_php_total'] = sum(c[k] for k in php_cols)
        r['multi_insert_queue'] = c['multi_insert_queue']
        r['retryable'] = c['retryable']
        r['mysql_specific_total'] = sum(c[k] for k in sql_cols if k not in WEAK)
        r['mysql_specific_nobacktick'] = r['mysql_specific_total'] - c['backtick_ident']
        r['handled_specific_total'] = sum(v for k, v in handled.items() if k.split(':')[0] not in WEAK)
        r['handled_specific_total'] = r['handled_specific_total']
        r['unhandled_total'] = sum(unhandled.values())
        r['ddl_mysql_total'] = sum(v for k, v in ddl_names.items() if k not in ('ddl_backtick', 'ddl_drop_fk_index'))
        r['handled_total'] = sum(handled.values())
        r['unhandled_kinds'] = ';'.join(f'{k}={v}' for k, v in sorted(unhandled.items()))
        r['bucket'] = classify(r)
        rows.append(r)
        hit_rows += hits
        str_rows += strs
    cols = list(rows[0].keys())
    with open(os.path.join(out, 'plugins.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    if '--hits' in opts:
        with open(opts['--hits'], 'w') as fh:
            for h in hit_rows:
                fh.write('\t'.join(str(x).replace('\t', ' ') for x in h) + '\n')
    if '--strings' in opts:
        with open(opts['--strings'], 'w') as fh:
            for s in str_rows:
                fh.write(json.dumps(s) + '\n')
    meta = {'plugins': len(rows), 'buckets': dict(Counter(r['bucket'] for r in rows))}
    with open(os.path.join(out, 'meta.json'), 'w') as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)
    print(json.dumps(meta, sort_keys=True))


if __name__ == '__main__':
    main()
