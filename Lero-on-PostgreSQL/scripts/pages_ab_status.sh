#!/usr/bin/env bash
# Progress of the pages A/B run (collection -> training -> eval).
# Usage: ./scripts/pages_ab_status.sh        (one-shot)
#        while true; do clear; ./scripts/pages_ab_status.sh; sleep 30; done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="${ROOT}/experiments/pages_ab"
QUERIES="${ROOT}/lero/reproduce/training_query/job_excl_17tab.txt"
date

if [[ -s "${D}/RESULTS.md" ]]; then
  echo "DONE -> ${D}/RESULTS.md"
  sed -n '/## Headline/,/## Per-query/p' "${D}/RESULTS.md" | sed '$d'
  exit 0
fi

last=$(grep -E '^[0-9.]+ q[0-9]+ ' "${D}/collect.out" 2>/dev/null | tail -1)
if [[ -n "${last}" ]]; then
  q=$(awk '{print $2}' <<<"${last}")
  pos=$(awk -F'#####' -v q="${q}" '$1==q{print NR}' "${QUERIES}")
  ago=$(( $(date +%s) - $(awk '{print int($1)}' <<<"${last}") ))
  echo "Collection: ${pos:-?} / $(grep -c '' "${QUERIES}") queries (last result ${ago}s ago), failures: $(grep -c failed "${D}/collect.out")"
fi
grep -h "training groups" "${D}/collect.out" 2>/dev/null

for f in "${D}"/models/*.train.log; do
  [[ -e "$f" ]] || continue
  ep=$(grep -o 'Epoch [0-9]*' "$f" | tail -1)
  echo "Train $(basename "$f" .train.log): ${ep:-starting} / 100$(grep -q 'saving model' "$f" && echo ' (saved)')"
done

if [[ -d "${D}/eval" ]]; then
  echo "Eval passes (110 queries each):"
  for f in "${D}"/eval/*.log; do
    [[ -e "$f" ]] && printf '  %-14s %3d\n' "$(basename "$f" .log)" "$(wc -l < "$f")"
  done
fi

if pgrep -f "collect_training_data.py|run_pages_ab.sh" >/dev/null; then
  echo "Status: RUNNING"
else
  echo "Status: NOT RUNNING (watchdog retries if no RESULTS.md; check ${D}/run_pages_ab.out)"
fi
