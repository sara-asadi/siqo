held-out queries: 186, PG total 414.7s, best-candidate total 281.0s

| variant | seeds | pair accuracy | picked total (s) | geomean vs PG | page pred. error (median) |
|---|---:|---:|---:|---:|---:|
| base | 2 | 0.702 (0.695 / 0.709) | 339.9 | 1.549x (1.556 / 1.541) | — |
| pages | 2 | 0.724 (0.733 / 0.716) | 339.8 | 1.554x (1.521 / 1.587) | — |
| auxonly | 2 | 0.692 (0.695 / 0.688) | 348.5 | 1.518x (1.505 / 1.532) | 4.67x / 3.22x |
| robustnoaux | 2 | 0.730 (0.726 / 0.735) | 352.7 | 1.568x (1.575 / 1.560) | — |
| robust | 2 | 0.738 (0.749 / 0.728) | 327.1 | 1.582x (1.605 / 1.558) | 3.96x / 2.99x |
