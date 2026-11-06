#!/usr/bin/env python3
"""Summarize run_pages_ab.sh: PG vs Lero (base features) vs Lero + estimated pages."""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics

SEP = "#####"


def parse(path: str) -> dict[str, dict]:
    """query -> {ms, pages (shared hit+read at root), plan_ms, sig}"""
    out = {}
    with open(path) as f:
        for line in f:
            if SEP not in line:
                continue
            name, payload = line.strip().split(SEP, 1)
            plan = json.loads(payload)[0]
            root = plan["Plan"]
            out[name] = {
                "ms": float(plan["Execution Time"]),
                "pages": root.get("Shared Hit Blocks", 0) + root.get("Shared Read Blocks", 0),
                "plan_ms": float(plan.get("Planning Time", 0)),
                "sig": signature(root),
            }
    return out


def signature(n):
    return (n["Node Type"], n.get("Relation Name"), tuple(signature(c) for c in n.get("Plans", [])))


def geomean(xs):
    return math.exp(sum(math.log(max(x, 1e-9)) for x in xs) / len(xs))


def load_variant(eval_dir, name):
    """Average latency over repetitions (r1, r2, ...) of one variant."""
    runs = [parse(p) for p in sorted(glob.glob(os.path.join(eval_dir, f"{name}_r*.log")))]
    if not runs:
        return None
    qs = set.intersection(*(set(r) for r in runs))
    return {q: {"ms": statistics.mean(r[q]["ms"] for r in runs),
                "pages": statistics.mean(r[q]["pages"] for r in runs),
                "plan_ms": statistics.mean(r[q]["plan_ms"] for r in runs),
                "sig": runs[0][q]["sig"]} for q in qs}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eval_dir", required=True)
    ap.add_argument("--seeds", nargs="+", default=["0", "1"])
    ap.add_argument("--out")
    args = ap.parse_args()

    pg_runs = [parse(p) for p in sorted(glob.glob(os.path.join(args.eval_dir, "pg_r*.log")))]
    variants = {"pg": load_variant(args.eval_dir, "pg")}
    for s in args.seeds:
        variants[f"base_s{s}"] = load_variant(args.eval_dir, f"base_s{s}")
        variants[f"pages_s{s}"] = load_variant(args.eval_dir, f"pages_s{s}")
    imdb = load_variant(args.eval_dir, "imdb_pw")
    if imdb:
        variants["imdb_pw"] = imdb
    variants = {k: v for k, v in variants.items() if v}
    qs = sorted(set.intersection(*(set(v) for v in variants.values())),
                key=lambda q: (int("".join(c for c in q if c.isdigit())), q))
    pg = variants["pg"]

    # run-to-run noise on identical plans (PG r1 vs r2)
    noise = None
    if len(pg_runs) >= 2:
        ratios = sorted(max(pg_runs[0][q]["ms"], 0.01) / max(pg_runs[1][q]["ms"], 0.01) for q in qs)
        sym = sorted(max(r, 1 / r) for r in ratios)
        noise = (geomean(ratios), sym[int(0.9 * (len(sym) - 1))])

    L = ["# Lero vs Lero + estimated pages-read feature — JOB test", ""]
    L.append(f"Queries: **{len(qs)}** (job_excl_29). Latency = mean of repetitions; speedup = PG / variant (>1 is faster than PG).")
    if noise:
        L.append(f"Noise (PG pass 1 vs pass 2, same plans): geomean ratio {noise[0]:.3f}, p90 |ratio| {noise[1]:.2f}x.")
    L += ["", "## Headline", "",
          "| variant | total exec (s) | total speedup vs PG | geomean speedup vs PG | pages touched (M, sum) | planning (s) | same plan as PG |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    tot_pg = sum(pg[q]["ms"] for q in qs)
    for name, v in variants.items():
        tot = sum(v[q]["ms"] for q in qs)
        geo = geomean([pg[q]["ms"] / max(v[q]["ms"], 1e-3) for q in qs])
        pages = sum(v[q]["pages"] for q in qs) / 1e6
        plan = sum(v[q]["plan_ms"] for q in qs) / 1e3
        same = sum(v[q]["sig"] == pg[q]["sig"] for q in qs)
        L.append(f"| {name} | {tot/1e3:.1f} | {tot_pg/tot:.3f}x | {geo:.3f}x | {pages:.1f} | {plan:.1f} | {same}/{len(qs)} |")

    thr = noise[1] if noise else 1.5
    L += ["", f"## Head-to-head: pages vs base (same seed)", "",
          f"Win/loss = latency ratio beyond the p90 noise ({thr:.2f}x) and >5 ms difference.", "",
          "| seed | geomean base/pages | total base (s) | total pages (s) | plans differ | pages wins | pages losses |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    detail = []
    for s in args.seeds:
        b, p = variants.get(f"base_s{s}"), variants.get(f"pages_s{s}")
        if not b or not p:
            continue
        geo = geomean([b[q]["ms"] / max(p[q]["ms"], 1e-3) for q in qs])
        differ = [q for q in qs if b[q]["sig"] != p[q]["sig"]]
        wins = [q for q in differ if b[q]["ms"] / max(p[q]["ms"], 1e-3) > thr and b[q]["ms"] - p[q]["ms"] > 5]
        losses = [q for q in differ if p[q]["ms"] / max(b[q]["ms"], 1e-3) > thr and p[q]["ms"] - b[q]["ms"] > 5]
        L.append(f"| {s} | {geo:.3f}x | {sum(b[q]['ms'] for q in qs)/1e3:.1f} | {sum(p[q]['ms'] for q in qs)/1e3:.1f} "
                 f"| {len(differ)} | {len(wins)} | {len(losses)} |")
        detail.append((s, wins, losses, b, p))
    for s, wins, losses, b, p in detail:
        fmt = lambda qq: ", ".join(f"{q} {b[q]['ms']/max(p[q]['ms'],1e-3):.1f}x" for q in qq) or "—"
        L.append(f"\n- seed {s} wins (base/pages): {fmt(wins)}")
        L.append(f"- seed {s} losses (base/pages): {fmt(losses)}")

    cols = [k for k in variants]
    L += ["", "## Per-query latency (ms) and pages touched (k)", "",
          "| query | " + " | ".join(cols) + " | " + " | ".join(f"{c} kpages" for c in cols) + " |",
          "|---|" + "---:|" * (2 * len(cols))]
    for q in qs:
        L.append(f"| {q} | " + " | ".join(f"{variants[c][q]['ms']:.1f}" for c in cols) + " | "
                 + " | ".join(f"{variants[c][q]['pages']/1e3:.1f}" for c in cols) + " |")

    report = "\n".join(L) + "\n"
    print(report)
    if args.out:
        with open(args.out, "w") as f:
            f.write(report)


if __name__ == "__main__":
    main()
