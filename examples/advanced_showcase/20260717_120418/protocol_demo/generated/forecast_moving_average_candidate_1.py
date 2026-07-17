import pandas as pd

def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = pd.to_numeric(pd.Series(history), errors="coerce").dropna().clip(lower=0)
    if clean.empty:
        raise ValueError("empty history")
    estimate = float(clean.iloc[-min(14, len(clean)):].mean())
    return [estimate for _ in range(horizon)]

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
