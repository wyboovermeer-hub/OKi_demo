"""
energy_forecast_engine.py — OKi Energy Forecast Engine
Version: 1.0
Spec: OKi 002 Claude Implementation Brief v1.0 — FILE 4

Responsibilities:
    - Calculate net energy flow (sources minus consumption)
    - Predict battery trajectory over next 0–8 hours
    - Compute time-to-critical and time-to-shutdown
    - Integrate solar forecast from solar_input_module
    - Integrate operator strategy from energy_strategy_engine
    - Recalculate dynamically when inputs change

Called by engine_cycle().
Reads:  state["Battery"], state["Solar"], state["Strategy"], state["AC"]
Writes: state["EnergyForecast"]
"""

from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

# Battery thresholds
SOC_CRITICAL        = 15.0    # % — shutdown warning level
SOC_LOW             = 20.0    # % — advisory level
SOC_SHUTDOWN        = 10.0    # % — assumed BMS cutoff

# Simulation
FORECAST_HOURS      = 8       # how far ahead to simulate
SIMULATION_STEPS_H  = 0.25    # 15-minute resolution

# Default consumption when no real data available
DEFAULT_CONSUMPTION_W = 200.0

# Battery capacity (vessel default — override in vessel config)
DEFAULT_BATTERY_CAPACITY_WH = 20000.0   # 20kWh — typical hybrid vessel


# ============================================================
# MAIN FORECAST FUNCTION
# ============================================================

def compute_energy_forecast(state: dict) -> None:
    """
    Calculate time-to-critical and time-to-shutdown.
    Simulate battery trajectory over next 8 hours.

    Writes to state["EnergyForecast"]:
        NetPowerW           — current net power flow (W, + = gaining, - = losing)
        ConsumptionW        — current total consumption (W)
        ChargingSourcesW    — current total charging (W)
        TimeToCriticalH     — hours until SOC reaches critical level
        TimeToShutdownH     — hours until SOC reaches shutdown level
        TimeToCriticalStr   — human string e.g. "5h 40m"
        TimeToShutdownStr   — human string e.g. "7h 20m"
        Trajectory          — list of {step_h, predicted_soc}
        ForecastSummary     — human-readable summary string
        Confidence          — LOW / MEDIUM / HIGH
    """
    forecast = _get_section(state, "EnergyForecast")

    # ----------------------------------------------------------------
    # Step 1 — Gather current state
    # ----------------------------------------------------------------
    battery   = state.get("Battery") or {}
    solar_s   = state.get("Solar")   or {}
    ac        = state.get("AC")       or {}
    strategy  = state.get("Strategy") or {}

    soc         = _safe_float(battery.get("SoC"), 50.0)
    voltage     = _safe_float(battery.get("Voltage"), 24.0)
    dc_current  = _safe_float(battery.get("Current"), 0.0)

    # Battery capacity — from vessel config or default
    capacity_wh = _safe_float(
        (state.get("VesselConfig") or {}).get("BatteryCapacityWh"),
        DEFAULT_BATTERY_CAPACITY_WH
    )

    # ----------------------------------------------------------------
    # Step 2 — Current energy flows
    # ----------------------------------------------------------------
    consumption_w   = _estimate_consumption(state, dc_current, voltage)
    charging_w      = _estimate_charging(state, solar_s, ac, strategy)
    net_power_w     = charging_w - consumption_w

    forecast["ConsumptionW"]     = round(consumption_w, 1)
    forecast["ChargingSourcesW"] = round(charging_w, 1)
    forecast["NetPowerW"]        = round(net_power_w, 1)

    # ----------------------------------------------------------------
    # Step 3 — Simulate battery trajectory
    # ----------------------------------------------------------------
    trajectory      = []
    current_soc     = soc
    remaining_wh    = (soc / 100.0) * capacity_wh
    time_critical_h = None
    time_shutdown_h = None

    solar_forecast  = solar_s.get("Forecast") or []

    steps = int(FORECAST_HOURS / SIMULATION_STEPS_H)

    for i in range(steps + 1):
        step_h = i * SIMULATION_STEPS_H

        # Get solar power at this future point from solar forecast
        solar_w_at_step = _solar_at_hour(solar_forecast, step_h, charging_w)

        # Net energy this step
        net_w_step      = solar_w_at_step - consumption_w
        delta_wh        = net_w_step * SIMULATION_STEPS_H
        remaining_wh    = max(0.0, remaining_wh + delta_wh)
        current_soc     = min(100.0, (remaining_wh / capacity_wh) * 100.0)

        trajectory.append({
            "step_h":       round(step_h, 2),
            "predicted_soc": round(current_soc, 1),
            "solar_w":      round(solar_w_at_step, 1),
            "net_w":        round(net_w_step, 1),
        })

        # Record first crossing of thresholds
        if time_critical_h is None and current_soc <= SOC_CRITICAL:
            time_critical_h = step_h

        if time_shutdown_h is None and current_soc <= SOC_SHUTDOWN:
            time_shutdown_h = step_h

    forecast["Trajectory"] = trajectory

    # ----------------------------------------------------------------
    # Step 4 — Time-to outputs
    # ----------------------------------------------------------------
    forecast["TimeToCriticalH"]   = time_critical_h
    forecast["TimeToShutdownH"]   = time_shutdown_h
    forecast["TimeToCriticalStr"] = _format_hours(time_critical_h) if time_critical_h else "Beyond forecast window"
    forecast["TimeToShutdownStr"] = _format_hours(time_shutdown_h) if time_shutdown_h else "Beyond forecast window"

    # ----------------------------------------------------------------
    # Step 5 — Summary and confidence
    # ----------------------------------------------------------------
    forecast["ForecastSummary"] = _build_summary(
        soc, net_power_w, charging_w, consumption_w,
        solar_s, time_critical_h, time_shutdown_h
    )
    forecast["Confidence"] = _assess_confidence(state, solar_s)


# ============================================================
# ENERGY FLOW ESTIMATION
# ============================================================

def _estimate_consumption(state: dict, dc_current: float, voltage: float) -> float:
    """
    Estimate current consumption in watts.
    Uses DC bus current if available, otherwise default.
    Consumption = positive value (energy leaving battery).
    """
    ac = state.get("AC") or {}

    # If discharging, DC power = direct consumption proxy
    if dc_current < -0.5:
        dc_power = abs(dc_current * voltage)
    else:
        dc_power = 0.0

    # Add AC load from Shelly if available
    ac_power = _safe_float(ac.get("GridPower"), 0.0)

    if dc_power > 0:
        return dc_power
    elif ac_power > 0:
        return ac_power
    else:
        return DEFAULT_CONSUMPTION_W


def _estimate_charging(state: dict, solar: dict, ac: dict, strategy: dict) -> float:
    """
    Estimate current total charging input in watts.
    Sources: solar MPPT, shore power charger, DC-DC, generator.
    """
    total_w = 0.0

    # Solar MPPT
    solar_w = _safe_float(solar.get("Power"), 0.0)
    if solar.get("State") not in ("NIGHT", None):
        total_w += solar_w

    # Shore power (AC charger) — if shore connected and charging
    battery = state.get("Battery") or {}
    dc_current = _safe_float(battery.get("Current"), 0.0)
    voltage    = _safe_float(battery.get("Voltage"), 24.0)

    if dc_current > 0.5:
        # Battery is charging — total source = DC power
        charging_from_dc = dc_current * voltage
        # Subtract solar if already counted
        shore_contribution = max(0.0, charging_from_dc - solar_w)
        total_w += shore_contribution

    # Operator strategy boost (DC-DC, generator planned)
    strategy_type = strategy.get("Selected")
    if strategy_type == "DC_DC":
        # DC-DC charger contribution estimate
        total_w += _safe_float(strategy.get("ExpectedContributionW"), 500.0)
    elif strategy_type == "GENERATOR":
        total_w += _safe_float(strategy.get("ExpectedContributionW"), 2000.0)

    return total_w


def _solar_at_hour(forecast: list, hour: float, current_solar: float) -> float:
    """
    Interpolate solar power from forecast at a given future hour.
    If no forecast available, returns current_solar until sunset then 0.
    """
    if not forecast:
        return current_solar

    # Find surrounding forecast points
    lower = None
    upper = None
    for f in forecast:
        if f["hour"] <= hour:
            lower = f
        elif upper is None:
            upper = f
            break

    if lower is None:
        return current_solar
    if upper is None:
        return float(lower["predicted_w"])

    # Linear interpolation between hours
    span  = upper["hour"] - lower["hour"]
    if span == 0:
        return float(lower["predicted_w"])
    frac  = (hour - lower["hour"]) / span
    return lower["predicted_w"] + frac * (upper["predicted_w"] - lower["predicted_w"])


# ============================================================
# SUMMARY AND CONFIDENCE
# ============================================================

def _build_summary(
    soc: float,
    net_w: float,
    charging_w: float,
    consumption_w: float,
    solar: dict,
    time_critical: Optional[float],
    time_shutdown: Optional[float],
) -> str:
    """Build the human-readable energy forecast summary shown in UI."""

    lines = []

    solar_w   = _safe_float(solar.get("Power"), 0.0)
    solar_str = solar.get("CountdownString") or ""

    if solar_w > 10:
        lines.append(f"Solar input: {solar_w:.0f}W")

    if solar_str:
        lines.append(solar_str)

    if net_w >= 0:
        lines.append(f"Net: +{net_w:.0f}W — battery gaining energy")
    else:
        lines.append(f"Net: {net_w:.0f}W — battery losing energy")

    if time_critical:
        lines.append(f"Time to critical battery: {_format_hours(time_critical)}")

    if time_shutdown:
        lines.append(f"Estimated time to shutdown: {_format_hours(time_shutdown)}")
    else:
        lines.append("Battery sufficient beyond 8-hour forecast window")

    return " | ".join(lines)


def _assess_confidence(state: dict, solar: dict) -> str:
    """
    Rate forecast confidence based on data quality.
    HIGH  = real sensor data, solar active and stable
    MEDIUM = some data missing or estimated
    LOW   = mostly defaults, no sensor confirmation
    """
    battery = state.get("Battery") or {}
    issues  = 0

    if battery.get("SoC") is None:
        issues += 2
    if battery.get("Current") is None:
        issues += 1
    if solar.get("State") is None:
        issues += 1
    if solar.get("Anomaly"):
        issues += 1

    if issues == 0:
        return "HIGH"
    elif issues <= 2:
        return "MEDIUM"
    else:
        return "LOW"


# ============================================================
# HELPERS
# ============================================================

def _get_section(state: dict, key: str) -> dict:
    if key not in state or state[key] is None:
        state[key] = {}
    return state[key]


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _format_hours(hours: float) -> str:
    """Format decimal hours as human string."""
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OKi energy_forecast_engine.py — Dev Test")
    print("=" * 60)

    def run(label, state):
        compute_energy_forecast(state)
        f = state["EnergyForecast"]
        print(f"\n📋 {label}")
        print(f"   Consumption    : {f['ConsumptionW']}W")
        print(f"   Charging       : {f['ChargingSourcesW']}W")
        print(f"   Net            : {f['NetPowerW']}W")
        print(f"   To critical    : {f['TimeToCriticalStr']}")
        print(f"   To shutdown    : {f['TimeToShutdownStr']}")
        print(f"   Confidence     : {f['Confidence']}")
        print(f"   Summary        : {f['ForecastSummary']}")
        traj = f["Trajectory"]
        sample = [t for t in traj if t["step_h"] in (0, 1, 2, 4, 6, 8)]
        print(f"   Trajectory SoC : {[t['predicted_soc'] for t in sample]}")

    # Test 1 — Good solar, healthy battery
    run("Good solar, SoC 75%", {
        "Battery": {"SoC": 75, "Voltage": 26.5, "Current": 5.0},
        "Solar":   {"Power": 850, "State": "ACTIVE",
                    "Forecast": [{"hour": h, "predicted_w": max(0, 850 - h*120)} for h in range(9)],
                    "CountdownString": "☀️ Solar active — 850W — sunset in 4h 20m"},
        "AC":      {"GridVoltage": 0, "GridPower": 0},
        "Strategy": {},
    })

    # Test 2 — No solar, discharging, critical soon
    run("No solar, discharging fast, SoC 25%", {
        "Battery": {"SoC": 25, "Voltage": 24.2, "Current": -18.0},
        "Solar":   {"Power": 0, "State": "NIGHT", "Forecast": []},
        "AC":      {"GridVoltage": 0},
        "Strategy": {},
    })

    # Test 3 — Shore power, charging
    run("Shore power charging, SoC 40%", {
        "Battery": {"SoC": 40, "Voltage": 26.8, "Current": 15.0},
        "Solar":   {"Power": 0, "State": "NIGHT", "Forecast": []},
        "AC":      {"GridVoltage": 230, "GridPower": 380},
        "Strategy": {},
    })

    # Test 4 — Solar + DC-DC strategy
    run("Solar + DC-DC strategy selected", {
        "Battery": {"SoC": 30, "Voltage": 24.5, "Current": -5.0},
        "Solar":   {"Power": 400, "State": "ACTIVE",
                    "Forecast": [{"hour": h, "predicted_w": max(0, 400 - h*80)} for h in range(9)]},
        "AC":      {},
        "Strategy": {"Selected": "DC_DC", "ExpectedContributionW": 500},
    })

    print("\n" + "=" * 60)
    print("Test complete.")
