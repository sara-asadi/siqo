#!/usr/bin/env python3
"""Compare PG vs Lero latency logs produced by test.py / train_model.py."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys


SEP = "#####"


def parse_latency_file(path: str) -> dict[str, float]:
    """Return query_name -> execution time (ms). Last write wins if duplicates."""
    results: dict[str, float] = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or SEP not in line:
                continue
            name, payload = line.split(SEP, 1)
            try:
                plan = json.loads(payload)
                if isinstance(plan, list):
                    plan = plan[0]
                results[name] = float(plan["Execution Time"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                print(f"skip {name}: {e}", file=sys.stderr)
    return results


def geomean(values: list[float]) -> float:
    if not values:
        return float("nan")
    # clamp zeros for log safety
    logs = [math.log(max(v, 1e-9)) for v in values]
    return math.exp(sum(logs) / len(logs))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg", required=True, help="PG latency log")
    parser.add_argument("--lero", required=True, help="Lero latency log")
    parser.add_argument("--out", default=None, help="Optional markdown report path")
    args = parser.parse_args()

    pg = parse_latency_file(args.pg)
    lero = parse_latency_file(args.lero)
    common = sorted(set(pg) & set(lero))
    only_pg = sorted(set(pg) - set(lero))
    only_lero = sorted(set(lero) - set(pg))

    if not common:
        print("ERROR: no overlapping queries between logs", file=sys.stderr)
        sys.exit(1)

    rows = []
    speedups = []
    for q in common:
        sp = pg[q] / lero[q] if lero[q] > 0 else float("inf")
        speedups.append(sp)
        rows.append((q, pg[q], lero[q], sp))

    total_pg = sum(pg[q] for q in common)
    total_lero = sum(lero[q] for q in common)
    total_speedup = total_pg / total_lero if total_lero > 0 else float("inf")
    geo = geomean(speedups)

    lines = []
    lines.append("# JOB latency comparison")
    lines.append("")
    lines.append(f"- Queries compared: **{len(common)}**")
    lines.append(f"- PG total (ms): **{total_pg:.2f}**")
    lines.append(f"- Lero total (ms): **{total_lero:.2f}**")
    lines.append(f"- Total speedup (PG/Lero): **{total_speedup:.3f}x**")
    lines.append(f"- Geomean per-query speedup: **{geo:.3f}x**")
    if only_pg:
        lines.append(f"- Only in PG log: {len(only_pg)}")
    if only_lero:
        lines.append(f"- Only in Lero log: {len(only_lero)}")
    lines.append("")
    lines.append("| query | pg_ms | lero_ms | speedup |")
    lines.append("|---|---:|---:|---:|")
    for q, p, l, s in rows:
        lines.append(f"| {q} | {p:.2f} | {l:.2f} | {s:.3f} |")

    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write(report)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
