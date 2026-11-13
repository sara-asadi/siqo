# Robustness to data updates — Lero variants on JOB

Models are trained once on `imdb` and evaluated on each database without retraining.
`imdb_upd` = `imdb` with every movie after the cutoff year (and all referencing rows) deleted, then VACUUM FULL + ANALYZE (scripts/make_updated_db.sh).
Speedups are vs PostgreSQL on the same database (>1 = faster than PG). One timed pass per model.

## imdb (110 queries)

| model | total exec (s) | total speedup vs PG | geomean speedup vs PG | >2x slower than PG | pages touched (M) | same plan as PG |
|---|---:|---:|---:|---:|---:|---:|
| base_s0 | 292.8 | 0.617x | 0.609x | 29 | 383.9 | 9/110 |
| base_s1 | 249.5 | 0.723x | 0.746x | 22 | 373.4 | 9/110 |
| imdb_pw | 238.8 | 0.756x | 0.744x | 29 | 215.4 | 22/110 |
| pg | 180.5 | 1.000x | 1.000x | 0 | 207.5 | 110/110 |
| robust_s0 | 227.1 | 0.795x | 0.771x | 20 | 239.1 | 12/110 |
| robust_s1 | 271.4 | 0.665x | 0.681x | 23 | 350.6 | 13/110 |

## imdb_upd (110 queries)

| model | total exec (s) | total speedup vs PG | geomean speedup vs PG | >2x slower than PG | pages touched (M) | same plan as PG |
|---|---:|---:|---:|---:|---:|---:|
| base_s0 | 152.4 | 0.703x | 0.643x | 29 | 212.6 | 11/110 |
| base_s1 | 146.2 | 0.733x | 0.752x | 23 | 247.5 | 11/110 |
| imdb_pw | 130.4 | 0.822x | 0.738x | 26 | 153.9 | 22/110 |
| pg | 107.2 | 1.000x | 1.000x | 0 | 140.7 | 110/110 |
| robust_s0 | 145.4 | 0.737x | 0.756x | 22 | 176.5 | 21/110 |
| robust_s1 | 154.3 | 0.695x | 0.696x | 23 | 259.0 | 13/110 |

## Change after the update (imdb → imdb_upd), averaged over seeds

Relative geomean = geomean speedup vs PG on the updated DB ÷ the same on the original DB (1.0 = keeps its standing against PG; <1 = degrades).

| model family | geomean vs PG on imdb | geomean vs PG on imdb_upd | relative | >2x slower than PG (imdb → imdb_upd) |
|---|---:|---:|---:|---:|
| base (n=2) | 0.678x | 0.698x | 1.029 | 25.5 → 26.0 |
| imdb_pw (n=1) | 0.744x | 0.738x | 0.992 | 29.0 → 26.0 |
| robust (n=2) | 0.726x | 0.726x | 1.000 | 21.5 → 22.5 |
