# ============================================================
# OKi ENGINE v8.2 – Supervisory Intelligence Core
# ============================================================
#
# Changelog v8.2
# ---------------
# • consult_case_library() now writes state["System"]["AdvisoryCase"]
#   with the matched case_id — web UI uses this to render advisory
#   as a direct link into the Knowledge Base
#
# Changelog v8.1
# ---------------
# • All top-level module imports wrapped in try/except — crash-safe on Render
# • "generator_failure" scenario added to load_scenario()
# • consult_case_library() fixed: Case objects use .case_id/.title not dict keys
# • New modules integrated into engine_cycle():
#     fuel_tank_module     → compute_fuel_state()
#     energy_time_module   → compute_energy_time()
#     situation_classifier → evaluate_situation_type(), evaluate_decision_window()
#     diagnostic_engine    → run_diagnostics()
# • All v8.0 logic preserved
#
# ============================================================

import time
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ------------------------------------------------------------
# CASE LIBRARY
# ------------------------------------------------------------

sys.path.append(str(Path(__file__).resolve().parents[1] / "02_OKi_Knowledge"))

try:
    from case_library import CASE_LIBRARY
except Exception as _e:
    print(f"[OKi] Warning — case_library import failed: {_e}")
    class _EmptyLibrary:
        cases = {}
        def search_cases(self, *a, **kw): return []
    CASE_LIBRARY = _EmptyLibrary()

# ------------------------------------------------------------
# HEALTH ENGINE
# ------------------------------------------------------------

try:
    from health_engine import score_from_state as health_score_from_state
except Exception as _e:
    print(f"[OKi] Warning — health_engine import failed: {_e}")
    @dataclass
    class _HealthResult:
        score: int = 100
        category_a_penalty: int = 0
        category_b_penalty: int = 0
        category_c_penalty: int = 0
        category_d_penalty: int = 0
        category_e_penalty: int = 0
        category_f_penalty: int = 0
        active_penalties: list = field(default_factory=list)
        advisories: list = field(default_factory=list)
    def health_score_from_state(*a, **kw): return _HealthResult()

# ------------------------------------------------------------
# BLACKOUT MONITOR
# ------------------------------------------------------------

try:
    from blackout_monitor import detect_blackout
except Exception as _e:
    print(f"[OKi] Warning — blackout_monitor import failed: {_e}")
    def detect_blackout(*a, **kw): pass

# ------------------------------------------------------------
# PREDICTIVE MODULES
# ------------------------------------------------------------

try:
    from solar_input_module import compute_solar_state
except Exception as _e:
    print(f"[OKi] Warning — solar_input_module import failed: {_e}")
    def compute_solar_state(*a, **kw): pass

try:
    from energy_forecast_engine import compute_energy_forecast
except Exception as _e:
    print(f"[OKi] Warning — energy_forecast_engine import failed: {_e}")
    def compute_energy_forecast(*a, **kw): pass

try:
    from energy_strategy_engine import evaluate_strategy
except Exception as _e:
    print(f"[OKi] Warning — energy_strategy_engine import failed: {_e}")
    def evaluate_strategy(*a, **kw): pass

try:
    from vessel_state_engine import evaluate_vessel_state
except Exception as _e:
    print(f"[OKi] Warning — vessel_state_engine import failed: {_e}")
    def evaluate_vessel_state(*a, **kw): pass

try:
    from operator_question_engine import (
        run_question_engine,
        process_answer as process_operator_answer_new,
    )
except Exception as _e:
    print(f"[OKi] Warning — operator_question_engine import failed: {_e}")
    def run_question_engine(*a, **kw): pass
    def process_operator_answer_new(*a, **kw): pass

try:
    from attention_engine import compute_attention
except Exception as _e:
    print(f"[OKi] Warning — attention_engine import failed: {_e}")
    def compute_attention(*a, **kw): pass

# ------------------------------------------------------------
# NEW MODULES v8.1
# ------------------------------------------------------------

try:
    from fuel_tank_module import compute_fuel_state
except Exception as _e:
    print(f"[OKi] Warning — fuel_tank_module import failed: {_e}")
    def compute_fuel_state(*a, **kw): pass

try:
    from energy_time_module import compute_energy_time
except Exception as _e:
    print(f"[OKi] Warning — energy_time_module import failed: {_e}")
    def compute_energy_time(*a, **kw): pass

try:
    from situation_classifier import evaluate_situation_type, evaluate_decision_window
except Exception as _e:
    print(f"[OKi] Warning — situation_classifier import failed: {_e}")
    def evaluate_situation_type(*a, **kw): pass
    def evaluate_decision_window(*a, **kw): pass

try:
    from diagnostic_engine import run_diagnostics
except Exception as _e:
    print(f"[OKi] Warning — diagnostic_engine import failed: {_e}")
    def run_diagnostics(*a, **kw): pass

State = Dict[str, Any]

# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class EngineConfig:
    question_cooldown: int = 20
    answer_display_time: int = 5

    can_warning_threshold: int = 5
    can_critical_threshold: int = 15

    soc_critical: int = 20
    soc_low: int = 30
    soc_full: int = 95
    charge_low_current: float = 3.0

    solar_detection_threshold: float = 30.0
    solar_power_minimum: float = 1.0

    ac_present_threshold: float = 200.0
    ac_high_load_threshold: float = 300.0

    aggressive_discharge_threshold: float = -30.0

    care_reward_interval: int = 30
    care_reward_increment: int = 1


CONFIG = EngineConfig()

# ============================================================
# SMALL HELPERS
# ============================================================


def get_section(state: State, section: str) -> Dict[str, Any]:
    if section not in state or state[section] is None:
        state[section] = {}
    return state[section]


def get_value(state: State, section: str, key: str, default: float = 0.0) -> float:
    return float(get_section(state, section).get(key) or default)


def get_optional(state: State, section: str, key: str) -> Any:
    return get_section(state, section).get(key)


# ============================================================
# ENERGY COMPUTATION
# ============================================================


def compute_energy_mode(state: State) -> None:
    battery = get_section(state, "Battery")
    voltage = float(battery.get("Voltage") or 0.0)
    current = float(battery.get("Current") or 0.0)

    derived = get_section(state, "Derived")
    derived["DCPower"] = round(voltage * current, 1)

    if current < -0.5:
        derived["EnergyMode"] = "DISCHARGING"
    elif current > 0.5:
        derived["EnergyMode"] = "CHARGING"
    else:
        derived["EnergyMode"] = "IDLE"


# ============================================================
# AC STATE ANALYSIS
# ============================================================


def compute_ac_state(state: State) -> None:
    ac      = get_section(state, "AC")
    voltage = ac.get("GridVoltage")
    power   = ac.get("GridPower")

    if voltage is None:
        ac["State"] = "UNKNOWN"
        return
    if voltage < CONFIG.ac_present_threshold:
        ac["State"] = "NO_SHORE"
        return
    if power is None:
        ac["State"] = "AC_PRESENT"
        return

    if power < 5:
        ac["State"] = "IDLE"
    elif power < 50:
        ac["State"] = "LOW_LOAD"
    elif power < CONFIG.ac_high_load_threshold:
        ac["State"] = "ACTIVE_LOAD"
    else:
        ac["State"] = "HIGH_LOAD"


# ============================================================
# SOLAR DETECTION
# ============================================================


def compute_solar_detection(state: State) -> None:
    solar = get_section(state, "Solar")
    solar_voltage = float(solar.get("Voltage") or 0.0)
    solar["Detected"] = solar_voltage > CONFIG.solar_detection_threshold


# ============================================================
# CAN WATCHDOG
# ============================================================


def evaluate_can_health(state: State) -> Optional[str]:
    comm     = get_section(state, "Communication")
    last_msg = comm.get("LastCANMessage")
    now      = datetime.utcnow()

    if last_msg is None:
        comm["CANHealthy"] = False
        return "CRITICAL"

    try:
        last_dt = datetime.fromisoformat(str(last_msg))
    except Exception:
        comm["CANHealthy"] = False
        return "CRITICAL"

    delta = (now - last_dt).total_seconds()

    if delta > CONFIG.can_critical_threshold:
        comm["CANHealthy"] = False
        return "CRITICAL"
    if delta > CONFIG.can_warning_threshold:
        comm["CANHealthy"] = False
        return "WARNING"

    comm["CANHealthy"] = True
    return None


# ============================================================
# HEALTH ENGINE BRIDGE
# ============================================================


def _build_health_input(state: State) -> dict:
    comm    = get_section(state, "Communication")
    battery = get_section(state, "Battery")
    ac      = get_section(state, "AC")
    care    = get_section(state, "Care")

    can_healthy = comm.get("CANHealthy")
    can_online  = True if can_healthy is True else (False if can_healthy is False else None)

    bms_data_present = battery.get("SoC") is not None
    if can_online is True and bms_data_present:
        bms_online = True
    elif can_online is False:
        bms_online = False
    else:
        bms_online = None

    shelly_status = ac.get("ShellyStatus")
    if shelly_status == "ONLINE":
        critical_systems_online = True
    elif shelly_status == "OFFLINE":
        critical_systems_online = False
    else:
        critical_systems_online = None

    soc_raw     = battery.get("SoC")
    soc_percent = float(soc_raw) if soc_raw is not None else None
    current     = float(battery.get("Current") or 0.0)

    return {
        "bms_online":               bms_online,
        "can_online":               can_online,
        "critical_systems_online":  critical_systems_online,
        "soc_percent":              soc_percent,
        "deep_discharge_count":     int(care.get("DeepDischargeCount") or 0),
        "high_load_detected":       ac.get("State") == "HIGH_LOAD",
        "aggressive_discharge":     current < CONFIG.aggressive_discharge_threshold,
        "battery_temp_celsius":     battery.get("TemperatureCelsius"),
        "engine_room_temp_celsius": get_section(state, "Environment").get("EngineRoomTempCelsius"),
        "firmware_outdated":        False,
        "minor_warnings":           0,
        "blackout_active":          bool(get_section(state, "Blackout").get("BlackoutMode", False)),
        "blackout_count":           int(get_section(state, "Blackout").get("BlackoutCount") or 0),
        "local_network_loss":       False,
    }


# ============================================================
# SYSTEM HEALTH
# ============================================================


def compute_system_health(state: State) -> None:
    system = get_section(state, "System")

    evaluate_can_health(state)

    health_input  = _build_health_input(state)
    health_result = health_score_from_state(health_input)

    system["SystemHealth"]     = health_result.score
    system["HealthPenalties"]  = health_result.active_penalties
    system["HealthAdvisories"] = health_result.advisories
    system["HealthCategories"] = {
        "A_SystemIntegrity":   health_result.category_a_penalty,
        "B_EnergyBattery":     health_result.category_b_penalty,
        "C_OperationalStress": health_result.category_c_penalty,
        "D_Environmental":     health_result.category_d_penalty,
        "E_Minor":             health_result.category_e_penalty,
        "F_PowerContinuity":   health_result.category_f_penalty,
    }

    raw_issues = [
        p.split(" ", 1)[1] if p and p[0] in "🔴🟠🟡" else p
        for p in health_result.active_penalties
    ]
    system["Inconsistency"] = raw_issues if raw_issues else None

    cat_a = health_result.category_a_penalty
    cat_f = health_result.category_f_penalty
    worst = max(cat_a, cat_f)
    if worst >= 30:
        system["Severity"] = "CRITICAL"
    elif worst >= 10:
        system["Severity"] = "WARNING"
    else:
        system["Severity"] = None

    _track_deep_discharge(state)


def _track_deep_discharge(state: State) -> None:
    battery = get_section(state, "Battery")
    care    = get_section(state, "Care")

    soc_raw = battery.get("SoC")
    if soc_raw is None:
        return

    soc              = float(soc_raw)
    was_in_discharge = bool(care.get("_InDeepDischarge", False))

    if soc < 20.0 and not was_in_discharge:
        care["DeepDischargeCount"] = int(care.get("DeepDischargeCount") or 0) + 1
        care["_InDeepDischarge"]   = True
    elif soc >= 25.0:
        care["_InDeepDischarge"] = False


# ============================================================
# RECOMMENDATION ENGINE
# ============================================================


def evaluate_recommendation(state: State) -> None:
    system     = get_section(state, "System")
    ac_state   = get_section(state, "AC").get("State")
    soc        = get_optional(state, "Battery", "SoC")
    advisories = system.get("HealthAdvisories") or []

    if soc is not None:
        soc = float(soc)

    recommendation = "System operating normally."
    reason: Optional[str] = None
    rule:   Optional[str] = None

    if soc is not None:
        if soc <= CONFIG.soc_critical:
            recommendation = (
                f"Battery critically low at {soc:.0f}%. "
                "Connect shore power or reduce loads immediately."
            )
            reason, rule = "Battery SoC critical", "SOC_CRITICAL"
        elif soc <= CONFIG.soc_low:
            recommendation = (
                f"Battery low at {soc:.0f}%. "
                "Consider connecting shore power soon."
            )
            reason, rule = "Battery SoC low", "SOC_LOW"
        elif soc >= CONFIG.soc_full:
            recommendation = (
                f"Battery fully charged at {soc:.0f}%. "
                "Shore power can be disconnected if not needed."
            )
            reason, rule = "Battery full", "SOC_FULL"

    if rule is None:
        if ac_state == "NO_SHORE":
            recommendation = "No shore power detected."
            reason, rule = "AC disconnected", "AC_DISCONNECTED"
        elif ac_state == "HIGH_LOAD":
            recommendation = "High AC load detected. Verify connected equipment."
            reason, rule = "High power consumption", "HIGH_LOAD"
        elif ac_state == "IDLE":
            recommendation = "AC present but no load active."
            reason, rule = "System idle", "IDLE"

    if rule is None and advisories:
        adv_text = advisories[0]
        for prefix in ("⚠️ ", "💡 "):
            adv_text = adv_text.replace(prefix, "")
        recommendation = adv_text
        reason, rule = "Health advisory", "HEALTH_ADVISORY"

    system["Recommendation"]       = recommendation
    system["RecommendationReason"] = reason
    system["RecommendationRule"]   = rule


# ============================================================
# CASE CONSULTATION — FIXED v8.1
# Case objects are dataclasses — use attribute access, not dict keys
# ============================================================


def consult_case_library(state: State) -> None:
    system = get_section(state, "System")
    issues = system.get("Inconsistency")

    if not issues:
        system["Advisory"] = None
        return

    search_text = " ".join(issues)

    try:
        matches = CASE_LIBRARY.search_cases(search_text)
    except Exception:
        system["Advisory"] = None
        return

    if matches:
        top = matches[0]
        # Support both dataclass objects and plain dicts safely
        case_id = getattr(top, "case_id", None) or (top.get("case_id", "?") if isinstance(top, dict) else "?")
        title   = getattr(top, "title",   None) or (top.get("title",   "?") if isinstance(top, dict) else "?")
        system["Advisory"]     = f"Resembles case {case_id} — {title}"
        system["AdvisoryCase"] = case_id
    else:
        system["Advisory"]     = None
        system["AdvisoryCase"] = None


# ============================================================
# CARE INTELLIGENCE
# ============================================================


def compute_care(state: State) -> None:
    system = get_section(state, "System")
    care   = get_section(state, "Care")

    sys_score = int(system.get("SystemHealth") or 0)
    op_score  = int(care.get("OperatorCareScore") or 0)

    care["SystemCareScore"] = sys_score
    care["CareIndex"]       = round(0.6 * sys_score + 0.4 * op_score)


def apply_care_task(state_manager, increment: int = 3) -> None:
    state = state_manager.get()
    care  = get_section(state, "Care")

    current = int(care.get("OperatorCareScore") or 0)
    care["OperatorCareScore"] = min(100, current + increment)
    compute_care(state)


def _auto_care_reward(state: State) -> None:
    system = get_section(state, "System")
    care   = get_section(state, "Care")

    health = int(system.get("SystemHealth") or 0)
    soc    = get_value(state, "Battery", "SoC", default=50.0)

    if health < 80 or soc < CONFIG.soc_low:
        return

    counter = int(care.get("HealthyCycleCounter") or 0) + 1
    care["HealthyCycleCounter"] = counter

    if counter % CONFIG.care_reward_interval == 0:
        current = int(care.get("OperatorCareScore") or 0)
        care["OperatorCareScore"] = min(100, current + CONFIG.care_reward_increment)
        compute_care(state)


# ============================================================
# SNAPSHOT MEMORY SYSTEM
# ============================================================


def build_snapshot(state: State) -> Dict[str, Any]:
    ac      = get_section(state, "AC")
    derived = get_section(state, "Derived")
    system  = get_section(state, "System")

    return {
        "timestamp":        datetime.utcnow().isoformat(),
        "ACVoltage":        ac.get("GridVoltage"),
        "ACPower":          ac.get("GridPower"),
        "Mode":             derived.get("EnergyMode"),
        "Health":           system.get("SystemHealth"),
        "Severity":         system.get("Severity"),
        "Inconsistency":    system.get("Inconsistency"),
        "Advisory":         system.get("Advisory"),
        "Recommendation":   system.get("Recommendation"),
        "HealthCategories": system.get("HealthCategories"),
    }


def snapshot_changed(state: State, snapshot: Dict[str, Any]) -> bool:
    system    = get_section(state, "System")
    signature = (
        snapshot["ACVoltage"],
        snapshot["ACPower"],
        snapshot["Mode"],
        snapshot["Health"],
    )
    last = system.get("LastSnapshotSignature")
    if signature == last:
        return False
    system["LastSnapshotSignature"] = signature
    return True


# ============================================================
# OPERATOR QUESTION SYSTEM
# ============================================================


def generate_question(state: State) -> None:
    now    = time.time()
    op     = get_section(state, "Operator")
    system = get_section(state, "System")

    if op.get("InteractionState"):
        return

    last_question_time = float(op.get("LastQuestionTime") or 0.0)
    if now - last_question_time < CONFIG.question_cooldown:
        return

    issues = system.get("Inconsistency")
    if not issues:
        return

    op["InteractionState"]   = "AwaitingResponse"
    op["ActiveQuestionText"] = f"Inconsistency detected: {'; '.join(issues)}. Confirm?"
    op["OptionA"]            = "Expected"
    op["OptionB"]            = "Investigating"
    op["OptionC"]            = "Unexpected"
    op["LastQuestionTime"]   = now


# ============================================================
# OPERATOR RESPONSE
# ============================================================


def process_operator_response(state_manager, choice: str) -> None:
    state      = state_manager.get()
    op         = get_section(state, "Operator")
    option_map = {"A": op.get("OptionA"), "B": op.get("OptionB"), "C": op.get("OptionC")}

    op["LastAnswerText"]     = f"Recorded: {option_map.get(choice)}"
    op["AnswerTimestamp"]    = time.time()
    op["InteractionState"]   = None
    op["ActiveQuestionText"] = None
    op["OptionA"]            = None
    op["OptionB"]            = None
    op["OptionC"]            = None


# ============================================================
# DEV MODE
# ============================================================


def toggle_dev_mode(state_manager) -> bool:
    state             = state_manager.get()
    system            = get_section(state, "System")
    current           = bool(system.get("DevMode", False))
    system["DevMode"] = not current
    print(f"DEV mode set to: {system['DevMode']}")
    return system["DevMode"]


# ============================================================
# SCENARIOS
# ============================================================


def load_scenario(state_manager, name: str) -> None:
    state   = state_manager.get()
    battery = get_section(state, "Battery")
    ac      = get_section(state, "AC")
    derived = get_section(state, "Derived")
    comm    = get_section(state, "Communication")

    if name == "anchor":
        battery["SoC"]     = 63
        battery["Voltage"] = 25.1
        battery["Current"] = -8.0
        ac["Shore"]        = False
        ac["GridVoltage"]  = 0
        ac["GridPower"]    = 0
        ac["ShellyStatus"] = "OFFLINE"
        derived["EnergyMode"]  = "DISCHARGING"
        comm["CANHealthy"]     = True
        comm["LastCANMessage"] = datetime.utcnow().isoformat()

    elif name == "casa":
        battery["SoC"]     = 72
        battery["Voltage"] = 26.8
        battery["Current"] = 12.0
        ac["Shore"]        = True
        ac["GridVoltage"]  = 230
        ac["GridPower"]    = 420
        ac["ShellyStatus"] = "ONLINE"
        derived["EnergyMode"]  = "CHARGING"
        comm["CANHealthy"]     = True
        comm["LastCANMessage"] = datetime.utcnow().isoformat()

    elif name == "drain":
        battery["SoC"]     = 18
        battery["Voltage"] = 23.8
        battery["Current"] = -22.0
        ac["Shore"]        = False
        ac["GridVoltage"]  = 0
        ac["GridPower"]    = 0
        ac["ShellyStatus"] = "OFFLINE"
        derived["EnergyMode"]  = "DISCHARGING"
        comm["CANHealthy"]     = None
        comm["LastCANMessage"] = None

    elif name == "generator_failure":
        # Demo: battery low + discharging + generator expected but not running
        # Immediately triggers CRITICAL_COUNTDOWN and diagnostic engine
        from datetime import timezone
        battery["SoC"]     = 22
        battery["Voltage"] = 24.1
        battery["Current"] = -10.0
        ac["Shore"]        = False
        ac["GridVoltage"]  = 0
        ac["GridPower"]    = 0
        ac["ShellyStatus"] = "OFFLINE"
        derived["EnergyMode"]  = "DISCHARGING"
        comm["CANHealthy"]     = True
        comm["LastCANMessage"] = datetime.utcnow().isoformat()

        gen = get_section(state, "Generator")
        gen["Running"]     = False
        gen["Expected"]    = True
        gen["RecentlyRan"] = False
        gen["ErrorCode"]   = ""

        fuel = get_section(state, "Fuel")
        fuel["LevelPercent"]   = 40.0
        fuel["LastUpdate"]     = datetime.now(timezone.utc)
        fuel["SensorReliable"] = True
        fuel["State"]          = "OK"
        fuel["Inconsistency"]  = None

        solar = get_section(state, "Solar")
        solar["Power"]   = 0.0
        solar["Voltage"] = 0.0
        solar["State"]   = "NIGHT"

    state_manager.save()


# ============================================================
# ENGINE CYCLE v8.1
# ============================================================


def engine_cycle(state_manager) -> State:
    """
    Full OKi engine cycle — 21 steps.
    Steps 14–18 are new in v8.1.
    """
    state = state_manager.get()

    # Existing pipeline
    compute_energy_mode(state)
    compute_ac_state(state)
    compute_solar_detection(state)
    compute_solar_state(state)
    detect_blackout(state)
    compute_system_health(state)
    compute_energy_forecast(state)
    evaluate_vessel_state(state)
    evaluate_strategy(state)
    evaluate_recommendation(state)
    consult_case_library(state)
    compute_care(state)
    _auto_care_reward(state)

    # ── New modules v8.1 ──────────────────────────────────────
    compute_fuel_state(state)        # fuel level + sensor reliability
    compute_energy_time(state)       # time-to-critical / time-to-shutdown
    evaluate_situation_type(state)   # SituationType classification
    evaluate_decision_window(state)  # DecisionWindow pressure level
    run_diagnostics(state)           # diagnostic state machine + questions
    # ─────────────────────────────────────────────────────────

    run_question_engine(state)
    compute_attention(state)

    snap = build_snapshot(state)
    if snapshot_changed(state, snap):
        state_manager.append_memory(snap)

    return state
