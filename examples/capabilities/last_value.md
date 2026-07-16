# Last-value inventory forecasting capability

- name: last_value
- task_type: inventory_forecasting
- description: Repeat the latest observed demand as a transparent baseline.
- template_name: last_value
- input_contract: Non-negative daily demand history and a positive forecast horizon.
- output_contract: Non-negative daily forecast and horizon-total target inventory.
- suitable_for: short_history
- metrics: inventory_cost, wape, rmse, smape, bias
- dependencies: pandas
- parameters: {}
- version: 1.1.0
- source_title: M5 accuracy competition results, findings, and conclusions
- source_url: https://www.sciencedirect.com/science/article/pii/S0169207021001874
- source_license: citation_only
- accessed_at: 2026-07-16
- confidence: 0.95
- review_status: source_reviewed
- evidence_refs: article benchmark discussion, inventory_agent/forecasting/models.py:12
