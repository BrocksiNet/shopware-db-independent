#!/usr/bin/env python3
"""Paired, interleaved (AB / BA) benchmark runner and bootstrap CI calculator (wave 10 D).

Method (docs/51-timing-reliability.md):
- Runs variant A and variant B in R paired rounds (default R=10).
- Alternates order across rounds (AB, BA, AB, BA, ...) to cancel monotonic drift
  (thermal ramp, background load trend, cache warming).
- Each round produces one summary number per metric (typically the median of that
  round's iterations, or throughput of a load window).
- Computes:
    * median(A), median(B), min..max of round values
    * ratio = median(B) / median(A) and median of paired ratios (B_i / A_i)
    * 95 % bootstrap confidence interval of the paired ratio (default 10,000 resamples
      of paired rounds, deterministic seed=42)
    * A/A noise summary: max |1 - CI bound| as percentage spread
- Saves every raw round as JSONL (--out) so numbers can be re-analyzed with --analyze.

Modes:
1. Run commands:
   scripts/wave10-paired.py run \\
     --label-a O1 --cmd-a '...' \\
     --label-b O1a --cmd-b '...' \\
     --parser orm-spike \\
     --rounds 10 --out /tmp/w10d/o1-vs-o1a.jsonl

2. Analyze an existing JSONL file:
   scripts/wave10-paired.py analyze /tmp/w10d/o1-vs-o1a.jsonl

Parsers (--parser):
- float:       last float on stdout -> {"value": float}
- json-kv:     JSON object on last non-empty stdout line, numeric values -> metrics
- orm-spike:   parses `orm-spike:bench` output (scenario median ms and statements)
- read-store:  parses `read-store:load` output (throughput, p50, p95, R1/R2/R3b p50,
               statements/req, optional "write database CPU: X s")
- walk-e:      parses `/tmp/wave10-e/walk.py` JSON (step ms + total ms)
- regex:       --pattern 'NAME=REGEX' (repeatable), first capture group as float
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import time
from typing import Any


def host_load() -> list[float]:
    return [round(x, 2) for x in os.getloadavg()]


def parse_orm_spike(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        # BenchCommand SymfonyStyle::table row: "  S1   ok   12.42   15.10   4   41.0"
        m = re.match(
            r"^\s*\|?\s*(S[1-5]|R3b|R4)\s+\|?\s*ok\s+\|?\s*([0-9]+(?:\.[0-9]+)?)\s+\|?\s*([0-9]+(?:\.[0-9]+)?)\s+\|?\s*([0-9]+)",
            line,
        )
        if m:
            sc = m.group(1)
            metrics[f"{sc}_p50_ms"] = float(m.group(2))
            metrics[f"{sc}_p95_ms"] = float(m.group(3))
            metrics[f"{sc}_stmts"] = float(m.group(4))
            continue
    # Also support JSON output if the command cats the result json file
    stripped = text.strip()
    if not metrics and stripped.startswith("{"):
        data = json.loads(stripped)
        scenarios = data.get("scenarios", data)
        if isinstance(scenarios, dict):
            for sc, vals in scenarios.items():
                if isinstance(vals, dict) and vals.get("status") == "ok" and "medianMs" in vals:
                    label = "R3b" if sc == "R3B" else sc
                    metrics[f"{label}_p50_ms"] = float(vals["medianMs"])
                    if "p95Ms" in vals:
                        metrics[f"{label}_p95_ms"] = float(vals["p95Ms"])
                    if "statementsMedian" in vals:
                        metrics[f"{label}_stmts"] = float(vals["statementsMedian"])
    if not metrics:
        raise ValueError(f"orm-spike parser found no metrics in output:\n{text[-500:]}")
    return metrics


def parse_read_store_load(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    m = re.search(
        r"R5\s+\S+\s+c=(\d+)\s+duration=([0-9.]+)s\s+requests=(\d+)\s+throughput=([0-9.]+)/s\s+p50=([0-9.]+)ms\s+p95=([0-9.]+)ms\s+errors=(\d+)\s+statements=(\d+)\s+\(([0-9.]+)\s+per request\)",
        text,
    )
    if not m:
        raise ValueError(f"read-store parser found no R5 summary in output:\n{text[-500:]}")
    metrics["throughput_rps"] = float(m.group(4))
    metrics["p50_ms"] = float(m.group(5))
    metrics["p95_ms"] = float(m.group(6))
    metrics["errors"] = float(m.group(7))
    metrics["stmts_per_req"] = float(m.group(9))
    for sc in ("R1", "R2", "R3b"):
        ms = re.search(rf"\b{sc}\s+n=\d+\s+p50=([0-9.]+)ms\s+p95=([0-9.]+)ms", text)
        if ms:
            metrics[f"{sc}_p50_ms"] = float(ms.group(1))
            metrics[f"{sc}_p95_ms"] = float(ms.group(2))
    mcpu = re.search(r"write database CPU:\s*([0-9.]+)\s*s", text)
    if mcpu:
        metrics["db_cpu_s"] = float(mcpu.group(1))
    return metrics


def parse_walk_e(text: str) -> dict[str, float]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    data = json.loads(lines[-1])
    if "steps" in data:
        steps = data["steps"]
        metrics = {f"step_{k}_ms": float(v[1]) for k, v in steps.items()}
        tot = sum(
            float(v[1])
            for k, v in steps.items()
            if k != "confirm" or steps.get("register_guest") != v
        )
        metrics["total_ms"] = tot
        metrics["ok"] = 1.0 if (data.get("orderNumber") and all(v[0] < 400 for v in steps.values())) else 0.0
        return metrics
    if "median_p95_ms" in data:
        metrics = {f"{k}_p50_ms": float(v[0]) for k, v in data["median_p95_ms"].items()}
        metrics["fails"] = float(data.get("fails", 0))
        return metrics
    raise ValueError(f"walk-e parser did not recognize JSON:\n{lines[-1]}")


def parse_output(parser: str, text: str, patterns: list[str]) -> dict[str, float]:
    if parser == "float":
        nums = re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", text)
        if not nums:
            raise ValueError(f"No float found in output:\n{text[-300:]}")
        return {"value": float(nums[-1])}
    if parser == "json-kv":
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        obj = json.loads(lines[-1])
        return {k: float(v) for k, v in obj.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if parser == "orm-spike":
        return parse_orm_spike(text)
    if parser == "read-store":
        return parse_read_store_load(text)
    if parser == "walk-e":
        return parse_walk_e(text)
    if parser == "regex":
        metrics: dict[str, float] = {}
        for spec in patterns:
            name, pat = spec.split("=", 1)
            m = re.search(pat, text, re.MULTILINE)
            if not m:
                raise ValueError(f"Pattern {name!r} ({pat}) did not match:\n{text[-400:]}")
            metrics[name] = float(m.group(1))
        return metrics
    raise ValueError(f"Unknown parser: {parser}")


def run_one(cmd: str) -> tuple[int, str, float]:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    dt = time.monotonic() - t0
    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out, dt


def bootstrap_paired_ratio(
    a_vals: list[float],
    b_vals: list[float],
    resamples: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    n = len(a_vals)
    assert n == len(b_vals) and n > 0
    med_a = statistics.median(a_vals)
    med_b = statistics.median(b_vals)
    ratio_of_medians = med_b / med_a if med_a != 0 else math.nan

    paired_ratios = [b / a for a, b in zip(a_vals, b_vals) if a != 0]
    med_paired_ratio = statistics.median(paired_ratios) if paired_ratios else math.nan

    rng = random.Random(seed)
    boot_ratio_meds: list[float] = []
    boot_med_ratios: list[float] = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        sa = [a_vals[i] for i in idx]
        sb = [b_vals[i] for i in idx]
        ma = statistics.median(sa)
        mb = statistics.median(sb)
        if ma != 0:
            boot_ratio_meds.append(mb / ma)
        pr = [sb[j] / sa[j] for j in range(n) if sa[j] != 0]
        if pr:
            boot_med_ratios.append(statistics.median(pr))

    def ci95(xs: list[float]) -> tuple[float, float]:
        if not xs:
            return (math.nan, math.nan)
        xs.sort()
        lo = xs[int(0.025 * (len(xs) - 1))]
        hi = xs[int(0.975 * (len(xs) - 1))]
        return (lo, hi)

    ci_rm = ci95(boot_ratio_meds)
    ci_mr = ci95(boot_med_ratios)
    spread_pct = (
        max(abs(ci_rm[0] - 1.0), abs(ci_rm[1] - 1.0)) * 100.0
        if not (math.isnan(ci_rm[0]) or math.isnan(ci_rm[1]))
        else math.nan
    )
    cv_a = (statistics.stdev(a_vals) / statistics.mean(a_vals) * 100.0) if (n > 1 and statistics.mean(a_vals) != 0) else 0.0
    cv_b = (statistics.stdev(b_vals) / statistics.mean(b_vals) * 100.0) if (n > 1 and statistics.mean(b_vals) != 0) else 0.0

    return {
        "n": n,
        "a_median": med_a,
        "a_min": min(a_vals),
        "a_max": max(a_vals),
        "a_cv_pct": cv_a,
        "b_median": med_b,
        "b_min": min(b_vals),
        "b_max": max(b_vals),
        "b_cv_pct": cv_b,
        "ratio": ratio_of_medians,
        "ratio_ci95": [ci_rm[0], ci_rm[1]],
        "paired_ratio_median": med_paired_ratio,
        "paired_ratio_ci95": [ci_mr[0], ci_mr[1]],
        "aa_max_dev_pct": spread_pct,
    }


def summarize_records(records: list[dict[str, Any]], resamples: int = 10000, seed: int = 42) -> dict[str, Any]:
    meta = next((r for r in records if r.get("type") == "meta"), {})
    rounds = [r for r in records if r.get("type") == "round"]
    if not rounds:
        raise ValueError("No round records found")
    label_a = meta.get("label_a", "A")
    label_b = meta.get("label_b", "B")
    metric_names = sorted(set(rounds[0]["a"].keys()) & set(rounds[0]["b"].keys()))
    stats: dict[str, Any] = {}
    for m in metric_names:
        a_vals = [float(r["a"][m]) for r in rounds if m in r["a"] and m in r["b"]]
        b_vals = [float(r["b"][m]) for r in rounds if m in r["a"] and m in r["b"]]
        stats[m] = bootstrap_paired_ratio(a_vals, b_vals, resamples=resamples, seed=seed)
    return {
        "label_a": label_a,
        "label_b": label_b,
        "rounds": len(rounds),
        "resamples": resamples,
        "seed": seed,
        "metrics": stats,
    }


def print_table(summary: dict[str, Any]) -> None:
    la, lb = summary["label_a"], summary["label_b"]
    print(f"\nPaired AB/BA summary: {lb} / {la} ({summary['rounds']} rounds, bootstrap B={summary['resamples']})\n")
    print(f"| Metric | {la} median (min..max) | {lb} median (min..max) | Ratio {lb}/{la} | 95% CI (ratio of med) | 95% CI (med of ratios) |")
    print("|---|---|---|---|---|---|")
    for m, s in summary["metrics"].items():
        r = s["ratio"]
        lo, hi = s["ratio_ci95"]
        plo, phi = s["paired_ratio_ci95"]
        print(
            f"| `{m}` | {s['a_median']:.3g} ({s['a_min']:.3g}..{s['a_max']:.3g}) "
            f"| {s['b_median']:.3g} ({s['b_min']:.3g}..{s['b_max']:.3g}) "
            f"| **{r:.3f}x** | [{lo:.3f}, {hi:.3f}] | [{plo:.3f}, {phi:.3f}] |"
        )


def cmd_run(args: argparse.Namespace) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    meta = {
        "type": "meta",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "label_a": args.label_a,
        "label_b": args.label_b,
        "cmd_a": args.cmd_a,
        "cmd_b": args.cmd_b,
        "parser": args.parser,
        "rounds": args.rounds,
        "load_start": host_load(),
    }
    records: list[dict[str, Any]] = [meta]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        fh.flush()

        for r in range(args.rounds):
            order = ("a", "b") if (r % 2 == 0 or not args.alternate) else ("b", "a")
            rec: dict[str, Any] = {
                "type": "round",
                "round": r + 1,
                "order": "".join(order).upper(),
                "load_before": host_load(),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            for side in order:
                cmd = args.cmd_a if side == "a" else args.cmd_b
                rc, out, dt = run_one(cmd)
                if rc != 0:
                    print(f"[round {r+1} {side.upper()}] rc={rc} in {dt:.1f}s\n{out[-800:]}", file=sys.stderr)
                    return rc
                rec[side] = parse_output(args.parser, out, args.pattern)
                rec[f"{side}_wall_s"] = round(dt, 2)
                if args.sleep > 0:
                    time.sleep(args.sleep)
            rec["load_after"] = host_load()
            records.append(rec)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            first_key = sorted(rec["a"].keys())[0]
            print(
                f"round {r+1:2d}/{args.rounds} ({rec['order']}) "
                f"{first_key}: {args.label_a}={rec['a'][first_key]:.3g} {args.label_b}={rec['b'][first_key]:.3g} "
                f"load={rec['load_after']}",
                flush=True,
            )

    summary = summarize_records(records, resamples=args.resamples, seed=args.seed)
    print_table(summary)
    if args.summary_json:
        with open(args.summary_json, "w", encoding="utf-8") as sf:
            json.dump(summary, sf, indent=2)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    records = []
    with open(args.jsonl, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    summary = summarize_records(records, resamples=args.resamples, seed=args.seed)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_table(summary)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Paired AB/BA benchmark runner with bootstrap 95% CI")
    sub = p.add_subparsers(dest="sub", required=True)

    pr = sub.add_parser("run", help="Run paired AB/BA rounds")
    pr.add_argument("--label-a", required=True)
    pr.add_argument("--label-b", required=True)
    pr.add_argument("--cmd-a", required=True)
    pr.add_argument("--cmd-b", required=True)
    pr.add_argument("--parser", choices=("float", "json-kv", "orm-spike", "read-store", "walk-e", "regex"), default="float")
    pr.add_argument("--pattern", action="append", default=[], help="For --parser regex: NAME=REGEX")
    pr.add_argument("--rounds", type=int, default=10)
    pr.add_argument("--no-alternate", dest="alternate", action="store_false", default=True)
    pr.add_argument("--sleep", type=float, default=0.0, help="Seconds to pause between A and B")
    pr.add_argument("--resamples", type=int, default=10000)
    pr.add_argument("--seed", type=int, default=42)
    pr.add_argument("--out", required=True, help="Output JSONL path")
    pr.add_argument("--summary-json", default=None)

    pa = sub.add_parser("analyze", help="Analyze a saved JSONL file")
    pa.add_argument("jsonl")
    pa.add_argument("--resamples", type=int, default=10000)
    pa.add_argument("--seed", type=int, default=42)
    pa.add_argument("--json", action="store_true")

    args = p.parse_args()
    if args.sub == "run":
        return cmd_run(args)
    return cmd_analyze(args)


if __name__ == "__main__":
    raise SystemExit(main())
