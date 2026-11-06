"""Collect one shared pairwise training set for A/B-ing Lero feature variants.

For each training query: run PG's default plan plus (topK - 1) randomly sampled
Lero cardinality-guided candidates (seeded), all with EXPLAIN (ANALYZE, BUFFERS).
Unlike train_model.py, candidate choice does not depend on the model being trained,
so every feature variant trains on exactly the same executed plans.

Run from a fresh working directory so the latency history cache starts empty.
"""
import argparse
import json
import os
import random

from utils import *

LERO_CARD_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", LERO_DUMP_CARD_FILE))


def lero_candidates(q):
    """Distinct candidate card lists Lero's server enumerated for q."""
    explain_query(q, get_lero_run_args())
    with open(LERO_CARD_FILE, "r") as f:
        return [line.strip().split(";")[0] for line in f if line.strip()]


def plan_signature(n):
    """Plan shape: operators, relations and child structure (ignores runtime stats)."""
    return (n["Node Type"], n.get("Relation Name"), n.get("Index Name"),
            tuple(plan_signature(c) for c in n.get("Plans", [])))


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
    args = parser.parse_args()

    rng = random.Random(args.seed)
    queries = load_queries(args.query_path, limit=args.limit)
    print("Read", len(queries), "training queries; topK", args.topK, "timeout", TIMEOUT)
    os.makedirs(LOG_PATH, exist_ok=True)
    ensure_card_dir()

    out = args.output_query_latency_file
    done = set()
    if os.path.exists(out):
        with open(out) as f:
            done = {line.split(SEP)[0] for line in f}

    for fp, q in queries:
        if fp in done:
            continue
        try:
            do_run_query(q, fp, [], out, True, None, None)
            cands = lero_candidates(q)
        except Exception as e:
            # e.g. a backend crash; skip this query instead of aborting a multi-hour run
            print("candidate generation failed", fp, e)
            continue
        for i, card_str in enumerate(rng.sample(cands, min(args.topK - 1, len(cands)))):
            card_file_name = "collect_" + fp.replace("/", "_") + "_" + str(i) + ".txt"
            write_card_file(card_file_name, "\n".join(card_str.strip().split(" ")))
            do_run_query(q, fp, get_card_run_args(card_file_name), out, True, None, None)

    build_training_file(out, out + ".training")
