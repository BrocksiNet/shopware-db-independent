#!/usr/bin/env python3
"""Group PHPUnit junit failures/errors by normalised message.

Usage: group-phpunit-failures.py junit.xml [--examples N] [--json out.json]
"""
import argparse
import collections
import json
import re
import xml.etree.ElementTree as ET


def normalise(text):
    first = text.strip().split("\n")
    if len(first) > 1 and "::" in first[0]:
        first = first[1:]  # PHPUnit prints the test id first
    # keep SQLSTATE and the first meaningful line
    msg = " ".join(first[:2])
    state = re.search(r"SQLSTATE\[(\w+)\]", text)
    msg = re.sub(r"[0-9a-f]{32}", "<id>", msg)
    msg = re.sub(r"\\x[0-9a-fA-F]{2}", "", msg)
    msg = re.sub(r"'[^']{0,200}'", "'?'", msg)
    msg = re.sub(r"\b\d+\b", "N", msg)
    msg = re.sub(r"\s+", " ", msg)
    return (state.group(1) if state else "-", msg[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("junit")
    ap.add_argument("--examples", type=int, default=2)
    ap.add_argument("--json")
    a = ap.parse_args()
    groups = collections.defaultdict(list)
    for tc in ET.parse(a.junit).iter("testcase"):
        for kind in ("error", "failure"):
            for el in tc.findall(kind):
                key = normalise(el.text or el.get("type") or "")
                groups[key].append(f"{tc.get('class') or tc.get('classname')}::{tc.get('name')}")
    rows = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(v) for v in groups.values())
    print(f"total {total}, groups {len(rows)}")
    for (state, msg), tests in rows:
        print(f"{len(tests):4d} {state:6s} {msg}")
        for t in tests[: a.examples]:
            print(f"        {t}")
    if a.json:
        json.dump([{"sqlstate": s, "message": m, "count": len(t), "tests": t} for (s, m), t in rows], open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
