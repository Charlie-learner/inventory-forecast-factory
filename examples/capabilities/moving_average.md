# Moving-average inventory forecasting capability

- name: moving_average
- task_type: inventory_forecasting
- description: Forecast stable demand with the mean of the most recent observations.
- template_name: moving_average
- input_contract: Non-negative daily demand history and a positive forecast horizon.
- output_contract: Non-negative daily forecast and horizon-total target inventory.
- suitable_for: stable, short_history
- metrics: inventory_cost, wape, rmse
- dependencies: pandas
- parameters: {"window": 14}
- version: 1.1.0
