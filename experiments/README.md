# Experiment artifacts land in dated/run_id subdirs (committed; see eval_20260918_153352/RESULTS.txt for the PG vs Lero result).
# Keep this README tracked.

See ../EXPERIMENTS.md for the full workflow.

Typical layout after a baseline run:

```
experiments/
  baselines/
    config.json
    pg_job_test.log
    lero_imdb_pw_job_test.log
    comparison.md
  <run_id>/
    config.json
    ...
```
