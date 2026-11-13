# Latency label noise: cache control vs single cold run

old: `experiments/pages_ab/train_runs.log` (one run per plan, PG plan first)  
new: `experiments/cache_control/train_runs.log` (untimed warm-up, shuffled timed repeats, median kept)  
restricted to the 190 queries in the new collection; timeouts excluded

### Before: one cold run per plan

queries with ≥2 distinct finished plans: 190, plan pairs: 471
share of execution time waiting on reads: 62.0%; share of pages served from PG's buffer cache: 83.6%

- earlier-executed plan is the slower one: **74.1%** of 471 comparisons (50% = no order effect)
- PG's plan labelled slower than the candidate: **77.8%** of 297 pairs

| plan with less … is faster | agreement | pairs |
|---|---:|---:|
| pages (hit + read) | 57.2% | 416 |
| disk reads | 68.0% | 459 |
| buffer hits | 50.1% | 467 |
| read wait time | 91.9% | 471 |

| page gap | pairs | fewer pages is faster |
|---|---:|---:|
| 1–1.1x | 188 | 49.5% |
| 1.1–1.5x | 82 | 40.2% |
| 1.5–2x | 43 | 74.4% |
| 2–5x | 60 | 66.7% |
| 5–∞x | 43 | 93.0% |

### After: warm-up + shuffled repeats

queries with ≥2 distinct finished plans: 177, plan pairs: 411
share of execution time waiting on reads: 3.8%; share of pages served from PG's buffer cache: 99.7%

- earlier-executed plan is the slower one: **54.2%** of 1233 comparisons (50% = no order effect)
- PG's plan labelled slower than the candidate: **47.6%** of 294 pairs

| plan with less … is faster | agreement | pairs |
|---|---:|---:|
| pages (hit + read) | 68.7% | 367 |
| disk reads | 60.0% | 20 |
| buffer hits | 68.3% | 369 |
| read wait time | 60.0% | 20 |

| page gap | pairs | fewer pages is faster |
|---|---:|---:|
| 1–1.1x | 167 | 55.7% |
| 1.1–1.5x | 71 | 76.1% |
| 1.5–2x | 36 | 80.6% |
| 2–5x | 52 | 69.2% |
| 5–∞x | 41 | 97.6% |

### Repeatability of the new labels

- per plan, slowest / fastest of its timed runs: median 1.13x, p90 1.64x (484 plans)
- pairs whose winner is the same in every round: **58.9%** of 411
  - latency gap <1.1x: 29.5% of 190
  - latency gap 1.1–1.5x: 73.8% of 130
  - latency gap ≥1.5x: 98.9% of 91

### Same plan pairs in both collections

- pairs found in both: 352; label flipped by cache control: **35.2%**
- PG's plan labelled slower: 80.0% before → 50.2% after (205 pairs)
