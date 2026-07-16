# Moving-average inventory forecasting capability

- name: moving_average
- task_type: inventory_forecasting
- description: Forecast stable demand with the mean of the most recent observations.
- template_name: moving_average
- input_contract: Non-negative daily demand history and a positive forecast horizon.
- output_contract: Non-negative daily forecast and horizon-total target inventory.
- suitable_for: stable, short_history
- metrics: inventory_cost, wape, rmse, smape, bias
- dependencies: pandas
- parameters: {"window": 14}
- version: 1.1.0
- source_title: The accuracy of intermittent demand estimates
- source_url: https://www.sciencedirect.com/science/article/pii/S0169207004000792
- source_license: citation_only
- accessed_at: 2026-07-16
- confidence: 0.9
- review_status: source_reviewed
- evidence_refs: SMA benchmark description, inventory_agent/forecasting/models.py:22
