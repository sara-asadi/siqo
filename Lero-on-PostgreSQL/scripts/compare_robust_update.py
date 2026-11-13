#!/usr/bin/env python3
"""Summarize run_robust_update.sh: each model vs PG on the original and the updated DB."""
from __future__ import annotations

import argparse
import glob
import os
import re
import statistics

from compare_pages_ab import geomean, parse


def load_db(eval_dir):
    runs = {}
    for path in sorted(glob.glob(os.path.join(eval_dir, "*.log"))):
        name = os.path.basename(path)[:-4]
        if name != "pg_warmup":
            runs[name] = parse(path)
    return runs


def model_family(name):
    """base_s0 -> base; imdb_pw -> imdb_pw"""
    return re.sub(r"_s\d+$", "", name)


def stats(run, pg, qs):
    tot = sum(run[q]["ms"] for q in qs)
    return {
        "total_s": tot / 1e3,
        "total_x": sum(pg[q]["ms"] for q in qs) / tot,
        "geo_x": geomean([pg[q]["ms"] / max(run[q]["ms"], 1e-3) for q in qs]),
        "pages_m": sum(run[q]["pages"] for q in qs) / 1e6,
        "same": sum(run[q]["sig"] == pg[q]["sig"] for q in qs),
        "worse2x": sum(run[q]["ms"] > 2 * pg[q]["ms"] and run[q]["ms"] - pg[q]["ms"] > 5 for q in qs),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--dbs", nargs="+", default=["imdb", "imdb_upd"])
    ap.add_argument("--out")
    args = ap.parse_args()

    per_db = {}
    for db in args.dbs:
        runs = load_db(os.path.join(args.out_dir, f"eval_{db}"))
        qs = sorted(set.intersection(*(set(r) for r in runs.values())))
        per_db[db] = {name: stats(r, runs["pg"], qs) for name, r in runs.items()}
        per_db[db]["_n"] = len(qs)

    L = ["# Robustness to data updates — Lero variants on JOB", "",
         "Models are trained once on `imdb` and evaluated on each database without retraining.",
         "`imdb_upd` = `imdb` with every movie after the cutoff year (and all referencing rows) deleted, "
         "then VACUUM FULL + ANALYZE (scripts/make_updated_db.sh).",
         "Speedups are vs PostgreSQL on the same database (>1 = faster than PG). One timed pass per model.", ""]
    for db in args.dbs:
        d = per_db[db]
        L += [f"## {db} ({d['_n']} queries)", "",
              "| model | total exec (s) | total speedup vs PG | geomean speedup vs PG | >2x slower than PG | pages touched (M) | same plan as PG |",
              "|---|---:|---:|---:|---:|---:|---:|"]
        for name, s in d.items():
            if name == "_n":
                continue
            L.append(f"| {name} | {s['total_s']:.1f} | {s['total_x']:.3f}x | {s['geo_x']:.3f}x | {s['worse2x']} "
                     f"| {s['pages_m']:.1f} | {s['same']}/{d['_n']} |")
        L.append("")

    if len(args.dbs) == 2:
        a, b = args.dbs
        L += [f"## Change after the update ({a} → {b}), averaged over seeds", "",
              "Relative geomean = geomean speedup vs PG on the updated DB ÷ the same on the original DB "
              "(1.0 = keeps its standing against PG; <1 = degrades).", "",
              f"| model family | geomean vs PG on {a} | geomean vs PG on {b} | relative | >2x slower than PG ({a} → {b}) |",
              "|---|---:|---:|---:|---:|"]
        families = sorted({model_family(n) for n in per_db[a] if n not in ("_n", "pg")})
        for fam in families:
            names = [n for n in per_db[a] if n != "_n" and model_family(n) == fam and n in per_db[b]]
            ga = statistics.mean(per_db[a][n]["geo_x"] for n in names)
            gb = statistics.mean(per_db[b][n]["geo_x"] for n in names)
            wa = statistics.mean(per_db[a][n]["worse2x"] for n in names)
            wb = statistics.mean(per_db[b][n]["worse2x"] for n in names)
            L.append(f"| {fam} (n={len(names)}) | {ga:.3f}x | {gb:.3f}x | {gb / ga:.3f} | {wa:.1f} → {wb:.1f} |")

    report = "\n".join(L) + "\n"
    print(report)
    if args.out:
        with open(args.out, "w") as f:
            f.write(report)


if __name__ == "__main__":
    main()
