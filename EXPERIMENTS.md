# Lero JOB Experiment Playground

Reproducible Join Order Benchmark loop: vanilla PostgreSQL vs upstream Lero (`imdb_pw`) vs your own checkpoints.

## Prerequisites

- Docker Postgres `postgres-lero` on host port **5433**, database **`imdb`** (JOB data already loaded)
- Python 3.9+ venv with Lero deps
- Lero ranker server (`server.py`) on port **14567**

## One-time setup

```bash
cd /Users/hogwartz/Documents/Proposal/Lero-on-PostgreSQL

# Postgres (card bind-mount + host.docker.internal)
docker compose up -d postgres-lero

# Python env
python3 -m venv .venv
.venv/bin/pip install -r lero/requirements.txt

# Start Lero server (loads reproduce/imdb_pw from server.conf)
cd lero && ../.venv/bin/python server.py
```

Config already points scripts at `imdb:5433`. Card files are written under `lero_cards/` on the host and opened by Postgres as `lero_cards/<file>` relative to the data directory. Sessions set `lero_server_host=host.docker.internal`.

## Fair protocol

- Same DB, GUCs (`geqo=off`, no parallel workers), same query files
- Sequential runs: `--pool_num 1`
- Paper split: train `lero/reproduce/training_query/job.txt` (999), test `lero/reproduce/test_query/job.txt` (113)
- Optional `WARMUP=1` for a non-recorded pass before timing

## Commands

### Smoke (3 queries)

```bash
cd /Users/hogwartz/Documents/Proposal/Lero-on-PostgreSQL
# terminal A: cd lero && ../.venv/bin/python server.py
LIMIT=3 RUN_ID=smoke ./scripts/run_job_baselines.sh
```

### Full baselines (PG + imdb_pw)

```bash
./scripts/run_job_baselines.sh
# → experiments/baselines/{pg_job_test.log,lero_imdb_pw_job_test.log,comparison.md}
```

### Eval a custom checkpoint

```bash
MODEL_PATH=/path/to/checkpoint RUN_ID=my_model ./scripts/run_job_eval.sh
```

### Online train on JOB

```bash
QUERY_NUM_PER_CHUNK=20 TOPK=3 MODEL_PREFIX=job_exp ./scripts/run_job_train.sh
# Short path for plumbing checks:
LIMIT_TRAIN=5 LIMIT_TEST=3 QUERY_NUM_PER_CHUNK=5 ./scripts/run_job_train.sh
```

### Compare two latency logs

```bash
.venv/bin/python scripts/compare_job_results.py \
  --pg experiments/baselines/pg_job_test.log \
  --lero experiments/baselines/lero_imdb_pw_job_test.log \
  --out experiments/baselines/comparison.md
```

## Where to edit the model

| File | Role |
|------|------|
| `lero/model.py` | Tree-CNN / loss |
| `lero/feature.py` | Plan features |
| `lero/train.py` | Offline training loop / hyperparameters |
| `lero/card_picker.py` | Candidate plan generation |

Workflow after edits: retrain (`run_job_train.sh` or offline `train.py`) → `run_job_eval.sh` → compare against `experiments/baselines/`.

## Out of scope

- Siqo (`postgres:16`) — not Lero-compatible
- Restoring volume backups onto other Postgres images
- Rebuilding the Postgres C patch unless a model change requires it
