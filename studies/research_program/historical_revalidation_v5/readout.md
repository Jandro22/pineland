# Frozen v5 historical confrontation

Computation status: **failed**; stage: `afghanistan_full`.

No calibration, mechanism modification, or COIN inference is licensed.

## Nepal

Verdict: `simple_models_not_beaten_on_all_holdouts`.

| Holdout | Pineland Brier | Best simple Brier | Pineland log score | Best simple log score | Pass both |
|---|---:|---:|---:|---:|---|
| geographic_validation | 0.157781 | 0.133062 | -3.263468 | -0.436563 | False |
| strict_joint_holdout | 0.054855 | 0.052069 | -1.127114 | -0.214576 | False |
| temporal_validation | 0.058140 | 0.052764 | -1.203564 | -0.204840 | False |

Afghanistan: historical competition pending.

## Nepal theory diagnostics

The v4/v5 rows, targets, splits and simple predictions are identical. These diagnostics do not override the primary gate.

| Split | v4 recorded AUC | v5 recorded AUC | v5 latent AUC | v5 prior control AUC | v5 Brier improvement over v4 |
|---|---:|---:|---:|---:|---:|
| geographic_validation | 0.499696 | 0.498245 | 0.499082 | 0.468103 | -0.000096 |
| strict_joint_holdout | 0.498330 | 0.503075 | 0.507555 | 0.614735 | 0.000118 |
| temporal_validation | 0.502041 | 0.496819 | 0.494062 | 0.636127 | -0.000155 |
| training | 0.499672 | 0.501280 | 0.504282 | 0.592567 | 0.000180 |

The control signal is model-implied state, not independently validated organizational capacity. Aggregate action failures cannot identify local belief or support errors.
