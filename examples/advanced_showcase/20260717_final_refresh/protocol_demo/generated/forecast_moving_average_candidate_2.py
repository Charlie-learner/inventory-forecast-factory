import numpy as np

def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = np.asarray([max(float(value), 0.0) for value in history], dtype=float)
    estimate = float(clean[-min(14, clean.size):].mean())
    return np.repeat(estimate, horizon).astype(float).tolist()

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
