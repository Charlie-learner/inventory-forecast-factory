def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = [max(float(value), 0.0) for value in history]
    recent = clean[-min(14, len(clean)):]
    estimate = float(sum(recent) / len(recent))
    return [estimate] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
