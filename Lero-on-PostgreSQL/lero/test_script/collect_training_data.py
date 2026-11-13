"""Collect one shared pairwise training set for A/B-ing Lero feature variants.

For each training query: PG's default plan plus (topK - 1) randomly sampled
Lero cardinality-guided candidates (seeded). Unlike train_model.py, candidate
choice does not depend on the model being trained, so every feature variant
trains on exactly the same executed plans.

Cache control: a single cold run per plan makes the latency label depend on
execution order (the first plan of a query pays for loading the data). So each
distinct plan is first run untimed (--warmup), then timed --repeats times with
EXPLAIN (ANALYZE, BUFFERS), in a fresh random order every round; the median
run is kept. The latency history cache is not used.
"""
import argparse
import json
import os
import random

import psycopg2

from utils import *

LERO_CARD_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", LERO_DUMP_CARD_FILE))
ANALYZE = "EXPLAIN (ANALYZE, BUFFERS, TIMING, VERBOSE, COSTS, SUMMARY, FORMAT JSON) "


def lero_candidates(q):
    """Distinct candidate card lists Lero's server enumerated for q."""
    explain_query(q, get_lero_run_args())
    with open(LERO_CARD_FILE, "r") as f:
        return [line.strip().split(";")[0] for line in f if line.strip()]


def plan_signature(n):
    """Plan shape: operators, relations and child structure (ignores runtime stats)."""
    return (n["Node Type"], n.get("Relation Name"), n.get("Index Name"),
            tuple(plan_signature(c) for c in n.get("Plans", [])))


def timed_run(sql, run_args):
    """One EXPLAIN ANALYZE run; returns the plan JSON list, or None on timeout."""
    try:
        _, res = run_query(ANALYZE + sql, run_args)
    except psycopg2.errors.QueryCanceled:
        return None
    return res[0][0]


def timeout_plan(sql, run_args):
    _, res = run_query("EXPLAIN (VERBOSE, COSTS, FORMAT JSON, SUMMARY) " + sql, run_args)
    plan = res[0][0]
    plan[0]["Execution Time"] = TIMEOUT
    return plan


def measure_query(sql, plans, warmup, repeats, rng):
    """plans: list of run_args. Returns one plan JSON list per plan (median run)."""
    timed_out = set()
    for _ in range(warmup):
        order = list(range(len(plans)))
        rng.shuffle(order)
        for i in order:
            if i in timed_out:
                continue
            try:
                run_query(sql, plans[i])
            except psycopg2.errors.QueryCanceled:
                # a plan that cannot finish warm will not finish timed either
                timed_out.add(i)

    runs = {i: [] for i in range(len(plans))}
    for r in range(repeats):
        order = [i for i in range(len(plans)) if i not in timed_out]
        rng.shuffle(order)
        for pos, i in enumerate(order):
            res = timed_run(sql, plans[i])
            if res is None:
                timed_out.add(i)
                continue
            res[0]["Run Round"], res[0]["Run Position"] = r, pos
            runs[i].append(res)

    out = []
    for i, args in enumerate(plans):
        if i in timed_out or not runs[i]:
            out.append(timeout_plan(sql, args))
            continue
        rs = sorted(runs[i], key=lambda p: p[0]["Execution Time"])
        med = rs[(len(rs) - 1) // 2]
        med[0]["Execution Times"] = [p[0]["Execution Time"] for p in runs[i]]
        med[0]["Run Positions"] = [p[0]["Run Position"] for p in runs[i]]
        out.append(med)
    return out


def build_training_file(latency_file, training_file):
    groups = {}
    with open(latency_file, "r") as f:
        for line in f:
            name, plan = line.strip().split(SEP)
            plan_json = json.loads(plan)[0]
            # identical plans, or two plans that both hit the timeout, give no ranking signal
            key = "timeout" if plan_json["Execution Time"] >= TIMEOUT else plan_signature(plan_json["Plan"])
            groups.setdefault(name, {}).setdefault(key, plan)
    lines = [SEP.join(plans.values()) for plans in groups.values() if len(plans) > 1]
    with open(training_file, "w") as f:
        f.write("\n".join(lines))
    print("training groups:", len(lines), "pairs:", sum(len(l.split(SEP)) * (len(l.split(SEP)) - 1) // 2 for l in lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Collect shared Lero training data")
    parser.add_argument("--query_path", required=True)
    parser.add_argument("--output_query_latency_file", required=True)
    parser.add_argument("--topK", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=1, help="untimed runs of each plan before timing")
    parser.add_argument("--repeats", type=int, default=3, help="timed runs per plan; the median is kept")
    args = parser.parse_args()

    # candidate sampling uses its own stream so it matches collections made before cache control
    rng = random.Random(args.seed)
    order_rng = random.Random(args.seed + 1)
    queries = load_queries(args.query_path, limit=args.limit)
    print("Read", len(queries), "training queries; topK", args.topK, "timeout", TIMEOUT,
          "warmup", args.warmup, "repeats", args.repeats)
    ensure_card_dir()

    out = args.output_query_latency_file
    done = set()
    if os.path.exists(out):
        with open(out) as f:
            done = {line.split(SEP)[0] for line in f}

    for fp, q in queries:
        sql = q.strip().replace("\n", " ").replace("\t", " ")
        try:
            cands = lero_candidates(q)
        except Exception as e:
            # e.g. a backend crash; skip this query instead of aborting a multi-hour run
            print("candidate generation failed", fp, e)
            continue
        sampled = rng.sample(cands, min(args.topK - 1, len(cands)))
        if fp in done:
            continue

        plans, seen = [], set()
        for i, card_str in enumerate([None] + sampled):
            run_args = []
            if card_str is not None:
                card_file_name = "collect_" + fp.replace("/", "_") + "_" + str(i) + ".txt"
                write_card_file(card_file_name, "\n".join(card_str.strip().split(" ")))
                run_args = get_card_run_args(card_file_name)
            sig = plan_signature(explain_query(sql, run_args)[0]["Plan"])
            # identical plans give no ranking signal; run each distinct plan once
            if sig not in seen:
                seen.add(sig)
                plans.append(run_args)

        try:
            results = measure_query(sql, plans, args.warmup, args.repeats, order_rng)
        except Exception as e:
            print("execution failed", fp, e)
            continue
        with open(out, "a") as f:
            for plan_json in results:
                f.write(fp + SEP + json.dumps(plan_json) + "\n")
        print(fp, len(plans), "plans", [round(p[0]["Execution Time"]) for p in results], flush=True)

    build_training_file(out, out + ".training")
