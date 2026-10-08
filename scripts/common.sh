#!/usr/bin/env bash
# Shared helpers for JOB experiment runners.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LERO_DIR="${ROOT}/lero"
TEST_SCRIPT_DIR="${LERO_DIR}/test_script"
EXPERIMENTS_DIR="${ROOT}/experiments"
VENV_PY="${ROOT}/.venv/bin/python"
# job_excl_29.txt drops 29a/29b/29c: 17-table joins with self-joins (comp_cast_type,
# info_type) that, with geqo=off (Lero's documented setting), force exhaustive
# join-order search and run the backend out of memory. Override with JOB_TEST_QUERIES=.../job.txt
# to run the full 112-query set (expect an OOM crash on those three).
JOB_TEST_QUERIES="${JOB_TEST_QUERIES:-${LERO_DIR}/reproduce/test_query/job_excl_29.txt}"
JOB_TRAIN_QUERIES="${JOB_TRAIN_QUERIES:-${LERO_DIR}/reproduce/training_query/job.txt}"
DEFAULT_MODEL="${LERO_DIR}/reproduce/imdb_pw"

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5433}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-imdb}"
LERO_PORT="${LERO_PORT:-14567}"

require_venv() {
  if [[ ! -x "${VENV_PY}" ]]; then
    echo "ERROR: missing venv at ${ROOT}/.venv — create it with:" >&2
    echo "  cd ${ROOT} && python3 -m venv .venv && .venv/bin/pip install -r lero/requirements.txt" >&2
    exit 1
  fi
}

check_postgres() {
  if command -v psql >/dev/null 2>&1; then
    if ! PGPASSWORD=postgres psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -c 'SELECT 1' >/dev/null 2>&1; then
      echo "ERROR: cannot connect to Postgres at ${PG_HOST}:${PG_PORT}/${PG_DB}" >&2
      echo "  Start with: cd ${ROOT} && docker compose up -d postgres-lero" >&2
      exit 1
    fi
  elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx postgres-lero; then
    if ! docker exec -e PGPASSWORD=postgres postgres-lero psql -U "${PG_USER}" -d "${PG_DB}" -c 'SELECT 1' >/dev/null 2>&1; then
      echo "ERROR: cannot connect to Postgres (via docker exec) as db ${PG_DB}" >&2
      echo "  Start with: cd ${ROOT} && docker compose up -d postgres-lero" >&2
      exit 1
    fi
  else
    echo "ERROR: no psql on host and postgres-lero container not running" >&2
    echo "  Start with: cd ${ROOT} && docker compose up -d postgres-lero" >&2
    exit 1
  fi
  echo "OK Postgres ${PG_HOST}:${PG_PORT}/${PG_DB}"
}

check_lero_server() {
  if ! (echo >/dev/tcp/127.0.0.1/"${LERO_PORT}") 2>/dev/null; then
    if ! nc -z 127.0.0.1 "${LERO_PORT}" 2>/dev/null; then
      echo "ERROR: Lero server not listening on :${LERO_PORT}" >&2
      echo "  Start with: cd ${LERO_DIR} && ${VENV_PY} server.py" >&2
      exit 1
    fi
  fi
  echo "OK Lero server :${LERO_PORT}"
}

snapshot_config() {
  local out_dir="$1"
  local model_path="${2:-}"
  local extra="${3:-}"
  mkdir -p "${out_dir}"
  local git_commit="unknown"
  if git -C "${ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    git_commit="$(git -C "${ROOT}" rev-parse HEAD)"
  fi
  cat > "${out_dir}/config.json" <<EOF
{
  "pg_host": "${PG_HOST}",
  "pg_port": ${PG_PORT},
  "pg_db": "${PG_DB}",
  "lero_port": ${LERO_PORT},
  "model_path": "${model_path}",
  "job_test_queries": "${JOB_TEST_QUERIES}",
  "job_train_queries": "${JOB_TRAIN_QUERIES}",
  "pool_num": 1,
  "geqo": "off",
  "git_commit": "${git_commit}",
  "extra": ${extra:-null}
}
EOF
}

load_model_on_server() {
  local model_path="$1"
  require_venv
  MODEL_ABS="$(cd "$(dirname "${model_path}")" && pwd)/$(basename "${model_path}")"
  "${VENV_PY}" - "${MODEL_ABS}" "${LERO_PORT}" <<'PY'
import json, socket, sys
path, port = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", port))
s.sendall((json.dumps({"msg_type": "load", "model_path": path}) + "*LERO_END*").encode("utf-8"))
print(s.recv(4096).decode("utf-8", errors="replace"))
s.close()
PY
}
