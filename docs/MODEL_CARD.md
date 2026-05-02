# Model Card

## Model Details

- **Name:** MLET Phase 5 Baseline Classifier
- **Version:** 1.0.0
- **Type:** Logistic Regression / MLP (PyTorch)
- **Framework:** Scikit-Learn, PyTorch
- **Training Date:** TBD
- **Authors:** Lucas Silva

## Intended Use

- **Primary use:** Classification task for the MLET Phase 5 Datathon
- **Out-of-scope:** Production deployment without drift monitoring in place

## Training Data

- **Source:** TBD (tracked via DVC)
- **Size:** TBD
- **Preprocessing:** Standard scaling, one-hot encoding (see `src/features/feature_engineering.py`)

## Evaluation Metrics

| Metric    | Value  |
|-----------|--------|
| Accuracy  | TBD    |
| F1        | TBD    |
| ROC-AUC   | TBD    |

## Ethical Considerations

- Model outputs should be reviewed before use in decisions affecting individuals.
- LGPD compliance: personal data is not used as a training feature without consent.

## Limitations

- Performance may degrade on out-of-distribution data.
- Drift should be monitored using Evidently + PSI thresholds defined in `configs/monitoring_config.yaml`.

## Caveats and Recommendations

- Retrain when PSI > 0.2 on any feature.
- MLflow tracks all runs with required tags: `model_version`, `dataset_version`, `author`, `environment`.
