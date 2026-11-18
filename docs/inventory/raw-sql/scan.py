#!/usr/bin/env python3
"""Inventory of raw SQL / MySQL-specific constructs outside the DAL.

Usage: python3 scan.py /path/to/instance [outdir]

Writes into outdir (default: directory of this script):
  raw-sql.csv   one row per in-scope file
  hits.tsv      every individual hit: construct, path, line, source line
  tables.md     summary tables (totals, areas, top 30)
  meta.json     scope numbers

Method: each PHP file is tokenised just enough to separate comments, string
literals (incl. heredoc/nowdoc) and code. SQL constructs are matched only inside
string literals (so PHP `if(` and comments do not count). PHP-side constructs
(Uuid helpers, ArrayParameterType::BINARY, QueryBuilder, ...) are matched in code
with comments and string contents blanked out.
"""
import csv, json, os, re, sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- tokenizer
HEREDOC = re.compile(r'<<<[ \t]*(["\']?)([A-Za-z_]\w*)\1\r?\n')

def tokenize(src):
    """Return (code, strings). code = src with comments and string contents blanked
    (newlines kept). strings = list of (start_line, content)."""
    n = len(src); i = 0; line = 1
    code = []; strings = []
    def blank(s):
        return ''.join('\n' if c == '\n' else ' ' for c in s)
    while i < n:
        c = src[i]
        two = src[i:i+2]
        if two == '//' or (c == '#' and src[i+1:i+2] != '['):
            j = src.find('\n', i)
            j = n if j == -1 else j
            code.append(blank(src[i:j])); i = j; continue
        if two == '/*':
            j = src.find('*/', i + 2)
            j = n if j == -1 else j + 2
            seg = src[i:j]; code.append(blank(seg)); line += seg.count('\n'); i = j; continue
        if c in '\'"':
            j = i + 1
            while j < n:
                if src[j] == '\\': j += 2; continue
                if src[j] == c: break
                j += 1
            content = src[i+1:j]
            strings.append((line, content))
            code.append(c + blank(content) + c)
            line += content.count('\n'); i = j + 1; continue
        if two == '<<' and src[i:i+3] == '<<<':
            m = HEREDOC.match(src, i)
            if m:
                ident = m.group(2)
                end = re.compile(r'^[ \t]*' + ident + r'\b', re.M).search(src, m.end())
                j = end.start() if end else n
                content = src[m.end():j]
                strings.append((line + 1, content))
                code.append(blank(src[i:j])); line += src[i:j].count('\n'); i = j; continue
        if c == '\n': line += 1
        code.append(c); i += 1
    return ''.join(code), strings

# ---------------------------------------------------------------- constructs
F = re.I
# SQL constructs, matched in string literal contents. (name, regex, flags)
SQL = [
 ('backtick_ident',   r'`[^`\n]+`', 0),
 ('hex_fn',           r'(?<![\w])HEX\s*\(', F),
 ('unhex_fn',         r'(?<![\w])UNHEX\s*\(', F),
 ('lower_hex',        r'\bLOWER\s*\(\s*HEX\s*\(', F),
 ('json_fn',          r'\bJSON_[A-Z_]+\s*\(', F),   # also split per function below
 ('json_arrow',       r"->>?\s*\\?['\"]\$", 0),
 ('group_concat',     r'\bGROUP_CONCAT\s*\(', F),
 ('group_concat_separator', r'\bSEPARATOR\b', F),
 ('on_dup_key',       r'\bON\s+DUPLICATE\s+KEY\s+UPDATE\b', F),
 ('replace_into',     r'\bREPLACE\s+INTO\b', F),
 ('insert_ignore',    r'\bINSERT\s+IGNORE\b', F),
 ('ifnull',           r'\bIFNULL\s*\(', F),
 ('if_fn',            r'(?<![\w])IF\s*\(', F),
 ('limit_offset_comma', r'\bLIMIT\s+(?:\d+|:\w+|\?)\s*,\s*(?:\d+|:\w+|\?)', F),
 ('date_format',      r'\bDATE_FORMAT\s*\(', F),
 ('now_fn',           r'\bNOW\s*\(', F),
 ('date_add',         r'\bDATE_ADD\s*\(', F),
 ('date_sub',         r'\bDATE_SUB\s*\(', F),
 ('interval_kw',      r'\bINTERVAL\s+(?:[-\d:?]|\w+\s+(?:SECOND|MINUTE|HOUR|DAY|WEEK|MONTH|YEAR)\b)', F),
 ('unix_timestamp',   r'\bUNIX_TIMESTAMP\s*\(', F),
 ('concat_fn',        r'\bCONCAT\s*\(', F),
 ('concat_ws',        r'\bCONCAT_WS\s*\(', F),
 ('find_in_set',      r'\bFIND_IN_SET\s*\(', F),
 ('regexp',           r'(?<=[\w`)\]])\s(?:NOT\s+)?(?:REGEXP|RLIKE)\s', F),
 ('match_against',    r'\bAGAINST\s*\(', F),
 ('last_insert_id',   r'\bLAST_INSERT_ID\s*\(', F),
 ('for_update',       r'\bFOR\s+UPDATE\b', F),
 ('skip_locked',      r'\bSKIP\s+LOCKED\b', F),
 ('lock_in_share',    r'\bLOCK\s+IN\s+SHARE\s+MODE\b', F),
 ('fk_checks',        r'\bFOREIGN_KEY_CHECKS\b', F),
 ('at_at_var',        r'@@\w+', 0),
 ('user_var',         r'(?<![@\w])@\w+\s*:=|\bSET\s+@\w+|(?<![@\w])@(?!@)[A-Za-z_]\w*$', F),
 ('information_schema', r'\bINFORMATION_SCHEMA\b', F),
 ('show_stmt',        r'\bSHOW\s+(?:FULL\s+)?(?:TABLES|COLUMNS|INDEX|INDEXES|KEYS|CREATE|VARIABLES|STATUS|DATABASES|TABLE\s+STATUS|PROCESSLIST|GRANTS|WARNINGS|ENGINES|GLOBAL|SESSION)\b', F),
 ('straight_join',    r'\bSTRAIGHT_JOIN\b', F),
 ('index_hint',       r'\b(?:USE|FORCE|IGNORE)\s+INDEX\s*\(', F),
 ('collate',          r'\bCOLLATE\b', F),
 # additional MySQL-only constructs noticed while sampling (see summary.md)
 ('cast_unsigned',    r'\bAS\s+(?:UNSIGNED|SIGNED)\b', F),
 ('cast_char_binary', r'\bAS\s+(?:CHAR|BINARY)\b|\bCONVERT\s*\([^)]*\bUSING\b', F),
 ('date_diff_fns',    r'\b(?:CONVERT_TZ|TIMESTAMPDIFF|DATEDIFF|TIMESTAMPADD|FROM_UNIXTIME|STR_TO_DATE|CURDATE|CURTIME|UTC_TIMESTAMP|SYSDATE|ADDDATE|SUBDATE|LAST_DAY|DAYOFWEEK|WEEKDAY|YEARWEEK)\s*\(', F),
 ('field_fn',         r'\b(?:FIELD|ELT)\(', F),
 ('substring_index',  r'\bSUBSTRING_INDEX\s*\(', F),
 ('rand_fn',          r'\bRAND\(\s*\)', F),
 ('uuid_fn',          r'\b(?:UUID|UUID_TO_BIN|BIN_TO_UUID)\(', F),
 ('ddl_keywords',       r'\bENGINE\s*=|\bAUTO_INCREMENT\b|\bUNSIGNED\b(?!\s*\))', F),
 ('multi_table_dml',  r'\b(?:DELETE\s+\w+(?:\s*,\s*\w+)*\s+FROM|UPDATE\s+[\w`.]+(?:\s+(?:AS\s+)?\w+)?\s+(?:INNER\s+|LEFT\s+)?JOIN)\b', 0),  # case-sensitive: avoids prose such as "could not load and delete tags from"
 ('insert_set',       r'\bINSERT\s+(?:IGNORE\s+)?INTO\s+[\w`.]+\s+SET\b', F),
 ('table_maint',      r'\b(?:OPTIMIZE|ANALYZE|REPAIR|CHECK)\s+TABLE\b|\bLOCK\s+TABLES\b|\bUNLOCK\s+TABLES\b|\bGET_LOCK\s*\(|\bRELEASE_LOCK\s*\(', F),
 ('truncate',         r'\bTRUNCATE\b', F),
 ('sql_calc_found_rows', r'\bSQL_CALC_FOUND_ROWS\b|\bFOUND_ROWS\s*\(', F),
 ('null_safe_eq',     r'<=>', 0),
 ('misc_fns',     r'\b(?:BIT_OR|BIT_AND|BIT_COUNT|INET_ATON|INET_NTOA|MD5|SHA1|SHA2|LOCATE|INSTR|ISNULL|STD|REGEXP_\w+)\s*\(', F),
 ('div_mod_kw',       r'\b(?:DIV|XOR)\b(?=\s)', 0),
 ('date_part_fns',   r'\b(?:YEAR|MONTH|DAY|DAYOFMONTH|HOUR|MINUTE|WEEK|QUARTER|MONTHNAME|DAYNAME)\(', F),
 ('cast_datetime',    r'\bAS\s+DATETIME\b|\bAS\s+DATE\b', F),
 ('order_by_null',    r'\bORDER\s+BY\s+NULL\b', F),
 ('values_fn', r'\bVALUES\s*\(\s*`?\w+`?\s*\)', F),  # VALUES(col) in ON DUPLICATE
]
SQL_RE = [(n, re.compile(p, f)) for n, p, f in SQL]
JSON_FN_RE = re.compile(r'\b(JSON_[A-Z_]+)\s*\(', re.I)

# PHP-side constructs, matched in code with comments/strings blanked
PHP = [
 ('uuid_fromHexToBytes',    r'\bUuid::fromHexToBytes\s*\(|\bUuid::fromHexToBytesList\s*\('),
 ('uuid_fromBytesToHex',    r'\bUuid::fromBytesToHex\s*\(|\bUuid::fromBytesToHexList\s*\('),
 ('uuid_randomBytes',       r'\bUuid::randomBytes\s*\('),
 ('array_param_binary',     r'\bArrayParameterType::BINARY\b|\bConnection::PARAM_\w+_ARRAY\b|\bParameterType::BINARY\b'),
 ('multi_insert_queue',     r'\bMultiInsertQueryQueue\b'),
 ('retryable',              r'\bRetryable(?:Query|Transaction)\b'),
 ('qb_calls',               r'->createQueryBuilder\s*\(|\bnew\s+QueryBuilder\s*\(|\bnew\s+QuerySelect\b'),
 ('exec_calls',             r'->(?:executeQuery|executeStatement|executeUpdate|executeCacheQuery|fetchAllAssociative|fetchAllAssociativeIndexed|fetchAllKeyValue|fetchAllNumeric|fetchAssociative|fetchFirstColumn|fetchNumeric|fetchOne|iterateAssociative|iterateKeyValue|iterateColumn|executeQuery|prepare|exec)\s*\('),
]
PHP_RE = [(n, re.compile(p)) for n, p in PHP]
# Metrics that are not MySQL-specific by themselves.
METRICS = {'multi_insert_queue', 'retryable', 'qb_calls', 'exec_calls', 'raw_sql_literals'}
PHP_SPECIFIC = {'uuid_fromHexToBytes', 'uuid_fromBytesToHex', 'uuid_randomBytes', 'array_param_binary'}

SQL_START = re.compile(r'^\s*\(?\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH|SET|SHOW|ALTER|CREATE|DROP|TRUNCATE|OPTIMIZE|ANALYZE|LOCK|UNLOCK|CALL|START|ROLLBACK|COMMIT)\b', re.I)
SQL_BODY  = re.compile(r'\b(FROM|INTO|SET|TABLE|WHERE|JOIN|VALUES|SELECT)\b|:\w+|\?', re.I)

CONN_IMPORT = re.compile(r'^\s*use\s+Doctrine\\DBAL\\Connection\b', re.M)

def line_of(strline, content, off):
    return strline + content.count('\n', 0, off)

def scan_file(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        src = fh.read()
    code, strings = tokenize(src)
    lines = src.split('\n')
    counts = Counter(); hits = []; json_fns = Counter()
    for sl, content in strings:
        text = content.replace("\\'", "'").replace('\\"', '"')
        for name, rx in SQL_RE:
            for m in rx.finditer(text):
                counts[name] += 1
                ln = line_of(sl, content, min(m.start(), len(content)))
                hits.append((name, ln, lines[ln-1].strip() if ln-1 < len(lines) else ''))
                if name == 'json_fn':
                    json_fns[m.group(0).split('(')[0].strip().upper()] += 1
        if SQL_START.match(text) and len(text) >= 12 and SQL_BODY.search(text):
            counts['raw_sql_literals'] += 1
    code = re.sub(r'(?m)^[ \t]*use\s[^;\n]*;', lambda m: ' ' * len(m.group(0)), code)  # ignore import lines
    for name, rx in PHP_RE:
        for m in rx.finditer(code):
            counts[name] += 1
            ln = code.count('\n', 0, m.start()) + 1
            hits.append((name, ln, lines[ln-1].strip()))
    return counts, hits, json_fns, code

def classify_scope(code, src_has_conn):
    exec_like = PHP_RE[-1][1].search(code) or PHP_RE[-2][1].search(code) \
        or PHP_RE[4][1].search(code) or PHP_RE[5][1].search(code)
    if src_has_conn: return 'imports_connection'
    if exec_like: return 'executes_sql_no_connection_import'
    return None

def area_sub(rel):
    parts = rel.split('/')[1:]  # drop 'src'
    if parts[0] == 'Core':
        area = 'Core/' + parts[1] if len(parts) > 2 else 'Core'
        sub = parts[2] if len(parts) > 3 else '(root)'
    else:
        area = parts[0]
        sub = parts[1] if len(parts) > 2 else '(root)'
    return area, sub

def main():
    if len(sys.argv) < 2:
        sys.exit('usage: scan.py /path/to/instance [outdir]')
    root = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
    srcdir = os.path.join(root, 'src')
    meta = Counter(); rows = []; allhits = []; jsonfn_total = Counter(); jsonfn_files = Counter()
    for dp, dn, fn in os.walk(srcdir):
        dn.sort()
        for f in sorted(fn):
            if not f.endswith('.php'): continue
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root)
            if '/Migration/' in '/' + rel + '/' or '/Migration/' in rel: meta['excluded_migration'] += 1; continue
            if rel.startswith('src/Core/Framework/DataAbstractionLayer/'): meta['excluded_dal'] += 1; continue
            meta['php_files_considered'] += 1
            with open(full, encoding='utf-8', errors='replace') as fh: raw = fh.read()
            has_conn = bool(CONN_IMPORT.search(raw))
            counts, hits, jf, code = scan_file(full)
            reason = classify_scope(code, has_conn)
            if not reason: continue
            meta['in_scope'] += 1; meta['scope_' + reason] += 1
            area, sub = area_sub(rel)
            rows.append(dict(path=rel, area=area, subdomain=sub, scope=reason, counts=counts, jf=jf))
            for h in hits: allhits.append((h[0], rel, h[1], h[2]))
            for k, v in jf.items(): jsonfn_total[k] += v; jsonfn_files[k] += 1
    sql_cols = [n for n, _, _ in SQL]
    php_cols = [n for n, _ in PHP]
    jcols = sorted(jsonfn_total)
    cols = sql_cols + php_cols + ['raw_sql_literals']
    SUBSET = {'lower_hex'}  # LOWER(HEX( is already counted in hex_fn; excluded from totals to avoid double counting
    def sql_total(r): return sum(r['counts'][c] for c in sql_cols if c not in SUBSET)
    def all_total(r): return sql_total(r) + sum(r['counts'][c] for c in PHP_SPECIFIC)
    with open(os.path.join(out, 'raw-sql.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['path', 'area', 'subdomain', 'scope'] + cols + ['sql_constructs_total', 'sql_plus_php_binary_total'] + ['jsonfn_' + j for j in jcols])
        for r in rows:
            w.writerow([r['path'], r['area'], r['subdomain'], r['scope']] + [r['counts'][c] for c in cols]
                       + [sql_total(r), all_total(r)] + [r['jf'][j] for j in jcols])
    with open(os.path.join(out, 'hits.tsv'), 'w') as fh:
        fh.write('construct\tpath\tline\tsource_line\n')
        for h in allhits: fh.write('%s\t%s\t%d\t%s\n' % (h[0], h[1], h[2], h[3].replace('\t', ' ')[:300]))
    with open(os.path.join(out, 'meta.json'), 'w') as fh: json.dump(dict(meta), fh, indent=1)

    # ---- tables.md
    L = []
    L.append('Scope numbers: ' + ', '.join('%s=%d' % kv for kv in sorted(meta.items())) + '\n')
    L.append('### (a) Totals per construct\n')
    L.append('| construct | files | occurrences | kind |\n|---|---:|---:|---|')
    for c in cols:
        files = sum(1 for r in rows if r['counts'][c]); occ = sum(r['counts'][c] for r in rows)
        kind = 'metric (not MySQL-specific)' if c in METRICS else ('PHP-side binary-uuid' if c in PHP_SPECIFIC else 'SQL string')
        L.append('| %s | %d | %d | %s |' % (c, files, occ, kind))
    L.append('\nJSON functions found (inside `json_fn`):\n\n| function | files | occurrences |\n|---|---:|---:|')
    for j in jcols: L.append('| %s | %d | %d |' % (j, jsonfn_files[j], jsonfn_total[j]))
    L.append('\nFiles with at least one SQL-string construct: %d of %d in scope.\n' % (sum(1 for r in rows if sql_total(r)), len(rows)))
    for title, key in (('Per area', 'area'), ('Per area / sub-domain', 'sub')):
        L.append('### (b) %s\n' % title)
        L.append('| %s | files in scope | files with SQL constructs | SQL constructs | raw SQL literals | QueryBuilder calls | exec calls |\n|---|---:|---:|---:|---:|---:|---:|' % key)
        agg = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
        for r in rows:
            k = r['area'] if key == 'area' else r['area'] + '/' + r['subdomain']
            a = agg[k]; a[0] += 1; a[1] += 1 if sql_total(r) else 0; a[2] += sql_total(r)
            a[3] += r['counts']['raw_sql_literals']; a[4] += r['counts']['qb_calls']; a[5] += r['counts']['exec_calls']
        for k, a in sorted(agg.items(), key=lambda kv: (-kv[1][2], kv[0])):
            L.append('| %s | %s |' % (k, ' | '.join(map(str, a))))
        L.append('')
    L.append('### (c) Top 30 files by SQL-string construct occurrences (`sql_constructs_total`; `lower_hex` is a subset of `hex_fn` and not added again)\n')
    L.append('| # | path | total | top constructs |\n|---:|---|---:|---|')
    for i, r in enumerate(sorted(rows, key=lambda r: (-sql_total(r), r['path']))[:30], 1):
        top = sorted(((r['counts'][c], c) for c in sql_cols if r['counts'][c]), reverse=True)[:5]
        L.append('| %d | %s | %d | %s |' % (i, r['path'], sql_total(r), ', '.join('%s=%d' % (c, n) for n, c in top)))
    with open(os.path.join(out, 'tables.md'), 'w') as fh: fh.write('\n'.join(L) + '\n')
    print('in scope:', meta['in_scope'], dict(meta))

if __name__ == '__main__':
    main()
