"""
energy_strategy_engine.py — OKi Energy Strategy Engine
Version: 1.0
Spec: OKi 002 Claude Implementation Brief v1.0 — FILE 2

Responsibilities:
    - Track operator-selected energy recovery strategy
    - Validate whether selected strategy is executing as expected
    - Detect strategy failure and trigger follow-up questions
    - Feed strategy into energy forecast engine
    - Update state when strategy succeeds or fails

Strategies:
    SOLAR       — rely on solar input
    DC_DC       — charge house from propulsion bank via DC-DC
    GENERATOR   — start generator later
    REDUCE      — reduce consumption
    INVESTIGATE — operator is investigating
    NONE        — no strategy selected

Called by engine_cycle() after solar_input_module and before operator_question_engine.
Reads:  state["Strategy"], state["Solar"], state["Battery"], state["AC"]
Writes: state["Strategy"] (enriched)
"""

from datetime import datetime, timezone
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

# How long to wait before checking if strategy is working (minutes)
STRATEGY_VALIDATION_DELAY_MIN   = 5

# Thresholds for declaring strategy failure
SOLAR_STRATEGY_MIN_W            = 50.0     # Solar must produce at least this
REDUCE_STRATEGY_MAX_CURRENT_A   = -5.0     # Current must be less negative (load reduced)
DCDC_STRATEGY_MIN_CURRENT_A     = 2.0      # Battery must be gaining current
GENERATOR_STRATEGY_MIN_CURRENT_A= 5.0      # Generator should push significant current

# How long before a failing strategy is flagged (minutes)
STRATEGY_FAILURE_GRACE_MIN      = 10


# ============================================================
# KNOWN STRATEGIES
# ============================================================

STRATEGY_OPTIONS = {
    "SOLAR":       "Use solar input",
    "DC_DC":       "Use DC-DC charging (house ← propulsion)",
    "GENERATOR":   "Start generator",
    "REDUCE":      "Reduce consumption",
    "INVESTIGATE": "Investigate the situation",
    "NONE":        "No strategy selected",
}


# ============================================================
# MAIN FUNCTION
# ============================================================

def evaluate_strategy(state: dict) -> None:
    """
    Main entry point. Called once per engine cycle.

    If no strategy is selected: no action.
    If strategy is selected:
        1. Wait for validation delay
        2. Check if strategy is executing
        3. Flag failure if not working within grace period
        4. Update strategy status
    """
    strategy = _get_section(state, "Strategy")
    selected = strategy.get("Selected")

    if not selected or selected == "NONE":
        strategy["Status"]        = "NONE"
        strategy["FailureReason"] = None
        strategy["FollowUpNeeded"] = False
        return

    now = datetime.now(timezone.utc).timestamp()

    # Record when strategy was set
    if strategy.get("StartedAt") is None:
        strategy["StartedAt"]    = now
        strategy["Status"]       = "WAITING"
        strategy["FailureReason"]= None
        strategy["FollowUpNeeded"] = False
        return

    elapsed_min = (now - float(strategy["StartedAt"])) / 60.0

    # Wait before validating
    if elapsed_min < STRATEGY_VALIDATION_DELAY_MIN:
        strategy["Status"] = "WAITING"
        return

    # Validate execution
    success, reason = _validate_strategy(state, selected)

    if success:
        strategy["Status"]         = "ACTIVE"
        strategy["FailureReason"]  = None
        strategy["FollowUpNeeded"] = False
    else:
        # Check if within grace period
        if elapsed_min < STRATEGY_VALIDATION_DELAY_MIN + STRATEGY_FAILURE_GRACE_MIN:
            strategy["Status"] = "MONITORING"
        else:
            strategy["Status"]         = "FAILED"
            strategy["FailureReason"]  = reason
            strategy["FollowUpNeeded"] = True


def select_strategy(state: dict, strategy_key: str) -> bool:
    """
    Called when operator selects a strategy via UI.
    Returns True if strategy key is valid.
    """
    if strategy_key not in STRATEGY_OPTIONS:
        return False

    strategy = _get_section(state, "Strategy")
    strategy["Selected"]       = strategy_key
    strategy["Label"]          = STRATEGY_OPTIONS[strategy_key]
    strategy["StartedAt"]      = None   # reset timer
    strategy["Status"]         = "WAITING"
    strategy["FailureReason"]  = None
    strategy["FollowUpNeeded"] = False
    strategy["SelectedAt"]     = datetime.now(timezone.utc).isoformat()
    return True


def clear_strategy(state: dict) -> None:
    """Clear current strategy — called when issue resolved."""
    strategy = _get_section(state, "Strategy")
    strategy["Selected"]        = "NONE"
    strategy["Label"]           = None
    strategy["StartedAt"]       = None
    strategy["Status"]          = "NONE"
    strategy["FailureReason"]   = None
    strategy["FollowUpNeeded"]  = False


# ============================================================
# STRATEGY VALIDATION
# ============================================================

def _validate_strategy(state: dict, selected: str) -> tuple:
    """
    Check if the selected strategy is producing the expected result.
    Returns (success: bool, failure_reason: str | None)
    """
    battery = state.get("Battery") or {}
    solar   = state.get("Solar")   or {}
    current = _safe_float(battery.get("Current"), 0.0)

    if selected == "SOLAR":
        return _validate_solar(solar)

    elif selected == "DC_DC":
        if current >= DCDC_STRATEGY_MIN_CURRENT_A:
            return True, None
        return False, (
            f"DC-DC strategy selected but battery current is {current:.1f}A. "
            "Is the DC-DC charger active?"
        )

    elif selected == "GENERATOR":
        if current >= GENERATOR_STRATEGY_MIN_CURRENT_A:
            return True, None
        return False, (
            "Generator strategy selected but no significant charging detected. "
            "Has the generator been started?"
        )

    elif selected == "REDUCE":
        if current >= REDUCE_STRATEGY_MAX_CURRENT_A:
            return True, None
        return False, (
            f"Load reduction selected but discharge rate is still {current:.1f}A. "
            "Which loads have been turned off?"
        )

    elif selected == "INVESTIGATE":
        # Investigating — always valid, no expected outcome
        return True, None

    return True, None


def _validate_solar(solar: dict) -> tuple:
    """Validate solar strategy."""
    state_str = solar.get("State")
    power_w   = _safe_float(solar.get("Power"), 0.0)
    anomaly   = bool(solar.get("Anomaly", False))
    anomaly_r = solar.get("AnomalyReason") or ""

    if state_str == "NIGHT":
        return False, (
            "Solar strategy selected but it is currently night. "
            "Solar input is not available until sunrise."
        )

    if anomaly:
        return False, f"Solar anomaly detected — {anomaly_r}"

    if power_w < SOLAR_STRATEGY_MIN_W:
        return False, (
            f"Solar input is only {power_w:.0f}W — below minimum useful contribution. "
            "Check panels or consider alternative strategy."
        )

    sunset_warn = solar.get("SunsetWarning")
    if sunset_warn == "CRITICAL":
        mins = solar.get("MinutesToSunset", 0)
        return False, (
            f"Solar strategy selected but sunset is in {mins} minutes. "
            "Plan alternative strategy now."
        )

    return True, None


# ============================================================
# STRATEGY FOLLOW-UP QUESTION BUILDER
# ============================================================

def build_followup_question(state: dict) -> Optional[dict]:
    """
    If strategy has failed, build the follow-up question for
    operator_question_engine to display.

    Returns question dict or None.
    """
    strategy = state.get("Strategy") or {}

    if not strategy.get("FollowUpNeeded"):
        return None

    selected = strategy.get("Selected", "NONE")
    reason   = strategy.get("FailureReason", "Strategy not executing as expected.")

    if selected == "SOLAR":
        return {
            "text":    f"Solar input is lower than expected. {reason} What is the situation?",
            "options": ["Panels are shaded", "Will switch to alternative", "Investigating"],
            "context": "STRATEGY_FOLLOWUP",
            "strategy": selected,
        }

    elif selected == "DC_DC":
        return {
            "text":    f"DC-DC charging not confirmed. {reason}",
            "options": ["Now activating", "Will use solar instead", "Investigating"],
            "context": "STRATEGY_FOLLOWUP",
            "strategy": selected,
        }

    elif selected == "GENERATOR":
        return {
            "text":    f"Generator not detected. {reason}",
            "options": ["Starting now", "Will use solar instead", "Investigating"],
            "context": "STRATEGY_FOLLOWUP",
            "strategy": selected,
        }

    elif selected == "REDUCE":
        return {
            "text":    f"Load reduction not confirmed. {reason}",
            "options": ["Loads being reduced now", "Cannot reduce further", "Investigating"],
            "context": "STRATEGY_FOLLOWUP",
            "strategy": selected,
        }

    return {
        "text":    f"Strategy '{selected}' is not executing as expected. {reason}",
        "options": ["Situation understood", "Investigating", "Need help"],
        "context": "STRATEGY_FOLLOWUP",
        "strategy": selected,
    }


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


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":
    import time as _time
    print("=" * 60)
    print("OKi energy_strategy_engine.py — Dev Test")
    print("=" * 60)

    def run(label, state, strategy_key=None):
        if strategy_key:
            select_strategy(state, strategy_key)
        evaluate_strategy(state)
        s = state.get("Strategy", {})
        print(f"\n📋 {label}")
        print(f"   Selected       : {s.get('Selected')}")
        print(f"   Status         : {s.get('Status')}")
        print(f"   FollowUp       : {s.get('FollowUpNeeded')}")
        print(f"   FailureReason  : {s.get('FailureReason') or 'none'}")
        fq = build_followup_question(state)
        if fq:
            print(f"   Follow-up Q    : {fq['text']}")
            print(f"   Options        : {fq['options']}")

    # Test 1 — Solar strategy, solar working
    run("Solar strategy — solar active 850W", {
        "Battery": {"SoC": 40, "Voltage": 24.5, "Current": 10.0},
        "Solar":   {"Power": 850, "State": "ACTIVE", "Anomaly": False},
        "Strategy": {"Selected": "SOLAR", "StartedAt": _time.time() - 400,
                     "Status": "WAITING"},
    })

    # Test 2 — Solar strategy, solar failing
    run("Solar strategy — anomaly detected", {
        "Battery": {"SoC": 30, "Voltage": 24.0, "Current": -8.0},
        "Solar":   {"Power": 20, "State": "LIMITED", "Anomaly": True,
                    "AnomalyReason": "Actual 20W vs expected 600W"},
        "Strategy": {"Selected": "SOLAR", "StartedAt": _time.time() - 1200,
                     "Status": "MONITORING"},
    })

    # Test 3 — Generator strategy, not started yet
    run("Generator strategy — not started", {
        "Battery": {"SoC": 25, "Voltage": 23.8, "Current": -10.0},
        "Solar":   {"Power": 0, "State": "NIGHT"},
        "Strategy": {"Selected": "GENERATOR", "StartedAt": _time.time() - 900,
                     "Status": "MONITORING"},
    })

    # Test 4 — No strategy
    run("No strategy selected", {
        "Battery": {"SoC": 80},
        "Solar": {},
        "Strategy": {},
    })

    print("\n" + "=" * 60)
    print("Test complete.")
