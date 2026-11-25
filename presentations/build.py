#!/usr/bin/env python3
"""Build two offline HTML decks from pinned Shopware excerpts. No dependencies."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
import re
import subprocess
import textwrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORE_REF = 'c8c6866ac19'
BATCH_REF = '46a47f1a7c9'
READ_STORE_REF = '91b22d0abbb'
WAVE10_REF = '0ed724decae'
DOC_REF = 'ce36f6c'
CORE_URL = 'https://github.com/BrocksiNet/shopware'
DOC_URL = 'https://github.com/BrocksiNet/shopware-db-independent'
DB = 'src/Core/Framework/Adapter/Database/'
V2 = 'src/Core/Framework/OrmSpike/DalV2/'
DAL = 'src/Core/Framework/DataAbstractionLayer/Dbal/'
NEWS = 'src/Core/Content/Newsletter/'
READ_STORE = 'src/Core/Framework/ReadStore/'


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True)


CORE_SHA = git(ROOT / 'instance', 'rev-parse', CORE_REF).strip()
BATCH_SHA = git(ROOT / 'instance', 'rev-parse', BATCH_REF).strip()
READ_STORE_SHA = git(ROOT / 'instance', 'rev-parse', READ_STORE_REF).strip()
WAVE10_SHA = git(ROOT / 'instance', 'rev-parse', WAVE10_REF).strip()
DOC_SHA = git(ROOT, 'rev-parse', DOC_REF).strip()
SOURCES: list[dict[str, str]] = []
SNIPPETS: list[dict] = []


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def source(label: str, url: str) -> str:
    if not any(s['url'] == url for s in SOURCES):
        SOURCES.append({'label': label, 'url': url})
    return url


def doc(path: str, label: str | None = None) -> str:
    # Validate every documentary link against the pinned research snapshot.
    git(ROOT, 'cat-file', '-e', f'{DOC_SHA}:{path}')
    return source(label or Path(path).name, f'{DOC_URL}/blob/{DOC_SHA}/{path}')


def commit(sha: str, label: str) -> str:
    full = git(ROOT / 'instance', 'rev-parse', f'{sha}^{{commit}}').strip()
    return source(f'{sha} · {label}', f'{CORE_URL}/commit/{full}')


def issue(n: int, label: str) -> str:
    return source(f'#{n} · {label} (recorded issue link)', f'https://github.com/shopware/shopware/issues/{n}')


TOKEN = re.compile(r"(?P<comment>//[^\n]*|/\*.*?\*/)|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")|(?P<variable>\$[A-Za-z_]\w*)|(?P<keyword>\b(?:public|private|protected|static|function|return|new|if|else|elseif|foreach|as|try|catch|throw|class|interface|final|readonly|const|null|true|false|void|string|array|bool|int|mixed|instanceof|continue|SELECT|FROM|WHERE|UPDATE|SET|CASE|WHEN|THEN|ELSE|END|ORDER|BY|FOR|OVER|COUNT|ASC|NULLS|FIRST)\b)|(?P<number>\b\d+(?:\.\d+)?\b)", re.S)


def syntax(text: str) -> str:
    out, last = [], 0
    for match in TOKEN.finditer(text):
        out += [esc(text[last:match.start()]), f'<span class="tok-{match.lastgroup}">{esc(match.group())}</span>']
        last = match.end()
    return ''.join(out) + esc(text[last:])


def code(path: str, ranges: list[tuple[int, int]], focus: list[tuple[str, list[int]]] = (), ref: str = CORE_SHA, label: str = '') -> str:
    raw = git(ROOT / 'instance', 'show', f'{ref}:{path}').splitlines()
    full = git(ROOT / 'instance', 'rev-parse', ref).strip()
    selected: list[tuple[int | None, str]] = []
    for a, b in ranges:
        assert 1 <= a <= b <= len(raw), (path, a, b, len(raw))
        if selected:
            selected.append((None, '…'))
        selected.extend((n, raw[n-1]) for n in range(a, b+1))
    common = min((len(line) - len(line.lstrip()) for n, line in selected if n and line.strip()), default=0)
    groups = [{'label': title, 'lines': lines} for title, lines in focus]
    assert all(set(group['lines']).issubset({n for n, _ in selected}) for group in groups), path
    url = source(f'{Path(path).name} · {ref[:11]} · selected lines', f'{CORE_URL}/blob/{full}/{path}#L{ranges[0][0]}-L{ranges[-1][1]}')
    lines = []
    for n, line in selected:
        if n:
            lines.append(f'<span class="code-line" data-line="{n}"><a class="ln" href="{CORE_URL}/blob/{full}/{path}#L{n}" target="_blank" rel="noopener noreferrer" aria-label="Open line {n}">{n}</a>{syntax(line[common:])}</span>')
        else:
            lines.append('<span class="code-line">    …</span>')
    SNIPPETS.append({'path': path, 'commit': full, 'ranges': ranges, 'focus': groups})
    controls = '<button class="focus-control" title="Cycle code highlights (H)"><span class="focus-count"></span><span class="focus-label"></span></button>' if groups else ''
    estimated_lines = sum(max(1, math.ceil(len(line[common:]) / 70)) for n, line in selected)
    dense = ' dense' if estimated_lines > 18 else ''
    return f'<div class="code{dense}" data-focus="{esc(json.dumps(groups))}"><div class="code-head"><span>{esc(label or Path(path).name)} · excerpts</span><a href="{url}" target="_blank" rel="noopener noreferrer">source ↗</a></div><pre><code>{"".join(lines)}</code></pre>{controls}</div>'


def read_code(path: str, ranges: list[tuple[int, int]], focus: list[tuple[str, list[int]]] = ()) -> str:
    return code(READ_STORE + path, ranges, focus, ref=READ_STORE_SHA)


def wave10_code(path: str, ranges: list[tuple[int, int]], focus: list[tuple[str, list[int]]] = ()) -> str:
    return code(path, ranges, focus, ref=WAVE10_SHA)


def sample(text: str, language: str = 'Illustrative SQL') -> str:
    return f'<div class="code"><div class="code-head"><span>{esc(language)} · explanatory example</span></div><pre><code>{"".join(f"<span class=code-line>{syntax(line)}</span>" for line in textwrap.dedent(text).strip().splitlines())}</code></pre></div>'


def point(label: str, text: str) -> str:
    return f'<div class="point"><div class="label">{label}</div><p>{text}</p></div>'


def callout(text: str, warn: bool = False) -> str:
    return f'<div class="callout{" warn" if warn else ""}">{text}</div>'


def metric(value: str, caption: str, sub: str = '') -> str:
    return f'<div class="metric"><div class="value">{value}</div><div class="caption">{caption}</div><div class="subcaption">{sub}</div></div>'


def node(title: str, text: str = '', cls: str = '') -> str:
    return f'<div class="node {cls}"><h3>{title}</h3><p>{text}</p></div>'


def flow(*nodes: str) -> str:
    return '<div class="flow">' + '<span class="arrow" aria-hidden="true">→</span>'.join(nodes) + '</div>'


def table(headers: list[str], rows: list[list[str]], compact: bool = False) -> str:
    return f'<table class="table{" compact" if compact else ""}"><thead><tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr></thead><tbody>{"".join("<tr>"+"".join(f"<td>{c}</td>" for c in row)+"</tr>" for row in rows)}</tbody></table>'


def split(left: str, right: str, wide: bool = False) -> str:
    return f'<div class="split{" wide" if wide else ""}"><div>{left}</div><div>{right}</div></div>'


def bars(rows: list[tuple[str, float, str]], maxvalue: float) -> str:
    return ''.join(f'<div class="bar-row"><div>{label}</div><div class="track"><div class="fill{" old" if i == 0 else ""}" style="width:{value/maxvalue*100:.2f}%"></div></div><div class="value">{text}</div></div>' for i, (label, value, text) in enumerate(rows))


def slide(slug: str, title: str, body: str, notes: str, citation: str = '', cls: str = '') -> dict:
    result = {'slug': slug, 'title': title, 'body': body, 'notes': notes, 'citation': citation, 'class': cls, 'sources': list(SOURCES)}
    SOURCES.clear()
    return result


def references(items: list[tuple[str, str, str]]) -> str:
    return '<div class="references">' + ''.join(f'<div class="reference"><a target="_blank" rel="noopener noreferrer" href="{url}">{title} ↗</a><p>{desc}</p></div>' for title, url, desc in items) + '</div>'


def architecture() -> list[dict]:
    slides = []

    doc('docs/10-architecture.md', 'Architecture and boundary changes')
    doc('docs/37-review-round-2.md', 'Review corrections and remaining gaps')
    overview = '''<p class="lead">A design review after the video: trace the boundaries, inspect the contracts, and choose what should become core.</p>
    <div class="agenda">
      <a href="#2"><span>02–07</span><div><h3>The database boundary</h3><p>SQL generation, ID binding, connection setup and the compatibility path.</p></div><b>↗</b></a>
      <a href="#8"><span>08–11</span><div><h3>The application boundary</h3><p>Storage ports, public events, DTO projections and the DAL contracts we keep.</p></div><b>↗</b></a>
      <a href="#12"><span>12–13</span><div><h3>Decisions and sources</h3><p>Questions for Jonas, with the evidence and code ready to open.</p></div><b>↗</b></a>
    </div><p class="small review-context">Assumes the experiment video is familiar · 24 November 2026 · about 20–25 minutes</p>'''
    slides.append(slide('architecture', 'Architecture review', overview,
        '<p>Assume Jonas knows the video. Skip the origin story, database scoreboard and benchmark recap.</p><p>This page is the agenda and return point. Click a chapter to jump, or press 1 from any slide to come back.</p><p>Ask which boundary Jonas wants to inspect first.</p>', cls='cover architecture-intro'))

    doc('docs/summary.md', 'Current architecture')
    doc('docs/08-dto-slice.md', 'Storage-port slice')
    slides.append(slide('boundaries', 'Three boundaries changed', table(
        ['Boundary', 'Responsibility in the PoC', 'What stays above it'],
        [['SQL generation', '<strong>SqlDialect</strong><br>Generate quoting, JSON, upsert and aggregate SQL.', 'DAL entity meaning and query intent.'],
         ['ID storage', '<strong>IdBinding</strong><br>Choose the value representation and parameter type.', 'Hex IDs in application code.'],
         ['Route storage', '<strong>NewsletterRecipientStorage</strong><br>Offer domain operations through DAL or SQL adapters.', 'Request validation and route behaviour.']])
        + '<div class="review-note">The first two serve database portability. The newsletter port tests a separate application-design idea.</div>',
        '<p>Explain these as three distinct changes. Do not present the newsletter port as a prerequisite for PostgreSQL.</p><p>The PoC still has legacy callers and SQL translation. This table describes the direction and the boundaries implemented in the slice.</p>'))

    doc('docs/summary.md', 'A storefront read reaches PostgreSQL')
    source('DAL EntityReader', f'{CORE_URL}/blob/{CORE_SHA}/{DAL}EntityReader.php')
    source('PostgreSQL factory', f'{CORE_URL}/blob/{CORE_SHA}/{DB}PostgreSQLFactory.php')
    read_flow = '''<div class="trace">
      <div><span class="trace-n">01</span><h3>Route and Criteria</h3><p>Choose requested fields, associations, filters and context.</p></div>
      <div><span class="trace-n">02</span><h3>DAL</h3><p>Resolve entity metadata, translations, inheritance and the query shape.</p></div>
      <div class="changed"><span class="trace-n">03</span><h3>Dialect + ID binding</h3><p>Generate platform SQL and bind IDs in the database’s representation.</p></div>
      <div><span class="trace-n">04</span><h3>DBAL connection</h3><p>The PostgreSQL middleware path still handles compatibility and decoding.</p></div>
      <div><span class="trace-n">05</span><h3>Database and result</h3><p>Execute the statement. The DAL hydrates the application result.</p></div>
    </div>'''
    slides.append(slide('read-path', 'One read, end to end', read_flow,
        '<p>Read the diagram top to bottom once. Pause on row 3: the change isolates platform decisions, while the DAL keeps the meaning of entities.</p><p>The compatibility layer still sees PostgreSQL statements. Generated native SQL does not bypass it automatically.</p><p>The next slide opens one concrete operation inside row 3.</p>'))

    commit('b4f6492fdf5', 'Use numeric JSON extraction for currency prices')
    doc('docs/20-currency-seo-codec.md', 'Currency arithmetic failure')
    left = code(DAL+'FieldAccessorBuilder/PriceFieldAccessorBuilder.php', [(150,158)],
        [('The caller asks for a numeric value', [154,155,156])])
    right = code(DB+'Dialect/PostgreSqlDialect.php', [(94,95),(97,98)],
        [('PostgreSQL supplies the explicit numeric cast', [97])])
    slides.append(slide('dialect', 'The caller names the operation',
        '<p class="slide-intro">Price access needs a number from JSON. Each database supplies the SQL for that operation.</p>'
        + '<div class="code-pair"><div><div class="compare-label">DAL price accessor</div>'+left+'</div><div><div class="compare-label">PostgreSQL dialect</div>'+right+'</div></div>'
        ,
        '<p>Trace from the price accessor to the PostgreSQL implementation. Press H to focus both sides.</p><p>The currency factor exposed text multiplied by numeric. jsonExtractNumber makes the intended type explicit.</p><p>Upserts need the same care: MySQL reacts to any unique key, PostgreSQL generally names a conflict target. A dialect contract needs semantic rules as well as syntax.</p>'))

    doc('docs/15-id-spike.md', 'Hex IDs above the database boundary')
    issue(23319, 'Central ID binding')
    snippet = code(DB+'Dialect/IdBinding.php', [(38,42),(49,50),(62,65)],
        [('Binary engines convert at binding time', [40,41]),
         ('PostgreSQL receives validated hex text', [49]),
         ('The parameter type follows the value', [64])])
    id_diagram = '''<div class="id-contract"><div class="id-root"><span>Application contract</span><h3>32-character hex ID</h3></div>
      <div class="id-branches"><div><span>MySQL / MariaDB / SQLite</span><h3>16 bytes</h3><p>Binary parameter</p></div><div class="uuid"><span>PostgreSQL</span><h3>Native UUID</h3><p>Hex text parameter</p></div></div></div>
      <div class="review-note">Keep representation and parameter type together. The legacy codec remains for unmigrated callers.</div>'''
    slides.append(slide('ids', 'IDs change representation at binding time', split(id_diagram, snippet),
        '<p>The left side is the contract. The right side shows its implementation.</p><p>Validation occurs in omitted lines 44–47. These are real source excerpts, with gaps explicitly marked.</p><p>IdBinding is a static migration facade. Whether that is the final API is a useful review question, especially for multiple connections.</p>'))

    source('SqlDialectFactory::forConnection()', f'{CORE_URL}/blob/{CORE_SHA}/{DB}Dialect/SqlDialectFactory.php#L24-L42')
    snippet = code(DB+'ConnectionFactory.php', [(29,40)],
        [('The configured driver chooses a connection factory', [31,32,33,35,36,37,39])])
    slides.append(slide('connection', 'Connection setup and SQL generation are separate', split(snippet,
        '<div class="ownership"><h3>ConnectionFactory</h3><p>DATABASE_URL chooses the driver, connection setup and middleware.</p></div>'
        + '<div class="ownership"><h3>SqlDialectFactory</h3><p>The actual DBAL platform chooses SQL generation for a connection.</p></div>'
        + '<div class="review-note"><strong>Review question:</strong> how should the static default behave in a process with multiple connections?</div>', True),
        '<p>The static SqlDialectFactory default is chosen from the configured driver, while forConnection uses the actual connection platform.</p><p>That is a convenience in the PoC. Explicit connection-scoped services would make the dependency easier to reason about.</p><p>Connection persistence and planning settings are operational concerns rather than responsibilities of the DAL caller.</p>'))

    doc('docs/10-architecture.md', 'Compatibility shim and target architecture')
    doc('docs/36-dal-v2-batched-update-postgresql.md', 'CASE identifiers and translator interference')
    doc('docs/37-review-round-2.md', 'Scope of the migration schema check')
    shim = '''<div class="path-lanes">
      <div class="path-label">Core SQL being migrated</div>
      <div class="path-row"><div><h3>DAL / raw SQL service</h3><p>Dialect-generated fragments</p></div><span>→</span><div class="connection-box"><h3>PostgreSQL connection</h3><p>Session, translator, ID codec</p></div><span>→</span><div><h3>PostgreSQL</h3><p>Native SQL execution</p></div></div>
      <div class="path-label legacy-label">Compatibility callers</div>
      <div class="path-row"><div><h3>Historic migrations / extensions</h3><p>Existing MySQL SQL</p></div><span>→</span><div class="connection-box"><h3>The same middleware path</h3><p>Translate remaining constructs</p></div><span>→</span><div><h3>PostgreSQL</h3><p>Translated SQL execution</p></div></div>
    </div><div class="review-note">The shim remains on both paths. New portable SQL can still expose translator ambiguities, as the batched CASE fix showed.</div>'''
    slides.append(slide('shim', 'The compatibility path still matters', shim,
        '<p>These are two caller paths through the current PoC, rather than two separate connection stacks.</p><p>The CASE problem shows why a long-lived translator has a cost beyond runtime overhead: it must interpret SQL that is already partly native.</p><p>New migrations need a neutral API. Old migrations and extension SQL keep the compatibility path for much longer.</p><p>If asked about the 910-migration result, use the corrected scope from doc 37. Do not reopen the video scoreboard here.</p>'))

    doc('docs/08-dto-slice.md', 'Newsletter storage slice and adapter limitations')
    commit('5657663d3e2', 'Route storage port and adapters')
    snippet = code(NEWS+'Domain/NewsletterRecipientStorage.php', [(15,17),(21,25)],
        [('The port names domain operations', [17,21,23,25])])
    port = '''<div class="port-path"><div><h3>Newsletter route</h3><p>Validate request, coordinate behaviour.</p></div><span>↓</span><div class="port-em"><h3>Storage port</h3><p>Find, upsert, confirm, opt out.</p></div><span>↓</span><div class="adapter-pair"><div><h3>DAL adapter</h3><p>Default. Keeps DAL writes and indexers.</p></div><div><h3>SQL adapter</h3><p>Opt-in. Skips DAL written events and indexers.</p></div></div></div>'''
    slides.append(slide('storage-port', 'A route can depend on domain operations', split(port, snippet),
        '<p>This is the application-design experiment, separate from the dialect work.</p><p>The default adapter remains the DAL. The SQL adapter is not behaviourally interchangeable because it skips DAL written events and indexers.</p><p>Ask whether this port clarifies the route enough to justify an extra abstraction and adapter contract.</p>'))

    commit('76d413489ec', 'Preserve event entities, extensions and explicit nulls')
    source('Storage event bridge contract', f'{CORE_URL}/blob/{CORE_SHA}/{NEWS}Domain/NewsletterRecipientStorage.php#L29-L34')
    snippet = code(NEWS+'SalesChannel/NewsletterSubscribeRoute.php', [(158,161),(197,201)],
        [('Build a typed request after existing validation', [158,160,161]),
         ('Write, read back and bridge to the public event entity', [197,199,200,201])])
    slides.append(slide('events', 'Public events constrain the DTO boundary', split(snippet,
        '<div class="ownership"><h3>Inside the route</h3><p>Typed requests and read models carry the use case.</p></div>'
        + '<div class="ownership"><h3>At the public event</h3><p>Subscribers still receive NewsletterRecipientEntity. The DAL adapter preserves the loaded entity and extension values.</p></div>'
        + '<div class="review-note"><strong>Review question:</strong> retain an entity bridge, or plan a versioned event contract?</div>', True),
        '<p>The initial DTO experiment rebuilt an entity too narrowly. Review corrected that bridge so loaded extension data reaches subscribers.</p><p>That is the architectural cost to discuss: a new internal type boundary does not make the existing public extension contract disappear.</p><p>The SQL adapter has different limitations and remains opt-in.</p>'))

    doc('docs/33-orm-spike-dal-v2.md', 'Projection implementation and partial-read trap')
    snippet = code(V2+'Projection/ProductListItem.php', [(11,25)],
        [('Paths describe the selected fields', [14,16,18,20,22,24]),
         ('The consumer gets a concrete DTO shape', [11,15,17,19,21,23,25])])
    projection = '''<div class="projection-steps"><div><span>1</span><p>Read the DTO’s <strong>Path attributes</strong>.</p></div><div><span>2</span><p>Build <strong>Criteria::addFields()</strong>.</p></div><div><span>3</span><p>Let the DAL load <strong>partial entities</strong>.</p></div><div><span>4</span><p>Copy the selected values into <strong>readonly DTOs</strong>.</p></div></div><div class="review-note">This prototype keeps DAL hydration. Direct-to-DTO hydration would be a separate change.</div>'''
    slides.append(slide('projections', 'A projection makes the requested shape explicit', split(snippet, projection, True),
        '<p>Keep the explanation on the read contract, rather than repeating the performance chart from the video.</p><p>The price property remains mixed and associations can be null. The prototype is concrete about the result class, but not fully typed for every field.</p><p>The parentId trap in inherited to-many partial reads is covered in the findings deck.</p>'))

    doc('docs/29-orm-alternatives.md', 'DAL contracts and ORM probes')
    doc('docs/33-orm-spike-dal-v2.md', 'Switchable DAL internals')
    source('DAL v2 composition', f'{CORE_URL}/blob/{CORE_SHA}/src/Core/Framework/OrmSpike/DalV2/DalV2Implementation.php')
    internals = '''<div class="contract-band"><span>Existing public contracts</span><p>EntityRepository · Criteria · definitions · entity events · APIs</p></div>
    <div class="internal-grid"><div><h3>Searcher</h3><p>Return exact totals with the page.</p><a href="core-findings.html#5">Inspect window totals ↗</a></div><div><h3>Read path</h3><p>Choose fields and project a result shape.</p><a href="core-findings.html#6">Inspect projections ↗</a></div><div><h3>Write gateway</h3><p>Fix existence lookups and batch compatible updates.</p><a href="core-findings.html#3">Inspect the key fix ↗</a></div></div>
    <div class="review-note">The spike composes alternate internals behind options. Plugin-field and app-lifecycle coverage still needs explicit probes.</div>'''
    slides.append(slide('dal-internals', 'DAL v2 experiments sit behind existing contracts', internals,
        '<p>Assume the video already covered the ORM comparison and the recommendation to keep the DAL.</p><p>The architectural point here is the seam: substitute an internal implementation while retaining the established concepts and API.</p><p>Keeping a signature does not prove behavioural compatibility. The findings deck shows where batching needed corrections.</p>'))

    issue(23318, 'Public dialect service')
    issue(23319, 'Central ID binding')
    issue(23311, 'DTO projections')
    slides.append(slide('decisions', 'Three design questions for Jonas',
        '<div class="review-decision"><span>01</span><div><h3>Which SQL operations deserve a public contract?</h3><p>Dialect methods, semantics, connection scope and extension access.</p></div></div>'
        + '<div class="review-decision"><span>02</span><div><h3>Where should ID binding live?</h3><p>The static facade speeds migration. A connection-scoped service makes dependencies explicit.</p></div></div>'
        + '<div class="review-decision"><span>03</span><div><h3>Which DTO boundary is useful enough to adopt?</h3><p>Consumer projections, route storage ports, and compatibility with public entity events.</p></div></div>',
        '<p>Ask for concrete design feedback, rather than another go/no-go on the whole experiment.</p><p>For each accepted next step, record an owner and an exit criterion. The PostgreSQL product decision can remain separate.</p><p>Use the findings deck to choose the first isolated implementation to land.</p>'))

    items = [
        ('Architecture detail', doc('docs/10-architecture.md'), 'Boundary changes and compatibility design.'),
        ('Newsletter slice', doc('docs/08-dto-slice.md'), 'Original experiment. The displayed code includes later bridge fixes.'),
        ('DAL v2 implementation', doc('docs/33-orm-spike-dal-v2.md'), 'Composition, projections, read shape and write levers.'),
        ('Latest review', doc('docs/37-review-round-2.md'), 'Correctness fixes and evidence limits.'),
        ('Core findings deck', 'core-findings.html', 'Continue with bugs, measured levers and upstream issues.'),
        ('Deck launcher', 'index.html', 'Choose either presentation.')]
    slides.append(slide('references', 'Code and research map', references(items),
        '<p>Each slide has its own source panel. Code links point to the pinned source snapshot.</p><p>Research links may require GitHub access. Press 1 to return to the architecture agenda, or Decks for the launcher.</p>'))
    for item in slides:
        item['class'] += ' arch'
    return slides


def findings() -> list[dict]:
    slides=[]
    doc('docs/core-findings.md','Core findings register')
    doc('docs/37-review-round-2.md','Latest review')
    slides.append(slide('findings','What the experiment<br><span class="accent">found in core</span>','<p class="lead">Bugs, expensive queries and implicit database behaviour.<br>Concrete changes worth reviewing on their own.</p><div class="cover-bottom"><p>Walkthrough with Jonas<br><span class="muted">24 November 2026 · about 30 minutes</span></p><div class="number">02</div></div>','<p>Start with the practical claim: the experiment produces useful core work even if PostgreSQL never becomes supported.</p><p>Use the subsystem agenda to choose OpenSearch hydration, DAL reads and writes, or PostgreSQL portability. The final slide connects the findings to concrete core work.</p>',cls='cover'))

    doc('docs/issues/README.md','Issue mapping and recorded filing status')
    slides.append(slide('map','Findings fall into three useful work streams',table(['Work stream','Examples','Value'],[['Correctness and robustness','Primary-key decoding, grouping, NULL order, transactions','Defined and reproducible behaviour'],['DAL performance','Window totals, projections, batching, lock order','Fewer statements and smaller reads'],['Database groundwork','Dialect, ID binding, migrations and extension SQL','A reviewable path to portability']])+callout('The research register contains 34 numbered findings. This deck selects the changes with the clearest explanation and evidence.'),'<p>The issue map records E1–E4 as filed and E5 as draft at the research snapshot. Live issue status may change.</p><p>Describe the PoC as evidence for small changes. The full experimental branch is not a merge candidate.</p>'))

    issue(23305,'Primary-key prefetch miss')
    commit('76ec3f5d17a','Decode storage-named keys before prefetch lookup')
    doc('docs/33-orm-spike-dal-v2.md','Key mismatch and isolated measurements')
    snippet=code(V2+'Write/WriteGatewayV2.php',[(922,934)],[('The input key uses storage names',[923,924]),('Fallback resolves version_id and product_id',[925,926,927]),('Decode before querying the prefetch bag',[928,931,932,933])])
    slides.append(slide('key-bug','A key-name mismatch defeats the prefetch cache',split(snippet,point('Mismatch','getField() expects a property name. The key contains storage names such as version_id.')+point('Consequence','The ID stays binary while the prefetched key is hex. A cache miss adds a SELECT.')+point('Fix','Resolve the field by storage name before decoding the key.'),True),'<p>Press H three times while tracing the actual lookup. The spike makes the fix switchable through fixExistenceKey.</p><p>PostgreSQL masked this bug because IDs already arrive as hex there. MySQL and MariaDB pay the extra queries.</p><p>The isolated fix is also in commit 76ec3f5d17a, outside the larger gateway experiment.</p>'))

    doc('docs/33-orm-spike-dal-v2.md','Isolated key-fix timing block')
    slides.append(slide('key-evidence','The key fix removes 250 statements in this run', '<div class="cols">'+metric('371','MySQL S4 statements before','50-product create + update scenario')+metric('121','statements with write=key','Isolated key-decoding fix')+metric('−32%','median: 88.55 to 60.60 ms','Doc 33 isolated-lever timing block')+'</div><div class="band">A small correctness fix makes an existing optimization work. It helps the current MySQL path without a PostgreSQL driver.</div><p class="small" style="margin-top:25px">Statement deltas and timings describe this specific harness run. They are separate from the later storefront and combined-lever timing blocks.</p>','<p>Keep the explanation narrow: a prefetch lookup that misses repeatedly. Do not generalize this ratio to every write workload.</p><p>The register also counts 248 excess lookups from the 371-versus-123 engine difference. The isolated MySQL before/after here is 371 versus 121, a reduction of 250. Keep those observations distinct.</p>'))

    issue(23306,'Exact total with a window count')
    commit('c34bd716ae8','Window count searcher')
    snippet=code(V2+'Read/WindowCountSearcher.php',[(136,150),(158,158)],[('Use the optimization only for eligible criteria',[136,137,138,139]),('Return count and page in one statement',[140,141,142,145,148,149]),('Empty pages still need the count fallback',[158])])
    slides.append(slide('window','A page can return its exact total in the same query',split(snippet,point('Existing work','The ID query runs, then a separate COUNT repeats its shape.')+point('Change','COUNT(*) OVER() adds the exact total to each returned row.')+point('Correctness','An empty page has no total-bearing row. Keep the fallback count.')+callout('The spike excludes score-field queries and requires a limit plus exact-total mode.'),True),'<p>Walk through the eligibility condition, total extraction and fallback.</p><p>The measured improvement for S3 and S5 was 15–45% in the isolated spike. The shape and data matter, so avoid promising a universal speedup.</p>'))

    issue(23311,'Typed DTO projections')
    doc('docs/51-timing-reliability.md','Paired 5k listing with all levers and projection')
    snippet=code(V2+'Projection/Projector.php',[(40,51),(54,54)],[('DTO metadata supplies the requested field list',[42,44,45,46,47]),('Use normal DAL partial loading',[49,51]),('Construct typed items afterwards',[54])])
    slides.append(slide('projection','Read only the fields the consumer asks for',split(snippet,point('Mechanism','DTO paths become the Criteria field list. The existing repository performs the read.')+point('Measured configuration','MySQL 5k listing: 10.82 to 4.77 ms with selected DAL optimizations and projection. Paired ratio 0.441×, 95% CI [0.411, 0.520].')+point('Limit','This implementation still hydrates partial entities before creating DTOs.'),True),'<p>Open ProductListItem from the architecture deck if Jonas needs to see the consumer type.</p><p>The quoted timing belongs to the combined configuration. It does not isolate projection cost.</p><p>The projector mutates the supplied Criteria and its reflection metadata is cached. Both are review topics for an additive public API.</p>'))

    issue(23310,'Inherited to-many association in partial reads')
    doc('docs/33-orm-spike-dal-v2.md','parentId requirement in partial reads')
    slides.append(slide('inheritance','Partial loading can drop an inherited association',sample('''// Explanatory field lists for the observed variant read
        ['id', 'prices']
        // inherited prices can come back empty

        ['id', 'parentId', 'prices']
        // matches the full read in the probe''','Illustrative PHP')+split('<div style="margin-top:30px">'+point('Cause','The inherited to-many fallback reads parentId from the loaded entity.')+'</div>','<div style="margin-top:30px">'+point('Proposed core fix','Select parentId implicitly when inherited associations require it.')+'</div>'),'<p>This is a discovered bug with a workaround and proposed fix. The deck does not claim it is fixed in core.</p><p>Explain why partial reads need semantic tests, not only field-count checks.</p><p>The snippet is explicitly illustrative. The issue and doc contain the reproducer context.</p>'))

    issue(23308,'Batched entity updates')
    doc('docs/36-dal-v2-batched-update-postgresql.md','PostgreSQL CASE fix and earlier timings')
    commit('bda47928e8d','Qualify CASE column references')
    slides.append(slide('batching','Batching removes repeated update statements',sample('''UPDATE product
        SET stock = CASE
          WHEN product.id = ? THEN ?
          WHEN product.id = ? THEN ?
          ELSE product.stock
        END
        WHERE product.id IN (?, ?)''')+split('<div style="margin-top:28px">'+point('Shape','Group compatible consecutive updates, preserve command order, and keep a typed ELSE column.')+'</div>','<div style="margin-top:28px">'+point('PoC discovery','Bare quoted CASE columns confused the translator. Table-qualified columns restored PostgreSQL batching.')+'</div>'),'<p>The SQL is schematic. The real gateway handles composite primary keys, varying columns and chunks of up to 100.</p><p>The PostgreSQL issue was in the PoC translator, rather than a general PostgreSQL requirement for casts.</p><p>The final semantics fixes were rebenchmarked: 27 statements on MySQL, MariaDB and SQLite; 29 on PostgreSQL. Four statements protect the two batches with savepoints.</p>'))

    commit('9cbb0be4f9e','Preserve uniqueness and failure attribution')
    commit('c8c6866ac19','Detect inline SQLite UNIQUE constraints')
    doc('docs/37-review-round-2.md','Batch semantics review')
    issue(23308,'Batch rules need to preserve single-command semantics')
    slides.append(slide('unique','Unique constraints make update order observable',split('<h3>Initial state</h3>'+table(['Row','Unique code'],[['a','1'],['b','2']])+flow(node('First command','b gets code 3'),node('Second command','a gets code 2','em')),'<h3>One command at a time</h3><p>The sequence succeeds because b frees code 2 first.</p><h3>One batched statement</h3><p>The plan may visit a first and reject the same logical change.</p>'+callout('Updates changing a primary-key or unique-index column stay single-row. Repeating the unchanged WHERE key still permits batching.')),'<p>The reverse discrepancy matters too: a batch may succeed when the command sequence should fail.</p><p>Replaying only after errors cannot catch that case. Excluding unique columns is therefore required, even with replay.</p><p>SQLite needs an extra pragma lookup because DBAL omits internal indexes backing inline UNIQUE constraints.</p>'))

    doc('docs/37-review-round-2.md','Failure attribution correction')
    snippet=code(V2+'Write/WriteGatewayV2.php',[(654,656),(659,664),(667,673)],[('Protect an active transaction before attempting the batch',[654,655,656]),('Undo a failed batch before replay',[661,662,663,664]),('Replay in command order and mark the actual failing row',[667,669,671,673])])
    slides.append(slide('failure','A failed batch must identify the right command',split(snippet,point('Transaction state','Roll back to a savepoint before continuing after a failed batch.')+point('Attribution','Replay the commands in their original order. Mark the command that actually fails.')+point('Consumers','Exception listeners and import/export rely on isFailed().'),True),'<p>Highlight the three stages with H. The code excerpt selects the failure path and omits the successful release below it.</p><p>A command that merely triggers a flush must not receive the failure flag for an earlier command.</p><p>Outside a transaction the code relies on statement atomicity before replay.</p>'))

    snippet=code('tests/unit/Core/Framework/OrmSpike/DalV2/Write/WriteGatewayV2BatchSemanticsTest.php',[(122,128),(131,136)],[('An unchanged key still allows one batched statement',[122,124,125,127,128]),('Changing a key preserves command-by-command execution',[131,133,135])],ref=BATCH_SHA)
    doc('docs/37-review-round-2.md','Four-engine batch verification')
    doc('docs/35-orm-spike-fair-write.md','Post-review batching rerun')
    doc('docs/36-dal-v2-batched-update-postgresql.md','Four-engine final batching measurements')
    slides.append(slide('batch-tests','Batching tests and the final-code rerun',split(snippet,
        '<p class="test-summary"><strong>7 tests / 19 assertions</strong><br>Passed on each of four engines.</p>'
        + table(['Engine','Statements','Median / DAL'],[['MySQL','27','46.57 ms / 0.56×'],['MariaDB','27','48.52 ms / 0.56×'],['SQLite','27','276.55 ms / 0.83×'],['PostgreSQL','29','69.29 ms / 0.85×']],True)
        + '<p class="small">50-product create + update. Four statements protect two batches with savepoints.</p>',True),
        '<p>The final guard distinguishes changed keys from unchanged WHERE keys repeated in the payload. The direct statement-count tests catch a guard that accidentally disables all batching.</p><p>The post-review rerun used 5 warm-ups and 50 measured iterations. All verification outputs matched the DAL. These are recorded single-block medians, not the later paired confidence intervals.</p><p>Unique swaps and CHECK failures also verify final rows, command flags and exception-event attribution. Savepoints had no measurable latency penalty in this block.</p>'))

    issue(23302,'Consistent row order in indexers')
    doc('docs/19-postgresql-parallel-writes.md','Deadlocks and ordered locks')
    doc('docs/26-postgresql-bulk-write.md','Sequential lock cost and write profiling')
    snippet=code('src/Core/Content/Product/DataAbstractionLayer/ProductIndexer.php',[(327,339)],[('Collect products, children and parents',[329,330,331,332]),('Acquire row locks in one ID order',[333]),('Run the indexer work after locking',[338])])
    slides.append(slide('locks','Concurrent indexers need a consistent lock order',split(snippet,point('Observed failure','Parallel product writers and indexers acquired shared rows in conflicting orders.')+point('PoC mitigation','PostgreSQL locks the affected product family in ID order before the updaters.')+point('Core direction','Give the updater paths a consistent row order across databases.')+callout('The recorded run moved from 31 deadlocks to 0. Median throughput rose from 1.59 to 3.09 requests/s.'),True),'<p>The excerpt begins after a platform guard. This particular mitigation is PostgreSQL-only.</p><p>The recorded parallel-write table is in the lock-order study. Separate later profiling reports about 40 ms additional sequential bulk latency; compare throughput and single-request latency separately.</p><p>Do not conflate indexer batching with the experimental DAL write gateway. They have different correctness requirements.</p>'))

    issue(23294,'Explicit NULL order')
    issue(23296,'String-filter accent semantics')
    doc('docs/23-postgresql-api-reads.md','NULL ordering, collations and indexes')
    slides.append(slide('semantics','Database defaults change visible results',table(['Behaviour','Observed difference','Core decision'],[['NULL ordering','ASC returns NULLs first on MySQL and last on PostgreSQL by default','Define the intended order and match indexes'],['Text comparison','MySQL collation matches muller with Müller. The PoC lower() path does not','Choose and test accent semantics'],['Numeric parameters','SQLite can compare text and numbers differently when values bind untyped','Bind numeric values explicitly'],['Price arithmetic','Implicit casts and decimal scale affect filters and rounding','State numeric type and scale explicitly']],True)+callout('A portable query must preserve agreed behaviour as well as valid syntax.'),'<p>NULL placement changes which rows appear on a paginated first page. It is a correctness issue visible in the administration.</p><p>The PostgreSQL lower() path trades accent insensitivity for performance. Sorting retains a different collation choice.</p><p>Explicit NULL ordering can also prevent a plain index from serving ORDER BY with LIMIT, so inspect the plan.</p>'))

    doc('docs/35-orm-spike-fair-write.md','DAL write profile and tested fair contract')
    slides.append(slide('profile','The write profile points beyond event dispatch', '<div class="cols">'+metric('39.6%','SQL execution and fetch','MySQL DAL v2 · 50-product create + update')+metric('1.1%','event dispatcher time','Includes observed listener work')+metric('59.3%','remaining writer PHP','Validation, serializers, extraction, change sets and other work')+'</div><div class="band">The profile supports investigating the writer. It does not isolate validation cost or prove every event listener is cheap.</div><p class="small" style="margin-top:26px">Instrumented profile timings are inflated. Use category shares rather than comparing their absolute milliseconds to benchmark tables.</p>','<p>This addresses the likely question about event overhead. The profile is one scenario and dataset.</p><p>The fair-write comparison adds selected validation and events to ORM paths. It still does not reproduce every DAL constraint.</p><p>Ask for a focused writer profile before proposing architectural removal of validation or events.</p>'))

    commit('071e6d9bea0','Scope UUID metadata cache to the connection')
    doc('docs/37-review-round-2.md','Codec cache review and limitations')
    snippet=code(DB+'PostgreSQL/IdCodecColumnTypes.php',[(41,49),(62,72)],[('Result-type data belongs to this connection instance',[41,43,44,45,48]),('Potential type-changing statements invalidate cached entries',[64,65]),('A process-wide generation invalidates all local connection caches',[69,71])])
    slides.append(slide('cache','SQL text alone cannot identify result types',split(snippet,point('Review finding','The same SQL can return uuid or text after DDL or on another session’s temporary objects.')+point('Fix','Keep metadata per connection. Invalidate process-local caches when statements can change type resolution.')+point('Remaining limit','Other-process DDL and schema changes inside a SELECT-called function remain outside coverage.'),True),'<p>This bug belongs to the PoC adapter. Label it as a review finding in the experimental infrastructure, rather than an upstream Shopware defect.</p><p>Per-result metadata lookup was measured as expensive, which explains why the cache stayed and gained explicit lifetime rules.</p><p>Two integration regressions cover same SQL after DDL and across separate sessions.</p>'))

    doc('docs/core-findings.md','Complete findings register')
    issue(23297,'Avoid rowCount after SELECT')
    issue(23289,'Strict grouping')
    issue(23291,'Window row numbering')
    issue(23293,'Duplicate keys in one upsert')
    slides.append(slide('smaller','Smaller findings are independent review candidates',table(['Finding','Problem','Direction'],[['SELECT rowCount()','Driver behaviour is undefined for result-row counts','Use fetchOne() !== false for existence'],['Strict GROUP BY','The session disables ONLY_FULL_GROUP_BY and queries rely on leniency','Make grouping and selected values explicit'],['To-many limits','Session-variable counters encode MySQL-specific state','Use ROW_NUMBER() OVER (PARTITION BY …)'],['Duplicate keys in an upsert','MySQL applies repeated keys sequentially. PostgreSQL rejects them','Define and apply queue-level deduplication semantics']],True),'<p>Use this slide as a menu. Open the issue that interests Jonas instead of reading all four rows.</p><p>The PoC has platform-specific fixes in places. An upstream proposal should choose and test the intended cross-platform contract explicitly.</p>'))

    doc('docs/issues/README.md','Issue map')
    slides.append(slide('priorities','A proposed order for core work', '<div class="decision"><div class="n">01</div><div><h3>Small correctness changes</h3><p>Primary-key decoding, defined existence checks and the inherited partial-read bug.</p></div></div><div class="decision"><div class="n">02</div><div><h3>Measured DAL improvements</h3><p>Window totals, aggregation fusion and compatible batching, with final-code measurements.</p></div></div><div class="decision"><div class="n">03</div><div><h3>Shared architecture decisions</h3><p>Public dialect, ID binding, DTO contracts, text semantics and a neutral migration API.</p></div></div>','<p>This ordering is a discussion proposal, not an approved backlog.</p><p>Pick the first two or three changes and assign an owner. Keep the PostgreSQL support decision separate from the independent MySQL benefits.</p><p>Check overlapping upstream work before preparing a new implementation.</p>'))

    items=[('Findings register',doc('docs/core-findings.md'),'All 34 findings and their recorded upstream mapping.'),('Issue map',doc('docs/issues/README.md'),'E1 robustness, E2 performance, E3 DAL v2, E4 abstraction, E5 PostgreSQL.'),('DAL v2 spike',doc('docs/33-orm-spike-dal-v2.md'),'Isolated levers, profiles, DX probes and known traps.'),('Comparable timing block',doc('docs/34-orm-spike-final-timings.md'),'Warm scenarios and output verification across candidates.'),('Fair writes and PostgreSQL CASE',doc('docs/35-orm-spike-fair-write.md'),'Selected write contract. Doc 36 corrects the translator diagnosis.'),('Review corrections',doc('docs/37-review-round-2.md'),'Final batching semantics, cache scope and evidence limits.')]
    doc('docs/36-dal-v2-batched-update-postgresql.md','CASE correction and earlier batching measurements')
    slides.append(slide('references','Source map',references(items),'<p>Sources in the sidebar include file, commit, issue and research links for each slide.</p><p>Issue URLs reflect the recorded research map. Their live status was not refreshed for this deck.</p>'))
    return slides


def architecture_wave9() -> list[dict]:
    base = architecture()
    fresh = []
    doc('docs/46-target-architecture.md', 'Consolidated target architecture, waves 1–9')
    doc('docs/38-read-store-plan.md', 'Wave 9 conclusion and remaining gates')
    base[0] = slide('architecture', 'Architecture review · through wave 9', '''
        <p class="lead">The DAL remains the write model. Storefront reads get a separate, rebuildable product document.</p>
        <div class="agenda">
          <a href="#read-write"><span>02–08</span><div><h3>The read model added in wave 9</h3><p>Documents, projection, existing OpenSearch queries and the narrow storage port.</p></div><b>↗</b></a>
          <a href="#boundaries"><span>09–18</span><div><h3>The DAL and database foundations</h3><p>Dialect, IDs, connection setup, route storage seams and DTO projections.</p></div><b>↗</b></a>
          <a href="#decisions"><span>19–20</span><div><h3>Decisions and remaining work</h3><p>What the PoC proves, what remains unbuilt, and what to review next.</p></div><b>↗</b></a>
        </div><p class="small review-context">24 November 2026 · follow-up to the video · wave 9 evidence and target kept distinct</p>''',
        '<p>Start with wave 9. The earlier architectural seams remain available as a second chapter.</p><p>O1+ is the recommended next implementation, not a measured end-to-end result. Full-document _source hydration is still unbuilt.</p>', cls='cover architecture-intro arch')

    doc('docs/46-target-architecture.md', 'Target architecture and dependencies')
    fresh.append(slide('read-write', 'Rebuildable reads beside the SQL write model', '''
        <div class="dual-model">
          <div class="model-column"><div class="model-label">Write side · source of truth</div><div class="model-box"><h3>DAL + indexers</h3><p>Admin, imports, plugins and stock writes.</p></div><span class="model-arrow">↓</span><div class="model-box dark"><h3>SQL database</h3><p>SqlDialect and IdBinding keep database decisions at the boundary.</p></div></div>
          <div class="model-column"><div class="model-label">Read side · proposed storefront path</div><div class="model-box"><h3>Existing OpenSearch query code</h3><p>IDs, total, filters, collapse and aggregations.</p></div><span class="model-arrow">↓</span><div class="model-box dark"><h3>ProductDocument through Storage</h3><p>Hydrate by ID from full OpenSearch _source or Valkey.</p></div></div>
        </div><div class="projection-link"><strong>Connection between the sides</strong><span>Indexer / stock events → projector → batch SQL builder + plugin extenders → documents</span></div>
        <div class="review-note">Target design. The document prototypes exist; full-document hydration through today’s OpenSearch path is the next implementation gate.</div>''',
        '<p>The diagram is a target, rather than a claim that the entire recommended route has been implemented.</p><p>SQL remains authoritative. The read store is a derived projection that can be rebuilt.</p><p>This read-model work is independent of whether PostgreSQL becomes a supported database.</p>', cls='arch'))

    doc('docs/38-read-store-plan.md', 'O1+ recommendation versus a multi-engine query port')
    doc('docs/42-read-store-opensearch.md', 'Existing OpenSearch path and unbuilt O1a')
    source('Current repository hydration seam', f'{CORE_URL}/blob/{READ_STORE_SHA}/src/Core/Framework/DataAbstractionLayer/EntityRepository.php#L280-L291')
    fresh.append(slide('query-hydration', 'Query execution and hydration are separate', '''
        <div class="path-lanes"><div class="path-label">O1 · existing OpenSearch path</div>
          <div class="path-row"><div><h3>OpenSearch query</h3><p>Return product IDs, total and aggregations.</p></div><span>→</span><div class="connection-box"><h3>SQL read</h3><p>cloneForRead($ids) loads entities.</p></div><span>→</span><div><h3>Store API</h3><p>Existing entity response.</p></div></div>
          <div class="path-label legacy-label">O1+ · recommended next step</div>
          <div class="path-row"><div><h3>Same query code</h3><p>Keep native OpenSearch search semantics.</p></div><span>→</span><div class="connection-box"><h3>Storage::mget()</h3><p>Read full product documents by ID.</p></div><span>→</span><div><h3>Store API</h3><p>Entity shape + live context.</p></div></div>
        </div><div class="review-note">The PoC’s generic query capabilities validated engines. The recommendation keeps only the narrow document-storage contract in core.</div>''',
        '<p>O1 already does the difficult query work. Wave 9 recommends replacing the SQL hydration after it.</p><p>The standalone OpenSearch adapter is a separate query implementation. Its timings are not O1+ timings.</p><p>Keep _source first as a proposed adapter, Valkey as the second, and SQL JSON as an optional detail/mget store.</p>', cls='arch'))

    doc('docs/40-read-store-port-and-document.md', 'Document layout and builder comparison')
    source('ProductDocument schema', f'{CORE_URL}/blob/{READ_STORE_SHA}/{READ_STORE}Document/ProductDocument.php')
    fresh.append(slide('document', 'One document per product, with context maps', table(
        ['In the document', 'At build time', 'At read time'],
        [['All languages', 'Resolve language fallback and variant inheritance.', 'Choose the language map entry.'],
         ['Currencies, rule buckets, visibility', 'Keep contextual values in one versioned document.', 'Choose the currency, rule and sales-channel keys.'],
         ['Custom fields and extensions', 'Run batched DocumentExtender hooks.', 'Use the declared read contract.']])
        + '<div class="review-note">150k-product comparison: one-per-product layout uses 150k documents. A visible product × channel × language layout needs 270k, with 1.46× the total size.</div>',
        '<p>These are documents for both parent and variant product rows, not one document per storefront context.</p><p>The layout has a schema version and is rebuildable. It is separate from the normalized SQL schema.</p><p>Do not confuse stored rule-price inputs with runtime-only app-script or cart-rule pricing. Those still have query-time limits.</p>', cls='arch'))

    doc('docs/40-read-store-port-and-document.md', 'Builders, projector and rebuild semantics')
    doc('docs/45-read-store-consistency.md', 'Event coverage and missed writes')
    commit('91b22d0abbb', 'Consistency probes and referenced-entity projection fixes')
    fresh.append(slide('projection-pipeline', 'The projector owns the coupling between models', '''
        <div class="pipeline-grid"><div><span>01</span><h3>Write signals</h3><p>Product indexer, stock and referenced-entity events.</p></div><b>→</b><div><span>02</span><h3>Affected products</h3><p>Expand parents to siblings. Queue or project synchronously.</p></div><b>→</b><div><span>03</span><h3>Batch builder</h3><p>SQL core fields plus DocumentExtender hooks.</p></div><b>→</b><div><span>04</span><h3>Storage</h3><p>Update live and pending generations.</p></div></div>
        <div class="split wave9-limits"><div><h3>Covered in the probes</h3><p>DAL writes, stock changes, deletes, version merges and the added reference listeners.</p></div><div><h3>Still needs a policy</h3><p>Raw SQL writes need explicit scheduling or reconciliation. Tax and currency changes need a catalog rebuild.</p></div></div>''',
        '<p>The corrected final table counts 15 of 18 scripted probes covered; an earlier handoff summary says 14 of 17. Use the concrete covered/missed categories on the slide.</p><p>The SQL builder took 28.32 seconds against 132.55 for the DAL builder at 150k with equal compared output. That is builder-only; full-store rebuilds took 46–132 seconds.</p><p>Delivery, cache invalidation and generation cleanup still need production hardening.</p>', cls='arch'))

    doc('docs/38-read-store-plan.md', 'Storage contract recommended for core')
    doc('docs/45-read-store-consistency.md', 'Generation cleanup race')
    snippet = read_code('Port/Storage.php', [(23,23),(28,28),(39,39),(44,44),(49,49),(56,56)],
        [('Read by ID', [49,56]), ('Project document changes', [39,44]), ('Build and activate generations', [23,28])])
    fresh.append(slide('storage-contract', 'Storage is the port worth keeping', split(snippet,
        point('Narrow contract', 'Store, remove, get and mget documents. Rebuild through setup and swap.')
        + point('Keep existing query code', 'FilterAware, SearchAware and per-engine criteria compilers remain experimental evidence.')
        + callout('The current swap contract drops old data immediately. The MongoDB probe shows why production needs delayed generation cleanup.', True), True),
        '<p>The excerpt selects six of Storage’s nine methods. liveGeneration, clear and destroy are also in the source.</p><p>The existing implementation does not yet satisfy the desired grace-period cleanup behaviour. Show that as a hardening task, not a completed fix.</p>', cls='arch'))

    doc('docs/44-read-store-integration.md', 'Display-time and query-time context boundaries')
    fresh.append(slide('live-parts', 'Live context and query membership need different rules', table(
        ['Concern', 'Display / hydration', 'Filter, sort and page membership'],
        [['Prices and rounding', 'Run existing price calculation on entity-shaped results.', 'Stored rule/currency buckets work only for matching rounding; otherwise fall back.'],
         ['Runtime-only script prices', 'Calculate at load time.', 'Cannot evaluate arbitrary PHP/Twig inside the index before pagination.'],
         ['Stock and closeout', 'Keep live calculation and checkout validation.', 'Listing membership is eventually consistent during projection lag.']])
        + '<div class="review-note">Entity-shaped Store API responses remain the compatibility default. The smaller DTO shape is opt-in work for new read endpoints.</div>',
        '<p>Updating a displayed price after a page is selected cannot repair the page’s membership or min/max aggregation.</p><p>The runtime-only price limitation also exists in the current SQL cheapest-price accessor and O1 path.</p><p>Cache invalidation must follow projection/visibility in async mode to prevent a stale cache refill.</p>', cls='arch'))

    doc('docs/46-target-architecture.md', 'Unproven work and next steps')
    doc('docs/44-read-store-integration.md', 'Parity sample and integration boundaries')
    doc('docs/issues/E6-read-store/00-epic.md', 'E6 draft acceptance criteria, not completed work')
    fresh.append(slide('wave9-status', 'Wave 9 supplies the pieces, with explicit next gates', '''
        <div class="split"><div class="ownership"><h3>Built and exercised</h3><p>Documents, builders, projector, storage adapters and Store API .pre hooks.</p><p>Contract tests, workload verification, consistency probes and 150k timing blocks.</p></div><div class="ownership"><h3>Remaining before a production proposal</h3><p>Full-document _source hydration on the existing OpenSearch path.</p><p>Cache/projection ordering, generation grace cleanup, circuit breaking and wider parity coverage.</p></div></div>
        <div class="review-note">E6 remains a draft. The 50-request sample matched SQL JSON 50/50 and OpenSearch 47/50; the latter had three tied-price order differences and five intentional fallbacks.</div>''',
        '<p>Do not present the E6 acceptance criteria as evidence they already pass.</p><p>Failure fallback was measured with fast-failing stores. A production circuit breaker and stalled-backend behaviour remain work.</p><p>The recommended O1+ path has not been measured end to end. Start with that implementation and its parity/latency check.</p>', cls='arch'))

    base[2]['title'] = 'The DAL read path remains the fallback'
    base[7]['title'] = 'Newsletter routes illustrate a separate storage seam'
    for item in base:
        item['body'] = item['body'].replace('core-findings.html#3', 'core-findings.html#key-bug').replace('core-findings.html#5', 'core-findings.html#window').replace('core-findings.html#6', 'core-findings.html#projection')
    doc('docs/46-target-architecture.md', 'Roadmap and prerequisites')
    doc('docs/issues/E6-read-store/00-epic.md', 'Read-model work, draft')
    base[-2] = slide('decisions', 'Three decisions after wave 9', '''
        <div class="review-decision"><span>01</span><div><h3>Validate O1+ before expanding the query abstraction</h3><p>Build full-document _source hydration on the existing OpenSearch path and measure parity and HTTP latency.</p></div></div>
        <div class="review-decision"><span>02</span><div><h3>Agree on the consistency contract</h3><p>Projection lag, raw SQL writers, cache invalidation order, safe rebuilds and fallback load.</p></div></div>
        <div class="review-decision"><span>03</span><div><h3>Land independent DAL improvements first</h3><p>Keep E1–E3 useful on MySQL. E6 can progress beside them; PostgreSQL still needs its own business decision.</p></div></div>''',
        '<p>The read store is independent of PostgreSQL and can run beside MySQL improvements.</p><p>Choose an owner and acceptance check for the recommended _source experiment. Avoid filing E6 as complete before that result.</p>', cls='arch')
    items = [('Target architecture', doc('docs/46-target-architecture.md'), 'Combined write/read model and phased core work.'),
             ('Wave 9 conclusion', doc('docs/38-read-store-plan.md'), 'Final timing block, recommendation and remaining gates.'),
             ('Port and document', doc('docs/40-read-store-port-and-document.md'), 'Schema, builders, projector and contract suite.'),
             ('Store API integration', doc('docs/44-read-store-integration.md'), 'Hooks, SQL accounting, live parts and response compatibility.'),
             ('Consistency probes', doc('docs/45-read-store-consistency.md'), 'Write coverage, lag, rebuild race and missed writes.'),
             ('Core findings deck', 'core-findings.html', 'Wave 9 first, then earlier code findings.')]
    base[-1] = slide('references', 'Code and research map', references(items), '<p>Code excerpts retain their milestone commits. Wave 9 uses 91b22d0abbb; earlier DAL excerpts use c8c6866ac19.</p>', cls='arch')
    return [base[0], *fresh, *base[1:]]


def findings_wave9() -> list[dict]:
    base = findings()
    fresh = []
    base[0]['body'] = '<p class="lead">Wave 9 adds read-model bottlenecks, consistency traps and Store API costs.<br>Earlier DAL fixes remain in the second chapter.</p><div class="cover-bottom"><p>Walkthrough with Jonas<br><span class="muted">24 November 2026 · wave 9 first, earlier findings as reference</span></p><div class="number">02</div></div>'
    base[1]['body'] = base[1]['body'].replace('34 numbered findings', '40 numbered findings') + '<div class="chapter-links"><a href="#wave9-results">Wave 9 findings ↗</a><a href="#key-bug">Earlier DAL findings ↗</a></div>'
    base[1]['notes'] += '<p>E6 is a draft, not a filed or implemented commitment. Use the jump links to focus the discussion.</p>'

    doc('docs/38-read-store-plan.md', 'Final warm benchmark, 150k products, handoff F')
    fresh.append(slide('wave9-results', 'Document reads win; the query path decides search', table(
        ['150k products · median', 'DAL', 'Existing OpenSearch (O1)', 'Experimental read store'],
        [['Detail', '6.15 ms', '10.98 ms', '0.15 ms · Valkey'],
         ['mget 24', '11.94 ms', '15.82 ms', '0.66 ms · Valkey'],
         ['Listing', '137.44 ms', '15.11 ms', '9.87 ms · OpenSearch adapter'],
         ['Word search', '1,222.48 ms', '<strong>25.54 ms</strong>', '573.81 ms · OpenSearch adapter']], True)
        + callout('The standalone adapter still runs SQL keyword interpretation. These are measured prototypes, not measurements of the proposed O1+ path.')
        + '<p class="small">Final F block · MySQL 8.4 write model · warm cache · one host · per-scenario medians, outside full HTTP routing.</p>',
        '<p>Compare rows within the final block. Store names matter: existing O1 and the standalone OpenSearch adapter have different search paths.</p><p>Supported scenarios verified against the DAL, with the keyword-aggregation count defect and known O1 differences recorded separately.</p><p>The handoff stopped other lanes; its own workers still created host load. Absolute values are indicative.</p>', cls='wave9'))

    doc('docs/38-read-store-plan.md', 'Final mixed-load block and remaining SQL keyword work')
    fresh.append(slide('wave9-scale', 'Existing OpenSearch already removes most read load', bars(
        [('DAL',10.4,'10.4 req/s'),('DAL v2',10.3,'10.3 req/s'),('Existing O1',453.8,'453.8 req/s'),('Standalone OS store',19.0,'19.0 req/s')],453.8)
        + '<div class="band">The standalone store keeps two SQL keyword queries in search. Under concurrency they saturate the write database despite fast document reads.</div>'
        + '<p class="small" style="margin-top:23px">150k products · c=8 · 50% detail, 30% listing, 20% search · approximately 20 seconds. DAL v2 does not move this catalog-scale bottleneck.</p>',
        '<p>O1 used about one MySQL core against 6.3 for the DAL; the remaining 2.7 statements per request were hydration.</p><p>These are short mixed-load runs, not a sustained production capacity claim. PostgreSQL store CPU was not included in the MySQL CPU column.</p><p>Earlier wave 8 slice gains still stand for those scenarios. They do not establish performance at 150k.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 39: SQL hydration after OpenSearch')
    doc('docs/42-read-store-opensearch.md', 'O1 versus standalone query paths')
    snippet = code('src/Core/Framework/DataAbstractionLayer/EntityRepository.php', [(280,280),(289,291)],
        [('IDs can come from the existing OpenSearch searcher', [280]), ('The repository still reads entities from SQL', [289,291])], ref=READ_STORE_SHA)
    fresh.append(slide('wave9-hydration', 'The repository re-reads OpenSearch hits from SQL', split(snippet,
        point('Observed seam', 'Search returns IDs. cloneForRead() sends them through entity hydration again.')
        + point('Proposed change', 'Keep OpenSearch queries, then hydrate from full documents through Storage::mget().')
        + callout('Full-document _source hydration on the existing path remains unbuilt. The E6.03 proposal needs that implementation and measurement.', True), True),
        '<p>The _searchIds call delegates through the configured searcher; this line is not itself specific to OpenSearch.</p><p>This is the narrow seam O1+ targets, rather than a new per-engine query compiler.</p>', cls='wave9'))

    commit('91b22d0abbb', 'Expand siblings and referenced-entity changes for projection')
    doc('docs/core-findings.md', 'Finding 37: sibling variants omitted by the indexer event')
    doc('docs/45-read-store-consistency.md', 'Sibling and inheritance miss probes')
    snippet = read_code('Projector/ReadStoreProjectorSubscriber.php', [(60,61),(64,73)],
        [('Start from the IDs emitted by the indexer', [60,61]), ('Expand parent IDs to their children', [64,65,66,69]), ('Schedule the full affected set', [73])])
    fresh.append(slide('wave9-siblings', 'An indexer event can omit affected sibling variants', split(snippet,
        point('Trigger', 'A variant update emits the variant and parent, while sibling-derived cheapest prices may also change.')
        + point('PoC fix', 'Expand affected parents to their children before scheduling projection.')
        + point('Core question', 'Should downstream projectors expand IDs, or should the indexer emit the full affected set?'), True),
        '<p>This is a concrete consistency bug in the event footprint exposed by a downstream document model.</p><p>The added manufacturer, property and media listeners cover their own dependent-product sets. Raw SQL, tax and currency are different gaps.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 38: surrounding route SQL')
    doc('docs/44-read-store-integration.md', 'Product versus surrounding SQL accounting')
    fresh.append(slide('wave9-route-sql', 'Zero product SQL still leaves 23 detail queries', table(
        ['Full detail route', 'Product read', 'Surrounding work', 'Total SQL'],
        [['DAL entity shape', '7', '23', '30'], ['Read-store entity shape', '0', '23', '23']])
        + '<div class="cols" style="margin-top:35px">' + metric('5','breadcrumb statements') + metric('4','configurator statements') + metric('14','CMS statements') + '</div>'
        + '<p class="small" style="margin-top:25px">Integration SQL-accounting probe · 5k products · full entity response. Listing retains 8 surrounding statements.</p>',
        '<p>This is a separate integration profiling block, not the 150k final harness.</p><p>The product fetch can become almost free without making the complete route free. Navigation, configurator and CMS projections are later candidates.</p><p>The .pre hooks avoid editing core route classes and return null to keep the DAL fallback available.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 40: entity response and JSON cost')
    doc('docs/44-read-store-integration.md', 'Response shape compatibility and HTTP measurements')
    fresh.append(slide('wave9-response', 'A smaller response needs an explicit API contract', '<div class="split"><div><h3>Existing entity-shaped response</h3>'
        + metric('165.2 KB','24-item listing · standalone OpenSearch store','Measured entity shape')
        + '<p class="small" style="margin-top:25px">Keeps SalesChannelProductEntity, loaded subscribers and existing Storefront expectations.</p></div><div><h3>Experimental DTO response</h3>'
        + metric('32.2 KB','same listing · DTO shape','Measured HTTP response size')
        + '<p class="small" style="margin-top:25px">Useful for new headless endpoints. It changes the response contract and cannot replace existing routes transparently.</p></div></div>'
        + callout('The smaller DTO omits entity behaviour. Keep entity hydration as the compatibility default.'),
        '<p>The HTTP block used 5k products, 15 measured requests after 3 warm-ups, with other lanes running and HTTP cache disabled.</p><p>The same store’s entity listing measured 52.43 ms and DTO listing 34.85 ms. Those observations do not isolate every source of serialization cost.</p><p>The DTO shape also breaks detail-response and loaded-subscriber assumptions. Do not call it a byte-equivalent Store API replacement.</p>', cls='wave9'))

    doc('docs/45-read-store-consistency.md', 'Blue/green swap under load: pointer-drop race')
    snippet = read_code('Adapter/MongoDb/MongoDbStorage.php', [(94,99)],
        [('Publish the new live pointer', [94]), ('Immediately deleting the old generation races with readers', [96,97,98,99])])
    fresh.append(slide('wave9-generation', 'An atomic pointer swap does not finish old reads', split(snippet,
        point('Observed failure', 'One of 5,226 concurrent MongoDB requests failed when swap() dropped a collection with an active aggregate cursor.')
        + point('Required hardening', 'Retain old generations beyond the maximum query lifetime, then garbage-collect them.')
        + callout('SQL MySQL and OpenSearch had zero errors in this probe. That does not prove every generation store is safe under every reader.', True), True),
        '<p>This race is in the experimental MongoDB adapter. Grace cleanup is a proposal, not a completed fix.</p><p>Pointer-based Valkey/SQL designs have the same lifecycle concern, even though this failure reproduced on MongoDB.</p><p>The test used 5k products, c=4 and a 12-second load period. E6.06 records the follow-up.</p>', cls='wave9'))

    doc('docs/44-read-store-integration.md', 'Async projection and stale HTTP cache refill')
    doc('docs/45-read-store-consistency.md', 'Observed write-to-read lag')
    fresh.append(slide('wave9-cache-order', 'HTTP invalidation must follow document visibility', flow(
        node('1 · SQL write', 'Invalidate the product HTTP cache.'),
        node('2 · Cache miss', 'Projection is still queued. Read the stale document.'),
        node('3 · Cache refill', 'Cache the old response beyond the projection lag.', 'dark'))
        + '<div class="band warn">Production requirement: invalidate again after the projected document is visible, or choose a synchronous policy for those writes.</div>'
        + '<p class="small" style="margin-top:25px">Recorded queue get() p50: Valkey 24.5 ms, OpenSearch 264.2 ms. OpenSearch search visibility with a 1s refresh interval had 760.7 ms p50 lag.</p>',
        '<p>This is a documented ordering hazard, rather than a measured stale-response rate.</p><p>Realtime OpenSearch get() and search refresh visibility differ. Invalidation after a store write alone may still precede query visibility.</p><p>Async delivery needs failure/retry and reconciliation policies. The experiment does not prove durable exactly-once projection.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 36: keyword terms aggregation over-count')
    doc('docs/39-read-store-baseline.md', 'O1 verify differences and counted products')
    fresh.append(slide('wave9-counts', 'A verification difference exposed a DAL count defect', '<div class="cols">'
        + metric('73','DAL manufacturer bucket','Hotel search · 5k dataset')
        + metric('71','distinct product count','Read-store contract result')
        + metric('2+','matching keyword rows can belong to one product','A join can multiply aggregation inputs') + '</div>'
        + '<div class="band">The product-ID query groups products. The terms aggregation can count the same product more than once when it matches multiple keywords.</div>'
        + '<p class="small" style="margin-top:25px">The doubled counts support a distinct-product fix. The aggregation SQL was not captured, so the missing DISTINCT is an inference. E6.07 remains a draft.</p>',
        '<p>Do not mark every non-equal verification result as an adapter bug. Check the agreed contract and actual products.</p><p>At 150k the final block reports 2,167 against 2,169 for this manufacturer bucket. The deck uses the smaller dataset’s concrete example.</p>', cls='wave9'))

    doc('docs/46-target-architecture.md', 'Next steps and evidence limits')
    doc('docs/44-read-store-integration.md', '50-request parity sample and fallback accounting')
    doc('docs/issues/E6-read-store/00-epic.md', 'E6 draft, not filed')
    fresh.append(slide('wave9-gates', 'The next experiment is a narrow O1+ implementation', table(
        ['Gate', 'Current evidence', 'Next check'],
        [['_source hydration', 'Recommended full-document path remains unbuilt.', 'Implement on existing OpenSearch queries; measure HTTP and parity.'],
         ['Compatibility', 'SQL JSON 50/50; OpenSearch 47/50 in the route sample.', 'Resolve tied-price ordering; count intentional fallback.'],
         ['Consistency and failure', 'Covered event paths; raw SQL and catalog-wide gaps remain.', 'Projection/cache ordering, grace GC, timeouts and circuit breaking.']], True)
        + '<div class="band">E6 is a draft. The read-model work can progress beside DAL improvements without a PostgreSQL support decision.</div>',
        '<p>Five OpenSearch sample requests fell back intentionally; three tied-price ordering differences account for the 47/50 comparison.</p><p>Fast-failing outage fallback had negligible overhead. Stalled backends still require a circuit breaker and a DAL load budget.</p><p>After this chapter, jump to earlier DAL findings if useful. The wave 8 benchmark numbers retain their own conditions.</p>', cls='wave9'))

    for item in base:
        item['body'] = item['body'].replace('All 34 findings', 'All 40 findings')
    base[-2]['notes'] += '<p>The source-hydration prototype is implemented. Productization requires write, cache-visibility and payload guards.</p>'
    items = [('Target architecture', doc('docs/46-target-architecture.md'), 'Write/read model and independent delivery gates.'),
             ('Wave 9 final evidence', doc('docs/38-read-store-plan.md'), '150k timing block, verification, scale and conclusion.'),
             ('Store API integration', doc('docs/44-read-store-integration.md'), 'SQL accounting, response shapes, parity and HTTP cache.'),
             ('Consistency probes', doc('docs/45-read-store-consistency.md'), 'Lag, missed writes, rebuild and fallback tests.'),
             ('Complete findings', doc('docs/core-findings.md'), '40 findings; E6 remains draft.'),
             ('Earlier DAL timings', doc('docs/34-orm-spike-final-timings.md'), 'Wave 8 conditions, kept separate from wave 9 results.')]
    base[-1] = slide('references', 'Source map · through wave 9', references(items), '<p>The source panel gives pinned file and commit links for every code example. E6 links are local research drafts rather than upstream issue claims.</p>')
    return [*base[:2], *fresh, *base[2:]]


def architecture_wave10() -> list[dict]:
    base = architecture_wave9()
    doc('docs/46-target-architecture.md', 'Architecture and wave 10 verdicts')
    doc('docs/51-timing-reliability.md', 'Canonical paired measurements')
    base[0] = slide('architecture', 'Architecture review · through wave 10', '''
        <p class="lead">O1a is now built and measured. The read/write split holds, with new conditions for indexing, cache visibility and document size.</p>
        <div class="agenda">
          <a href="#read-write"><span>02–09</span><div><h3>The implemented read model</h3><p>Source hydration, projection, custom-field limits and the remaining production gates.</p></div><b>↗</b></a>
          <a href="#boundaries"><span>10–19</span><div><h3>The DAL and database foundations</h3><p>Dialect, IDs, connection setup, storage seams and DTO projections.</p></div><b>↗</b></a>
          <a href="#postgresql-stack"><span>20–23</span><div><h3>PostgreSQL, evidence and decisions</h3><p>Production-like checks, measured uncertainty and the next core changes.</p></div><b>↗</b></a>
        </div><p class="small review-context">Updated 25 November 2026 · follow-up to the video · current results use doc 51’s paired timing block</p>''',
        '<p>Wave 10 closes the unbuilt O1a gate from the previous deck. Distinguish implemented proof of concept from production support.</p><p>Do not repeat the wave 9 claim that DAL v2 has no effect at 150k: its levers were off in that comparison. The corrected run is in the findings deck.</p>', cls='cover architecture-intro arch')

    doc('docs/47-o1a-source-hydration.md', 'Implemented source hydration design')
    doc('docs/46-target-architecture.md', 'Combined read/write architecture')
    base[1] = slide('read-write', 'The SQL write model now feeds an O1a read path', '''
        <div class="dual-model">
          <div class="model-column"><div class="model-label">Write side · source of truth</div><div class="model-box"><h3>DAL + product indexer</h3><p>Admin, imports, plugins and stock signals.</p></div><span class="model-arrow">↓</span><div class="model-box dark"><h3>SQL database</h3><p>SqlDialect and IdBinding keep database decisions at the boundary.</p></div></div>
          <div class="model-column"><div class="model-label">Read side · O1a implemented behind a flag</div><div class="model-box"><h3>Existing OpenSearch queries</h3><p>Keep filters, collapse, aggregations and native word search.</p></div><span class="model-arrow">↓</span><div class="model-box dark"><h3>SourceDocumentEntityReader</h3><p>Use documents from search hits or _mget, with counted SQL fallback.</p></div></div>
        </div><div class="projection-link"><strong>Write-side requirement</strong><span>Projector signals → full ElasticsearchIndexer::updateIds() → query fields + rs_document together</span></div>
        <div class="review-note">Built and measured in wave 10. Production still needs cache visibility, payload budgets and fallback policies.</div>''',
        '<p>The source reader decorates EntityReaderInterface. Repositories and the DAL write API are unchanged.</p><p>The feature flag is SHOPWARE_ES_SOURCE_DOCUMENT. The projector’s source storage re-indexes the whole product, rather than patching rs_document.</p>', cls='arch')

    doc('docs/47-o1a-source-hydration.md', 'Request-scoped buffer, reader and loaded events')
    source('Source reader implementation', f'{CORE_URL}/blob/{WAVE10_SHA}/src/Elasticsearch/Product/SourceDocument/SourceDocumentEntityReader.php')
    base[2] = slide('query-hydration', 'O1a changes hydration while keeping query semantics', '''
        <div class="path-lanes"><div class="path-label">O1 · existing path</div><div class="path-row"><div><h3>OpenSearch query</h3><p>Return IDs, total and aggregations.</p></div><span>→</span><div class="connection-box"><h3>SQL reader</h3><p>Read product rows for the returned IDs.</p></div><span>→</span><div><h3>Loaded events</h3><p>Existing entity behaviour.</p></div></div>
        <div class="path-label legacy-label">O1a · implemented document path</div><div class="path-row"><div><h3>Same query code</h3><p>Search hits also carry rs_document.</p></div><span>→</span><div class="connection-box"><h3>Source reader</h3><p>Consume the hit buffer. _mget missing IDs.</p></div><span>→</span><div><h3>Loaded events</h3><p>Entity prices and purchase limits.</p></div></div></div>
        <div class="review-note">Unsupported criteria, missing documents and unsupported associations use the inner SQL reader. Detail still needs a breadcrumb association fallback.</div>''',
        '<p>The buffer is consumed per request and reset through kernel.reset. The document is removed from hit data so it does not leak into an entity search extension.</p><p>DocumentHydrator’s event-free method avoids double loaded-event dispatch. SalesChannelRepository performs the normal dispatch afterwards.</p>', cls='arch')

    base[3]['body'] = base[3]['body'].replace('150k-product comparison: one-per-product layout uses 150k documents. A visible product × channel × language layout needs 270k, with 1.46× the total size.', 'Keep one reusable document, but deduplicate custom-field fallback values across languages. Wave 10 shows that document bytes become the next limit.')
    base[3]['notes'] += '<p>O1a uses the existing product index selection: 126k of the 150k catalog rows are indexed, just as in O1. Do not compare it with a store that indexes hidden parents as if the selections were identical.</p>'
    base[3]['sources'].append({'label':'Wave 10 document-size probes','url':f'{DOC_URL}/blob/{DOC_SHA}/docs/48-source-limits-custom-fields.md'})

    doc('docs/48-source-limits-custom-fields.md', 'Measured full-index cells versus extrapolated large documents')
    sizing = slide('source-size', 'Storing without indexing avoids mapping growth, not bytes', table(
        ['Custom fields × languages', 'Index size for 150k catalog', 'Evidence'],
        [['0 × 1', '0.42 GB', 'Measured full catalog'], ['100 × 5', '0.96 GB', 'Measured full catalog'],
         ['1,000 × 5', '2.66 GB', 'Extrapolated from a 20k subset'], ['5,000 × 20', '53.54 GB', 'Extrapolated from a 2k subset']], True)
        + '<div class="review-note">rs_document is an object with enabled: false. Custom fields still multiply stored values across languages; Valkey holds the same payload and does not solve that growth.</div>'
        + '<p class="small" style="margin-top:18px">Probe assumption: 10% field fill, 45-character names. One node, no replicas. Large-cell sizes are estimates, not full-catalog builds.</p>',
        '<p>The existing Shopware app custom-field mapping has its own field budget: 49,796 of 50,000 fields at 1,000 fields × 20 languages, and 61,501 at 5,000 × 5.</p><p>The source-only object adds one mapping entry. It does not make document JSON, network payloads or bulk request bytes free.</p><p>The largest probe sent 84.2 MB per bulk request. Use byte-budgeted batches and deduplicate fallback values before productionizing.</p>', cls='arch')

    doc('docs/47-o1a-source-hydration.md', 'Full re-index is required for projected source documents')
    commit('b09147c26f9', 'Re-index products instead of partial source updates')
    base[4] = slide('projection-pipeline', 'Projector writes must preserve the whole search document', '''
        <div class="pipeline-grid"><div><span>01</span><h3>Write signals</h3><p>Product, stock and referenced-entity changes.</p></div><b>→</b><div><span>02</span><h3>Affected IDs</h3><p>Expand siblings and schedule the product set.</p></div><b>→</b><div><span>03</span><h3>Full re-index</h3><p>ElasticsearchIndexer::updateIds() rebuilds each product.</p></div><b>→</b><div><span>04</span><h3>One document</h3><p>Query fields and rs_document update together.</p></div></div>
        <div class="split wave9-limits"><div><h3>Implemented constraint</h3><p>Partial _update can erase unstored query fields. A successful get() alone cannot verify search correctness.</p></div><div><h3>Remaining policy</h3><p>Raw SQL reconciliation, tax/currency rebuilds, refresh visibility and HTTP invalidation ordering.</p></div></div>''',
        '<p>SourceDocumentStorage::store treats supplied documents as a set of IDs to re-index. The indexer rebuilds the stored document again.</p><p>The source index lifecycle belongs to es:index. SourceDocumentStorage setup/swap are no-ops, unlike standalone generation stores.</p>', cls='arch')
    base[5]['notes'] += '<p>O1a now has a Storage adapter, but es:index owns its lifecycle. setup/swap/clear/destroy are intentionally no-ops on SourceDocumentStorage. Do not assume every adapter runs the standalone generation protocol.</p>'
    doc('docs/47-o1a-source-hydration.md', 'Source hydration and loaded-event responsibilities')
    doc('docs/51-timing-reliability.md', 'Search visibility and cache-window evidence')
    base[6] = slide('live-parts', 'Display calculation cannot repair query membership', table(
        ['Concern', 'O1a read behaviour', 'Boundary'],
        [['Prices and purchase limits', 'Normal loaded subscribers calculate display values.', 'OpenSearch query semantics stay unchanged; a later display calculation cannot repair the selected page.'],
         ['Stock and availability', 'Values arrive from the projected document.', 'Projection and search refresh introduce lag. Checkout validates against the write model.'],
         ['Unsupported read shapes', 'The decorated reader counts the reason and uses SQL.', 'O1a adds a hydration path, not a new query language.']])
        + '<div class="review-note">Invalidate HTTP output only after the search-visible document is current. Synchronous projection alone does not close the refresh window.</div>',
        '<p>The wave 9 generic query adapters had their own FieldResolver rounding guard. Do not present that guard as new O1a behaviour: O1a preserves existing OpenSearch queries.</p><p>SourceDocumentEntityReader hydrates without events; SalesChannelRepository then dispatches the normal loaded events once. Prices and purchase limits are calculated there; stock/availability remain document values.</p>', cls='arch')
    base[5]['sources'].append({'label':'O1a storage lifecycle','url':f'{CORE_URL}/blob/{WAVE10_SHA}/src/Elasticsearch/Product/SourceDocument/SourceDocumentStorage.php'})

    doc('docs/47-o1a-source-hydration.md', 'Implemented source path and parity sample')
    doc('docs/51-timing-reliability.md', 'Canonical throughput and SQL CPU')
    base[7] = slide('wave9-status', 'The O1a gate is closed, with production conditions', '''
        <div class="cols">''' + metric('50 / 50','Store API responses matched','46 document-served, 4 counted SQL fallbacks')
        + metric('1.42×','150k c=8 throughput versus O1','532 to 756 req/s · 95% CI [1.32, 1.48]')
        + metric('−84%','MySQL CPU in the same load block','15.1 to 2.44 CPU seconds per 15s window') + '''</div>
        <div class="review-note">This is an implemented PoC, not a supported release. Full re-indexing, post-refresh cache visibility and document/bulk size budgets are explicit requirements.</div>''',
        '<p>Parity and canonical load are different experiments. The parity sample is 50 Store API requests; the load block uses 150k products and 10 AB/BA rounds.</p><p>Listing and search hydrate product documents without SQL. Detail retains a mainCategories fallback and surrounding route SQL.</p>', cls='arch')

    doc('docs/49-postgresql-integration-suites.md', 'Classified non-DAL failures')
    doc('docs/50-postgresql-production-setup.md', 'Functional replica, TLS, search and worker checks')
    doc('docs/51-timing-reliability.md', 'Paired production-like journey and pooler timing')
    production = slide('postgresql-stack', 'PostgreSQL now has broader operational evidence', table(
        ['Area', 'Wave 10 result', 'Limit'],
        [['Production-like stack', 'Replica + TLS, OpenSearch, workers and PgBouncer exercised.', 'Functional coverage, not a support certification.'],
         ['Integration suites', 'PG-only failures: 386 to 90 across 8,072 tests.', 'CustomEntity DDL still fails 8 of 12 tests.'],
         ['Paired customer journey', 'PG / MariaDB: 1.178× total, CI [1.088, 1.227].', 'HTTP cache + OpenSearch; order step 1.372×.'],
         ['PgBouncer transaction mode', '1.312× direct PG, CI [1.128, 1.384], zero walk failures.', 'Disable the PHP SQL-level plan cache behind the pooler.']], True),
        '<p>Doc 50 supplies the functional checks. Doc 51 is the later timing authority: 50 measured walks per stack in each paired comparison, 200 across the two comparisons, with zero failures.</p><p>Direct PostgreSQL uses persistent connections and plan caching. PgBouncer uses non-persistent client connections and no PHP SQL-level plan cache.</p><p>The test counts exclude shared MariaDB failures from the PG-only classification; they are not an all-tests-green claim.</p>', cls='arch')

    doc('docs/51-timing-reliability.md', 'A/A noise and paired bootstrap method')
    reliability = slide('timing-reliability', 'Performance evidence now includes measured uncertainty', '''
        <div class="cols">''' + metric('10','paired AB/BA rounds','Alternate order to reduce drift')
        + metric('95%','paired bootstrap intervals','10,000 resamples of matched rounds')
        + metric('1 host','Apple M4 Pro / Podman VM','Target Linux hardware still needs verification') + '''</div>
        <div class="band">Measured A/A bounds vary by workload: ±1.7–8.2% for these CLI probes, and ±9.7–11.8% for full HTTP storefront probes.</div>
        <p class="small" style="margin-top:23px">Use doc 51 for current headline timings. Earlier wave 8 and wave 9 numbers retain their original, narrower experimental context.</p>''',
        '<p>A/A runs the same binary twice. These are host/workload-specific noise estimates, not universal accuracy guarantees.</p><p>Confidence intervals are for ratios of medians over paired rounds. Search under interleaved writes has an additional PostgreSQL bloat/autovacuum effect.</p>', cls='arch')

    doc('docs/46-target-architecture.md', 'Updated roadmap and next steps')
    doc('docs/issues/E6-read-store/00-epic.md', 'Updated E6 draft requirements')
    base[-2] = slide('decisions', 'Three decisions after wave 10', '''
        <div class="review-decision"><span>01</span><div><h3>Productize O1a with write and cache guards</h3><p>Full re-indexing, visibility-aware invalidation, counted SQL fallback and safe lifecycle ownership.</p></div></div>
        <div class="review-decision"><span>02</span><div><h3>Set document and bulk payload budgets</h3><p>Selective query mapping, custom-field deduplication and byte-based batching.</p></div></div>
        <div class="review-decision"><span>03</span><div><h3>Land independent fixes; keep the database decision explicit</h3><p>DAL v2 helps at 150k with levers enabled. PostgreSQL still needs its remaining fixes and a support/business decision.</p></div></div>''',
        '<p>The source-hydration implementation gate has been completed. E6 remains a draft ready for upstream discussion, not an already-filed commitment.</p><p>The architecture recommendation holds with stronger evidence, but its production conditions grew more concrete.</p>', cls='arch')
    refs = [('Target and verdicts', doc('docs/46-target-architecture.md'), 'Combined architecture, new evidence and remaining gates.'),
            ('O1a implementation', doc('docs/47-o1a-source-hydration.md'), 'Mapping, source buffer, reader, parity and full re-indexing.'),
            ('Custom-field limits', doc('docs/48-source-limits-custom-fields.md'), 'Measured cells, assumptions and extrapolation limits.'),
            ('PostgreSQL suites', doc('docs/49-postgresql-integration-suites.md'), 'Classified failures across the five non-DAL suites.'),
            ('Production-like setup', doc('docs/50-postgresql-production-setup.md'), 'Replicas, TLS, OpenSearch, workers and PgBouncer.'),
            ('Canonical measurements', doc('docs/51-timing-reliability.md'), 'Paired comparisons, cache poisoning and corrected DAL v2 claim.')]
    base[-1] = slide('references', 'Code and research map · through wave 10', references(refs), '<p>Wave 10 code is pinned to 0ed724decae. Historical code excerpts retain their earlier milestone commits.</p>', cls='arch')
    return [*base[:4], sizing, *base[4:18], production, reliability, *base[-2:]]


def findings_wave10() -> list[dict]:
    previous = findings_wave9()
    old = {s['slug']:s for s in previous}
    current = []
    old['findings']['body'] = '<p class="lead">Wave 10: implemented source hydration, corrected comparisons, indexing and cache defects, and PostgreSQL portability fixes.</p><div class="cover-bottom"><p>Walkthrough with Jonas<br><span class="muted">Updated 25 November 2026 · current evidence first, earlier findings as reference</span></p><div class="number">02</div></div>'
    doc('docs/core-findings.md', '50 findings through wave 10')
    doc('docs/51-timing-reliability.md', 'Current performance authority')
    old['map'] = slide('map', 'Three chapters for the core review', '''
        <div class="agenda">
          <a href="#wave9-results"><span>03–15</span><div><h3>Wave 10: implementation and corrected evidence</h3><p>O1a, DAL v2 with levers, new defects, PostgreSQL and timing reliability.</p></div><b>↗</b></a>
          <a href="#wave9-siblings"><span>16–19</span><div><h3>Read-model lessons still relevant from wave 9</h3><p>Sibling events, surrounding SQL, generation cleanup and count semantics.</p></div><b>↗</b></a>
          <a href="#key-bug"><span>20–35</span><div><h3>Earlier DAL fixes and review findings</h3><p>Prefetch keys, window counts, projections, batching and database semantics.</p></div><b>↗</b></a>
        </div><p class="small">The research register now contains 50 findings. E5/E6 remain drafts; upstream links reflect recorded status.</p>''',
        '<p>The wave 10 chapter replaces superseded wave 9 headlines. It is not another set of unqualified numbers appended to them.</p><p>Chapter links keep the deck useful as a reference if the meeting time is short.</p>')

    doc('docs/51-timing-reliability.md', '3e: O1 versus O1a, 150k products')
    current.append(slide('wave9-results', 'O1a removes SQL hydration on listing and search', table(
        ['150k · canonical paired block', 'O1 median', 'O1a median', 'O1a / O1 · 95% CI'],
        [['Detail', '7.64 ms', '3.37 ms', '0.440× [0.379, 0.491]'],
         ['Listing', '10.88 ms', '7.19 ms', '0.661× [0.654, 0.785]'],
         ['Word search', '24.66 ms', '22.02 ms', '0.893× [0.811, 0.996]'],
         ['Mixed c=8 throughput', '532.0 req/s', '756.1 req/s', '1.421× [1.318, 1.484]']], True)
        + callout('MySQL CPU drops from 15.07 to 2.44 seconds per 15s load window. Listing/search statements fall 2 to 0; detail still has one SQL statement.')
        + '<p class="small">Doc 51 · 10 AB/BA rounds · warm CLI harness and 15s c=8 blocks · one host. Full-route SQL is a separate accounting result.</p>',
        '<p>These replace the wave 9 standalone-store timings as the current O1a headline. They are not the same implementation as the standalone generic query adapter.</p><p>The separate 50-request Store API equality sample matched 50/50, with 46 document-served requests and four counted fallbacks.</p>', cls='wave9'))

    doc('docs/38-read-store-plan.md', 'Correction: wave 9 DAL v2 ran without levers')
    doc('docs/51-timing-reliability.md', '3c: corrected DAL v2 150k paired block')
    current.append(slide('wave9-scale', 'DAL v2 improves 150k reads when its levers are enabled', table(
        ['Scenario', 'DAL', 'DAL v2 + levers', 'Ratio · 95% CI'],
        [['Detail', '5.14 ms', '2.39 ms', '0.464× [0.410, 0.553]'],
         ['Listing', '115.6 ms', '67.38 ms', '0.583× [0.548, 0.641]'],
         ['Word search', '1,076 ms', '865.2 ms', '0.804× [0.761, 0.832]'],
         ['Mixed c=8 throughput', '14.05 req/s', '17.45 req/s', '1.242× [1.223, 1.285]']], True)
        + '<div class="band">The earlier “no change at 150k” claim was wrong: wave 9 omitted the options. With levers, throughput improves 24%, while the write database remains CPU-saturated.</div>'
        + '<p class="small">Options: count=window, agg=stats, write=key+upd, proj=1. The corrected DAL v2 throughput remains about 43× below O1a.</p>',
        '<p>Verify is OK on S1, S2, S3, R3b and R4. R4 itself has no resolved improvement: ratio 0.988 with CI [0.880,1.064].</p><p>The finding changes the quantitative claim, not the recommendation to retain OpenSearch for large-catalog storefront queries.</p>', cls='wave9'))

    doc('docs/47-o1a-source-hydration.md', 'Reader composition and unchanged repository flow')
    snippet = wave10_code('src/Elasticsearch/Product/SourceDocument/SourceDocumentEntityReader.php', [(107,118),(129,130)],
        [('Unsupported reads keep the SQL reader', [107,108,109]), ('Consume request documents and mget only missing IDs', [113,114,115,117]), ('Hydrate before normal loaded-event dispatch', [129,130])])
    current.append(slide('wave9-hydration', 'A reader decorator implements the hydration seam', split(snippet,
        point('Scope', 'Live sales-channel product reads by IDs. Queries and the repository flow stay unchanged.')
        + point('Request lifetime', 'Consume buffered hit documents. Reset the buffer between requests and worker iterations.')
        + point('Fallback', 'Unsupported associations, criteria or missing documents go to the inner SQL reader.'), True),
        '<p>The mainCategories association used by breadcrumbs is one observed detail fallback.</p><p>Loaded events run through SalesChannelRepository after the event-free document hydrator. This preserves live price and purchase-limit calculation without double dispatch.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 46: partial updates erase query fields')
    doc('docs/47-o1a-source-hydration.md', 'Observed 516 missing search documents and fix')
    commit('b09147c26f9', 'Re-index instead of partial source updates')
    snippet = wave10_code('src/Elasticsearch/Product/SourceDocument/SourceDocumentStorage.php', [(55,61)],
        [('Treat projected documents as IDs to rebuild', [57,58]), ('Rebuild search fields and source together', [59])])
    current.append(slide('source-partial-update', 'A partial source update can silently erase search fields', split(snippet,
        point('Observed failure', '516 of 4,140 products lost active, visibilities and parentId, leaving listings while get/mget still worked.')
        + point('Why', 'OpenSearch reconstructs an updated document from the stored _source. Unstored query fields disappear.')
        + point('Fix', 'Use ElasticsearchIndexer::updateIds() to rebuild the whole product.'), True),
        '<p>This exposes a broader risk with the product index’s filtered _source, not just one new rs_document field.</p><p>The repeated probe after a rebuild found zero of 4,140 missing active fields. A successful key-value get is not enough to test query correctness.</p>', cls='wave9'))

    doc('docs/48-source-limits-custom-fields.md', 'Mapping budget, size assumptions and measured versus estimated cells')
    snippet = wave10_code('src/Elasticsearch/Product/ElasticsearchProductDefinition.php', [(162,165)],
        [('Store the object without indexing its inner fields', [164])])
    current.append(slide('source-limits', 'One source field avoids mapping growth, not payload growth', split(snippet,
        point('Existing app mapping', '1,000 custom fields × 20 languages use 49,796 of Shopware’s 50,000 mapped fields. 5,000 × 5 exceeds the limit.')
        + point('Source layout', '100 fields × 5 languages: 0.96 GB measured. 5,000 × 20: 53.54 GB extrapolated from a 2k subset.')
        + point('Required changes', 'Select queryable fields, deduplicate fallback values and batch by bytes, not product count.'), True),
        '<p>Do not substitute OpenSearch’s default field limit for the 50,000 limit configured by this Shopware mapping.</p><p>Large cells are subset probes, assuming 10% fill and 45-character names. A 53.54 GB estimate is not a measured full-catalog index.</p><p>Valkey uses about 1.08–1.13 times the same JSON bytes. Switching stores does not shrink the document.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 42: returning writes routed to the replica')
    doc('docs/50-postgresql-production-setup.md', 'Guest-registration failure and primary-routing fix')
    commit('be901964bdb', 'Route number-range returning writes to the primary')
    snippet = wave10_code('src/Core/System/NumberRange/ValueGenerator/Pattern/IncrementStorage/IncrementSqlStorage.php', [(45,53)],
        [('Choose the primary before a write returning rows', [45,46]), ('fetchOne is executing a write, despite its read-shaped API', [49,50,51,52,53])])
    current.append(slide('replica-returning', 'A write returning rows must still choose the primary', split(snippet,
        point('Trigger', 'Guest registration reserves a number with INSERT … RETURNING through fetchOne().')
        + point('Failure', 'PrimaryReadReplicaConnection treated that API path as a replica read and PostgreSQL rejected the write.')
        + point('Fix', 'Ensure the primary explicitly before executing the statement.'), True),
        '<p>The read-only replica made a latent routing assumption visible. Database intent cannot be inferred from a helper name alone.</p><p>The fix is local to the number-range path; other writes through executeQuery/fetchOne deserve the same audit.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 47: MySQL SET evaluation order')
    doc('docs/49-postgresql-integration-suites.md', 'Stock portability fix')
    commit('0e25f43c691', 'Make stock and other core SQL portable')
    snippet = wave10_code('src/Core/Content/Product/Stock/StockStorage.php', [(56,60)],
        [('State both next values using the old row explicitly', [58])])
    current.append(slide('stock-assignment', 'Stock updates relied on MySQL assignment order', split(snippet,
        point('Before', 'stock = stock + delta, followed by available_stock = stock.')
        + point('Different meaning', 'MySQL reads the newly assigned stock. PostgreSQL evaluates the right-hand sides from the old row.')
        + point('Fix', 'Assign available_stock first and repeat stock + delta. Both engines now compute the same values.'), True),
        '<p>Repeating the expression without also ordering assignments carefully would be wrong on MySQL: it could add the delta twice.</p><p>This is a concrete semantics fix, rather than a quoting or SQL-syntax translation.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Finding 50: binary BlobField binding')
    doc('docs/49-postgresql-integration-suites.md', 'Binary payload regression and fix')
    commit('7036eb087c2', 'Bind BlobField payloads as binary')
    snippet = wave10_code('src/Core/Framework/DataAbstractionLayer/Dbal/EntityWriteGateway.php', [(501,511)],
        [('Resolve binary fields from the definition', [504,505]), ('Pass an explicit binary parameter type', [506])])
    current.append(slide('blob-binding', 'Blob payloads need a binary parameter type', split(snippet,
        point('Failure', 'Serialized PHP payloads contain backslashes. Text binding to PostgreSQL bytea can fail or alter the bytes.')
        + point('Fix', 'EntityWriteGateway supplies ParameterType::BINARY for BlobField inserts and updates.')
        + point('General lesson', 'An ID codec is not a substitute for typing every binary payload.'), True),
        '<p>The payload can be a serialized namespaced class. This is independent of UUID conversion.</p><p>The same commit also deduplicates colliding REPLACE rows; that behaviour is a separate portability concern.</p>', cls='wave9'))

    doc('docs/core-findings.md', 'Findings 43–45 and 48–49')
    doc('docs/49-postgresql-integration-suites.md', 'Integration fixes')
    doc('docs/50-postgresql-production-setup.md', 'Worker and shared-cache findings')
    current.append(slide('portability-followups', 'Other wave 10 fixes define behaviour explicitly', table(
        ['Area', 'Finding', 'Change or next step'],
        [['Message statistics', 'Grouped query sorts by a non-grouped created_at.', 'ORDER BY MAX(created_at).'],
         ['Shipping methods', 'No default sorting gives engine-dependent order.', 'Default to position, then name.'],
         ['OpenSearch indexing', 'GROUP BY p.id omits joined primary keys.', 'Group by every joined primary key.'],
         ['Sitemap worker', 'Hard-coded backtick alias differs from the iterator alias.', 'Join using the actual FROM alias.'],
         ['Shared prod cache', 'cache:clear deletes sibling prod_* cache directories.', 'Separate cache directories; scope cleanup by kernel prefix.']], True),
        '<p>The first four have PoC fixes. Cache cleanup remains a core robustness finding, with cache-directory isolation as the experiment workaround.</p><p>These are examples of core improvements valuable independently of PostgreSQL support.</p>', cls='wave9'))

    doc('docs/51-timing-reliability.md', '3d: confirmed immediate-invalidation cache defect')
    current.append(slide('wave9-cache-order', 'Synchronous projection still leaves a search-visibility gap', table(
        ['Mode after a write', 'Immediate stale API listing', 'Stale HTTP cache after 1.3s', 'Measured cost'],
        [['refresh=false + immediate invalidation', '9 / 10', '5 / 5', 'Default refresh interval: 1s'],
         ['Explicit refresh before invalidation', '0 / 10', '0 / 5', 'Refresh call median: 10.0 ms'],
         ['refresh=wait_for', '0 / 10', 'Not tested in HTTP-cache trial', 'Write median: 857 ms']], True)
        + '<div class="band warn">Invalidate after search visibility, or keep delayed invalidation longer than refresh_interval. Sync projection alone is insufficient.</div>'
        + '<p class="small">5k products · 1 shard · 1s refresh interval. Forced refresh is a probe mitigation, not a recommendation to flush segments on every high-volume write.</p>',
        '<p>Wave 9 described a hazard. Wave 10 reproduced stale HTTP cache entries even beyond the next search refresh.</p><p>The stale page mixed a fresh MySQL SEO URL with an old source-document name. Tests exercised real Storefront cache hits.</p><p>Post-refresh invalidation or a delay greater than refresh_interval is required; refresh=wait_for waits for search visibility and increases write latency. Its HTTP-cache trial was not run.</p>', cls='wave9'))

    doc('docs/51-timing-reliability.md', 'A/A noise, alternating paired rounds and confidence intervals')
    source('Paired timing runner', f'{DOC_URL}/blob/{DOC_SHA}/scripts/wave10-paired.py')
    current.append(slide('timing-method', 'The same binary defines the noise baseline', '<div class="cols">'
        + metric('10','alternating AB/BA rounds','Matched workloads and warm-ups')
        + metric('95%','paired bootstrap intervals','10,000 resamples of matched rounds')
        + metric('1 host','Apple M4 Pro / Podman VM','Absolute timings remain host-specific') + '</div>'
        + '<div class="band">A/A bounds: ±1.7% SQLite CLI, ±3.8% pinned MySQL CLI, ±5.7–8.2% unpinned DB CLI, ±9.7–11.8% HTTP storefront.</div>'
        + '<p class="small" style="margin-top:22px">The measurement supports a workload-specific interval, rather than one universal “10%” rule. Check target Linux/cloud hardware before setting release budgets.</p>',
        '<p>Pinning and lower concurrent host load both contributed to the narrower pinned MySQL interval; do not attribute the whole change to affinity alone.</p><p>Search under interleaved writes also degraded with PostgreSQL dead-tuple growth. Keep that condition separate from a clean read-only paired search run.</p>', cls='wave9'))

    doc('docs/49-postgresql-integration-suites.md', 'Suite totals and PG-only classification')
    current.append(slide('postgresql-suites', 'PostgreSQL-only failures fell from 386 to 90', table(
        ['Non-DAL suite', 'Tests', 'Remaining PG-only failures'],
        [['System, excluding CustomEntity', '458', '0'], ['Storefront', '777', '1'],
         ['Checkout', '1,992', '15'], ['Framework', '2,913', '24'], ['Content', '1,920', '42'],
         ['CustomEntity, within System', '12', '8']], True)
        + '<p class="small" style="margin-top:22px">8,072 tests on PostgreSQL; MariaDB reference failures are classified separately. This is progress toward support, not an all-green integration suite.</p>',
        '<p>The largest structural gap is runtime custom-entity DDL. Other remaining groups include test SQL, document generation, ordering and schema metadata.</p><p>The final PG run had 99 failing tests; 90 are PG-only after shared failures are excluded. Keep unique failing testcases distinct from teardown error totals.</p>', cls='wave9'))

    doc('docs/46-target-architecture.md', 'Updated roadmap')
    doc('docs/51-timing-reliability.md', 'Canonical conclusions and remaining limits')
    doc('docs/issues/E6-read-store/00-epic.md', 'Updated E6 draft, not filed')
    current.append(slide('wave9-gates', 'The remaining gates are production contracts', table(
        ['Gate', 'What wave 10 establishes', 'What remains'],
        [['Source hydration', 'O1a built, parity sampled, throughput and SQL savings measured.', 'Full re-index guard and complete fallback accounting.'],
         ['Visibility and size', 'Real HTTP-cache poisoning reproduced; large source documents probed.', 'Visibility-aware invalidation, selective mapping, deduplication and byte budgets.'],
         ['PostgreSQL support', 'Operational stack and broader suites exercised.', '90 classified PG-only failures, platform budgets and a business/support decision.']], True),
        '<p>Do not repeat the former “build O1a” next step. The implementation is now available for productization work.</p><p>E6 remains a draft, now backed by O1a evidence. E5 still depends on a PostgreSQL support decision.</p>', cls='wave9'))

    retained = [old['wave9-siblings'], old['wave9-route-sql'], old['wave9-generation'], old['wave9-counts']]
    doc('docs/47-o1a-source-hydration.md', 'Real route SQL accounting with O1a')
    retained[1] = slide('wave9-route-sql', 'Removing product SQL does not remove the whole route', table(
        ['Real Store API route · 5k products', 'O1 total SQL', 'O1a total SQL'],
        [['Detail, full', '30', '27'], ['Detail, skip configurator + CMS', '9', '7'],
         ['Listing', '12', '10'], ['Search', '11', '8']], True)
        + '<div class="band">Listing and search use source documents for all product-reader loads. Detail still falls back once for mainCategories; context, CMS, configurator and referenced entities add surrounding SQL.</div>',
        '<p>These are the O1a real-route counts from doc 47. They replace the standalone wave 9 route comparison in this position.</p><p>Do not substitute the CLI benchmark’s 2-to-0 listing statements for the complete route’s 12-to-10 total.</p>', cls='wave9')
    doc('docs/46-target-architecture.md', 'Architecture and verdicts')
    refs = [('O1a implementation', doc('docs/47-o1a-source-hydration.md'), 'Source reader, write-path fix and parity boundaries.'),
            ('Source limits', doc('docs/48-source-limits-custom-fields.md'), 'Field mapping, byte growth and extrapolation assumptions.'),
            ('PostgreSQL suites', doc('docs/49-postgresql-integration-suites.md'), 'Fixes and the remaining failure classification.'),
            ('Production-like setup', doc('docs/50-postgresql-production-setup.md'), 'Replica, TLS, worker and pooler checks.'),
            ('Canonical timing block', doc('docs/51-timing-reliability.md'), 'Current paired measurements and corrections.'),
            ('Findings register', doc('docs/core-findings.md'), 'All 50 findings and recorded issue mapping.')]
    reference_slide = slide('references', 'Source map · through wave 10', references(refs), '<p>New code uses the wave 10 milestone; earlier examples retain their original commits. External issue status has not been refreshed.</p>')
    earlier = previous[12:-1]
    earlier[-1]['notes'] += '<p>Wave 10 corrects the earlier 150k DAL v2 claim: with levers, reads improve materially while OpenSearch remains necessary for the measured catalog scale.</p>'
    return [old['findings'], old['map'], *current, *retained, *earlier, reference_slide]


def present_by_topic(arch: list[dict], core: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn milestone evidence into a story and a subsystem reference deck."""
    a = {s['slug']: s for s in arch}
    c = {s['slug']: s for s in core}

    def evidence(*items: dict) -> None:
        for item in items:
            for entry in item['sources']:
                source(entry['label'], entry['url'])

    def agenda(rows: list[tuple[str, str, str, str]]) -> str:
        return '<div class="agenda">' + ''.join(
            f'<a href="#{slug}"><span>{numbers}</span><div><h3>{title}</h3><p>{body}</p></div><b>↗</b></a>'
            for slug, numbers, title, body in rows) + '</div>'

    doc('docs/46-target-architecture.md', 'Architecture and conclusions')
    story = [slide('architecture', 'Scaling reads and strengthening the DAL',
        '<p class="lead">After the video: larger catalogs, PostgreSQL beyond the DAL, and core changes we can review independently.</p>'
        + agenda([('since-video', '02–07', 'Storefront reads at 150,000 products', 'The bottleneck, document hydration and its production constraints.'),
                  ('boundaries', '08–10', 'PostgreSQL without replacing the DAL', 'Database boundaries, operational evidence and remaining gaps.'),
                  ('dal-internals', '11–15', 'Core contracts and next decisions', 'DAL improvements, public events, measurement and the reading map.')])
        + '<p class="small review-context">Research snapshot: 25 November 2026 · about 20–25 minutes</p>',
        '<p>Assume the video is familiar. The next slide bridges from its small-catalog experiment to the new questions.</p><p>Use this agenda to choose a route. Press 1 to return here at any time.</p>', cls='cover architecture-intro arch')]

    doc('docs/38-read-store-plan.md', 'Why the larger catalog motivated a read model')
    doc('docs/47-o1a-source-hydration.md', 'Current search path versus source hydration')
    story.append(slide('since-video', 'The next questions after the video',
        '<p class="slide-intro">The video tested SQL at 5,000 products and argued for keeping the DAL. We then tested storefront reads at 150,000 products and PostgreSQL across the wider application.</p>'
        + table(['Question', 'What we tested'], [
            ['Larger catalogs', 'Can OpenSearch return product documents as well as search results?'],
            ['PostgreSQL scope', 'What breaks across 8,072 integration tests and a production-like stack?'],
            ['Useful core work', 'Which correctness fixes and DAL optimizations stand on their own?']], True)
        + '<div class="review-note"><strong>Two search paths:</strong> current OpenSearch returns IDs, then SQL loads products. Source hydration stores the product document in OpenSearch’s <code>_source</code> and reads it from the search hit.</div>',
        '<p>The research calls these paths O1 and O1a respectively. Those labels identify implementations, not separate search engines.</p><p>Hydration means turning stored data into the product entities expected by existing consumers.</p>', cls='arch bridge'))

    doc('docs/51-timing-reliability.md', 'Paired 150k mixed storefront comparisons')
    story.append(slide('catalog-scale', 'SQL tuning and OpenSearch at catalog scale',
        '<p class="slide-intro">Mixed storefront workload at 150,000 products, with 8 concurrent clients. Higher throughput is better.</p>'
        + table(['Read implementation', 'Requests / second', 'Comparison'], [
            ['DAL', '14.05', 'SQL baseline'],
            ['DAL v2, all options enabled', '17.45', '1.242× DAL · 95% CI [1.223, 1.285]'],
            ['Current OpenSearch + SQL products', '532.0', 'Existing search path'],
            ['OpenSearch source hydration', '756.1', '1.421× current search · 95% CI [1.318, 1.484]']], True)
        + '<div class="review-note">Source hydration delivers about 43× the throughput of the tuned SQL path in this workload. DAL v2 remains useful for SQL reads and writes.</div>',
        '<p>Two paired comparisons share the catalog and workload: DAL versus DAL v2, and current OpenSearch versus source hydration. The cross-family 43× value is descriptive, not its own paired interval.</p><p>DAL v2 options: count=window, agg=stats, write=key+upd, proj=1. The earlier large-catalog run omitted them; these are the corrected results.</p><p>Individual DAL v2 read latency ratios: detail 0.464 [0.410, 0.553], listing 0.583 [0.548, 0.641], filters 0.617 [0.595, 0.635], word search 0.804 [0.761, 0.832]. Multi-get is unresolved at 0.988 [0.880, 1.064].</p>', cls='arch scale'))

    hydration = a['query-hydration']
    hydration['title'] = 'Product hydration from OpenSearch documents'
    hydration['body'] = hydration['body'].replace('O1 · existing path', 'Current path · IDs then SQL').replace('O1a · implemented document path', 'Source hydration · same search query')
    hydration['body'] = hydration['body'].replace('Search hits also carry rs_document.', 'Search hits also carry the product document.').replace('Consume the hit buffer. _mget missing IDs.', 'Use hit documents. Fetch missing IDs in one document request.')
    hydration['notes'] += '<p>The document lives at _source.rs_document. A request-scoped buffer carries hit documents; _mget loads missing IDs. The feature flag is SHOPWARE_ES_SOURCE_DOCUMENT, disabled by default.</p>'
    story.append(hydration)

    evidence(a['document'], a['live-parts'])
    story.append(slide('live-parts', 'Stored product data and live entity behaviour', table(
        ['Concern', 'Source hydration behaviour'], [
            ['Product document', 'One document per product, with language and sales-channel context maps.'],
            ['Prices and purchase limits', 'Normal loaded events calculate display values after hydration.'],
            ['Stock and availability', 'Read from the projected document. Checkout validates against SQL.'],
            ['Search membership', 'Existing OpenSearch filters and ordering select the page before display calculations.']], True)
        + '<div class="review-note">Display calculation cannot repair a page selected from stale index data. Unsupported read shapes use a counted SQL fallback.</div>',
        a['live-parts']['notes'] + '<p>Builders resolve language fallback and inheritance. Custom fields and extensions use batched DocumentExtender hooks. The stored document schema has a version.</p>', cls='arch live-contract'))

    payoff = a['wave9-status']
    payoff['title'] = 'Measured payoff from source hydration'
    payoff['body'] = payoff['body'].replace('150k c=8 throughput versus O1', 'throughput versus current OpenSearch path').replace('This is an implemented PoC, not a supported release. Full re-indexing, post-refresh cache visibility and document/bulk size budgets are explicit requirements.', 'Paired latency: listing 10.88 to 7.19 ms (−34%); detail 7.64 to 3.37 ms (−56%). The prototype remains behind a feature flag.')
    payoff['notes'] += '<p>Listing latency ratio 0.661 [0.654, 0.785]; detail 0.440 [0.379, 0.491]; word search 24.66 to 22.02 ms, 0.893 [0.811, 0.996]. Warm CLI harness and 15-second mixed-load blocks on one host. This does not measure the entire HTTP route.</p>'
    story.append(payoff)

    evidence(a['projection-pipeline'], a['source-size'], c['wave9-cache-order'])
    story.append(slide('production-constraints', 'Three constraints before production',
        '<div class="review-decision"><span>01</span><div><h3>Rebuild the whole search document</h3><p>Partial updates erased unstored query fields. The adapter now re-indexes affected products.</p></div></div>'
        + '<div class="review-decision"><span>02</span><div><h3>Budget document and bulk-request bytes</h3><p>Large custom-field and language combinations inflate stored JSON, even when those fields are not indexed.</p></div></div>'
        + '<div class="review-decision"><span>03</span><div><h3>Invalidate HTTP cache after search visibility</h3><p>Synchronous projection alone still allowed stale listings to refill the HTTP cache.</p></div></div>'
        + '<div class="chapter-links"><a href="core-findings.html#source-partial-update">Indexing fix</a><a href="core-findings.html#source-limits">Size evidence</a><a href="core-findings.html#wave9-cache-order">Cache probe</a></div>',
        '<p>Partial updates caused 516 of 4,140 products to lose query fields; a rebuild fixed the probe.</p><p>Index size for 150k catalog rows: 0.42 GB at 0 custom fields / 1 language; 0.96 GB measured at 100 / 5. The 53.54 GB case at 5,000 / 20 extrapolates a 2k subset with 10% fill, 45-character names and no replicas. It is not a measured full build.</p><p>Immediate invalidation gave stale API listings in 9/10 trials and stale HTTP cache in 5/5 at +1.3 seconds. Explicit refresh before invalidation gave 0/10 and 0/5, with 10 ms median refresh cost. Flushing every write is not the proposed high-volume policy.</p>', cls='arch'))

    doc('docs/10-architecture.md', 'Database portability boundaries')
    doc('docs/20-currency-seo-codec.md', 'ID representation and numeric SQL operations')
    story.append(slide('boundaries', 'Database decisions stay at the SQL boundary',
        '<div class="path-lanes"><div class="path-row"><div><h3>DAL or SQL service</h3><p>Entity meaning and operation intent.</p></div><span>→</span><div class="connection-box"><h3>Dialect + ID binding</h3><p>Platform SQL, ID value and parameter type.</p></div><span>→</span><div><h3>DBAL connection</h3><p>Execute and decode results.</p></div></div></div>'
        + table(['Boundary', 'Responsibility'], [
            ['SqlDialect', 'Quote identifiers and generate JSON, numeric, upsert and aggregate operations.'],
            ['IdBinding', 'Keep application IDs as hex, bind binary IDs on MySQL and UUID text on PostgreSQL.'],
            ['Connection setup', 'Choose the driver and middleware. SQL generation uses the connection’s platform.']], True),
        '<p>The PoC uses static migration facades in places. Connection-scoped services would make multiple-connection behaviour explicit.</p><p>These boundaries serve portability. The separate newsletter storage-port experiment is an application design choice.</p>', cls='arch boundary-summary'))

    story.append(a['shim'])
    production = a['postgresql-stack']
    production['title'] = 'PostgreSQL beyond the DAL'
    production['body'] = production['body'].replace('Wave 10 result', 'Recorded evidence')
    production['notes'] += '<p>Uncached persistent-connection storefront comparisons put PostgreSQL around 1.13–1.30× MariaDB latency. Bulk writes remain a larger gap: 50-product sequential sync 506.5 versus 280.6 ms (1.805×, CI [1.681, 1.844]); at 4 concurrent clients, throughput 3.74 versus 10.89 req/s (0.344×, CI [0.283, 0.384]).</p><p>Remaining gaps include runtime CustomEntity DDL and text/collation semantics. The 200 measured walks had zero failures across two comparisons, not a production support guarantee.</p>'
    story.append(production)

    internals = a['dal-internals']
    internals['title'] = 'DAL improvements retain the public contracts'
    internals['body'] = internals['body'].replace('core-findings.html#3', 'core-findings.html#key-bug').replace('core-findings.html#5', 'core-findings.html#window').replace('core-findings.html#6', 'core-findings.html#projection')
    story.append(internals)

    evidence(a['storage-port'], a['events'])
    story.append(slide('storage-port', 'A small route experiment exposes the event boundary',
        '<p class="slide-intro">The newsletter route tests a separate idea: can a route depend on domain operations instead of a generic repository?</p>'
        + '<div class="path-lanes"><div class="path-row"><div><h3>Newsletter route</h3><p>Validate and coordinate the request.</p></div><span>→</span><div class="connection-box"><h3>Storage port</h3><p>Find, upsert, confirm and opt out.</p></div><span>→</span><div><h3>DAL adapter</h3><p>Keep writes, indexers and loaded entities.</p></div></div></div>'
        + '<div class="ownership" style="margin-top:35px"><h3>Public subscribers still expect an entity</h3><p>The route uses typed internal requests, then bridges back to NewsletterRecipientEntity with extension values for the public event.</p></div>'
        + '<div class="review-note">The opt-in SQL adapter skips DAL written events and indexers. It demonstrates a seam, with different behaviour.</div>',
        '<p>This slice is not required for PostgreSQL. It tests the cost and value of an application-level port.</p><p>Review fixed a bridge that originally dropped loaded extension data. A new internal DTO does not remove the public entity contract.</p>', cls='arch'))

    reliability = a['timing-reliability']
    reliability['title'] = 'Measurement and uncertainty'
    reliability['body'] = reliability['body'].replace('Use doc 51 for current headline timings. Earlier wave 8 and wave 9 numbers retain their original, narrower experimental context.', 'Paired runs alternate the two implementations. The same implementation tested against itself supplies the workload’s noise baseline.')
    story.append(reliability)

    decisions = a['decisions']
    decisions['title'] = 'Decisions for the next implementation'
    decisions['body'] = (
        '<div class="review-decision"><span>01</span><div><h3>Productize source hydration</h3><p>Require full re-indexing, visibility-aware cache invalidation, byte budgets and counted fallbacks.</p></div></div>'
        '<div class="review-decision"><span>02</span><div><h3>Review independent core fixes</h3><p>Key decoding, replica write routing, stock assignment, binary binding and batching semantics each have focused evidence.</p></div></div>'
        '<div class="review-decision"><span>03</span><div><h3>Set the PostgreSQL support scope</h3><p>Resolve the remaining 90 PostgreSQL-only failures, write budgets and platform coverage before a support decision.</p></div></div>')
    decisions['notes'] = '<p>These are proposals for review, not an approved backlog or a release commitment.</p><p>The read-store epic E6 remains a draft. The source-hydration prototype is built; the remaining work is production hardening. E5 remains conditional on PostgreSQL support scope.</p>'
    story.append(decisions)

    doc('docs/46-target-architecture.md', 'Consolidated architecture')
    doc('docs/51-timing-reliability.md', 'Canonical paired measurements and method')
    story.append(slide('references', 'Reading map by subsystem', references([
        ('OpenSearch hydration', 'core-findings.html#wave9-hydration', 'Reader decorator, indexing, cache visibility and lifecycle safety.'),
        ('DAL reads and writes', 'core-findings.html#key-bug', 'Prefetch keys, totals, projections and safe batching.'),
        ('PostgreSQL and core semantics', 'core-findings.html#replica-returning', 'Replica routing, stock, binary payloads and remaining suites.'),
        ('Architecture research', doc('docs/46-target-architecture.md'), 'Design boundaries and production conditions.'),
        ('Measurement research', doc('docs/51-timing-reliability.md'), 'Paired comparisons, confidence intervals and recorded limitations.'),
        ('Deck launcher', 'index.html', 'Choose the story or the code reference.')]),
        '<p>Every slide has its own S Sources drawer. Code and documentary links are pinned to the recorded research snapshots.</p><p>The engineering deck is a reference: choose a subsystem rather than reading every code example live.</p>', cls='arch'))

    # The engineering deck follows subsystem dependencies, never research dates.
    evidence(c['findings'], c['map'])
    cover = slide('findings', 'Code and core findings',
        '<p class="lead">Product documents in OpenSearch reduce SQL hydration. The code walkthrough then covers DAL improvements and cross-database correctness.</p>'
        + agenda([('wave9-hydration', '02–08', 'OpenSearch and read-model correctness', 'Reader composition, route SQL, indexing, cache visibility and safe rebuilds.'),
                  ('key-bug', '09–16', 'DAL performance and write semantics', 'Prefetch keys, totals, partial reads, batching and the write profile.'),
                  ('replica-returning', '17–25', 'PostgreSQL and cross-engine bugs', 'Primary routing, stock, binary types, locks and the remaining support gaps.')])
        + '<p class="small review-context">25 November 2026 · choose a chapter · H highlights code · S opens sources</p>',
        '<p>The architecture deck carries the motivation, full cross-family benchmarks and measurement method. This deck opens the implementation and its failure cases.</p><p>Follow the three chapters in order or select the relevant subsystem. The final slide proposes core work beyond the original DAL backlog.</p>', cls='cover architecture-intro arch')

    reader = c['wave9-hydration']
    reader['title'] = 'A reader decorator consumes product documents'
    reader['notes'] += '<p>OpenSearch returns the selected product document in _source.rs_document. The decorator consumes a request-scoped hit buffer, uses _mget to fetch missing IDs in bulk and falls back to the inner SQL reader when necessary.</p><p>Storage::get/mget return documents; store/remove modify them. SourceDocumentStorage delegates rebuild and lifecycle to es:index; setup/swap/clear/destroy are no-ops.</p>'
    route = c['wave9-route-sql']
    route['body'] = route['body'].replace('O1 total SQL', 'Current search + SQL').replace('O1a total SQL', 'Source hydration')
    route['notes'] = '<p>Real-route SQL accounting at 5k products: these totals include surrounding context, CMS, configurator and referenced-entity reads.</p><p>The warm CLI benchmark’s listing product-reader statements fall 2 to 0; the complete route still falls only 12 to 10. Detail has one breadcrumb association fallback.</p>'
    c['source-limits']['title'] = 'Source storage avoids inner mapping growth'

    evidence(c['wave9-siblings'], c['wave9-counts'])
    snippet = read_code('Projector/ReadStoreProjectorSubscriber.php', [(60,61),(64,73)],
        [('Expand parents to their affected children', [64,65,66,69]), ('Schedule the full affected set', [73])])
    siblings = slide('wave9-siblings', 'Affected products and aggregate counts need distinct IDs', split(snippet,
        point('Projection footprint', 'A variant event can omit siblings whose derived prices changed. Expand the parent’s children before scheduling.')
        + point('Count evidence', 'A keyword manufacturer bucket returned 73 versus 71 distinct products in the 5k probe.')
        + point('Review direction', 'Define the complete affected-ID set and count each product once per bucket.'), True),
        c['wave9-siblings']['notes'] + '<p>The aggregation SQL was not captured. Duplicate keyword matches support the distinct-product explanation, but a missing DISTINCT remains an inference. The count fix is a draft proposal.</p>')
    generation = c['wave9-generation']
    generation['body'] = generation['body'].replace('Observed failure', 'Standalone-store prototype').replace('One of 5,226 concurrent MongoDB requests failed', 'Alternative stores (SQL, Valkey, OpenSearch and MongoDB) tested the same document contract. One of 5,226 MongoDB requests failed')
    generation['notes'] += '<p>This is a sibling prototype, not the source-hydration adapter used by the existing OpenSearch path. Only the standalone generation stores publish pointers; source hydration retains the normal es:index lifecycle.</p>'

    key = c['key-bug']
    key['body'] = key['body'].replace('A cache miss adds a SELECT.', 'A cache miss adds a SELECT. In the isolated MySQL 50-product create/update probe, statements fell from 371 to 121 after the fix.')
    evidence(c['key-evidence'])
    key['sources'] += list(SOURCES); SOURCES.clear()
    key['notes'] += c['key-evidence']['notes']
    c['window']['notes'] = '<p>Trace the eligibility check, total extraction and empty-page fallback. Use the returned total only when a page contains a row.</p><p>The optimization excludes score-field queries and requires a limit and exact-total mode. Gains depend on the query shape.</p>'

    projection = c['projection']
    projection['title'] = 'Partial reads need the inherited parent context'
    projection['body'] = projection['body'].replace('MySQL listing: 12.42 to 3.78 ms with all selected levers and projection, in doc 34.', 'Paired MySQL listing at 5k: 10.82 to 4.77 ms. Ratio 0.441×, 95% CI [0.411, 0.520]. All options + projection; the gain is not isolated to projection.')
    projection['body'] = projection['body'].replace('This implementation still hydrates partial entities before creating DTOs.', 'Inherited prices need parentId. [id, prices] can return empty; including parentId matches the full read. The proposed core fix selects it implicitly.')
    projection['notes'] = '<p>DTO paths become Criteria fields, then the existing DAL hydrates partial entities before constructing DTOs.</p><p>The paired result supersedes the earlier 12.42-to-3.78 ms timing. It measures the combined configuration, not projection alone.</p><p>The inherited to-many bug is a reproducer with a workaround and proposed core fix. It is not already fixed upstream. Criteria mutation and cached reflection metadata are separate API review points.</p>'
    evidence(c['inheritance'])
    doc('docs/51-timing-reliability.md', 'Paired 5k listing comparison')
    projection['sources'] += list(SOURCES); SOURCES.clear()

    c['batching']['notes'] = '<p>The schematic SQL omits composite keys, varying columns and chunks of up to 100. Preserve command order and group only compatible consecutive updates.</p><p>Qualifying CASE column references fixed an ambiguity in the experimental SQL translator. This is not a general PostgreSQL cast requirement.</p><p>The final-code rerun is on the batching-test slide, after the uniqueness and failure rules.</p>'
    c['profile']['body'] = c['profile']['body'].replace('MySQL DAL v2 S4 profile', 'MySQL DAL v2 · 50-product create + update')
    c['locks']['body'] = c['locks']['body'].replace('from 45 deadlocks to 0', 'from 31 deadlocks to 0')
    c['locks']['notes'] = '<p>The recorded list-as-built run moved from 31 deadlocks to zero, with median throughput 1.59 to 3.09 requests/second. The informal 45-deadlock observation was not recorded.</p><p>The excerpt follows a PostgreSQL platform guard. A separate sequential bulk-write profile records roughly 40 ms additional lock cost; that is not the same measurement block as the concurrent deadlock table.</p><p>Indexer lock ordering and DAL gateway batching address different correctness requirements.</p>'

    followups = c['portability-followups']
    followups['title'] = 'Other core fixes make behaviour explicit'
    followups['body'] = followups['body'].replace('Other wave 10', 'Other core')
    followups['notes'] += c['smaller']['notes'] + '<p>Additional independent candidates: fetchOne() !== false instead of SELECT rowCount(); explicit strict GROUP BY; ROW_NUMBER() OVER(PARTITION BY ...) for to-many limits; defined duplicate-key upsert semantics. Their recorded issue links are in Sources.</p>'
    evidence(c['smaller'])
    followups['sources'] += list(SOURCES); SOURCES.clear()

    evidence(c['priorities'], c['wave9-gates'], c['references'])
    doc('docs/35-orm-spike-fair-write.md', 'Post-review batching rerun')
    priorities = slide('priorities', 'Core work to review next',
        '<div class="decision"><div class="n">01</div><div><h3>Isolated correctness fixes</h3><p>Prefetch keys, replica RETURNING writes, stock assignment order, binary binding and inherited partial reads.</p></div></div>'
        + '<div class="decision"><div class="n">02</div><div><h3>Measured DAL changes and source hydration</h3><p>Review totals and safe batching. Harden the built hydration path with indexing, cache and byte-budget contracts.</p></div></div>'
        + '<div class="decision"><div class="n">03</div><div><h3>Explicit PostgreSQL support scope</h3><p>Resolve 90 PostgreSQL-only failures and write-performance gaps. Agree on collation, migration and extension guarantees.</p></div></div>'
        + '<div class="chapter-links"><a href="architecture.html#references">Architecture and research map</a><a href="#findings">Chapter overview</a></div>',
        '<p>This is a proposed review sequence, not an approved backlog. The read-store epic E6 remains a draft, with source hydration already implemented. E5 still needs a support decision.</p><p>The Sources drawer links the findings register, issue map, implementation, timing method and batching rerun. Check live upstream work before preparing changes.</p>')

    engineering = [cover, reader, route, c['source-partial-update'], c['source-limits'], c['wave9-cache-order'], siblings, generation,
        key, c['window'], projection, c['batching'], c['unique'], c['failure'], c['batch-tests'], c['profile'],
        c['replica-returning'], c['stock-assignment'], c['blob-binding'], c['locks'], c['semantics'], c['cache'], followups, c['postgresql-suites'], priorities]
    for item in engineering:
        if item is not cover:
            item['class'] = 'engineering'
    # Preserve named links shared from earlier drafts, even when two slides merged.
    aliases = {
        'architecture': {'read-write':'query-hydration', 'document':'live-parts', 'source-size':'production-constraints', 'projection-pipeline':'production-constraints', 'read-path':'boundaries', 'dialect':'boundaries', 'id-binding':'boundaries', 'connection':'boundaries', 'events':'storage-port', 'projections':'dal-internals'},
        'core': {'map':'findings', 'key-evidence':'key-bug', 'inheritance':'projection', 'wave9-counts':'wave9-siblings', 'smaller':'portability-followups', 'wave9-gates':'priorities', 'references':'priorities', 'timing-method':'architecture.html#timing-reliability', 'wave9-results':'architecture.html#wave9-status', 'wave9-scale':'architecture.html#catalog-scale'}}
    for name, slides in [('architecture', story), ('core', engineering)]:
        for item in slides:
            item['sources'] = list({entry['url']: entry for entry in item['sources']}.values())
            item['aliases'] = [key for key, value in aliases[name].items() if value == item['slug']]
    return story, engineering


def render(name: str, title: str, slides: list[dict]) -> None:
    css=(HERE/'deck.css').read_text()
    js=(HERE/'deck.js').read_text()
    content=[]
    for i,s in enumerate(slides):
        heading='h1' if 'cover' in s['class'] else 'h2'
        citation=f'<div class="citation">{s["citation"]}</div>' if s['citation'] else ''
        content.append(f'<section class="slide {s["class"]}" data-slug="{esc(s["slug"])}" data-aliases="{esc(json.dumps(s.get("aliases", [])))}" data-sources="{esc(json.dumps(s["sources"]))}" aria-labelledby="title-{i+1}"><div class="eyebrow">{esc(title)} / {i+1:02}</div><{heading} id="title-{i+1}">{s["title"]}</{heading}><div class="content">{s["body"]}</div>{citation}<template class="speaker-notes">{s["notes"]}</template></section>')
    footer=f'<nav class="footer" aria-label="Presentation controls"><a class="deck-name" href="index.html" aria-label="Back to deck launcher">⌂ Decks</a><button class="start-button go-start" aria-label="Go to slide 1">1 · Start</button><button class="overview-button" aria-label="Open slide picker">O · Slides</button><span class="footer-spacer">{esc(title)}</span><button class="notes-button" aria-expanded="false">N · notes</button><button class="sources-button" aria-expanded="false">S · sources</button><button class="fullscreen-button">F · fullscreen</button><button class="help-button" aria-label="Keyboard shortcuts">? help</button><button class="prev" aria-label="Previous slide">←</button><button class="counter" aria-label="Current slide, open slide picker"></button><button class="next" aria-label="Next slide">→</button><div class="progress"></div></nav>'
    panels='''<aside class="panel" aria-label="Slide notes and sources"><button class="close" aria-label="Close sidebar">×</button><div class="panel-mode tiny">SPEAKER NOTES</div><p><span class="timer">00:00</span><button class="reset">reset timer</button></p><h2 class="panel-title"></h2><div class="panel-content"></div></aside>
<div class="overlay overview" role="dialog" aria-modal="true" aria-label="Slide overview"><div class="overview-heading"><h2>Slide picker</h2><button class="go-start">Go to slide 1 · 1</button><a href="index.html">Back to decks</a></div><button class="close">Close · Esc</button><div class="overview-grid"></div></div>
<div class="overlay help" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"><button class="close">Close · Esc</button><div class="help-content"><h2>Present at your own pace</h2><p><kbd>→</kbd> <kbd>Space</kbd> next slide &nbsp; <kbd>←</kbd> previous slide</p><p><kbd>H</kbd> cycle code highlights. Click the bar below a snippet to focus that snippet alone.</p><p><kbd>N</kbd> speaker notes and timer &nbsp; <kbd>S</kbd> source links</p><p><kbd>O</kbd> slide picker &nbsp; <kbd>F</kbd> fullscreen &nbsp; <kbd>?</kbd> this help</p><p><kbd>1</kbd> back to slide 1 &nbsp; <kbd>Home</kbd> first slide &nbsp; <kbd>End</kbd> last slide &nbsp; <kbd>Esc</kbd> close panel</p><p>The URL hash links to a slide. Printing includes every slide, with all code visible. The deck works offline. Source links need a connection and may need GitHub access.</p><p>Speaker notes appear in this window and are visible during screen sharing. Keep them closed when sharing the whole window.</p></div></div><div class="sr-only announcer" aria-live="polite"></div>'''
    redirects = {'timing-method':'architecture.html#timing-reliability','wave9-results':'architecture.html#wave9-status','wave9-scale':'architecture.html#catalog-scale'} if name == 'core-findings.html' else {}
    page=f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{esc(title)}</title><style>{css}</style></head><body data-title="{esc(title)}" data-redirects="{esc(json.dumps(redirects))}"><main class="stage">{"".join(content)}{footer}</main>{panels}<script>{js}</script></body></html>\n'
    (HERE/name).write_text(page)
    print(f'{name}: {len(slides)} slides, {len(page):,} characters')


if __name__=='__main__':
    arch,core=present_by_topic(architecture_wave10(),findings_wave10())
    render('architecture.html','Architecture',arch)
    render('core-findings.html','Core findings',core)
    used = '\n'.join(s['body'] for s in arch+core)
    snippets = {json.dumps(s,sort_keys=True):s for s in SNIPPETS if f'/blob/{s["commit"]}/{s["path"]}#L{s["ranges"][0][0]}-L{s["ranges"][-1][1]}' in used}
    (HERE/'sources.json').write_text(json.dumps({'core_commit':CORE_SHA,'batch_commit':BATCH_SHA,'read_store_commit':READ_STORE_SHA,'wave10_commit':WAVE10_SHA,'research_commit':DOC_SHA,'snippets':list(snippets.values()),'decks':{'architecture.html':[{'slug':s['slug'],'aliases':s.get('aliases',[]),'title':' '.join(html.unescape(re.sub('<[^>]+>',' ',s['title'])).split()),'sources':s['sources']} for s in arch],'core-findings.html':[{'slug':s['slug'],'aliases':s.get('aliases',[]),'title':' '.join(html.unescape(re.sub('<[^>]+>',' ',s['title'])).split()),'sources':s['sources']} for s in core]}},indent=2)+'\n')
