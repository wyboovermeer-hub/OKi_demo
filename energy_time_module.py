"""
OKi — Energy Time Awareness Module
Computes time remaining before battery reaches critical and shutdown thresholds.
All outputs are in hours. Safe-defaults everywhere — never raises on bad state.
"""

# ── Thresholds ────────────────────────────────────────────────────────────────
SOC_CRITICAL = 15.0       # % — point at which OKi escalates
SOC_SHUTDOWN = 10.0       # % — point at which system may cut out
CAPACITY_DEFAULT_AH = 200.0  # Ah — fallback if not declared in state
POST_BLACKOUT_HOURS = 48.0   # fixed survival planning window

MIN_CURRENT_A = 0.5       # A — below this, discharge rate is noise


# ── Core computation ──────────────────────────────────────────────────────────

def compute_energy_time(state: dict) -> None:
    """
    Read battery state and write time-remaining estimates into state["Energy"].

    If the battery is charging, time values are set to None (not applicable).
    If data is missing or current is negligible, values are set to None.
    """
    battery = state.get("Battery", {})
    energy = state.setdefault("Energy", {})

    soc = battery.get("SoC")           # float %
    current_a = battery.get("CurrentA")  # float A, positive = discharging
    capacity_ah = battery.get("CapacityAh", CAPACITY_DEFAULT_AH)

    # ── Guard: insufficient data ──────────────────────────────────────────────
    if soc is None or current_a is None or capacity_ah is None:
        _write_unknown(energy)
        return

    soc = float(soc)
    current_a = float(current_a)
    capacity_ah = float(capacity_ah)

    # ── Not discharging ───────────────────────────────────────────────────────
    if current_a < MIN_CURRENT_A:
        energy["TimeToCriticalHours"] = None
        energy["TimeToShutdownHours"] = None
        energy["PostBlackoutHours"] = POST_BLACKOUT_HOURS
        energy["DischargeRate"] = 0.0
        return

    # ── Discharge rate in % per hour ─────────────────────────────────────────
    # current_a / capacity_ah = fraction per hour → × 100 = % per hour
    discharge_rate_pct_per_hour = (current_a / capacity_ah) * 100.0

    energy["DischargeRate"] = round(discharge_rate_pct_per_hour, 3)

    # ── Time to thresholds ────────────────────────────────────────────────────
    energy["TimeToCriticalHours"] = _hours_to_threshold(
        soc, SOC_CRITICAL, discharge_rate_pct_per_hour
    )
    energy["TimeToShutdownHours"] = _hours_to_threshold(
        soc, SOC_SHUTDOWN, discharge_rate_pct_per_hour
    )
    energy["PostBlackoutHours"] = POST_BLACKOUT_HOURS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hours_to_threshold(
    current_soc: float,
    threshold_soc: float,
    discharge_rate: float,
) -> float | None:
    """
    Return hours until SoC reaches threshold_soc at the given discharge rate.
    Returns None if already at or below threshold, or if rate is negligible.
    """
    if current_soc <= threshold_soc:
        return 0.0
    if discharge_rate < 0.001:
        return None
    hours = (current_soc - threshold_soc) / discharge_rate
    return round(hours, 2)


def _write_unknown(energy: dict) -> None:
    energy["TimeToCriticalHours"] = None
    energy["TimeToShutdownHours"] = None
    energy["PostBlackoutHours"] = POST_BLACKOUT_HOURS
    energy["DischargeRate"] = None
