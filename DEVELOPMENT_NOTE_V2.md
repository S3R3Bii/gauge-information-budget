# Separate v2 development results

Only Wisconsin/Delaware training years 2020–2021 and validation 2022 were modelled. Original v1 source failure remains unchanged. No final-period or held-basin predictive score was computed.

| Lag (days) | Family | Penalty | Equal-basin validation MSE (log-flow squared) | Selected |
|---:|---|---:|---:|---|
| 3 | local | 0.001 | 0.088397457 | no |
| 3 | local | 0.01 | 0.088329223 | no |
| 3 | local | 0.1 | 0.087904075 | yes |
| 3 | local | 1.0 | 0.089698527 | no |
| 3 | pair | 0.001 | 0.075315322 | no |
| 3 | pair | 0.01 | 0.074379014 | yes |
| 3 | pair | 0.1 | 0.075925051 | no |
| 3 | pair | 1.0 | 0.081934608 | no |
| 1 | local | 0.001 | 0.020215421 | no |
| 1 | local | 0.01 | 0.020207900 | no |
| 1 | local | 0.1 | 0.020191622 | yes |
| 1 | local | 1.0 | 0.021274283 | no |
| 1 | pair | 0.001 | 0.013876017 | yes |
| 1 | pair | 0.01 | 0.014106028 | no |
| 1 | pair | 0.1 | 0.015590133 | no |
| 1 | pair | 1.0 | 0.018530177 | no |

The one-day pair model selects lambda 0.001, the lower grid boundary. No grid expansion or claim of a global optimum follows. All 32 fits, 36 fold scores including persistence, 16 equal-basin objectives and 13,140 predictions are retained. Both fitted families share the same training and validation support.

| Basin | Lag (days) | Model | Selected penalty | Validation MSE (log-flow squared) |
|---|---:|---|---:|---:|
| wisconsin | 3 | persistence | — | 0.045786018 |
| wisconsin | 3 | local | 0.1 | 0.043032621 |
| wisconsin | 3 | pair | 0.01 | 0.022903828 |
| wisconsin | 1 | persistence | — | 0.011922591 |
| wisconsin | 1 | local | 0.1 | 0.010949447 |
| wisconsin | 1 | pair | 0.001 | 0.008499959 |
| delaware | 3 | persistence | — | 0.155354261 |
| delaware | 3 | local | 0.1 | 0.132775530 |
| delaware | 3 | pair | 0.01 | 0.125854200 |
| delaware | 1 | persistence | — | 0.037020677 |
| delaware | 1 | local | 0.1 | 0.029433797 |
| delaware | 1 | pair | 0.001 | 0.019252074 |

The independent source/SQL feature joins, augmented-design SVD fits, scalar forecasts and SQL metric checks pass216, 162 finite conditions. Maximum log-space discrepancy is 1.36e-14, below the declared 1e-8 tolerance. Twenty-three authored fixture methods pass. These checks do not establish operational availability or predictive value on final years.

Next: commit and freeze exact source, protocol, methods, code, fixtures and development-selection dependencies before computing final outcomes.
