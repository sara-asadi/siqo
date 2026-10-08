#!/usr/bin/env bash
# Online Lero training loop on JOB (train chunks + periodic test).
# Usage:
#   ./scripts/run_job_train.sh
#   QUERY_NUM_PER_CHUNK=20 TOPK=3 MODEL_PREFIX=job_exp ./scripts/run_job_train.sh
#   LIMIT_TRAIN=5 LIMIT_TEST=3 QUERY_NUM_PER_CHUNK=5 ./scripts/run_job_train.sh  # smoke
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_venv
check_postgres
check_lero_server

RUN_ID="${RUN_ID:-train_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID}"
MODEL_PREFIX="${MODEL_PREFIX:-job_lero}"
QUERY_NUM_PER_CHUNK="${QUERY_NUM_PER_CHUNK:-20}"
TOPK="${TOPK:-3}"
POOL_NUM="${POOL_NUM:-1}"

mkdir -p "${OUT_DIR}"
snapshot_config "${OUT_DIR}" "" \
  "{\"query_num_per_chunk\": ${QUERY_NUM_PER_CHUNK}, \"topK\": ${TOPK}, \"model_prefix\": \"${MODEL_PREFIX}\"}"

TRAIN_Q="${JOB_TRAIN_QUERIES}"
TEST_Q="${JOB_TEST_QUERIES}"

if [[ -n "${LIMIT_TRAIN:-}" || -n "${LIMIT_TEST:-}" ]]; then
  TRAIN_Q="${OUT_DIR}/train_slice.txt"
  TEST_Q="${OUT_DIR}/test_slice.txt"
  head -n "${LIMIT_TRAIN:-5}" "${JOB_TRAIN_QUERIES}" > "${TRAIN_Q}"
  head -n "${LIMIT_TEST:-3}" "${JOB_TEST_QUERIES}" > "${TEST_Q}"
fi

echo "==> Online train → ${OUT_DIR}/lero_train.log"
(
  cd "${TEST_SCRIPT_DIR}"
  "${VENV_PY}" train_model.py \
    --query_path "${TRAIN_Q}" \
    --test_query_path "${TEST_Q}" \
    --algo lero \
    --query_num_per_chunk "${QUERY_NUM_PER_CHUNK}" \
    --output_query_latency_file "${OUT_DIR}/lero_train.log" \
    --model_prefix "${MODEL_PREFIX}" \
    --pool_num "${POOL_NUM}" \
    --topK "${TOPK}"
)

echo "Done. Artifacts in ${OUT_DIR}"
echo "Trained model checkpoints are under ${LERO_DIR}/ (prefix ${MODEL_PREFIX}_*)."
echo "Eval with: MODEL_PATH=${LERO_DIR}/<checkpoint> ./scripts/run_job_eval.sh"
