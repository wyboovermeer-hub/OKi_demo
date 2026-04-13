"""
OKi — Diagnostic Reasoning Layer  (v2 — time-aware)
Detects FAILURE OF EXPECTED SOLUTION and collaborates with the operator
through a single, calm, structured question at a time.

Changes from v1:
  - CRITICAL_COUNTDOWN injects time-remaining context into PrimaryState /
    SecondaryContext without altering the state machine structure.
  - Questions shift from confirmation to decision under time pressure.
  - Tone rules enforced: no ERROR / FAILURE / URGENT / ALERT language.
"""

from fuel_tank_module import is_fuel_available

# ── Diagnostic state constants ────────────────────────────────────────────────
DS_GENERATOR_EXPECTED       = "GENERATOR_EXPECTED"
DS_GENERATOR_NOT_RESPONDING = "GENERATOR_NOT_RESPONDING"
DS_GENERATOR_ERROR_CODE     = "GENERATOR_ERROR_CODE"
DS_FUEL_UNCERTAIN           = "FUEL_UNCERTAIN"

# ── Generator error code interpretations ─────────────────────────────────────
GENERATOR_ERROR_MAP = {
    "E01": "Low oil pressure — check oil level and pressure sensor",
    "E02": "High coolant temperature — inspect coolant level and radiator",
    "E03": "Overcrank fault — starter engaged too long without ignition",
    "E04": "Low fuel pressure — check fuel pump, filter, and supply lines",
    "E05": "Speed sensor fault — governor or pickup sensor may have failed",
    "E06": "High AC voltage — voltage regulator or AVR issue",
    "E07": "Low AC voltage — AVR, exciter, or load issue",
    "E08": "Overload / overcurrent — reduce connected load",
    "E09": "Battery charger fault — check charger and DC supply",
    "E10": "Emergency stop activated — inspect physical stop switch",
}

UNKNOWN_ERROR_ADVISORY = (
    "Unrecognised code. Consult the generator manual or contact the manufacturer."
)


# ── Trigger evaluation ────────────────────────────────────────────────────────

def _should_enter_diagnostic(state: dict) -> bool:
    battery   = state.get("Battery", {})
    system    = state.get("System", {})
    solar     = state.get("Solar", {})
    generator = state.get("Generator", {})

    return (
        battery.get("SoC", 100) < 25
        and battery.get("Status") == "DISCHARGING"
        and not system.get("ShorePower", False)
        and solar.get("InputWatts", 0) < 50
        and generator.get("Expected", False)
        and not generator.get("Running", False)
    )


# ── Time-context helpers ──────────────────────────────────────────────────────

def _is_critical_countdown(state: dict) -> bool:
    return state.get("System", {}).get("SituationType") == "CRITICAL_COUNTDOWN"


def _time_context_sentence(state: dict) -> str:
    """Return a calm, factual time-remaining sentence, or empty string."""
    hours = state.get("Energy", {}).get("TimeToCriticalHours")
    if hours is None:
        return ""
    return f"Battery will reach critical level in ~{hours:.1f} hours."


def _no_charging_sentence(state: dict) -> str:
    system  = state.get("System", {})
    gen_on  = state.get("Generator", {}).get("Running", False)
    solar_w = state.get("Solar", {}).get("InputWatts", 0)
    shore   = system.get("ShorePower", False)
    if not shore and not gen_on and solar_w < 50:
        return "No charging source is currently active."
    return ""


def _build_secondary_context(state: dict, base_context: str) -> str:
    """
    Prepend time and charging sentences when in CRITICAL_COUNTDOWN.
    Returns base_context unchanged in all other situations.
    """
    if not _is_critical_countdown(state):
        return base_context
    parts = [
        s for s in [
            _time_context_sentence(state),
            _no_charging_sentence(state),
            base_context,
        ]
        if s
    ]
    return " ".join(parts)


# ── Step handlers ─────────────────────────────────────────────────────────────

def _step_initial(state: dict, diag: dict) -> None:
    countdown = _is_critical_countdown(state)

    if countdown:
        diag["PrimaryState"]   = "Limited energy remaining"
        diag["ActiveQuestion"] = "Do you plan to restore charging?"
        diag["Options"]        = [
            "A: Start generator",
            "B: Reduce consumption",
            "C: Not yet",
        ]
    else:
        diag["PrimaryState"]   = "Energy recovery unavailable"
        diag["ActiveQuestion"] = "Is it expected that the generator is not responding?"
        diag["Options"]        = ["A: Yes", "B: No", "C: Investigating"]

    diag["SecondaryContext"] = _build_secondary_context(
        state,
        "Battery is low, no charging source active, generator not responding",
    )
    diag["Step"] = "INITIAL"


def _step_confirm_issue(state: dict, diag: dict) -> None:
    diag["ActiveQuestion"]   = "What is the generator reporting?"
    diag["Options"]          = [
        "A: A code is displayed",
        "B: No display — unresponsive",
        "C: Other",
    ]
    diag["SecondaryContext"] = _build_secondary_context(state, "")
    diag["Step"]             = "CONFIRM_ISSUE"


def _step_error_code(state: dict, diag: dict) -> None:
    error_code = state.get("Generator", {}).get("ErrorCode", "")
    advisory   = GENERATOR_ERROR_MAP.get(error_code.upper(), UNKNOWN_ERROR_ADVISORY)

    diag["DiagnosticState"]  = DS_GENERATOR_ERROR_CODE
    diag["PrimaryState"]     = f"Generator has indicated a condition: {error_code}"
    diag["SecondaryContext"] = _build_secondary_context(state, advisory)
    diag["ActiveQuestion"]   = "Has the advisory above been actioned?"
    diag["Options"]          = [
        "A: Yes — generator now running",
        "B: Not yet — need further help",
        "C: In progress",
    ]
    diag["Step"] = "ERROR_CODE"

    state.setdefault("Generator", {})["ErrorCode"] = error_code


def _step_not_responding(state: dict, diag: dict) -> None:
    diag["DiagnosticState"]  = DS_GENERATOR_NOT_RESPONDING
    diag["PrimaryState"]     = "Generator is not responding"
    diag["SecondaryContext"] = _build_secondary_context(state, "")

    if _is_critical_countdown(state):
        diag["ActiveQuestion"] = "Do you plan to restore charging?"
        diag["Options"]        = [
            "A: Start generator",
            "B: Reduce consumption",
            "C: Not yet",
        ]
    else:
        diag["ActiveQuestion"] = "Are you working on the generator?"
        diag["Options"]        = ["A: Yes", "B: Not yet", "C: Need guidance"]

    diag["Step"] = "NOT_RESPONDING"


def _step_fuel_check(state: dict, diag: dict) -> None:
    state.setdefault("System", {}).setdefault(
        "SensorConfidence", {}
    )["Fuel"] = "UNCERTAIN"

    diag["DiagnosticState"]  = DS_FUEL_UNCERTAIN
    diag["PrimaryState"]     = "Generator not responding — fuel status is uncertain"
    diag["SecondaryContext"] = _build_secondary_context(
        state, "Fuel sensor reads empty or is unreliable."
    )
    diag["ActiveQuestion"]   = "Can you confirm whether the fuel tank has fuel?"
    diag["Options"]          = [
        "A: Yes, tank has fuel",
        "B: Tank is empty",
        "C: Unable to check right now",
    ]
    diag["Step"] = "FUEL_CHECK"


# ── State machine ─────────────────────────────────────────────────────────────

def _advance_diagnostic(state: dict, diag: dict) -> None:
    response     = diag.get("OperatorResponse", "")
    current_step = diag.get("Step", "")

    if current_step == "INITIAL":
        if response == "B":
            _step_confirm_issue(state, diag)
        elif response == "A":
            diag["PrimaryState"]     = "Generator offline — operator acknowledged"
            diag["ActiveQuestion"]   = ""
            diag["SecondaryContext"] = _build_secondary_context(state, "")
            diag["Step"]             = "ACKNOWLEDGED"
        else:
            _step_initial(state, diag)   # re-render with fresh time context

    elif current_step == "CONFIRM_ISSUE":
        if response == "A":
            _step_error_code(state, diag)
        elif response == "B":
            _step_not_responding(state, diag)
        else:
            _step_confirm_issue(state, diag)

    elif current_step == "NOT_RESPONDING":
        fuel_state = state.get("Fuel", {}).get("State")
        if not is_fuel_available(state) or fuel_state in ("UNKNOWN", "CRITICAL"):
            _step_fuel_check(state, diag)
        else:
            _step_not_responding(state, diag)   # refresh question tone

    elif current_step in ("ERROR_CODE", "FUEL_CHECK", "ACKNOWLEDGED"):
        # Refresh secondary context with latest time data on every cycle
        diag["SecondaryContext"] = _build_secondary_context(
            state, diag.get("SecondaryContext", "")
        )


# ── Public entry point ────────────────────────────────────────────────────────

def run_diagnostics(state: dict) -> None:
    """
    Evaluate system state and either enter/advance diagnostic mode
    or clear it when conditions resolve.
    Writes state["Diagnostic"]. May set state["System"]["Mode"].
    """
    if not _should_enter_diagnostic(state):
        if state.get("System", {}).get("Mode") == "DIAGNOSTIC":
            state["System"]["Mode"] = "NORMAL"
        state.pop("Diagnostic", None)
        return

    state.setdefault("System", {})["Mode"] = "DIAGNOSTIC"

    diag = state.setdefault("Diagnostic", {
        "PrimaryState":     "",
        "SecondaryContext": "",
        "ActiveQuestion":   "",
        "Options":          [],
        "Step":             "",
        "DiagnosticState":  DS_GENERATOR_EXPECTED,
        "OperatorResponse": "",
    })

    if not diag.get("Step"):
        _step_initial(state, diag)
        return

    _advance_diagnostic(state, diag)

    # Normalise for attention engine
    state["Diagnostic"] = {
        "PrimaryState":     diag.get("PrimaryState", ""),
        "SecondaryContext": diag.get("SecondaryContext", ""),
        "ActiveQuestion":   diag.get("ActiveQuestion", ""),
        "Options":          diag.get("Options", []),
        "Step":             diag.get("Step", ""),
        "DiagnosticState":  diag.get("DiagnosticState", DS_GENERATOR_EXPECTED),
        "OperatorResponse": diag.get("OperatorResponse", ""),
    }
