#!/usr/bin/env bash
# Progress of the robustness experiment (offline ablation -> train -> eval on imdb and imdb_upd).
# Usage: ./scripts/robust_update_status.sh
#        while true; do clear; ./scripts/robust_update_status.sh; sleep 60; done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
R="${ROOT}/experiments/robust_update"
date

echo "== 1. Offline ablation (10 runs: 5 variants x 2 seeds)"
done_runs=$(cat "${R}/offline_ablation.jsonl" "${ROOT}/lero/experiments/robust_update/offline_ablation.jsonl" 2>/dev/null \
  | sed -E 's/.*"variant": "([a-z]+)", "seed": ([0-9]+).*/\1_s\2/' | sort -u)
echo "  done ($(echo "${done_runs}" | grep -c .)/10): $(echo ${done_runs})"
running=$(pgrep -fl "offline_ablation.py --variant" | grep -v zsh | sed -E 's/.*--variant ([a-z]+) --seed ([0-9]+).*/\1_s\2/' | sort -u)
[[ -n "${running}" ]] && echo "  training now: $(echo ${running})"
[[ -s "${R}/ABLATION.md" ]] && echo "  summary: ${R}/ABLATION.md"

echo "== 2. Robustness benchmark"
if [[ ! -f "${R}/run_robust_update.out" ]]; then
  echo "  not started (starts after the ablation)"
else
  for f in "${R}"/models/*.train.log; do
    [[ -e "$f" ]] || continue
    ep=$(grep -o 'Epoch [0-9]*' "$f" | tail -1)
    echo "  train $(basename "$f" .train.log): ${ep:-starting} / 100$(grep -q 'saving model' "$f" && echo ' (saved)')"
  done
  # expected passes per DB: pg_warmup, pg, base_s0, robust_s0, base_s1, robust_s1, imdb_pw
  for db in imdb imdb_upd; do
    d="${R}/eval_${db}"
    [[ -d "$d" ]] || { echo "  eval ${db}: not started"; continue; }
    line="  eval ${db}:"
    for p in pg_warmup pg base_s0 robust_s0 base_s1 robust_s1 imdb_pw; do
      n=$( [[ -f "$d/$p.log" ]] && grep -c '' "$d/$p.log" || echo 0)
      line+=" ${p}=${n}/110"
    done
    echo "${line}"
  done
  [[ -s "${R}/RESULTS.md" ]] && echo "  DONE -> ${R}/RESULTS.md"
fi

if pgrep -f "offline_ablation.py --variant|run_robust_update.sh|test.py --query_path" >/dev/null; then
  echo "Status: RUNNING"
else
  echo "Status: idle (finished, or stopped — check ${R}/run_robust_update.out)"
fi
