#!/usr/bin/env python3
"""Offline ablation on executed candidate plans: train on 80% of queries, score the rest.

Every candidate of a held-out query was executed, so we can measure which plan each
model would pick without running the benchmark.

  python scripts/offline_ablation.py --variant robust --seed 0 --out results.jsonl
  python scripts/offline_ablation.py --summarize results.jsonl
"""
import argparse
import contextlib
import io
import json
import math
import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "lero"))
sys.path.insert(0, os.path.join(ROOT, "lero", "test_script"))
# Lero code loads files relative to lero/; resolve user paths against the caller's cwd first
CALLER_CWD = os.getcwd()
os.chdir(os.path.join(ROOT, "lero"))

# variant -> (use_pages, robust, aux_pages_weight)
VARIANTS = {
    "base": (False, False, 0.0),
    "pages": (True, False, 0.0),
    "auxonly": (False, False, 1.0),
    "robustnoaux": (False, True, 0.0),
    "robust": (False, True, 1.0),
}


def run(variant, seed, training_file, out):
    import numpy as np
    import torch
    from feature import FeatureGenerator
    from model import LeroModel, LeroModelPairWise
    from train import get_training_pair

    groups = [line.strip().split("#####") for line in open(training_file) if line.strip()]
    idx = list(range(len(groups)))
    random.Random(42).shuffle(idx)
    cut = int(0.8 * len(idx))
    train_g = [groups[i] for i in idx[:cut]]
    test_g = [groups[i] for i in idx[cut:]]

    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(2)
    use_pages, robust, aux = VARIANTS[variant]
    X1, X2 = [], []
    for g in train_g:
        a, b = get_training_pair(g)
        X1 += a; X2 += b
    fg = FeatureGenerator(use_pages, robust)
    with contextlib.redirect_stdout(io.StringIO()):
        fg.fit(X1 + X2)
        F1, Y1 = fg.transform(X1)
        F2, Y2 = fg.transform(X2)
        m = LeroModelPairWise(fg)
        m.fit(F1, F2, Y1, Y2, False, aux)

    lat = lambda p: json.loads(p)[0]["Execution Time"]
    correct = total = 0
    picked = pg = best = 0.0
    ratios, page_err = [], []
    for g in test_g:
        feats, _ = fg.transform(g)
        scores = [m.predict(f)[0][0] for f in feats]
        lats = [lat(p) for p in g]
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if lats[i] != lats[j]:
                    total += 1
                    correct += (scores[i] < scores[j]) == (lats[i] < lats[j])
        choice = lats[int(np.argmin(scores))]
        picked += choice; pg += lats[0]; best += min(lats)
        ratios.append(lats[0] / max(choice, 1e-3))
        if aux > 0:
            pred = LeroModel.predict_pages(m, feats)
            for p, f in zip(pred, feats):
                if f.total_pages_label is not None:
                    actual = math.expm1(f.total_pages_label * 10)
                    page_err.append(abs(math.log1p(p) - math.log1p(actual)))

    rec = {"variant": variant, "seed": seed, "pair_acc": correct / total,
           "picked_s": picked / 1e3, "pg_s": pg / 1e3, "oracle_s": best / 1e3,
           "geomean_vs_pg": math.exp(sum(math.log(r) for r in ratios) / len(ratios)),
           "held_out_queries": len(test_g)}
    if page_err:
        # median |log error| -> typical multiplicative error of the page prediction
        rec["pages_median_x_error"] = math.exp(sorted(page_err)[len(page_err) // 2])
    with open(out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))


def summarize(path):
    import statistics
    recs = [json.loads(l) for l in open(path) if l.strip()]
    first = recs[0]
    print(f"held-out queries: {first['held_out_queries']}, PG total {first['pg_s']:.1f}s, "
          f"best-candidate total {first['oracle_s']:.1f}s\n")
    print("| variant | seeds | pair accuracy | picked total (s) | geomean vs PG | page pred. error (median) |")
    print("|---|---:|---:|---:|---:|---:|")
    for v in VARIANTS:
        rs = [r for r in recs if r["variant"] == v]
        if not rs:
            continue
        fmt = lambda k: " / ".join(f"{r[k]:.3f}" for r in rs)
        pe = " / ".join(f"{r['pages_median_x_error']:.2f}x" for r in rs if "pages_median_x_error" in r) or "—"
        print(f"| {v} | {len(rs)} | {statistics.mean(r['pair_acc'] for r in rs):.3f} ({fmt('pair_acc')}) "
              f"| {statistics.mean(r['picked_s'] for r in rs):.1f} "
              f"| {statistics.mean(r['geomean_vs_pg'] for r in rs):.3f}x ({fmt('geomean_vs_pg')}) | {pe} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", choices=list(VARIANTS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--training_file", default=os.path.join(ROOT, "experiments/pages_ab/train_runs.log.training"))
    ap.add_argument("--out")
    ap.add_argument("--summarize")
    args = ap.parse_args()
    args.training_file = os.path.join(CALLER_CWD, args.training_file)
    if args.out:
        args.out = os.path.join(CALLER_CWD, args.out)
    if args.summarize:
        args.summarize = os.path.join(CALLER_CWD, args.summarize)
    if args.summarize:
        summarize(args.summarize)
    else:
        run(args.variant, args.seed, args.training_file, args.out)
