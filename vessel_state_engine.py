"""
vessel_state_engine.py — OKi Vessel State & Situational Awareness Engine
Version: 1.0
Spec: OKi 002 Situational Awareness & Shore Power Logic v1.1

Responsibilities:
    - Detect vessel movement state (MOVING / NOT_MOVING)
    - Derive available energy sources based on context
    - Detect Survival Priority Mode (low battery + no charging + time critical)
    - Track operator-confirmed location context (ANCHOR / DOCK_SHORE / DOCK_NO_SHORE)
    - Feed context into operator_question_engine and energy_strategy_engine
    - Enforce information hierarchy: situation first, options second

Vessel States:
    MOVING          — speed above threshold, shore power impossible
    NOT_MOVING      — speed zero or unknown, shore power potentially available

Location Context (operator confirmed):
    UNKNOWN         — not yet confirmed
    AT_ANCHOR       — anchored, no shore power
    DOCK_SHORE      — at dock, shore power available
    DOCK_NO_SHORE   — at dock, shore power not available

Survival Priority Mode:
    Triggered when:
    - Battery SoC below critical threshold AND
    - No active charging AND
    - Time-to-shutdown below survival threshold

Called by engine_cycle() after compute_energy_forecast().
Reads:  state["GPS"], state["Battery"], state["EnergyForecast"], state["AC"]
Writes: state["VesselState"]
"""

from datetime import datetime, timezone
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

# Movement detection
MOVING_SPEED_KNOTS          = 1.5     # Above this = vessel is moving
SPEED_UNKNOWN_AS_MOVING     = False   # If GPS unavailable, assume not moving

# Survival Priority Mode thresholds
SURVIVAL_SOC_THRESHOLD      = 20.0   # % — below this triggers survival check
SURVIVAL_TIME_TO_SHUTDOWN_H = 4.0    # hours — below this triggers survival mode
SURVIVAL_NO_CHARGING_A      = 0.5    # amps — below this = not charging

# Location context timeout (hours) — after this, re-confirm location
LOCATION_CONTEXT_TIMEOUT_H  = 6.0


# ============================================================
# VESSEL STATES
# ============================================================

MOVEMENT_MOVING     = "MOVING"
MOVEMENT_STOPPED    = "NOT_MOVING"
MOVEMENT_UNKNOWN    = "UNKNOWN"

LOCATION_UNKNOWN        = "UNKNOWN"
LOCATION_ANCHOR         = "AT_ANCHOR"
LOCATION_DOCK_SHORE     = "DOCK_SHORE"
LOCATION_DOCK_NO_SHORE  = "DOCK_NO_SHORE"


# ============================================================
# MAIN FUNCTION
# ============================================================

def evaluate_vessel_state(state: dict) -> None:
    """
    Main entry point. Called once per engine cycle.

    Determines:
    1. Movement state from GPS speed
    2. Available energy sources based on movement + location
    3. Survival Priority Mode
    4. Primary UI message (information hierarchy)

    Writes to state["VesselState"]:
        MovementState           — MOVING / NOT_MOVING / UNKNOWN
        SpeedKnots              — float
        LocationContext         — UNKNOWN / AT_ANCHOR / DOCK_SHORE / DOCK_NO_SHORE
        ShorePowerPossible      — bool
        AvailableSources        — list of strings
        SurvivalMode            — bool
        SurvivalPrimaryMessage  — str (dominant UI message when in survival mode)
        SurvivalTimeString      — str e.g. "3h 40m"
        NeedsLocationQuestion   — bool (trigger for question engine)
        LastLocationConfirmed   — ISO timestamp or None
    """
    vessel = _get_section(state, "VesselState")

    # ----------------------------------------------------------------
    # Step 1 — Movement detection
    # ----------------------------------------------------------------
    _detect_movement(state, vessel)

    # ----------------------------------------------------------------
    # Step 2 — Shore power possibility
    # ----------------------------------------------------------------
    moving = vessel.get("MovementState") == MOVEMENT_MOVING
    vessel["ShorePowerPossible"] = not moving

    # ----------------------------------------------------------------
    # Step 3 — Available energy sources
    # ----------------------------------------------------------------
    vessel["AvailableSources"] = _derive_available_sources(state, vessel)

    # ----------------------------------------------------------------
    # Step 4 — Location context expiry check
    # ----------------------------------------------------------------
    _check_location_expiry(vessel)

    # ----------------------------------------------------------------
    # Step 5 — Survival Priority Mode
    # ----------------------------------------------------------------
    _evaluate_survival_mode(state, vessel)

    # ----------------------------------------------------------------
    # Step 6 — Location question trigger
    # ----------------------------------------------------------------
    _evaluate_location_question_needed(vessel)


def confirm_location(state: dict, location_key: str) -> bool:
    """
    Called when operator answers the location context question.
    location_key: AT_ANCHOR | DOCK_SHORE | DOCK_NO_SHORE

    Returns True if valid.
    """
    valid = {LOCATION_ANCHOR, LOCATION_DOCK_SHORE, LOCATION_DOCK_NO_SHORE}
    if location_key not in valid:
        return False

    vessel = _get_section(state, "VesselState")
    vessel["LocationContext"]       = location_key
    vessel["LastLocationConfirmed"] = datetime.now(timezone.utc).isoformat()
    vessel["NeedsLocationQuestion"] = False

    # If operator confirmed dock + shore power, flag expectation
    if location_key == LOCATION_DOCK_SHORE:
        vessel["ExpectingShorePower"] = True
    else:
        vessel["ExpectingShorePower"] = False

    return True


# ============================================================
# MOVEMENT DETECTION
# ============================================================

def _detect_movement(state: dict, vessel: dict) -> None:
    """
    Determine movement state from GPS speed.
    Falls back gracefully when GPS not available.
    """
    gps   = state.get("GPS") or {}
    speed = gps.get("SpeedKnots")

    if speed is None:
        # GPS not available
        if SPEED_UNKNOWN_AS_MOVING:
            vessel["MovementState"] = MOVEMENT_MOVING
        else:
            vessel["MovementState"] = MOVEMENT_UNKNOWN
        vessel["SpeedKnots"] = None
        return

    speed = float(speed)
    vessel["SpeedKnots"] = round(speed, 1)

    if speed > MOVING_SPEED_KNOTS:
        vessel["MovementState"] = MOVEMENT_MOVING
        # Clear location context when underway
        vessel["LocationContext"]       = LOCATION_UNKNOWN
        vessel["LastLocationConfirmed"] = None
        vessel["ExpectingShorePower"]   = False
    else:
        vessel["MovementState"] = MOVEMENT_STOPPED


# ============================================================
# AVAILABLE ENERGY SOURCES
# ============================================================

def _derive_available_sources(state: dict, vessel: dict) -> list:
    """
    Determine which energy sources are realistically available
    given current vessel state and location context.

    This list feeds into energy_strategy_engine to filter options.
    """
    sources    = []
    moving     = vessel.get("MovementState") == MOVEMENT_MOVING
    location   = vessel.get("LocationContext", LOCATION_UNKNOWN)
    solar      = state.get("Solar") or {}
    solar_state= solar.get("State", "NIGHT")

    # Solar — available if sun is up, regardless of movement
    if solar_state not in ("NIGHT", None):
        sources.append("SOLAR")

    # Generator — always potentially available
    sources.append("GENERATOR")

    # Shore power — only when stopped and at dock with shore
    if not moving and location == LOCATION_DOCK_SHORE:
        sources.append("SHORE_POWER")

    # DC-DC from propulsion — available when moving (propulsion bank charged)
    if moving:
        sources.append("DC_DC_PROPULSION")

    # Load reduction — always available
    sources.append("REDUCE_LOAD")

    return sources


# ============================================================
# SURVIVAL PRIORITY MODE
# ============================================================

def _evaluate_survival_mode(state: dict, vessel: dict) -> None:
    """
    Detect survival conditions and build primary UI message.

    Survival = battery critically low + no charging + time running out.
    When active, this message takes absolute UI priority (information hierarchy).
    """
    battery   = state.get("Battery") or {}
    forecast  = state.get("EnergyForecast") or {}
    blackout  = state.get("Blackout") or {}

    soc         = _safe_float(battery.get("SoC"), 100.0)
    dc_current  = _safe_float(battery.get("Current"), 0.0)
    shutdown_h  = forecast.get("TimeToShutdownH")
    blackout_on = bool(blackout.get("BlackoutMode", False))

    # Survival conditions
    battery_critical   = soc <= SURVIVAL_SOC_THRESHOLD
    not_charging       = dc_current < SURVIVAL_NO_CHARGING_A
    time_critical      = (
        shutdown_h is not None and
        float(shutdown_h) <= SURVIVAL_TIME_TO_SHUTDOWN_H
    )

    survival_active = battery_critical and not_charging and time_critical

    vessel["SurvivalMode"] = survival_active

    if not survival_active:
        vessel["SurvivalPrimaryMessage"] = None
        vessel["SurvivalTimeString"]     = None
        return

    # Build primary message — calm, clear, information hierarchy
    shutdown_str = _format_hours(float(shutdown_h)) if shutdown_h else "unknown"
    vessel["SurvivalTimeString"] = shutdown_str

    if blackout_on:
        ups_str = blackout.get("UPSDisplayString", "unknown")
        vessel["SurvivalPrimaryMessage"] = (
            f"Power is critically low. "
            f"Vessel power has been lost. "
            f"OKi operational on backup for: {ups_str}."
        )
    else:
        vessel["SurvivalPrimaryMessage"] = (
            f"Power is critically low. "
            f"Estimated time to blackout: {shutdown_str}. "
            f"OKi operational after blackout: up to 48h."
        )


# ============================================================
# LOCATION QUESTION TRIGGER
# ============================================================

def _evaluate_location_question_needed(vessel: dict) -> None:
    """
    Set NeedsLocationQuestion = True when:
    - Vessel is stopped AND
    - Location context is UNKNOWN (not yet confirmed)
    - And not already expired / timed out (handled in _check_location_expiry)
    """
    moving   = vessel.get("MovementState") == MOVEMENT_MOVING
    location = vessel.get("LocationContext", LOCATION_UNKNOWN)

    if moving:
        vessel["NeedsLocationQuestion"] = False
        return

    if location == LOCATION_UNKNOWN:
        vessel["NeedsLocationQuestion"] = True
    else:
        vessel["NeedsLocationQuestion"] = False


def _check_location_expiry(vessel: dict) -> None:
    """
    If location was confirmed more than LOCATION_CONTEXT_TIMEOUT_H ago,
    reset it to UNKNOWN so OKi re-confirms next time relevant.
    """
    confirmed = vessel.get("LastLocationConfirmed")
    if not confirmed:
        return

    try:
        confirmed_dt = datetime.fromisoformat(str(confirmed))
        if confirmed_dt.tzinfo is None:
            confirmed_dt = confirmed_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        elapsed_h = (now - confirmed_dt).total_seconds() / 3600.0
        if elapsed_h > LOCATION_CONTEXT_TIMEOUT_H:
            vessel["LocationContext"]       = LOCATION_UNKNOWN
            vessel["LastLocationConfirmed"] = None
            vessel["ExpectingShorePower"]   = False
    except Exception:
        pass


# ============================================================
# SHORE POWER EXPECTATION CHECK
# ============================================================

def check_shore_power_expectation(state: dict) -> Optional[str]:
    """
    If operator confirmed dock + shore power but no AC charging detected,
    return a follow-up message for the question engine.
    Returns None if no mismatch.
    """
    vessel = state.get("VesselState") or {}
    ac     = state.get("AC") or {}

    if not vessel.get("ExpectingShorePower"):
        return None

    ac_state = ac.get("State", "UNKNOWN")
    if ac_state in ("NO_SHORE", "UNKNOWN"):
        return "Shore power is available but not active. What is the situation?"

    return None


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
    total_min = int(hours * 60)
    h = total_min // 60
    m = total_min % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OKi vessel_state_engine.py — Dev Test")
    print("=" * 60)

    def run(label, state, location=None):
        evaluate_vessel_state(state)
        if location:
            confirm_location(state, location)
            evaluate_vessel_state(state)
        v = state["VesselState"]
        shore_msg = check_shore_power_expectation(state)
        print(f"\n📋 {label}")
        print(f"   Movement       : {v.get('MovementState')}")
        print(f"   Speed          : {v.get('SpeedKnots')} kn")
        print(f"   Location       : {v.get('LocationContext')}")
        print(f"   Shore Possible : {v.get('ShorePowerPossible')}")
        print(f"   Sources        : {v.get('AvailableSources')}")
        print(f"   Survival Mode  : {v.get('SurvivalMode')}")
        print(f"   Needs Loc Q    : {v.get('NeedsLocationQuestion')}")
        if v.get("SurvivalPrimaryMessage"):
            print(f"   🔴 PRIMARY     : {v['SurvivalPrimaryMessage']}")
        if shore_msg:
            print(f"   ⚠️  Shore Q     : {shore_msg}")

    # Test 1 — Moving at 6 knots
    run("Vessel moving — 6 knots", {
        "GPS":     {"SpeedKnots": 6.0},
        "Battery": {"SoC": 55, "Current": -5.0},
        "Solar":   {"State": "ACTIVE"},
        "AC":      {"GridVoltage": 0, "State": "NO_SHORE"},
        "EnergyForecast": {"TimeToShutdownH": 12.0},
        "Blackout": {},
    })

    # Test 2 — Stopped, location unknown → needs question
    run("Stopped, location unknown — needs location question", {
        "GPS":     {"SpeedKnots": 0.0},
        "Battery": {"SoC": 45, "Current": -3.0},
        "Solar":   {"State": "ACTIVE"},
        "AC":      {"GridVoltage": 0, "State": "NO_SHORE"},
        "EnergyForecast": {"TimeToShutdownH": 10.0},
        "Blackout": {},
    })

    # Test 3 — At anchor
    run("Confirmed at anchor", {
        "GPS":     {"SpeedKnots": 0.0},
        "Battery": {"SoC": 40, "Current": -4.0},
        "Solar":   {"State": "ACTIVE"},
        "AC":      {"GridVoltage": 0, "State": "NO_SHORE"},
        "EnergyForecast": {"TimeToShutdownH": 8.0},
        "Blackout": {},
    }, location=LOCATION_ANCHOR)

    # Test 4 — At dock, shore power available, but not connected
    run("Dock + shore power expected but not active", {
        "GPS":     {"SpeedKnots": 0.0},
        "Battery": {"SoC": 30, "Current": -5.0},
        "Solar":   {"State": "NIGHT"},
        "AC":      {"GridVoltage": 0, "State": "NO_SHORE"},
        "EnergyForecast": {"TimeToShutdownH": 5.0},
        "Blackout": {},
    }, location=LOCATION_DOCK_SHORE)

    # Test 5 — Survival mode
    run("Survival mode — low battery, no charging, 2h left", {
        "GPS":     {"SpeedKnots": 0.0},
        "Battery": {"SoC": 15, "Current": -8.0},
        "Solar":   {"State": "NIGHT"},
        "AC":      {"GridVoltage": 0, "State": "NO_SHORE"},
        "EnergyForecast": {"TimeToShutdownH": 2.0},
        "Blackout": {"BlackoutMode": False},
    })

    # Test 6 — No GPS
    run("No GPS available", {
        "GPS":     {},
        "Battery": {"SoC": 60, "Current": 5.0},
        "Solar":   {"State": "ACTIVE"},
        "AC":      {"GridVoltage": 230},
        "EnergyForecast": {},
        "Blackout": {},
    })

    print("\n" + "=" * 60)
    print("Test complete.")
