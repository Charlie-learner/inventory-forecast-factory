# Ridge lag-regression inventory forecasting capability

- name: ridge_lag
- task_type: inventory_forecasting
- description: Fit regularized autoregression on recent demand lags and forecast recursively.
- template_name: ridge_lag
- input_contract: Dense non-negative daily history with enough observations for lag construction.
- output_contract: Non-negative daily forecast and horizon-total target inventory.
- suitable_for: trend, dense, volatile
- metrics: inventory_cost, wape, rmse
- dependencies: numpy, pandas, scikit-learn
- parameters: {"lags": 14, "alpha": 1.0}
- version: 1.1.0
- source_title: scikit-learn Ridge regression API
- source_url: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html
- source_license: BSD-3-Clause documentation and citation metadata
- accessed_at: 2026-07-16
- confidence: 0.9
- review_status: source_reviewed
- evidence_refs: Ridge L2 objective, inventory_agent/forecasting/models.py:84

