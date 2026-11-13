#!/usr/bin/env python3
"""How noisy are the latency labels, and do pages agree with latency?

Compares a training-data collection without cache control (one cold run per
plan, PG plan first) against one made with collect_training_data.py's warm-up +
shuffled repeats, on the queries both contain.

Usage:
  scripts/label_noise_report.py --old experiments/pages_ab/train_runs.log \
      --new experiments/cache_control/train_runs.log --out experiments/cache_control/RESULTS.md
"""
import argparse
import itertools
import json
import statistics
from collections import defaultdict

SEP = "#####"
TIMEOUT_MS = 30000
GAPS = [(1, 1.1), (1.1, 1.5), (1.5, 2), (2, 5), (5, float("inf"))]


def signature(n):
    return (n["Node Type"], n.get("Relation Name"), n.get("Index Name"),
            tuple(signature(c) for c in n.get("Plans", [])))


def load(path):
    """query -> list of plans in file order (file order = PG plan first)."""
    plans = defaultdict(list)
    with open(path) as f:
        for line in f:
            q, plan = line.strip().split(SEP)
            d = json.loads(plan)[0]
            if d["Execution Time"] >= TIMEOUT_MS:
                continue
            p = d["Plan"]
            plans[q].append(dict(
                idx=len(plans[q]),
                sig=signature(p),
                lat=d["Execution Time"],
                lats=d.get("Execution Times"),
                poss=d.get("Run Positions"),
                hit=p["Shared Hit Blocks"],
                read=p["Shared Read Blocks"],
                io=p.get("I/O Read Time", 0.0),
            ))
            plans[q][-1]["pages"] = p["Shared Hit Blocks"] + p["Shared Read Blocks"]
    return plans


def pairs(plans):
    for q, ps in plans.items():
        for a, b in itertools.combinations(ps, 2):
            if a["sig"] != b["sig"] and a["lat"] != b["lat"]:
                yield q, a, b


def ratio(x, y):
    return max(x, y) / max(min(x, y), 1)


def pct(n, d):
    return f"{n / d:.1%}" if d else "—"


def agreement(plans, key):
    ok = tot = 0
    for _, a, b in pairs(plans):
        if a[key] == b[key]:
            continue
        lo, hi = (a, b) if a[key] < b[key] else (b, a)
        tot += 1
        ok += lo["lat"] < hi["lat"]
    return pct(ok, tot), tot


def order_effect(plans):
    """Share of (pair, run) where the plan executed earlier was the slower one."""
    early_slow = tot = 0
    for _, a, b in pairs(plans):
        if a["lats"] is None:
            # one run each, executed in file order
            tot += 1
            early_slow += a["lat"] > b["lat"]
            continue
        for la, pa, lb, pb in zip(a["lats"], a["poss"], b["lats"], b["poss"]):
            if la == lb:
                continue
            tot += 1
            early_slow += (la > lb) if pa < pb else (lb > la)
    return pct(early_slow, tot), tot


def pg_slower(plans):
    n = s = 0
    for _, a, b in pairs(plans):
        if a["idx"] == 0:
            n += 1
            s += a["lat"] > b["lat"]
    return pct(s, n), n


def section(name, plans):
    ps = list(pairs(plans))
    total_lat = sum(p["lat"] for v in plans.values() for p in v)
    total_io = sum(p["io"] for v in plans.values() for p in v)
    total_hit = sum(p["hit"] for v in plans.values() for p in v)
    total_read = sum(p["read"] for v in plans.values() for p in v)
    out = [f"### {name}", "",
           f"queries with ≥2 distinct finished plans: {sum(len(v) >= 2 for v in plans.values())}, plan pairs: {len(ps)}",
           f"share of execution time waiting on reads: {pct(total_io, total_lat)}; "
           f"share of pages served from PG's buffer cache: {pct(total_hit, total_hit + total_read)}",
           ""]
    e, n = order_effect(plans)
    s, m = pg_slower(plans)
    out += [f"- earlier-executed plan is the slower one: **{e}** of {n} comparisons (50% = no order effect)",
            f"- PG's plan labelled slower than the candidate: **{s}** of {m} pairs", ""]
    out += ["| plan with less … is faster | agreement | pairs |", "|---|---:|---:|"]
    for k, label in [("pages", "pages (hit + read)"), ("read", "disk reads"), ("hit", "buffer hits"), ("io", "read wait time")]:
        a, t = agreement(plans, k)
        out.append(f"| {label} | {a} | {t} |")
    out += ["", "| page gap | pairs | fewer pages is faster |", "|---|---:|---:|"]
    for lo, hi in GAPS:
        sub = [(a, b) for _, a, b in ps if lo <= ratio(a["pages"], b["pages"]) < hi and a["pages"] != b["pages"]]
        ok = sum((a["lat"] < b["lat"]) == (a["pages"] < b["pages"]) for a, b in sub)
        out.append(f"| {lo}–{hi if hi != float('inf') else '∞'}x | {len(sub)} | {pct(ok, len(sub))} |")
    return out


def repeat_stability(plans):
    spreads = [max(p["lats"]) / max(min(p["lats"]), 1e-3) for v in plans.values() for p in v if p["lats"] and len(p["lats"]) > 1]
    stable = tot = 0
    by_gap = defaultdict(lambda: [0, 0])
    for _, a, b in pairs(plans):
        if not (a["lats"] and b["lats"]) or len(a["lats"]) != len(b["lats"]):
            continue
        wins = {la < lb for la, lb in zip(a["lats"], b["lats"])}
        tot += 1
        stable += len(wins) == 1
        g = ratio(a["lat"], b["lat"])
        k = "<1.1x" if g < 1.1 else ("1.1–1.5x" if g < 1.5 else "≥1.5x")
        by_gap[k][0] += 1
        by_gap[k][1] += len(wins) == 1
    q = statistics.quantiles(spreads, n=10) if len(spreads) > 1 else [float("nan")] * 9
    out = ["### Repeatability of the new labels", "",
           f"- per plan, slowest / fastest of its timed runs: median {statistics.median(spreads):.2f}x, p90 {q[8]:.2f}x ({len(spreads)} plans)",
           f"- pairs whose winner is the same in every round: **{pct(stable, tot)}** of {tot}"]
    for k in ["<1.1x", "1.1–1.5x", "≥1.5x"]:
        if by_gap[k][0]:
            out.append(f"  - latency gap {k}: {pct(by_gap[k][1], by_gap[k][0])} of {by_gap[k][0]}")
    return out


def matched(old, new):
    """Same plan pair in both collections: how often does the label flip?"""
    same = flip = pg_old = pg_new = pg_n = 0
    for q, ps in new.items():
        old_by_sig = {p["sig"]: p for p in old.get(q, [])}
        for a, b in itertools.combinations(ps, 2):
            oa, ob = old_by_sig.get(a["sig"]), old_by_sig.get(b["sig"])
            if not (oa and ob) or a["sig"] == b["sig"]:
                continue
            same += 1
            flip += (oa["lat"] < ob["lat"]) != (a["lat"] < b["lat"])
            if oa["idx"] == 0 or ob["idx"] == 0:
                pg, other, npg, nother = (oa, ob, a, b) if oa["idx"] == 0 else (ob, oa, b, a)
                pg_n += 1
                pg_old += pg["lat"] > other["lat"]
                pg_new += npg["lat"] > nother["lat"]
    return ["### Same plan pairs in both collections", "",
            f"- pairs found in both: {same}; label flipped by cache control: **{pct(flip, same)}**",
            f"- PG's plan labelled slower: {pct(pg_old, pg_n)} before → {pct(pg_new, pg_n)} after ({pg_n} pairs)"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    new = load(args.new)
    old = {q: v for q, v in load(args.old).items() if q in new}
    lines = ["# Latency label noise: cache control vs single cold run", "",
             f"old: `{args.old}` (one run per plan, PG plan first)  ",
             f"new: `{args.new}` (untimed warm-up, shuffled timed repeats, median kept)  ",
             f"restricted to the {len(new)} queries in the new collection; timeouts excluded", ""]
    lines += section("Before: one cold run per plan", old) + [""]
    lines += section("After: warm-up + shuffled repeats", new) + [""]
    lines += repeat_stability(new) + [""]
    lines += matched(old, new)
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
