"""
attention_engine.py — OKi Attention Engine & Communication Layer
Version: 1.0
Spec: OKi 002 Attention Engine & Communication Layer v1.3

Position in architecture:
    Sits ABOVE all other engines.
    Receives signals from every engine.
    Decides what the operator sees.
    Outputs exactly three things — no more, no less.

Outputs:
    primary_state       — one clear condition, always present
    secondary_context   — 2–3 supporting facts, never competing
    active_question     — one question, always present

Priority levels:
    1. SURVIVAL         — blackout imminent, shutdown imminent, critical failure
    2. TIME_CRITICAL    — energy running out soon, no charging path, solar ending
    3. DECISION         — question unresolved, strategy unclear
    4. BACKGROUND       — minor inefficiencies, optimisation opportunities
    5. STABLE           — all systems within expected parameters

Tone rules (never violated):
    - Always calm
    - No exclamation marks
    - No alarm language
    - No urgency exaggeration
    - One clear thought at a time
"""

from typing import Optional


# ============================================================
# PRIORITY LEVELS
# ============================================================

PRIORITY_SURVIVAL       = 1
PRIORITY_TIME_CRITICAL  = 2
PRIORITY_DECISION       = 3
PRIORITY_BACKGROUND     = 4
PRIORITY_STABLE         = 5


# ============================================================
# CONFIGURATION
# ============================================================

# Time thresholds (hours) for priority escalation
TIME_CRITICAL_THRESHOLD_H   = 6.0    # Under 6h → time critical
SURVIVAL_THRESHOLD_H        = 2.0    # Under 2h → survival

# Battery SoC thresholds
SOC_SURVIVAL                = 15.0
SOC_TIME_CRITICAL           = 25.0

# Sunset warning threshold (minutes)
SUNSET_CRITICAL_MIN         = 30


# ============================================================
# OUTPUT CONTAINER
# ============================================================

class AttentionState:
    """
    The complete output of the attention engine.
    This is what the UI renders — nothing else.
    """

    def __init__(self):
        self.priority:          int   = PRIORITY_STABLE
        self.priority_label:    str   = "STABLE"
        self.primary_state:     str   = "System operating normally."
        self.secondary_context: list  = []
        self.active_question:   Optional[dict] = None
        self.silence:           bool  = False   # True = no new alerts, steady display

    def to_dict(self) -> dict:
        return {
            "Priority":         self.priority,
            "PriorityLabel":    self.priority_label,
            "PrimaryState":     self.primary_state,
            "SecondaryContext": self.secondary_context,
            "ActiveQuestion":   self.active_question,
            "Silence":          self.silence,
        }


# ============================================================
# MAIN FUNCTION
# ============================================================

def compute_attention(state: dict) -> AttentionState:
    """
    Main entry point. Called by engine_cycle() as the final step
    before writing to UI state.

    Steps:
    1. Collect signals from all engines
    2. Assign priority level
    3. Build primary state message
    4. Build secondary context (2–3 supporting facts)
    5. Attach active question
    6. Evaluate silence

    Returns AttentionState — written to state["Attention"].
    """
    result = AttentionState()

    # ----------------------------------------------------------------
    # Step 1 — Collect signals
    # ----------------------------------------------------------------
    signals = _collect_signals(state)

    # ----------------------------------------------------------------
    # Step 2 — Assign priority
    # ----------------------------------------------------------------
    priority, priority_label = _assign_priority(signals)
    result.priority       = priority
    result.priority_label = priority_label

    # ----------------------------------------------------------------
    # Step 3 — Build primary state
    # ----------------------------------------------------------------
    result.primary_state = _build_primary_state(priority, signals, state)

    # ----------------------------------------------------------------
    # Step 4 — Build secondary context
    # ----------------------------------------------------------------
    result.secondary_context = _build_secondary_context(priority, signals, state)

    # ----------------------------------------------------------------
    # Step 5 — Attach active question
    # ----------------------------------------------------------------
    result.active_question = _select_active_question(priority, state)

    # ----------------------------------------------------------------
    # Step 6 — Silence evaluation
    # ----------------------------------------------------------------
    result.silence = _evaluate_silence(priority, signals, state)

    # Write to state
    state["Attention"] = result.to_dict()

    return result


# ============================================================
# STEP 1 — SIGNAL COLLECTION
# ============================================================

def _collect_signals(state: dict) -> dict:
    """
    Extract all relevant signals from engine outputs.
    Returns a flat signal dict — one source of truth for priority logic.
    """
    battery  = state.get("Battery")       or {}
    system   = state.get("System")        or {}
    blackout = state.get("Blackout")      or {}
    forecast = state.get("EnergyForecast") or {}
    vessel   = state.get("VesselState")   or {}
    solar    = state.get("Solar")         or {}
    strategy = state.get("Strategy")      or {}
    operator = state.get("Operator")      or {}
    derived  = state.get("Derived")       or {}
    ac       = state.get("AC")            or {}

    soc             = _safe_float(battery.get("SoC"), 100.0)
    health          = _safe_float(system.get("SystemHealth"), 100.0)
    shutdown_h      = forecast.get("TimeToShutdownH")
    critical_h      = forecast.get("TimeToCriticalH")
    net_power       = _safe_float(forecast.get("NetPowerW"), 0.0)
    mode            = derived.get("EnergyMode", "IDLE")

    return {
        # Battery
        "soc":                  soc,
        "mode":                 mode,
        "net_power_w":          net_power,

        # Health
        "health":               health,
        "health_penalties":     system.get("HealthPenalties") or [],
        "severity":             system.get("Severity"),

        # Blackout
        "blackout_active":      bool(blackout.get("BlackoutMode", False)),
        "blackout_ups_h":       _safe_float(blackout.get("UPSRemainingHours"), 48.0),
        "blackout_warning":     blackout.get("UPSWarningLevel"),
        "blackout_message":     blackout.get("OperatorMessage"),

        # Forecast
        "shutdown_h":           shutdown_h,
        "critical_h":           critical_h,

        # Vessel state
        "survival_mode":        bool(vessel.get("SurvivalMode", False)),
        "survival_message":     vessel.get("SurvivalPrimaryMessage"),
        "vessel_movement":      vessel.get("MovementState", "UNKNOWN"),
        "location_context":     vessel.get("LocationContext", "UNKNOWN"),
        "needs_location_q":     bool(vessel.get("NeedsLocationQuestion", False)),

        # Solar
        "solar_state":          solar.get("State", "NIGHT"),
        "solar_w":              _safe_float(solar.get("Power"), 0.0),
        "solar_countdown":      solar.get("CountdownString"),
        "solar_summary":        solar.get("ForecastSummary"),
        "sunset_warning":       solar.get("SunsetWarning"),
        "solar_anomaly":        bool(solar.get("Anomaly", False)),

        # Strategy
        "strategy_selected":    strategy.get("Selected", "NONE"),
        "strategy_status":      strategy.get("Status", "NONE"),
        "strategy_failed":      strategy.get("Status") == "FAILED",
        "strategy_followup":    bool(strategy.get("FollowUpNeeded", False)),

        # Operator
        "active_question":      operator.get("ActiveQuestionText"),
        "awaiting_response":    operator.get("InteractionState") == "AwaitingResponse",
        "question_options":     operator.get("Options"),
        "question_layer":       operator.get("QuestionLayer"),

        # AC
        "ac_state":             ac.get("State", "UNKNOWN"),
        "shore_power":          ac.get("State") not in ("NO_SHORE", "UNKNOWN", None),
    }


# ============================================================
# STEP 2 — PRIORITY ASSIGNMENT
# ============================================================

def _assign_priority(signals: dict) -> tuple:
    """
    Determine the highest priority signal.
    Returns (priority_int, priority_label_str).

    Rule: highest urgency wins. All others suppressed.
    """

    # ---- SURVIVAL (Priority 1) ----
    if signals["blackout_active"]:
        ups_h = signals["blackout_ups_h"]
        if ups_h < SURVIVAL_THRESHOLD_H:
            return PRIORITY_SURVIVAL, "SURVIVAL"

    if signals["survival_mode"]:
        return PRIORITY_SURVIVAL, "SURVIVAL"

    shutdown_h = signals["shutdown_h"]
    if shutdown_h is not None and float(shutdown_h) <= SURVIVAL_THRESHOLD_H:
        return PRIORITY_SURVIVAL, "SURVIVAL"

    if signals["soc"] <= SOC_SURVIVAL and signals["mode"] == "DISCHARGING":
        return PRIORITY_SURVIVAL, "SURVIVAL"

    if signals["severity"] == "CRITICAL" and signals["health"] <= 15:
        return PRIORITY_SURVIVAL, "SURVIVAL"

    # ---- TIME CRITICAL (Priority 2) ----
    if signals["blackout_active"]:
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"   # blackout but not yet urgent

    if shutdown_h is not None and float(shutdown_h) <= TIME_CRITICAL_THRESHOLD_H:
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"

    if signals["soc"] <= SOC_TIME_CRITICAL and signals["mode"] == "DISCHARGING":
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"

    if signals["sunset_warning"] == "CRITICAL" and signals["mode"] == "DISCHARGING":
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"

    if signals["strategy_failed"]:
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"

    if signals["severity"] == "CRITICAL":
        return PRIORITY_TIME_CRITICAL, "TIME_CRITICAL"

    # ---- DECISION REQUIRED (Priority 3) ----
    if signals["awaiting_response"]:
        return PRIORITY_DECISION, "DECISION"

    if signals["needs_location_q"]:
        return PRIORITY_DECISION, "DECISION"

    if signals["strategy_followup"]:
        return PRIORITY_DECISION, "DECISION"

    if signals["severity"] == "WARNING":
        return PRIORITY_DECISION, "DECISION"

    if signals["solar_anomaly"]:
        return PRIORITY_DECISION, "DECISION"

    # ---- BACKGROUND (Priority 4) ----
    if signals["sunset_warning"] == "WARNING":
        return PRIORITY_BACKGROUND, "BACKGROUND"

    if signals["health"] < 70:
        return PRIORITY_BACKGROUND, "BACKGROUND"

    if signals["soc"] < 40 and signals["mode"] == "DISCHARGING":
        return PRIORITY_BACKGROUND, "BACKGROUND"

    # ---- STABLE (Priority 5) ----
    return PRIORITY_STABLE, "STABLE"


# ============================================================
# STEP 3 — PRIMARY STATE MESSAGE
# ============================================================

def _build_primary_state(priority: int, signals: dict, state: dict) -> str:
    """
    Build the single primary state message.
    Calm. Clear. No exclamation marks. One thought.
    """

    if priority == PRIORITY_SURVIVAL:

        # Blackout active
        if signals["blackout_active"]:
            ups_h = signals["blackout_ups_h"]
            ups_str = _format_hours(ups_h)
            return (
                f"Vessel power has been lost.\n"
                f"OKi operational on backup battery: {ups_str} remaining."
            )

        # Survival mode message from vessel_state_engine
        if signals["survival_message"]:
            return signals["survival_message"]

        # Shutdown imminent
        shutdown_h = signals["shutdown_h"]
        if shutdown_h is not None:
            t = _format_hours(float(shutdown_h))
            return (
                f"Power is critically low.\n"
                f"Estimated time to blackout: {t}.\n"
                f"OKi operational after blackout: up to 48h."
            )

        # Generic survival
        soc = signals["soc"]
        return (
            f"Battery is critically low at {soc:.0f}%.\n"
            f"Immediate action is required to restore power."
        )

    elif priority == PRIORITY_TIME_CRITICAL:

        if signals["blackout_active"]:
            ups_h   = signals["blackout_ups_h"]
            ups_str = _format_hours(ups_h)
            w_level = signals["blackout_warning"] or ""
            return (
                f"Vessel power lost — running on OKi backup.\n"
                f"Remaining backup time: {ups_str}."
            )

        shutdown_h = signals["shutdown_h"]
        if shutdown_h is not None and float(shutdown_h) <= TIME_CRITICAL_THRESHOLD_H:
            t   = _format_hours(float(shutdown_h))
            soc = signals["soc"]
            return (
                f"Battery at {soc:.0f}% with no sufficient charging source.\n"
                f"Estimated time to blackout: {t}."
            )

        if signals["strategy_failed"]:
            selected = signals["strategy_selected"]
            label    = _strategy_label(selected)
            return (
                f"{label} is not producing the expected result.\n"
                f"An alternative energy source may be needed."
            )

        if signals["severity"] == "CRITICAL":
            penalties = signals["health_penalties"]
            top = _clean_penalty(penalties[0]) if penalties else "System fault detected"
            return top

        soc = signals["soc"]
        return (
            f"Battery at {soc:.0f}% and discharging.\n"
            f"No sufficient charging source is active."
        )

    elif priority == PRIORITY_DECISION:

        if signals["awaiting_response"] and signals["active_question"]:
            return "Operator input required."

        if signals["needs_location_q"]:
            return "Vessel is stationary. Location context is required."

        if signals["severity"] == "WARNING":
            penalties = signals["health_penalties"]
            top = _clean_penalty(penalties[0]) if penalties else "System warning active"
            return top

        if signals["solar_anomaly"]:
            solar = state.get("Solar") or {}
            return solar.get("AnomalyReason") or "Solar input anomaly detected."

        return "System attention required."

    elif priority == PRIORITY_BACKGROUND:

        if signals["sunset_warning"] == "WARNING":
            solar_str = signals["solar_countdown"] or "Sunset approaching"
            net = signals["net_power_w"]
            if net < 0:
                shutdown_h = signals["shutdown_h"]
                if shutdown_h:
                    t = _format_hours(float(shutdown_h))
                    return (
                        f"{solar_str}.\n"
                        f"After sunset, estimated runtime: {t}."
                    )
            return solar_str

        soc = signals["soc"]
        mode = signals["mode"].lower()
        return f"Battery at {soc:.0f}% and {mode}."

    else:  # STABLE
        soc    = signals["soc"]
        mode   = signals["mode"]
        health = signals["health"]

        if mode == "CHARGING":
            source = _charging_source_label(signals)
            return f"System stable. Battery at {soc:.0f}%, charging via {source}."

        if mode == "DISCHARGING":
            return f"System stable. Battery at {soc:.0f}%, no active charging source."

        return f"System operating normally. Battery at {soc:.0f}%."


# ============================================================
# STEP 4 — SECONDARY CONTEXT
# ============================================================

def _build_secondary_context(priority: int, signals: dict, state: dict) -> list:
    """
    Build 2–3 supporting context lines.
    Must not duplicate primary state.
    Must clarify, not alarm.
    """
    context = []
    forecast = state.get("EnergyForecast") or {}

    # Solar status — useful at most priorities
    if priority <= PRIORITY_TIME_CRITICAL:
        solar_str = signals.get("solar_summary")
        if solar_str and signals["solar_state"] not in ("NIGHT", None):
            context.append(solar_str)
        elif signals["solar_state"] == "NIGHT":
            context.append("Solar input not available — night")

    # Net energy flow
    net = signals["net_power_w"]
    consumption = _safe_float(forecast.get("ConsumptionW"), 0.0)
    if consumption > 0 and priority <= PRIORITY_TIME_CRITICAL:
        if net >= 0:
            context.append(f"Net energy: +{net:.0f}W — battery gaining")
        else:
            context.append(f"Net energy: {net:.0f}W — battery losing")

    # Strategy status
    strategy_sel = signals["strategy_selected"]
    strategy_sta = signals["strategy_status"]
    if strategy_sel not in ("NONE", None) and strategy_sta == "ACTIVE":
        context.append(f"{_strategy_label(strategy_sel)} active and confirmed")

    # Vessel location
    location = signals["location_context"]
    movement = signals["vessel_movement"]
    if movement == "MOVING":
        speed = (state.get("VesselState") or {}).get("SpeedKnots")
        if speed:
            context.append(f"Vessel underway at {speed:.1f} knots")
    elif location not in ("UNKNOWN", None):
        context.append(_location_label(location))

    # Health penalties — show top non-critical ones at background/stable
    if priority >= PRIORITY_BACKGROUND:
        penalties = signals["health_penalties"]
        minor = [p for p in penalties if p.startswith("🟡")]
        if minor:
            context.append(_clean_penalty(minor[0]))

    # Cap at 3 items
    return context[:3]


# ============================================================
# STEP 5 — ACTIVE QUESTION
# ============================================================

def _select_active_question(priority: int, state: dict) -> Optional[dict]:
    """
    Select the one active question to show.

    Rules:
    - If operator_question_engine has an active question → use it
    - If stable → show default care-based question
    - Always one question, never none (when operator is present)
    """
    operator = state.get("Operator") or {}

    # Active question from question engine
    if operator.get("InteractionState") == "AwaitingResponse":
        return {
            "text":    operator.get("ActiveQuestionText"),
            "options": operator.get("Options") or [],
            "layer":   operator.get("QuestionLayer"),
            "context": operator.get("QuestionContext"),
        }

    # Default question — stable operation
    if priority == PRIORITY_STABLE:
        health = _safe_float((state.get("System") or {}).get("SystemHealth"), 100.0)
        if health >= 80:
            return {
                "text":    "Would you like to improve the system health score?",
                "options": ["Yes — show me how", "No — keep current operation", "I don't know"],
                "layer":   "CARE",
                "context": "CARE_BASELINE",
            }
        else:
            return {
                "text":    "System health is below optimal. Would you like to review the issues?",
                "options": ["Yes — show issues", "Not now"],
                "layer":   "CARE",
                "context": "CARE_REVIEW",
            }

    # Background — soft prompt
    if priority == PRIORITY_BACKGROUND:
        solar = state.get("Solar") or {}
        if solar.get("SunsetWarning") == "WARNING":
            return {
                "text":    "Solar is declining. Do you want to review energy options for tonight?",
                "options": ["Yes", "No — I have a plan", "Later"],
                "layer":   "BACKGROUND",
                "context": "SUNSET_PREP",
            }

        return {
            "text":    "All systems within normal parameters. Anything to report?",
            "options": ["All good", "I have a concern"],
            "layer":   "BACKGROUND",
            "context": "BACKGROUND_CHECK",
        }

    # Decision / time critical / survival — question engine is handling it
    return None


# ============================================================
# STEP 6 — SILENCE EVALUATION
# ============================================================

def _evaluate_silence(priority: int, signals: dict, state: dict) -> bool:
    """
    True = OKi remains in steady display mode.
    No new alerts, no new prompts.

    Silence when:
    - System is STABLE
    - No active question from question engine
    - No pending follow-ups
    - No warnings

    Always broken by Priority 1–3 conditions.
    """
    if priority <= PRIORITY_DECISION:
        return False

    operator = state.get("Operator") or {}
    if operator.get("InteractionState") == "AwaitingResponse":
        return False

    strategy = state.get("Strategy") or {}
    if strategy.get("FollowUpNeeded"):
        return False

    return True


# ============================================================
# HELPERS
# ============================================================

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


def _clean_penalty(penalty: str) -> str:
    """Strip emoji prefix from penalty string for calm display."""
    for prefix in ("🔴 ", "🟠 ", "🟡 ", "🔵 "):
        if penalty.startswith(prefix):
            return penalty[len(prefix):]
    return penalty


def _strategy_label(key: str) -> str:
    labels = {
        "SOLAR":       "Solar charging",
        "DC_DC":       "DC-DC charging",
        "GENERATOR":   "Generator",
        "REDUCE":      "Load reduction",
        "INVESTIGATE": "Investigation",
    }
    return labels.get(key, key)


def _charging_source_label(signals: dict) -> str:
    if signals["shore_power"]:
        return "shore power"
    if signals["solar_w"] > 10 and signals["solar_state"] != "NIGHT":
        return "solar"
    strategy = signals["strategy_selected"]
    if strategy == "DC_DC":
        return "DC-DC charger"
    if strategy == "GENERATOR":
        return "generator"
    return "unknown source"


def _location_label(location: str) -> str:
    labels = {
        "AT_ANCHOR":       "Vessel at anchor",
        "DOCK_SHORE":      "Vessel at dock — shore power available",
        "DOCK_NO_SHORE":   "Vessel at dock — no shore power",
    }
    return labels.get(location, "")


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OKi attention_engine.py — Dev Test")
    print("=" * 60)

    def run(label, state):
        result = compute_attention(state)
        print(f"\n📋 {label}")
        print(f"   Priority       : {result.priority_label}")
        print(f"   Silence        : {result.silence}")
        print(f"   Primary State  :")
        for line in result.primary_state.split("\n"):
            print(f"     {line}")
        if result.secondary_context:
            print(f"   Context        :")
            for c in result.secondary_context:
                print(f"     — {c}")
        if result.active_question:
            print(f"   Question       : {result.active_question['text']}")
            print(f"   Options        : {result.active_question['options']}")

    # Test 1 — Fully stable
    run("Fully stable — solar charging", {
        "Battery":  {"SoC": 72, "Current": 12.0, "Voltage": 26.8},
        "Derived":  {"EnergyMode": "CHARGING"},
        "System":   {"SystemHealth": 95, "Severity": None, "HealthPenalties": []},
        "Solar":    {"State": "ACTIVE", "Power": 850, "CountdownString": "☀️ Solar active — 850W — sunset in 4h 20m", "ForecastSummary": "Sunset in 4h 20m — estimated 3700Wh solar remaining"},
        "Blackout": {"BlackoutMode": False},
        "EnergyForecast": {"NetPowerW": 650, "ConsumptionW": 200, "TimeToShutdownH": None, "TimeToCriticalH": None},
        "VesselState": {"SurvivalMode": False, "MovementState": "NOT_MOVING", "LocationContext": "DOCK_SHORE", "NeedsLocationQuestion": False},
        "Strategy": {"Selected": "NONE", "Status": "NONE", "FollowUpNeeded": False},
        "Operator": {"InteractionState": None},
        "AC":       {"State": "ACTIVE_LOAD", "GridVoltage": 230},
    })

    # Test 2 — Sunset approaching, discharging
    run("Sunset approaching, battery draining", {
        "Battery":  {"SoC": 48, "Current": -8.0, "Voltage": 25.1},
        "Derived":  {"EnergyMode": "DISCHARGING"},
        "System":   {"SystemHealth": 75, "Severity": None, "HealthPenalties": []},
        "Solar":    {"State": "DECLINING", "Power": 120, "SunsetWarning": "WARNING",
                     "CountdownString": "🟠 Sunset in 45m — 120W now",
                     "ForecastSummary": "Sunset in 45m — estimated 90Wh remaining"},
        "Blackout": {"BlackoutMode": False},
        "EnergyForecast": {"NetPowerW": -88, "ConsumptionW": 208, "TimeToShutdownH": 5.5, "TimeToCriticalH": 4.2},
        "VesselState": {"SurvivalMode": False, "MovementState": "NOT_MOVING", "LocationContext": "AT_ANCHOR", "NeedsLocationQuestion": False},
        "Strategy": {"Selected": "NONE", "Status": "NONE", "FollowUpNeeded": False},
        "Operator": {"InteractionState": None},
        "AC":       {"State": "NO_SHORE"},
    })

    # Test 3 — Survival mode
    run("Survival — 2h to blackout, no charging", {
        "Battery":  {"SoC": 14, "Current": -12.0, "Voltage": 23.5},
        "Derived":  {"EnergyMode": "DISCHARGING"},
        "System":   {"SystemHealth": 20, "Severity": "CRITICAL", "HealthPenalties": ["🔴 Battery critically low at 14%"]},
        "Solar":    {"State": "NIGHT", "Power": 0},
        "Blackout": {"BlackoutMode": False},
        "EnergyForecast": {"NetPowerW": -288, "ConsumptionW": 288, "TimeToShutdownH": 1.8, "TimeToCriticalH": 0.8},
        "VesselState": {"SurvivalMode": True, "SurvivalPrimaryMessage": "Power is critically low.\nEstimated time to blackout: 1h 48m.\nOKi operational after blackout: up to 48h.", "MovementState": "NOT_MOVING", "LocationContext": "UNKNOWN", "NeedsLocationQuestion": True},
        "Strategy": {"Selected": "NONE", "Status": "NONE", "FollowUpNeeded": False},
        "Operator": {"InteractionState": None},
        "AC":       {"State": "NO_SHORE"},
    })

    # Test 4 — Active blackout, 9h backup remaining
    run("Blackout active — 9h backup remaining", {
        "Battery":  {"SoC": 5, "Current": 0.0, "Voltage": 12.0},
        "Derived":  {"EnergyMode": "IDLE"},
        "System":   {"SystemHealth": 10, "Severity": "CRITICAL", "HealthPenalties": ["🔴 Vessel power lost"]},
        "Solar":    {"State": "NIGHT", "Power": 0},
        "Blackout": {"BlackoutMode": True, "UPSRemainingHours": 9.2, "UPSDisplayString": "9h 12m", "UPSWarningLevel": "WARNING", "OperatorMessage": "Vessel power lost for 38h 00m. OKi backup battery: 9h 12m remaining."},
        "EnergyForecast": {"NetPowerW": -10, "ConsumptionW": 10, "TimeToShutdownH": 9.2},
        "VesselState": {"SurvivalMode": False, "MovementState": "UNKNOWN", "LocationContext": "UNKNOWN", "NeedsLocationQuestion": False},
        "Strategy": {"Selected": "NONE", "Status": "NONE", "FollowUpNeeded": False},
        "Operator": {"InteractionState": None},
        "AC":       {"State": "UNKNOWN"},
    })

    # Test 5 — Active question from operator engine
    run("Active question — awaiting operator response", {
        "Battery":  {"SoC": 22, "Current": -10.0, "Voltage": 24.0},
        "Derived":  {"EnergyMode": "DISCHARGING"},
        "System":   {"SystemHealth": 55, "Severity": "WARNING", "HealthPenalties": ["🟠 CAN bus offline"]},
        "Solar":    {"State": "NIGHT", "Power": 0},
        "Blackout": {"BlackoutMode": False},
        "EnergyForecast": {"NetPowerW": -240, "ConsumptionW": 240, "TimeToShutdownH": 7.2},
        "VesselState": {"SurvivalMode": False, "MovementState": "NOT_MOVING", "LocationContext": "UNKNOWN", "NeedsLocationQuestion": False},
        "Strategy": {"Selected": "NONE", "Status": "NONE", "FollowUpNeeded": False},
        "Operator": {
            "InteractionState":  "AwaitingResponse",
            "ActiveQuestionText":"Battery is at 22% and discharging with no charging source detected. What is the situation?",
            "Options":           ["Expected", "Investigating", "I don't know"],
            "QuestionLayer":     "DIAGNOSIS",
            "QuestionContext":   "LOW_BATTERY_DIAGNOSIS",
        },
        "AC": {"State": "NO_SHORE"},
    })

    print("\n" + "=" * 60)
    print("Test complete.")
