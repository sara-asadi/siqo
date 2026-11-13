#!/usr/bin/env bash
# Robustness to data updates: train once on imdb, then evaluate on imdb and on the
# updated copy imdb_upd (scripts/make_updated_db.sh) WITHOUT retraining.
# Models: PG, Lero base (experiments/pages_ab/models), robust variants trained here, imdb_pw.
# Usage:
#   ./scripts/run_robust_update.sh
#   NEW_VARIANTS="robust auxonly" SEEDS="0 1" ./scripts/run_robust_update.sh
#   SKIP_TRAIN=1 ./scripts/run_robust_update.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
require_venv
check_postgres

OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID:-robust_update}"
TRAIN_FILE="${TRAIN_FILE:-${EXPERIMENTS_DIR}/pages_ab/train_runs.log.training}"
BASE_MODELS="${EXPERIMENTS_DIR}/pages_ab/models"
MODEL_DIR="${OUT_DIR}/models"
SEEDS="${SEEDS:-0 1}"
NEW_VARIANTS="${NEW_VARIANTS:-robust}"
DBS="${DBS:-imdb imdb_upd}"
mkdir -p "${MODEL_DIR}"
snapshot_config "${OUT_DIR}" "" "{\"train_file\": \"${TRAIN_FILE}\", \"seeds\": \"${SEEDS}\", \"new_variants\": \"${NEW_VARIANTS}\", \"dbs\": \"${DBS}\"}"

variant_flags() {
  case "$1" in
    robust) echo "--robust --aux_pages 1" ;;
    robustnoaux) echo "--robust" ;;
    auxonly) echo "--aux_pages 1" ;;
    *) echo "unknown variant $1" >&2; exit 1 ;;
  esac
}

if [[ -z "${SKIP_TRAIN:-}" ]]; then
  for seed in ${SEEDS}; do
    for v in ${NEW_VARIANTS}; do
      echo "==> Train ${v} seed ${seed}"
      # shellcheck disable=SC2046
      (cd "${LERO_DIR}" && "${VENV_PY}" -u train.py --training_type 1 --seed "${seed}" $(variant_flags "${v}") \
        --training_data "${TRAIN_FILE}" --model_name "${MODEL_DIR}/${v}_s${seed}") \
        > "${MODEL_DIR}/${v}_s${seed}.train.log" 2>&1
    done
  done
fi

# The ranker reads live table stats from LERO_DB, so it must run against the evaluated DB.
restart_server() {
  local db="$1"
  local pid
  pid="$(lsof -ti tcp:"${LERO_PORT}" -sTCP:LISTEN || true)"
  [[ -n "${pid}" ]] && kill ${pid} && sleep 2
  (cd "${LERO_DIR}" && LERO_DB="${db}" nohup "${VENV_PY}" -u server.py > "${OUT_DIR}/server_${db}.out" 2>&1 &)
  for _ in $(seq 1 60); do nc -z 127.0.0.1 "${LERO_PORT}" 2>/dev/null && return 0; sleep 1; done
  echo "ERROR: Lero server did not start" >&2; exit 1
}

run_pass() {
  local db="$1" name="$2" algo="$3" model="${4:-}"
  local work
  work="$(mktemp -d)"
  [[ -n "${model}" ]] && load_model_on_server "${model}"
  echo "==> [${db}] ${name}"
  (cd "${work}" && LERO_DB="${db}" "${VENV_PY}" "${TEST_SCRIPT_DIR}/test.py" --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_DIR}/eval_${db}/${name}.log" --algo "${algo}" --pool_num 1) \
    > "${OUT_DIR}/eval_${db}/${name}.stdout" 2>&1
  rm -rf "${work}"
}

for db in ${DBS}; do
  mkdir -p "${OUT_DIR}/eval_${db}"
  restart_server "${db}"
  run_pass "${db}" pg_warmup pg
  run_pass "${db}" pg pg
  for seed in ${SEEDS}; do
    run_pass "${db}" "base_s${seed}" lero "${BASE_MODELS}/base_s${seed}"
    for v in ${NEW_VARIANTS}; do
      run_pass "${db}" "${v}_s${seed}" lero "${MODEL_DIR}/${v}_s${seed}"
    done
  done
  run_pass "${db}" imdb_pw lero "${DEFAULT_MODEL}"
done
# leave the server on the original database
restart_server imdb

"${VENV_PY}" "${SCRIPT_DIR}/compare_robust_update.py" --out_dir "${OUT_DIR}" --dbs ${DBS} \
  --out "${OUT_DIR}/RESULTS.md"
echo "Done. Artifacts in ${OUT_DIR}"
