# Seasonal-naive inventory forecasting capability

- name: seasonal_naive
- task_type: inventory_forecasting
- description: Repeat the latest weekly pattern over the forecast horizon.
- template_name: seasonal_naive
- input_contract: Non-negative daily demand history and a positive forecast horizon.
- output_contract: Non-negative daily forecast and horizon-total target inventory.
- suitable_for: weekly_seasonal, stable
- metrics: inventory_cost, wape, rmse
- dependencies: pandas
- parameters: {"period": 7}
- version: 1.1.0
- source_title: M5 accuracy competition results, findings, and conclusions
- source_url: https://www.sciencedirect.com/science/article/pii/S0169207021001874
- source_license: citation_only
- accessed_at: 2026-07-16
- confidence: 0.95
- review_status: source_reviewed
- evidence_refs: article seasonal-naive benchmark discussion, inventory_agent/forecasting/models.py:36

