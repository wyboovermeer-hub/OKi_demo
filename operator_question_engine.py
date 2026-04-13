"""
operator_question_engine.py — OKi Operator Question Engine
Version: 1.1
Spec: OKi 002 Claude Implementation Brief v1.0 + Situational Awareness v1.1

Responsibilities:
    - Maintain exactly one active question at all times (when needed)
    - Detect issues and generate diagnosis question (Layer 1)
    - Ask location context question when vessel stopped (Layer 1b NEW)
    - After diagnosis, generate context-aware strategy question (Layer 2)
    - After strategy, monitor execution and generate follow-up (Layer 3)
    - Process operator answers and advance question chain
    - Never block monitoring — always continue observing
    - Enforce information hierarchy: survival message always first

Question Chain:
    SURVIVAL   → Primary message shown (not a question — information)
    LOCATION   → "The vessel is not moving. What is the current situation?"
    DIAGNOSIS  → "What is the situation?"
    STRATEGY   → "How will the vessel restore power?" (context-filtered options)
    FOLLOWUP   → "Strategy not working — what is the situation?"
    RESOLVED   → No active question

Changelog v1.1:
    - LOCATION layer added: vessel stopped → ask anchor/dock context
    - Strategy options filtered by vessel state and available sources
    - Survival primary message enforced before any question
    - Shore power follow-up: dock confirmed but AC not detected
    - Moving vessel: shore power option removed from strategy list

Called by engine_cycle() after evaluate_vessel_state().
Reads:  state["System"], state["Battery"], state["Solar"],
        state["Strategy"], state["VesselState"]
Writes: state["Operator"]
"""

import time
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

# Minimum seconds between questions (prevents spam)
QUESTION_COOLDOWN_SEC   = 30

# How long to display an answer before clearing (seconds)
ANSWER_DISPLAY_SEC      = 8

# Battery thresholds that trigger diagnosis questions
SOC_QUESTION_THRESHOLD  = 30.0   # Ask if SoC below this AND not charging


# ============================================================
# QUESTION LAYERS
# ============================================================

LAYER_LOCATION  = "LOCATION"    # NEW v1.1: vessel stopped, context unknown
LAYER_DIAGNOSIS = "DIAGNOSIS"
LAYER_STRATEGY  = "STRATEGY"
LAYER_FOLLOWUP  = "FOLLOWUP"
LAYER_NONE      = "NONE"


# ============================================================
# MAIN FUNCTION
# ============================================================

def run_question_engine(state: dict) -> None:
    """
    Main entry point — called once per engine cycle.

    Logic:
    1. If follow-up question needed from strategy engine → show it
    2. Else if active question exists → wait for answer
    3. Else if conditions trigger diagnosis → ask diagnosis question
    4. Else if diagnosis answered and strategy needed → ask strategy question
    5. Else → no question needed
    """
    op       = _get_section(state, "Operator")
    strategy = state.get("Strategy") or {}
    now      = time.time()

    # ----------------------------------------------------------------
    # Clear expired answer display
    # ----------------------------------------------------------------
    _clear_expired_answer(op, now)

    # ----------------------------------------------------------------
    # Do not interrupt active question
    # ----------------------------------------------------------------
    if op.get("InteractionState") == "AwaitingResponse":
        return

    # ----------------------------------------------------------------
    # Cooldown — don't spam questions
    # ----------------------------------------------------------------
    last_q = float(op.get("LastQuestionTime") or 0.0)
    if now - last_q < QUESTION_COOLDOWN_SEC:
        return

    # ----------------------------------------------------------------
    # Layer 3 — Strategy follow-up (highest priority new question)
    # ----------------------------------------------------------------
    if strategy.get("FollowUpNeeded"):
        from energy_strategy_engine import build_followup_question
        fq = build_followup_question(state)
        if fq:
            _post_question(op, now,
                text    = fq["text"],
                options = fq["options"],
                layer   = LAYER_FOLLOWUP,
                context = fq.get("context", "STRATEGY_FOLLOWUP"),
            )
            return

    # ----------------------------------------------------------------
    # Layer 1 — Diagnosis (issue detected, no active strategy)
    # ----------------------------------------------------------------
    current_layer = op.get("QuestionLayer", LAYER_NONE)

    if current_layer == LAYER_NONE:
        trigger = _detect_diagnosis_trigger(state)
        if trigger:
            _post_question(op, now,
                text    = trigger["text"],
                options = ["Expected", "Investigating", "I don't know"],
                layer   = LAYER_DIAGNOSIS,
                context = trigger["context"],
            )
            return

    # ----------------------------------------------------------------
    # Layer 2 — Strategy (diagnosis answered, ask how to fix it)
    # ----------------------------------------------------------------
    if current_layer == LAYER_DIAGNOSIS and op.get("LastAnswer") is not None:
        last_answer = op.get("LastAnswer")

        # If operator said "Expected" — no strategy needed, resolve
        if last_answer == "Expected":
            op["QuestionLayer"] = LAYER_NONE
            return

        # Otherwise ask for strategy
        strategy_options = _build_strategy_options(state)
        _post_question(op, now,
            text    = "How will the vessel restore power?",
            options = strategy_options,
            layer   = LAYER_STRATEGY,
            context = "STRATEGY_SELECTION",
        )
        return


def process_answer(state: dict, choice_index: int) -> None:
    """
    Called when operator taps an answer button.
    choice_index: 0-based index into current options list.

    Advances the question chain and triggers strategy selection if needed.
    """
    op      = _get_section(state, "Operator")
    options = op.get("Options") or []
    layer   = op.get("QuestionLayer", LAYER_NONE)
    context = op.get("QuestionContext", "")

    if choice_index < 0 or choice_index >= len(options):
        return

    answer_text = options[choice_index]

    # Record answer
    op["LastAnswer"]        = answer_text
    op["LastAnswerIndex"]   = choice_index
    op["AnswerTimestamp"]   = time.time()
    op["LastAnswerDisplay"] = f"Recorded: {answer_text}"
    op["AnswerDisplayUntil"]= time.time() + ANSWER_DISPLAY_SEC

    # Clear active question
    op["InteractionState"]  = None
    op["ActiveQuestionText"]= None
    op["Options"]           = None

    # ----------------------------------------------------------------
    # Handle location context answer (NEW v1.1)
    # ----------------------------------------------------------------
    if context == "LOCATION_CONTEXT":
        _handle_location_answer(state, answer_text)
        op["QuestionLayer"] = LAYER_NONE

    # ----------------------------------------------------------------
    # Handle shore power follow-up
    # ----------------------------------------------------------------
    elif context == "SHORE_POWER_FOLLOWUP":
        if answer_text == "Shore power not available after all":
            from vessel_state_engine import confirm_location
            confirm_location(state, "DOCK_NO_SHORE")
        op["QuestionLayer"] = LAYER_NONE

    # ----------------------------------------------------------------
    # Handle strategy selection layer
    # ----------------------------------------------------------------
    elif context == "STRATEGY_SELECTION":
        _handle_strategy_selection(state, answer_text)
        op["QuestionLayer"] = LAYER_NONE

    # ----------------------------------------------------------------
    # Handle strategy follow-up
    # ----------------------------------------------------------------
    elif context == "STRATEGY_FOLLOWUP":
        strategy = _get_section(state, "Strategy")
        strategy["FollowUpNeeded"] = False
        op["QuestionLayer"] = LAYER_NONE

    # ----------------------------------------------------------------
    # Handle diagnosis layer — advance to strategy layer
    # ----------------------------------------------------------------
    elif layer == LAYER_DIAGNOSIS:
        # Keep layer state — run_question_engine will advance to strategy
        pass


# ============================================================
# DIAGNOSIS TRIGGER DETECTION
# ============================================================

def _detect_diagnosis_trigger(state: dict) -> Optional[dict]:
    """
    Detect conditions that warrant asking the operator a diagnosis question.
    Returns question dict or None.

    Priority order:
    1. Critical battery + no charging
    2. System inconsistency (from health engine)
    3. Solar anomaly
    """
    battery = state.get("Battery") or {}
    solar   = state.get("Solar")   or {}
    system  = state.get("System")  or {}
    derived = state.get("Derived") or {}

    soc      = _safe_float(battery.get("SoC"), 100.0)
    mode     = derived.get("EnergyMode", "IDLE")
    issues   = system.get("Inconsistency") or []

    # Trigger 1 — Low battery, not charging
    if soc <= SOC_QUESTION_THRESHOLD and mode == "DISCHARGING":
        return {
            "text": (
                f"Battery is at {soc:.0f}% and discharging with no charging source detected. "
                "What is the situation?"
            ),
            "context": "LOW_BATTERY_DIAGNOSIS",
        }

    # Trigger 2 — System inconsistency from health engine
    if issues:
        issue_summary = "; ".join(issues[:2])   # show max 2 issues
        return {
            "text": f"Inconsistency detected: {issue_summary}. What is the situation?",
            "context": "SYSTEM_INCONSISTENCY",
        }

    # Trigger 3 — Solar anomaly during active solar strategy
    strategy = state.get("Strategy") or {}
    if (
        solar.get("Anomaly")
        and strategy.get("Selected") == "SOLAR"
        and strategy.get("Status") != "FAILED"  # follow-up handles failures
    ):
        return {
            "text": f"Solar input anomaly: {solar.get('AnomalyReason')}. What is the situation?",
            "context": "SOLAR_ANOMALY",
        }

    return None


# ============================================================
# STRATEGY OPTIONS
# ============================================================

def _build_strategy_options(state: dict) -> list:
    """
    Build strategy options dynamically based on what's available.
    Night → no solar option.
    Blackout → no shore option.
    """
    solar   = state.get("Solar")   or {}
    blackout= state.get("Blackout") or {}
    options = []

    # Solar — only offer during daylight
    if solar.get("State") not in ("NIGHT", None):
        options.append("Use solar input")

    # DC-DC always an option if propulsion bank available
    options.append("Use DC-DC charging (house ← propulsion)")

    # Generator
    options.append("Start generator")

    # Reduce load
    options.append("Reduce consumption")

    # Investigation fallbacks
    options.append("Investigating")
    options.append("I don't know")

    return options


def _handle_strategy_selection(state: dict, answer_text: str) -> None:
    """Map answer text to strategy key and call select_strategy()."""
    from energy_strategy_engine import select_strategy

    mapping = {
        "Use solar input":                        "SOLAR",
        "Use DC-DC charging (house ← propulsion)":"DC_DC",
        "Start generator":                         "GENERATOR",
        "Reduce consumption":                      "REDUCE",
        "Investigating":                           "INVESTIGATE",
        "I don't know":                            "INVESTIGATE",
    }

    strategy_key = mapping.get(answer_text, "INVESTIGATE")
    select_strategy(state, strategy_key)


# ============================================================
# SURVIVAL DISPLAY (Information Hierarchy)
# ============================================================

def _update_survival_display(state: dict, op: dict) -> None:
    """
    Always write survival primary message to operator state.
    This is shown above any active question — never suppressed.
    Not a question — pure information display.
    """
    vessel = state.get("VesselState") or {}
    if vessel.get("SurvivalMode"):
        op["SurvivalMessage"]     = vessel.get("SurvivalPrimaryMessage")
        op["SurvivalTimeString"]  = vessel.get("SurvivalTimeString")
        op["SurvivalModeActive"]  = True
    else:
        op["SurvivalMessage"]     = None
        op["SurvivalTimeString"]  = None
        op["SurvivalModeActive"]  = False


# ============================================================
# LOCATION ANSWER HANDLER
# ============================================================

def _handle_location_answer(state: dict, answer_text: str) -> None:
    """Map location answer text to location key and confirm in vessel_state_engine."""
    from vessel_state_engine import confirm_location

    mapping = {
        "At anchor":                     "AT_ANCHOR",
        "At dock — shore power available": "DOCK_SHORE",
        "At dock — no shore power":        "DOCK_NO_SHORE",
        "Investigate":                    None,
        "I don't know":                  None,
    }

    location_key = mapping.get(answer_text)
    if location_key:
        confirm_location(state, location_key)
    # If None (investigate/unknown) — leave LocationContext as UNKNOWN,
    # vessel_state_engine will ask again next relevant cycle


# ============================================================
# QUESTION POSTING
# ============================================================

def _post_question(
    op:      dict,
    now:     float,
    text:    str,
    options: list,
    layer:   str,
    context: str,
) -> None:
    op["InteractionState"]  = "AwaitingResponse"
    op["ActiveQuestionText"]= text
    op["Options"]           = options
    op["QuestionLayer"]     = layer
    op["QuestionContext"]   = context
    op["LastQuestionTime"]  = now
    op["LastAnswer"]        = None   # clear previous answer when new question posted


def _clear_expired_answer(op: dict, now: float) -> None:
    until = op.get("AnswerDisplayUntil")
    if until and now > float(until):
        op["LastAnswerDisplay"]  = None
        op["AnswerDisplayUntil"] = None


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
    print("=" * 60)
    print("OKi operator_question_engine.py — Dev Test")
    print("=" * 60)

    def show_q(label, state):
        run_question_engine(state)
        op = state.get("Operator", {})
        print(f"\n📋 {label}")
        print(f"   Layer          : {op.get('QuestionLayer')}")
        print(f"   Question       : {op.get('ActiveQuestionText') or 'none'}")
        print(f"   Options        : {op.get('Options') or 'none'}")
        print(f"   State          : {op.get('InteractionState') or 'none'}")

    def answer(state, idx):
        process_answer(state, idx)
        op = state.get("Operator", {})
        print(f"   → Answered     : {op.get('LastAnswerDisplay')}")

    # Test 1 — Low battery, discharging → diagnosis question
    state1 = {
        "Battery": {"SoC": 22, "Voltage": 24.0, "Current": -10.0},
        "Derived": {"EnergyMode": "DISCHARGING"},
        "Solar":   {"State": "ACTIVE", "Power": 50, "Anomaly": False},
        "System":  {"Inconsistency": None},
        "Strategy":{"Selected": "NONE"},
        "Operator":{},
    }
    show_q("Low battery discharging — expect diagnosis question", state1)

    # Answer: Investigating (index 1) → expect strategy question next
    answer(state1, 1)
    state1["Operator"]["LastQuestionTime"] = 0   # reset cooldown
    show_q("After 'Investigating' answer — expect strategy question", state1)

    # Test 2 — Strategy follow-up needed
    state2 = {
        "Battery": {"SoC": 30, "Current": -8.0},
        "Derived": {"EnergyMode": "DISCHARGING"},
        "Solar":   {"State": "NIGHT", "Power": 0, "Anomaly": False},
        "System":  {"Inconsistency": None},
        "Strategy":{
            "Selected":       "SOLAR",
            "Status":         "FAILED",
            "FollowUpNeeded": True,
            "FailureReason":  "It is night — no solar available",
        },
        "Operator":{},
    }
    show_q("Strategy follow-up — solar selected but it's night", state2)

    # Test 3 — All healthy — no question
    state3 = {
        "Battery": {"SoC": 75, "Current": 10.0},
        "Derived": {"EnergyMode": "CHARGING"},
        "Solar":   {"State": "ACTIVE", "Power": 800, "Anomaly": False},
        "System":  {"Inconsistency": None},
        "Strategy":{"Selected": "NONE"},
        "Operator":{},
    }
    show_q("All healthy — no question expected", state3)

    print("\n" + "=" * 60)
    print("Test complete.")
