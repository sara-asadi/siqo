#!/usr/bin/env bash
# Run PG baseline + upstream Lero (imdb_pw) on the 113 JOB test queries.
# Usage:
#   ./scripts/run_job_baselines.sh
#   LIMIT=3 ./scripts/run_job_baselines.sh          # smoke / short slice
#   WARMUP=1 ./scripts/run_job_baselines.sh
#   RUN_ID=baselines ./scripts/run_job_baselines.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_venv
check_postgres

RUN_ID="${RUN_ID:-baselines}"
OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID}"
LIMIT_ARGS=()
WARMUP_ARGS=()
MODEL_PATH="${MODEL_PATH:-${DEFAULT_MODEL}}"

if [[ -n "${LIMIT:-}" ]]; then
  LIMIT_ARGS=(--limit "${LIMIT}")
fi
if [[ -n "${WARMUP:-}" ]]; then
  WARMUP_ARGS=(--warmup)
fi

mkdir -p "${OUT_DIR}"
WARMUP_JSON=false
[[ -n "${WARMUP:-}" ]] && WARMUP_JSON=true
LIMIT_JSON=null
[[ -n "${LIMIT:-}" ]] && LIMIT_JSON="${LIMIT}"
snapshot_config "${OUT_DIR}" "${MODEL_PATH}" "{\"limit\": ${LIMIT_JSON}, \"warmup\": ${WARMUP_JSON}}"

echo "==> PG baseline → ${OUT_DIR}/pg_job_test.log"
(
  cd "${TEST_SCRIPT_DIR}"
  "${VENV_PY}" test.py \
    --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_DIR}/pg_job_test.log" \
    --algo pg \
    --pool_num 1 \
    "${LIMIT_ARGS[@]+"${LIMIT_ARGS[@]}"}" \
    "${WARMUP_ARGS[@]+"${WARMUP_ARGS[@]}"}"
)

check_lero_server
echo "==> Load model ${MODEL_PATH}"
load_model_on_server "${MODEL_PATH}"

echo "==> Lero eval → ${OUT_DIR}/lero_imdb_pw_job_test.log"
(
  cd "${TEST_SCRIPT_DIR}"
  "${VENV_PY}" test.py \
    --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_DIR}/lero_imdb_pw_job_test.log" \
    --algo lero \
    --pool_num 1 \
    "${LIMIT_ARGS[@]+"${LIMIT_ARGS[@]}"}" \
    "${WARMUP_ARGS[@]+"${WARMUP_ARGS[@]}"}"
)

echo "==> Compare"
"${VENV_PY}" "${SCRIPT_DIR}/compare_job_results.py" \
  --pg "${OUT_DIR}/pg_job_test.log" \
  --lero "${OUT_DIR}/lero_imdb_pw_job_test.log" \
  --out "${OUT_DIR}/comparison.md"

echo "Done. Artifacts in ${OUT_DIR}"
