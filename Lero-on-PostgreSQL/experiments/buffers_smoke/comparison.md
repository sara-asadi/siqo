# JOB latency comparison

- Queries compared: **10**
- PG total (ms): **22566.17**
- Lero total (ms): **18148.70**
- Total speedup (PG/Lero): **1.243x**
- Geomean per-query speedup: **1.084x**

| query | pg_ms | lero_ms | speedup |
|---|---:|---:|---:|
| 10a.sql | 3101.09 | 2449.12 | 1.266 |
| 10b.sql | 673.13 | 673.13 | 1.000 |
| 10c.sql | 9604.38 | 8115.02 | 1.184 |
| 11a.sql | 274.62 | 338.17 | 0.812 |
| 11b.sql | 156.78 | 280.16 | 0.560 |
| 11c.sql | 1070.02 | 410.98 | 2.604 |
| 11d.sql | 194.81 | 212.73 | 0.916 |
| 12a.sql | 2070.42 | 2041.88 | 1.014 |
| 12b.sql | 3.02 | 3.33 | 0.906 |
| 12c.sql | 5417.91 | 3624.18 | 1.495 |
