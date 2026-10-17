# E036: Phase 3 reference reproduction

Generated 2026-10-17T09:56 UTC. Tolerance 1e-09 absolute on every float, exact on every count and label. Expected figures are read from the committed result files.

**REPRODUCES** (move-size (E036's gate))

| figure | reproduced |
|---|---|
| folds · frame rows · out-of-sample rows | 27 · 64,180 · 54,472 |
| reference validation Brier · skill · ECE · rho | 0.22486794688851872 · 0.09831058812130411 · 0.013908212033160137 · 0.360210573019641 |
| reference exploration Brier · skill | 0.21357448100603457 · 0.1457009719998531 |
| EWMA rule validation Brier · skill | 0.2394624303810767 · 0.03978872487148288 |
| EWMA minus reference, validation (paired, 2,000 resamples) | 0.014594483492557986 [0.012611756091962877, 0.01651934785855354] |
