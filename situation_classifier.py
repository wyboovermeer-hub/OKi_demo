"""
OKi — Situation Classifier v2
Derives SituationType and DecisionWindow from combined system state.
CRITICAL_COUNTDOWN always wins — no other state may override it.
"""

# ── Priority order (highest → lowest) ────────────────────────────────────────
SITUATION_PRIORITY = [
    "CRITICAL_COUNTDOWN",
    "RECOVERY_FAILURE",
    "DIAGNOSTIC",
    "LOW_ENERGY",
    "NORMAL",
]

ATTENTION_PRIORITY = {s: i for i, s in enumerate(SITUATION_PRIORITY)}

# ── Thresholds ────────────────────────────────────────────────────────────────
SOC_LOW                  = 30.0
SHUTDOWN_HOURS_CRITICAL  = 3.0
WINDOW_LIMITED_THRESHOLD = 3.0   # hours — above this: OPEN
WINDOW_CLOSING_THRESHOLD = 1.0   # hours — below this: CLOSING


# ============================================================
# SITUATION TYPE
# ============================================================

def evaluate_situation_type(state: dict) -> None:
    """
    Evaluate all conditions and write state["System"]["SituationType"].
    CRITICAL_COUNTDOWN cannot be overridden by any other condition.
    """
    system     = state.setdefault("System", {})
    battery    = state.get("Battery", {})
    energy     = state.get("Energy", {})
    generator  = state.get("Generator", {})
    solar      = state.get("Solar", {})
    diagnostic = state.get("Diagnostic", {})

    soc          = float(battery.get("SoC", 100))
    discharging  = battery.get("Status") == "DISCHARGING"
    shore_power  = system.get("ShorePower", False)
    solar_watts  = float(solar.get("InputWatts", 0) or solar.get("Power", 0) or 0)
    gen_expected = generator.get("Expected", False)
    gen_running  = generator.get("Running", False)
    diag_active  = bool(diagnostic.get("Step"))
    shutdown_h   = energy.get("TimeToShutdownHours")

    situation = "NORMAL"

    if soc < SOC_LOW:
        situation = "LOW_ENERGY"

    if (
        soc < SOC_LOW
        and discharging
        and not shore_power
        and solar_watts < 50
        and gen_expected
        and not gen_running
    ):
        situation = "RECOVERY_FAILURE"

    if diag_active:
        situation = "DIAGNOSTIC"

    # Unconditional override — must remain last
    if shutdown_h is not None and float(shutdown_h) < SHUTDOWN_HOURS_CRITICAL:
        situation = "CRITICAL_COUNTDOWN"

    system["SituationType"] = situation


# ============================================================
# DECISION WINDOW
# ============================================================

def evaluate_decision_window(state: dict) -> None:
    """
    Derive state["System"]["DecisionWindow"] from TimeToShutdownHours.

    OPEN     — no time pressure (None or > 3 h)
    LIMITED  — 1–3 hours remaining
    CLOSING  — under 1 hour remaining
    """
    system     = state.setdefault("System", {})
    shutdown_h = state.get("Energy", {}).get("TimeToShutdownHours")

    if shutdown_h is None or float(shutdown_h) > WINDOW_LIMITED_THRESHOLD:
        system["DecisionWindow"] = "OPEN"
    elif float(shutdown_h) >= WINDOW_CLOSING_THRESHOLD:
        system["DecisionWindow"] = "LIMITED"
    else:
        system["DecisionWindow"] = "CLOSING"
