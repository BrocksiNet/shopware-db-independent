#!/usr/bin/env python3
"""File the issue drafts of docs/issues/E1..E4 on shopware/shopware.

Usage: scripts/file-issues.py [--dry-run] [--only E1,E2]

Pass 1 creates every issue that has no `upstream` URL yet (type, labels, body above the
research notes) and writes the URL back into the draft. Pass 2 replaces draft ids
(E1, E1.04) in the bodies with issue references, links sub-issues to their parent and
removes `needs-triage`. Re-running is safe: filed drafts are not created again.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "shopware/shopware"
LABELS = ["component/core", "domain/framework"]
DROP_LABELS = ["needs-triage"]
ROOT = Path(__file__).resolve().parent.parent / "docs" / "issues"
NOTES = "## Research notes (not for upstream)"

dry = "--dry-run" in sys.argv
only = None
if "--only" in sys.argv:
    only = set(sys.argv[sys.argv.index("--only") + 1].split(","))


def gh(*args, data=None):
    cmd = ["gh", "api", *args]
    if data is not None:
        cmd += ["--input", "-"]
    out = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"gh api {' '.join(args)} failed: {out.stderr.strip()}")
    return json.loads(out.stdout) if out.stdout.strip() else None


def parse(path):
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"')
    body = m.group(2).split(NOTES)[0].strip() + "\n"
    return meta, body, text


def set_meta(path, key, value):
    text = path.read_text()
    text = re.sub(rf"^{key}:.*$", f'{key}: {value}', text, count=1, flags=re.M)
    path.write_text(text)


drafts = []
for f in sorted(ROOT.glob("E[1-4]-*/*.md")):
    meta, body, _ = parse(f)
    if only and meta["id"].split(".")[0] not in only:
        continue
    drafts.append((f, meta, body))

stale = [m["id"] for _, m, _ in drafts if m.get("status") == "stale"]
if stale:
    raise SystemExit(f"stale drafts must be resolved first: {stale}")

# Pass 1: create
urls = {}
for f, meta, body in drafts:
    if meta.get("upstream"):
        urls[meta["id"]] = meta["upstream"]
        continue
    payload = {"title": meta["title"], "body": body, "type": meta["type"], "labels": LABELS}
    if dry:
        print(f"[dry] create {meta['id']:6} {meta['type']:11} {meta['title']} ({len(body)} chars)")
        urls[meta["id"]] = f"https://github.com/{REPO}/issues/{meta['id']}"
        continue
    issue = gh(f"repos/{REPO}/issues", "-X", "POST", data=payload)
    urls[meta["id"]] = issue["html_url"]
    set_meta(f, "upstream", f'"{issue["html_url"]}"')
    set_meta(f, "status", "filed")
    print(f"created {meta['id']:6} {issue['html_url']}")

num = {k: v.rsplit("/", 1)[1] for k, v in urls.items()}


def link_ids(body):
    # longest ids first so E1.04 is not read as E1
    def repl(m):
        key = m.group(0)
        return f"#{num[key]}" if key in num else key
    return re.sub(r"\bE[1-5](?:\.\d\d)?\b", repl, body)


# Pass 2: references, sub-issues, labels
for f, meta, body in drafts:
    n = num[meta["id"]]
    new_body = link_ids(body)
    if dry:
        left = sorted(set(re.findall(r"\bE[1-5](?:\.\d\d)?\b", new_body)))
        print(f"[dry] {meta['id']:6} parent={meta.get('parent') or '-'} unresolved ids: {left}")
        continue
    gh(f"repos/{REPO}/issues/{n}", "-X", "PATCH", data={"body": new_body})
    for label in DROP_LABELS:
        subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{REPO}/issues/{n}/labels/{label}"],
                       capture_output=True)
    parent = meta.get("parent")
    if parent:
        child_id = gh(f"repos/{REPO}/issues/{n}")["id"]
        existing = gh(f"repos/{REPO}/issues/{num[parent]}/sub_issues", "--paginate") or []
        if child_id not in [s["id"] for s in existing]:
            gh(f"repos/{REPO}/issues/{num[parent]}/sub_issues", "-X", "POST",
               data={"sub_issue_id": child_id})
    print(f"linked {meta['id']:6} #{n}")
