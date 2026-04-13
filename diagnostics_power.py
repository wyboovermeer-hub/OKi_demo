# ============================================================
# OKi POWER DIAGNOSTICS MODULE
# ============================================================
#
# Purpose
# -------
# This module performs advanced AC power diagnostics using
# data provided by the Shelly Pro EM energy monitor.
#
# Responsibilities
# ----------------
# • Classify AC power states
# • Detect load activity
# • Detect abnormal energy conditions
# • Provide engineering diagnostics
# • Generate advisory messages
#
# This module is intentionally independent from the main engine
# so diagnostic logic can grow without cluttering engine.py.
#
# ============================================================

from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

# Voltage threshold to detect shore power
AC_PRESENT_THRESHOLD = 200

# Power thresholds (Watts)
POWER_IDLE_THRESHOLD = 5
POWER_LOW_THRESHOLD = 30
POWER_ACTIVE_THRESHOLD = 150
POWER_HIGH_THRESHOLD = 500

# Event detection hysteresis
POWER_CHANGE_THRESHOLD = 10


# ============================================================
# AC STATE CLASSIFICATION
# ============================================================

def classify_ac_state(voltage, power):
    """
    Classify the AC system state.

    Returns one of the following states:

        NO_SHORE
        IDLE
        LOW_LOAD
        ACTIVE_LOAD
        HIGH_LOAD
    """

    if voltage is None:
        return "UNKNOWN"

    if voltage < AC_PRESENT_THRESHOLD:
        return "NO_SHORE"

    if power is None:
        return "AC_PRESENT"

    if power < POWER_IDLE_THRESHOLD:
        return "IDLE"

    if power < POWER_LOW_THRESHOLD:
        return "LOW_LOAD"

    if power < POWER_ACTIVE_THRESHOLD:
        return "ACTIVE_LOAD"

    return "HIGH_LOAD"


# ============================================================
# LOAD EVENT DETECTION
# ============================================================

def detect_load_event(state):
    """
    Detect transitions in power consumption.

    Example events:

        Load started
        Load stopped
        High load started
    """

    power = state["AC"]["GridPower"]
    previous = state["AC"].get("PreviousPower")

    if power is None:
        return None

    if previous is None:
        state["AC"]["PreviousPower"] = power
        return None

    delta = abs(power - previous)

    if delta < POWER_CHANGE_THRESHOLD:
        return None

    state["AC"]["PreviousPower"] = power

    if power > POWER_LOW_THRESHOLD and previous < POWER_IDLE_THRESHOLD:
        return "Load started"

    if power < POWER_IDLE_THRESHOLD and previous > POWER_LOW_THRESHOLD:
        return "Load stopped"

    if power > POWER_HIGH_THRESHOLD:
        return "High power load detected"

    return None


# ============================================================
# POWER ANOMALY DETECTION
# ============================================================

def detect_power_anomaly(state):
    """
    Detect abnormal AC power situations.
    """

    voltage = state["AC"]["GridVoltage"]
    power = state["AC"]["GridPower"]

    if voltage is None or power is None:
        return None

    # AC present but no load
    if voltage > AC_PRESENT_THRESHOLD and power < POWER_IDLE_THRESHOLD:
        return "AC available but no load detected"

    # Extremely high load
    if power > POWER_HIGH_THRESHOLD:
        return "Unusually high AC load detected"

    return None


# ============================================================
# ENGINEERING DIAGNOSTIC RULES
# ============================================================

def evaluate_power_diagnostics(state):
    """
    Perform engineering diagnostic reasoning
    based on AC energy behavior.
    """

    voltage = state["AC"]["GridVoltage"]
    power = state["AC"]["GridPower"]

    issues = []

    if voltage is None:
        issues.append("No AC measurement available")
        return issues

    if voltage < AC_PRESENT_THRESHOLD:
        issues.append("Shore power disconnected")

    if voltage > AC_PRESENT_THRESHOLD and power is not None:

        if power < POWER_IDLE_THRESHOLD:
            issues.append("AC present but system idle")

        if power > POWER_HIGH_THRESHOLD:
            issues.append("Excessive AC load")

    return issues


# ============================================================
# OPERATOR ADVISORY SYSTEM
# ============================================================

def generate_power_advisory(state):
    """
    Generate human-readable advisory message.
    """

    voltage = state["AC"]["GridVoltage"]
    power = state["AC"]["GridPower"]
    state_class = state["AC"].get("State")

    if voltage is None:
        return "AC monitoring unavailable"

    if state_class == "NO_SHORE":
        return "No shore power detected."

    if state_class == "IDLE":
        return "AC available but no active load."

    if state_class == "LOW_LOAD":
        return "Low AC load detected."

    if state_class == "ACTIVE_LOAD":
        return "Normal AC load operating."

    if state_class == "HIGH_LOAD":
        return "High AC load detected. Verify connected equipment."

    return "AC system state normal."


# ============================================================
# MASTER POWER DIAGNOSTIC FUNCTION
# ============================================================

def run_power_diagnostics(state):
    """
    Main diagnostic entry point.

    This function is called from engine.py.
    """

    voltage = state["AC"]["GridVoltage"]
    power = state["AC"]["GridPower"]

    # --------------------------------------------------------
    # AC state classification
    # --------------------------------------------------------

    ac_state = classify_ac_state(voltage, power)

    state["AC"]["State"] = ac_state

    # --------------------------------------------------------
    # Detect load events
    # --------------------------------------------------------

    event = detect_load_event(state)

    if event:
        state["System"]["Advisory"] = event

    # --------------------------------------------------------
    # Diagnostic reasoning
    # --------------------------------------------------------

    issues = evaluate_power_diagnostics(state)

    if issues:
        state["System"]["Inconsistency"] = issues

    # --------------------------------------------------------
    # Operator advisory
    # --------------------------------------------------------

    advisory = generate_power_advisory(state)

    state["System"]["Recommendation"] = advisory

    # --------------------------------------------------------
    # Timestamp diagnostic run
    # --------------------------------------------------------

    state["System"]["LastPowerDiagnostic"] = datetime.utcnow().isoformat()

    return state