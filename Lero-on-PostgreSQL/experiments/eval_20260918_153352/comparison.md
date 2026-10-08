# PG vs Lero (imdb_pw) — JOB test, 110 queries (job_excl_29)

Protocol (2026-10-08): same DB/GUCs (geqo=off, no parallel), sequential, history cache bypassed
(fresh cwd per pass). Passes: PG warmup (discarded) → PG timed (`pg_job_test.log`) →
Lero timed (`lero_rerun_job_test.log`). Lero rerun chose the same plan as `lero_job_test.log`
on 110/110 queries. Original log: 69/110 latencies were replayed from earlier-run history.

## Headline
| | PG | Lero (rerun) | Lero (orig log) |
|---|---:|---:|---:|
| Total exec | 353.8 s | 487.4 s (0.73x) | 565.5 s (0.63x) |
| Geomean speedup | — | 0.75x | 0.71x |
| Planning total | 2.3 s | 128.7 s | 120.9 s |

- Same plan as PG: 22/110; same join order: 30/110.
- Noise: identical plans ran 0.78x (geomean) in the Lero pass, p90 ratio 2.23x → this box is noisy;
  drift-corrected, Lero's differing plans are ~5% worse geomean, ~12% worse in total.

## Robust outcomes (>2.23x and >5 ms in BOTH Lero measurements)
Helped (6, +8.0 s): 13c 9.2x, 31b 6.4x, 13b 4.8x, 7b 3.4x, 26c 2.9x, 27c 2.3x
Hurt (10, −48.6 s): 3a 11.4x, 31c 6.6x, 7c 5.7x, 33a 5.2x, 11b 4.9x, 2a 4.2x, 27b 3.1x, 23a 2.4x, 23c 2.4x, 15a 2.3x
Likely hurt but within noise in one run: 18a (2.2x / 3.4x), 30a (1.5x / 3.1x).
