# Separate v2 final comparison

The additional-gauge model has greater log-MSE skill than the local-history model in each of the four primary basin/year panels. Equal-panel skill versus persistence is 28.96% for the pair model and 15.32% for local history. Their difference is 13.64 percentage points of persistence-normalized skill, not a measured operational benefit.

This uses the separately specified 2020–2024 Approved-data cohort. Training is 2020–2021, development validation is 2022, and final evaluation is 2023–2024. The original 2020–2025 approval gate remains failed. The revised period was informed by the approval ledger before modelling; no original-vintage or blinded-collection claim follows.

| Primary panel | Days | Local skill (%) | Pair skill (%) | Difference (percentage points) | Conditional 90% interval for difference |
|---|---:|---:|---:|---:|---|
| mississippi--2023 | 365 | 10.60 | 35.87 | 25.26 | [15.89, 34.44] |
| mississippi--2024 | 366 | 15.45 | 30.76 | 15.31 | [5.16, 25.33] |
| susquehanna--2023 | 365 | 15.57 | 21.28 | 5.71 | [2.06, 9.63] |
| susquehanna--2024 | 366 | 19.66 | 27.94 | 8.28 | [5.21, 12.35] |

The exploratory 14-day circular block intervals describe within-year resampling conditional on these records. They do not give future-year or new-basin coverage. All 500 draws per panel and each replicate estimate are retained.

| Basin/year | Lag | Scenario | Qualifier support | Days | Pair minus local skill (percentage points) |
|---|---:|---|---|---:|---:|
| wisconsin 2023 | 3 | normal | all-approved | 365 | 48.09 |
| wisconsin 2023 | 3 | seven-day-outage | all-approved | 365 | 39.01 |
| wisconsin 2023 | 3 | normal | empty-qualifiers | 220 | 46.62 |
| wisconsin 2023 | 3 | seven-day-outage | empty-qualifiers | 220 | 39.33 |
| wisconsin 2024 | 3 | normal | all-approved | 366 | 35.24 |
| wisconsin 2024 | 3 | seven-day-outage | all-approved | 366 | 26.92 |
| wisconsin 2024 | 3 | normal | empty-qualifiers | 267 | 35.66 |
| wisconsin 2024 | 3 | seven-day-outage | empty-qualifiers | 267 | 25.02 |
| wisconsin 2023 | 1 | normal | all-approved | 365 | 22.75 |
| wisconsin 2023 | 1 | seven-day-outage | all-approved | 365 | 19.34 |
| wisconsin 2023 | 1 | normal | empty-qualifiers | 225 | 24.36 |
| wisconsin 2023 | 1 | seven-day-outage | empty-qualifiers | 225 | 22.01 |
| wisconsin 2024 | 1 | normal | all-approved | 366 | 14.29 |
| wisconsin 2024 | 1 | seven-day-outage | all-approved | 366 | 11.45 |
| wisconsin 2024 | 1 | normal | empty-qualifiers | 270 | 14.77 |
| wisconsin 2024 | 1 | seven-day-outage | empty-qualifiers | 270 | 11.02 |
| delaware 2023 | 3 | normal | all-approved | 365 | 4.18 |
| delaware 2023 | 3 | seven-day-outage | all-approved | 365 | 4.04 |
| delaware 2023 | 3 | normal | empty-qualifiers | 197 | 1.80 |
| delaware 2023 | 3 | seven-day-outage | empty-qualifiers | 197 | 2.26 |
| delaware 2024 | 3 | normal | all-approved | 366 | 2.19 |
| delaware 2024 | 3 | seven-day-outage | all-approved | 366 | 1.98 |
| delaware 2024 | 3 | normal | empty-qualifiers | 64 | 3.46 |
| delaware 2024 | 3 | seven-day-outage | empty-qualifiers | 64 | 0.70 |
| delaware 2023 | 1 | normal | all-approved | 365 | 23.98 |
| delaware 2023 | 1 | seven-day-outage | all-approved | 365 | 20.75 |
| delaware 2023 | 1 | normal | empty-qualifiers | 205 | 13.11 |
| delaware 2023 | 1 | seven-day-outage | empty-qualifiers | 205 | 9.74 |
| delaware 2024 | 1 | normal | all-approved | 366 | 21.54 |
| delaware 2024 | 1 | seven-day-outage | all-approved | 366 | 18.05 |
| delaware 2024 | 1 | normal | empty-qualifiers | 86 | 27.68 |
| delaware 2024 | 1 | seven-day-outage | empty-qualifiers | 86 | 12.21 |
| susquehanna 2023 | 3 | normal | all-approved | 365 | 5.71 |
| susquehanna 2023 | 3 | seven-day-outage | all-approved | 365 | 5.53 |
| susquehanna 2023 | 3 | normal | empty-qualifiers | 345 | 6.26 |
| susquehanna 2023 | 3 | seven-day-outage | empty-qualifiers | 345 | 4.98 |
| susquehanna 2024 | 3 | normal | all-approved | 366 | 8.28 |
| susquehanna 2024 | 3 | seven-day-outage | all-approved | 366 | 6.98 |
| susquehanna 2024 | 3 | normal | empty-qualifiers | 363 | 8.24 |
| susquehanna 2024 | 3 | seven-day-outage | empty-qualifiers | 363 | 6.94 |
| susquehanna 2023 | 1 | normal | all-approved | 365 | 27.51 |
| susquehanna 2023 | 1 | seven-day-outage | all-approved | 365 | 19.34 |
| susquehanna 2023 | 1 | normal | empty-qualifiers | 345 | 28.08 |
| susquehanna 2023 | 1 | seven-day-outage | empty-qualifiers | 345 | 17.94 |
| susquehanna 2024 | 1 | normal | all-approved | 366 | 25.81 |
| susquehanna 2024 | 1 | seven-day-outage | all-approved | 366 | 23.67 |
| susquehanna 2024 | 1 | normal | empty-qualifiers | 362 | 25.82 |
| susquehanna 2024 | 1 | seven-day-outage | empty-qualifiers | 362 | 23.66 |
| mississippi 2023 | 3 | normal | all-approved | 365 | 25.26 |
| mississippi 2023 | 3 | seven-day-outage | all-approved | 365 | 21.77 |
| mississippi 2023 | 3 | normal | empty-qualifiers | 270 | 29.46 |
| mississippi 2023 | 3 | seven-day-outage | empty-qualifiers | 270 | 26.20 |
| mississippi 2024 | 3 | normal | all-approved | 366 | 15.31 |
| mississippi 2024 | 3 | seven-day-outage | all-approved | 366 | 10.13 |
| mississippi 2024 | 3 | normal | empty-qualifiers | 256 | 21.73 |
| mississippi 2024 | 3 | seven-day-outage | empty-qualifiers | 256 | 20.46 |
| mississippi 2023 | 1 | normal | all-approved | 365 | 8.59 |
| mississippi 2023 | 1 | seven-day-outage | all-approved | 365 | 7.59 |
| mississippi 2023 | 1 | normal | empty-qualifiers | 274 | 11.24 |
| mississippi 2023 | 1 | seven-day-outage | empty-qualifiers | 274 | 9.10 |
| mississippi 2024 | 1 | normal | all-approved | 366 | 3.99 |
| mississippi 2024 | 1 | seven-day-outage | all-approved | 366 | 1.83 |
| mississippi 2024 | 1 | normal | empty-qualifiers | 262 | 5.56 |
| mississippi 2024 | 1 | seven-day-outage | empty-qualifiers | 262 | 6.46 |

Every one of the 192 model-panel metric rows and 59,154 predictions remains available, including development-basin context, both lags, both outage scenarios, both qualifier rules, log/cfs MAE/MSE/RMSE, cfs signed error, train-mean-normalized cfs RMSE, clipping and fallback counts. Denominators can change with the qualifier rule; models within each panel always share dates.

The fixed selection and 34 analytical dependencies were committed at 085b5a5 before these outcomes. The independent SQL/SVD/scalar checker passes 831,539 finite final conditions. It also checks exact retained bootstrap draws and independently recomputed percentile endpoints. No new final-set selection occurred.

Use the result to justify a prospective availability/fidelity pilot for the specific gauge pair, rather than a gauge purchase, evacuation decision or general network claim. The synthetic observation lags and seven-day outages are not measured telemetry behavior. Costs, original publication vintages, physical flood-impact labels, deployment and realized benefit are unmeasured.
