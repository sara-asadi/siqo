#!/usr/bin/env bash
# A/B: Lero (original features) vs Lero + estimated-pages feature, trained on the
# same shared training set (lero/test_script/collect_training_data.py).
# Usage:
#   TRAIN_FILE=experiments/pages_ab/train_runs.log.training ./scripts/run_pages_ab.sh
#   SEEDS="0 1" SKIP_TRAIN=1 ./scripts/run_pages_ab.sh   # re-run eval only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_venv
check_postgres
check_lero_server

OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID:-pages_ab}"
TRAIN_FILE="$(cd "$(dirname "${TRAIN_FILE:-${OUT_DIR}/train_runs.log.training}")" && pwd)/$(basename "${TRAIN_FILE:-train_runs.log.training}")"
MODEL_DIR="${OUT_DIR}/models"
SEEDS="${SEEDS:-0 1}"
mkdir -p "${MODEL_DIR}" "${OUT_DIR}/eval"
snapshot_config "${OUT_DIR}" "" "{\"train_file\": \"${TRAIN_FILE}\", \"seeds\": \"${SEEDS}\"}"

if [[ -z "${SKIP_TRAIN:-}" ]]; then
  for seed in ${SEEDS}; do
    for variant in base pages; do
      flag=""
      [[ "${variant}" == pages ]] && flag="--use_pages"
      echo "==> Train ${variant} seed ${seed}"
      (cd "${LERO_DIR}" && "${VENV_PY}" train.py --training_type 1 --seed "${seed}" ${flag} \
        --training_data "${TRAIN_FILE}" --model_name "${MODEL_DIR}/${variant}_s${seed}") \
        > "${MODEL_DIR}/${variant}_s${seed}.train.log" 2>&1
    done
  done
fi

# One timed pass over the test set, from a fresh cwd so the latency history cache is empty.
run_pass() {
  local name="$1" algo="$2" model="${3:-}"
  local work
  work="$(mktemp -d)"
  [[ -n "${model}" ]] && load_model_on_server "${model}"
  echo "==> ${name} (${algo} ${model})"
  (cd "${work}" && "${VENV_PY}" "${TEST_SCRIPT_DIR}/test.py" --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_DIR}/eval/${name}.log" --algo "${algo}" --pool_num 1) \
    > "${OUT_DIR}/eval/${name}.stdout" 2>&1
  rm -rf "${work}"
}

LERO_PASSES=()
for seed in ${SEEDS}; do
  LERO_PASSES+=("base_s${seed}" "pages_s${seed}")
done

run_pass pg_warmup pg
run_pass pg_r1 pg
for p in "${LERO_PASSES[@]}"; do run_pass "${p}_r1" lero "${MODEL_DIR}/${p}"; done
run_pass imdb_pw_r1 lero "${DEFAULT_MODEL}"
# reversed order for the second repetition cancels slow drift on this box
for ((i=${#LERO_PASSES[@]}-1; i>=0; i--)); do
  run_pass "${LERO_PASSES[$i]}_r2" lero "${MODEL_DIR}/${LERO_PASSES[$i]}"
done
run_pass pg_r2 pg

"${VENV_PY}" "${SCRIPT_DIR}/compare_pages_ab.py" --eval_dir "${OUT_DIR}/eval" --seeds ${SEEDS} \
  --out "${OUT_DIR}/RESULTS.md"
echo "Done. Artifacts in ${OUT_DIR}"
