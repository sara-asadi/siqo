import argparse
import os
from multiprocessing import Pool

from utils import *


def run_queries(queries, run_args, output_file, pool_num, warmup=False):
    if warmup:
        print("Warmup pass (not recorded)...")
        for fp, q in queries:
            try:
                do_run_query(q, fp, run_args, output_file + ".warmup", False, None, None)
            except Exception as e:
                print("warmup error", fp, e)

    if pool_num <= 1:
        for fp, q in queries:
            do_run_query(q, fp, run_args, output_file, True, None, None)
    else:
        pool = Pool(pool_num)
        for fp, q in queries:
            pool.apply_async(do_run_query, args=(q, fp, run_args, output_file, True, None, None))
        print("Waiting for all subprocesses done...")
        pool.close()
        pool.join()


# python test.py --query_path ../reproduce/test_query/job.txt --output_query_latency_file job.test --algo lero
if __name__ == "__main__":
    parser = argparse.ArgumentParser("JOB / Lero query latency runner")
    parser.add_argument("--query_path", metavar="PATH", help="Load the queries", required=True)
    parser.add_argument("--output_query_latency_file", metavar="PATH", required=True)
    parser.add_argument("--algo", type=str, default="lero", choices=["lero", "pg"],
                        help="lero = enable Lero GUCs; pg = vanilla Postgres")
    parser.add_argument("--pool_num", type=int, default=1,
                        help="Parallel workers (use 1 for fair latency reporting)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N queries")
    parser.add_argument("--warmup", action="store_true",
                        help="Run each query once without recording, then timed run")
    args = parser.parse_args()

    test_queries = load_queries(args.query_path, limit=args.limit)
    print("Read", len(test_queries), "test queries.")

    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH)

    if args.algo == "lero":
        ensure_card_dir()
        run_args = get_lero_run_args()
    else:
        run_args = []

    print("algo:", args.algo, "pool_num:", args.pool_num, "run_args:", run_args)
    run_queries(test_queries, run_args, args.output_query_latency_file, args.pool_num, warmup=args.warmup)
