#!/usr/bin/env bash
# Eval any Lero checkpoint on the JOB test set.
# Usage:
#   MODEL_PATH=./reproduce/imdb_pw ./scripts/run_job_eval.sh
#   MODEL_PATH=/path/to/my_model RUN_ID=my_eval ./scripts/run_job_eval.sh
#   LIMIT=3 MODEL_PATH=... ./scripts/run_job_eval.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_venv
check_postgres
check_lero_server

MODEL_PATH="${MODEL_PATH:-${DEFAULT_MODEL}}"
RUN_ID="${RUN_ID:-eval_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID}"
LIMIT_ARGS=()
WARMUP_ARGS=()

if [[ -n "${LIMIT:-}" ]]; then
  LIMIT_ARGS=(--limit "${LIMIT}")
fi
if [[ -n "${WARMUP:-}" ]]; then
  WARMUP_ARGS=(--warmup)
fi

mkdir -p "${OUT_DIR}"
LIMIT_JSON=null
[[ -n "${LIMIT:-}" ]] && LIMIT_JSON="${LIMIT}"
snapshot_config "${OUT_DIR}" "${MODEL_PATH}" "{\"limit\": ${LIMIT_JSON}}"

echo "==> Load model ${MODEL_PATH}"
load_model_on_server "${MODEL_PATH}"

OUT_LOG="${OUT_DIR}/lero_job_test.log"
echo "==> Lero eval → ${OUT_LOG}"
(
  cd "${TEST_SCRIPT_DIR}"
  "${VENV_PY}" test.py \
    --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_LOG}" \
    --algo lero \
    --pool_num 1 \
    "${LIMIT_ARGS[@]+"${LIMIT_ARGS[@]}"}" \
    "${WARMUP_ARGS[@]+"${WARMUP_ARGS[@]}"}"
)

PG_BASELINE="${EXPERIMENTS_DIR}/baselines/pg_job_test.log"
if [[ -f "${PG_BASELINE}" ]]; then
  "${VENV_PY}" "${SCRIPT_DIR}/compare_job_results.py" \
    --pg "${PG_BASELINE}" \
    --lero "${OUT_LOG}" \
    --out "${OUT_DIR}/comparison.md"
else
  echo "Note: no PG baseline at ${PG_BASELINE}; skip compare."
fi

echo "Done. Artifacts in ${OUT_DIR}"
