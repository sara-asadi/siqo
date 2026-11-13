#!/usr/bin/env bash
# A/B: Lero trained on cold single-run latency labels vs on cache-controlled labels
# (experiments/cache_control, collect_training_data.py warm-up + repeats), on the SAME
# training queries. Evaluation warms each query up before its timed run (LERO_WARMUP_RUNS).
# Usage:
#   ./scripts/run_clean_label_ab.sh
#   SEEDS="0 1 2" SKIP_TRAIN=1 ./scripts/run_clean_label_ab.sh   # re-run eval only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_venv
check_postgres
check_lero_server

OUT_DIR="${EXPERIMENTS_DIR}/${RUN_ID:-clean_label_ab}"
CLEAN_LOG="${CLEAN_LOG:-${EXPERIMENTS_DIR}/cache_control/train_runs.log}"
OLD_LOG="${OLD_LOG:-${EXPERIMENTS_DIR}/pages_ab/train_runs.log}"
MODEL_DIR="${OUT_DIR}/models"
SEEDS="${SEEDS:-0 1}"
mkdir -p "${MODEL_DIR}" "${OUT_DIR}/eval"
snapshot_config "${OUT_DIR}" "" "{\"clean_log\": \"${CLEAN_LOG}\", \"old_log\": \"${OLD_LOG}\", \"seeds\": \"${SEEDS}\", \"eval_warmup_runs\": 1}"

# Old labels restricted to the queries of the clean collection, so only the labels differ.
"${VENV_PY}" - "${CLEAN_LOG}" "${OLD_LOG}" "${OUT_DIR}" <<'PY'
import sys
clean, old, out = sys.argv[1:]
SEP = "#####"
qs = {l.split(SEP)[0] for l in open(clean)}
with open(f"{out}/old_subset.log", "w") as f:
    f.writelines(l for l in open(old) if l.split(SEP)[0] in qs)
PY
# both collections used a 30s statement timeout; the builder needs it to drop timeout-vs-timeout pairs
(cd "${TEST_SCRIPT_DIR}" && LERO_TIMEOUT_MS=30000 "${VENV_PY}" -c "
from collect_training_data import build_training_file
build_training_file('${OUT_DIR}/old_subset.log', '${OUT_DIR}/old.training')
build_training_file('${CLEAN_LOG}', '${OUT_DIR}/clean.training')")

if [[ -z "${SKIP_TRAIN:-}" ]]; then
  for seed in ${SEEDS}; do
    for variant in old clean; do
      echo "==> Train ${variant} seed ${seed}"
      (cd "${LERO_DIR}" && "${VENV_PY}" train.py --training_type 1 --seed "${seed}" \
        --training_data "${OUT_DIR}/${variant}.training" --model_name "${MODEL_DIR}/${variant}_s${seed}") \
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
  (cd "${work}" && LERO_WARMUP_RUNS=1 "${VENV_PY}" "${TEST_SCRIPT_DIR}/test.py" --query_path "${JOB_TEST_QUERIES}" \
    --output_query_latency_file "${OUT_DIR}/eval/${name}.log" --algo "${algo}" --pool_num 1) \
    > "${OUT_DIR}/eval/${name}.stdout" 2>&1
  rm -rf "${work}"
}

PASSES=()
for seed in ${SEEDS}; do
  PASSES+=("old_s${seed}" "clean_s${seed}")
done

run_pass pg_r1 pg
for p in "${PASSES[@]}"; do run_pass "${p}_r1" lero "${MODEL_DIR}/${p}"; done
# reversed order for the second repetition cancels slow drift on this box
for ((i=${#PASSES[@]}-1; i>=0; i--)); do
  run_pass "${PASSES[$i]}_r2" lero "${MODEL_DIR}/${PASSES[$i]}"
done
run_pass pg_r2 pg

"${VENV_PY}" "${SCRIPT_DIR}/compare_pages_ab.py" --eval_dir "${OUT_DIR}/eval" --seeds ${SEEDS} \
  --a old --b clean --title "Lero trained on cold vs cache-controlled latency labels — JOB test" \
  --out "${OUT_DIR}/RESULTS.md"
echo "Done. Artifacts in ${OUT_DIR}"
