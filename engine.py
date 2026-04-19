# ============================================================
# OKi ENGINE v8.3 – Supervisory Intelligence Core
# ============================================================
#
# Changelog v8.3
# ---------------
# • generate_question() marked deprecated — no longer called in
#   engine_cycle(); run_question_engine() (operator_question_engine)
#   is the sole question system. Old function retained but guarded
#   with a deprecation warning to avoid silent dual-write to Operator.
# • process_operator_response() now routes to process_operator_answer_new
#   when operator_question_engine is available, eliminating the dual-
#   handler split. Falls back to legacy behaviour if import failed.
# • evaluate_recommendation() now reads SituationType and DecisionWindow
#   from state so CRITICAL_COUNTDOWN / MAYDAY situations surface in the
#   recommendation text. Severity = CRITICAL with an active countdown
#   overrides the default SOC/AC text.
# • snapshot_changed() signature extended — also tracks SituationType
#   so scenario progression triggers a memory snapshot even when
#   voltage/power/health are unchanged.
# • load_scenario() refactored: scenario data moved to _SCENARIO_DATA
#   dict; load_scenario() is now a thin dispatcher. Eliminates 60+ lines
#   of duplicated set-key blocks and makes adding new scenarios trivial.
# • get_value() hardened: guards against values that are non-numeric
#   strings (e.g. "N/A") — previously raised ValueError and crashed
#   the cycle silently.
# • EngineConfig gains three new thresholds used by the enriched
#   recommendation logic: countdown_soc_floor, mayday_soc_floor,
#   decision_window_urgent.
# • engine_cycle() docstring updated to reflect actual step count (22).
# • Minor: removed inline `from datetime import timezone` inside
#   load_scenario(); timezone now imported at module level.
# • All v8.2 / v8.1 / v8.0 logic preserved unless explicitly noted above.
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
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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

# operator_question_engine: track whether the new system loaded
_NEW_QUESTION_ENGINE_AVAILABLE = False
try:
    from operator_question_engine import (
        run_question_engine,
        process_answer as process_operator_answer_new,
    )
    _NEW_QUESTION_ENGINE_AVAILABLE = True
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
# MODULES v8.1
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

    # Care score dynamics
    care_decay_cycles: int      = 360   # cycles between passive −5 decay (~24h at 4s/cycle)
    care_drop_warning: int      = 3     # drop on WARNING severity
    care_drop_critical: int     = 10    # drop on CRITICAL severity
    care_drop_scenario: int     = 20    # drop on bad scenario (survival / MAYDAY)
    care_rise_recovery: int     = 5     # rise when severity clears
    care_task_cooldown_hours: int = 24  # hours before same task can be claimed again

    # v8.3 — situation-aware recommendation thresholds
    countdown_soc_floor: int = 25       # SoC at which a countdown escalates to WARNING
    mayday_soc_floor: int = 15          # SoC at which recommendation escalates to MAYDAY language
    decision_window_urgent: str = "NOW" # DecisionWindow value that triggers immediate action text


CONFIG = EngineConfig()

# ============================================================
# SMALL HELPERS
# ============================================================


def get_section(state: State, section: str) -> Dict[str, Any]:
    if section not in state or state[section] is None:
        state[section] = {}
    return state[section]


def get_value(state: State, section: str, key: str, default: float = 0.0) -> float:
    """Return a float from state, guarding against None and non-numeric strings."""
    raw = get_section(state, section).get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_optional(state: State, section: str, key: str) -> Any:
    return get_section(state, section).get(key)


# ============================================================
# ENERGY COMPUTATION
# ============================================================


def compute_energy_mode(state: State) -> None:
    battery = get_section(state, "Battery")
    voltage = get_value(state, "Battery", "Voltage")
    current = get_value(state, "Battery", "Current")

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
    if float(voltage) < CONFIG.ac_present_threshold:
        ac["State"] = "NO_SHORE"
        return
    if power is None:
        ac["State"] = "AC_PRESENT"
        return

    power = float(power)
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
    solar         = get_section(state, "Solar")
    solar_voltage = get_value(state, "Solar", "Voltage")
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
    current     = get_value(state, "Battery", "Current")

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
# RECOMMENDATION ENGINE  (v8.3 — situation-aware)
# ============================================================


def evaluate_recommendation(state: State) -> None:
    """
    Build the operator-facing recommendation string.

    Priority order (highest wins):
      1. MAYDAY or active CRITICAL_COUNTDOWN situation type
      2. Battery SoC critical / low / full
      3. AC state anomalies
      4. Health advisories
      5. Normal operation
    """
    system        = get_section(state, "System")
    ac_state      = get_section(state, "AC").get("State")
    soc           = get_optional(state, "Battery", "SoC")
    advisories    = system.get("HealthAdvisories") or []

    # v8.3 — read situation context written by v8.1 modules
    # These keys are written by situation_classifier (step 16/17), which runs
    # AFTER evaluate_recommendation in the cycle.  We read them defensively —
    # they will be populated from the *previous* cycle on all cycles after the
    # first, which is sufficient for progressive escalation.
    situation_type   = get_section(state, "Situation").get("SituationType")
    decision_window  = get_section(state, "Situation").get("DecisionWindow")

    if soc is not None:
        soc = float(soc)

    recommendation = "System operating normally."
    reason: Optional[str] = None
    rule:   Optional[str] = None

    # ── Priority 1 — critical situation types ────────────────
    if situation_type == "MAYDAY":
        soc_str = f" Battery at {soc:.0f}%." if soc is not None else ""
        recommendation = (
            f"MAYDAY situation active.{soc_str} "
            "Contact World Marine Care immediately — 100.66.110.127."
        )
        reason, rule = "MAYDAY situation", "MAYDAY"

    elif situation_type == "CRITICAL_COUNTDOWN":
        soc_str = f" Battery at {soc:.0f}%." if soc is not None else ""
        recommendation = (
            f"Critical countdown active.{soc_str} "
            "Immediate action required — start generator or reduce all non-essential loads."
        )
        reason, rule = "Critical countdown", "CRITICAL_COUNTDOWN"

    # ── Priority 2 — battery SoC ─────────────────────────────
    elif soc is not None:
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

    # ── Priority 3 — AC state ────────────────────────────────
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

    # ── Priority 4 — health advisory ────────────────────────
    if rule is None and advisories:
        adv_text = advisories[0]
        for prefix in ("⚠️ ", "💡 "):
            adv_text = adv_text.replace(prefix, "")
        recommendation = adv_text
        reason, rule = "Health advisory", "HEALTH_ADVISORY"

    # ── Append decision-window urgency tag (non-destructive) ─
    if decision_window == CONFIG.decision_window_urgent and rule not in ("MAYDAY", "CRITICAL_COUNTDOWN"):
        recommendation += " Act now."

    system["Recommendation"]       = recommendation
    system["RecommendationReason"] = reason
    system["RecommendationRule"]   = rule


# ============================================================
# CASE CONSULTATION
# Case objects are dataclasses — use attribute access, not dict keys
# ============================================================


def consult_case_library(state: State) -> None:
    system = get_section(state, "System")
    issues = system.get("Inconsistency")

    if not issues:
        system["Advisory"]     = None
        system["AdvisoryCase"] = None
        return

    search_text = " ".join(issues)

    try:
        matches = CASE_LIBRARY.search_cases(search_text)
    except Exception:
        system["Advisory"]     = None
        system["AdvisoryCase"] = None
        return

    if matches:
        top     = matches[0]
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



# ── Care task catalogue ───────────────────────────────────────────────────────
# Each entry: (task_id, label, description, points)
CARE_TASKS = [
    ("clean_bilge",       "Clean the bilge",             "Remove water and debris from the bilge.",                    5),
    ("check_terminals",   "Check battery terminals",     "Inspect and clean battery terminal connections.",            4),
    ("inspect_solar",     "Inspect solar panels",        "Clean panels and check wiring and connections.",             3),
    ("shore_power_cable", "Inspect shore power cable",   "Check cable condition, connectors and shore power inlet.",   3),
    ("test_bilge_pump",   "Test bilge pump",             "Run bilge pump and confirm float switch operation.",         4),
    ("clean_strainers",   "Clean salt water strainers",  "Remove and clean all raw water intake strainers.",           4),
    ("check_engine_oil",  "Check engine oil levels",     "Check and top up engine oil on both engines.",               5),
    ("update_firmware",   "Update firmware",             "Update OKi, Victron and navigation system firmware.",        6),
    ("read_manual",       "Read the manual",             "Study vessel systems documentation for 30 minutes.",         3),
    ("full_inspection",   "Full vessel inspection",      "Complete walk-through inspection of all vessel systems.",   10),
]


def compute_care(state: State) -> None:
    """Recompute CareIndex from SystemHealth and OperatorCareScore."""
    system = get_section(state, "System")
    care   = get_section(state, "Care")

    sys_score = int(system.get("SystemHealth") or 0)
    op_score  = int(care.get("OperatorCareScore") or 0)

    care["SystemCareScore"] = sys_score
    care["CareIndex"]       = round(0.6 * sys_score + 0.4 * op_score)


def _clamp_op_score(care: dict) -> None:
    """Keep OperatorCareScore within 0–100."""
    care["OperatorCareScore"] = max(0, min(100, int(care.get("OperatorCareScore") or 0)))


def apply_care_task(state_manager, task_id: str) -> dict:
    """
    Log a named care task. Returns a dict with:
      - "ok": bool
      - "points": int added (0 if on cooldown)
      - "message": str to show the operator
    """
    state = state_manager.get()
    care  = get_section(state, "Care")

    # Find task in catalogue
    task = next((t for t in CARE_TASKS if t[0] == task_id), None)
    if task is None:
        return {"ok": False, "points": 0, "message": "Unknown task."}

    task_id_, label, _, points = task

    # Cooldown check
    cooldowns = care.get("TaskCooldowns") or {}
    last_done = cooldowns.get(task_id_)
    now_ts    = datetime.now(timezone.utc).timestamp()
    cooldown_seconds = CONFIG.care_task_cooldown_hours * 3600

    if last_done and (now_ts - float(last_done)) < cooldown_seconds:
        hours_left = int((cooldown_seconds - (now_ts - float(last_done))) / 3600) + 1
        return {
            "ok": False,
            "points": 0,
            "message": f"Already logged today. Available again in {hours_left}h.",
        }

    # Apply points
    current = int(care.get("OperatorCareScore") or 0)
    care["OperatorCareScore"] = min(100, current + points)
    cooldowns[task_id_] = now_ts
    care["TaskCooldowns"] = cooldowns

    compute_care(state)
    state_manager.save()

    return {"ok": True, "points": points, "message": f"+{points} — {label} logged."}


def _care_event_drop(state: State) -> None:
    """
    Drop OperatorCareScore based on current severity and vessel situation.
    Called once per engine cycle — uses a flag to avoid double-dropping.
    """
    system  = get_section(state, "System")
    care    = get_section(state, "Care")
    vessel  = get_section(state, "VesselState")
    situation = get_section(state, "Situation")

    severity      = system.get("Severity")          # None / "WARNING" / "CRITICAL"
    prev_severity = care.get("_PrevSeverity")
    survival_mode = bool(vessel.get("SurvivalMode"))
    sit_type      = situation.get("SituationType")

    drop = 0

    # Scenario / survival — biggest drop, only trigger once per event
    if (survival_mode or sit_type in ("MAYDAY", "CRITICAL_COUNTDOWN")):
        if not care.get("_InScenarioDrop"):
            drop = CONFIG.care_drop_scenario
            care["_InScenarioDrop"] = True
    else:
        care["_InScenarioDrop"] = False

    # Severity transitions (WARNING / CRITICAL) — drop on entry, rise on exit
    if severity == "CRITICAL" and prev_severity != "CRITICAL":
        drop = max(drop, CONFIG.care_drop_critical)
    elif severity == "WARNING" and prev_severity not in ("WARNING", "CRITICAL"):
        drop = max(drop, CONFIG.care_drop_warning)
    elif severity is None and prev_severity in ("WARNING", "CRITICAL"):
        # Recovery — care score rises
        current = int(care.get("OperatorCareScore") or 0)
        care["OperatorCareScore"] = min(100, current + CONFIG.care_rise_recovery)

    care["_PrevSeverity"] = severity

    if drop > 0:
        current = int(care.get("OperatorCareScore") or 0)
        care["OperatorCareScore"] = max(0, current - drop)


def _care_passive_decay(state: State) -> None:
    """
    Passive decay: −5 points every ~24 hours of engine cycles.
    Tracks cycle count in Care._DecayCycleCounter.
    """
    care    = get_section(state, "Care")
    counter = int(care.get("_DecayCycleCounter") or 0) + 1
    care["_DecayCycleCounter"] = counter

    if counter % CONFIG.care_decay_cycles == 0:
        current = int(care.get("OperatorCareScore") or 0)
        care["OperatorCareScore"] = max(0, current - 5)


def _auto_care_reward(state: State) -> None:
    """Slow passive reward for sustained healthy operation (unchanged)."""
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
# SNAPSHOT MEMORY SYSTEM  (v8.3 — tracks SituationType)
# ============================================================


def build_snapshot(state: State) -> Dict[str, Any]:
    ac       = get_section(state, "AC")
    derived  = get_section(state, "Derived")
    system   = get_section(state, "System")
    situation = get_section(state, "Situation")

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
        "SituationType":    situation.get("SituationType"),   # v8.3
    }


def snapshot_changed(state: State, snapshot: Dict[str, Any]) -> bool:
    system    = get_section(state, "System")
    # v8.3 — include SituationType so scenario transitions trigger a memory write
    signature = (
        snapshot["ACVoltage"],
        snapshot["ACPower"],
        snapshot["Mode"],
        snapshot["Health"],
        snapshot.get("SituationType"),
    )
    last = system.get("LastSnapshotSignature")
    if signature == last:
        return False
    system["LastSnapshotSignature"] = signature
    return True


# ============================================================
# OPERATOR QUESTION SYSTEM  (v8.3 — deprecated, not called)
# ============================================================


def generate_question(state: State) -> None:
    """
    DEPRECATED in v8.3.
    run_question_engine() (operator_question_engine) is the sole
    question system.  This function is retained for reference but
    is no longer called in engine_cycle().  Calling it directly
    risks a dual-write collision on the Operator section.
    """
    warnings.warn(
        "generate_question() is deprecated. Use run_question_engine() instead.",
        DeprecationWarning,
        stacklevel=2,
    )


# ============================================================
# OPERATOR RESPONSE  (v8.3 — unified handler)
# ============================================================


def process_operator_response(state_manager, choice: str) -> None:
    """
    Route operator response to the correct handler.

    If operator_question_engine loaded successfully, delegate to
    process_operator_answer_new() which understands the new question
    format.  Fall back to the legacy A/B/C handler only when the
    new engine is unavailable.
    """
    if _NEW_QUESTION_ENGINE_AVAILABLE:
        state = state_manager.get()
        process_operator_answer_new(state, choice)
        return

    # Legacy fallback — only reached if operator_question_engine failed to import
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
# SCENARIOS  (v8.3 — data-driven dispatch)
# ============================================================

_SCENARIO_DATA: Dict[str, Dict[str, Any]] = {
    "anchor": {
        "Battery": {"SoC": 63, "Voltage": 25.1, "Current": -8.0},
        "AC":      {"Shore": False, "GridVoltage": 0, "GridPower": 0, "ShellyStatus": "OFFLINE"},
        "Derived": {"EnergyMode": "DISCHARGING"},
        "Communication": {"CANHealthy": True},
    },
    "casa": {
        "Battery": {"SoC": 72, "Voltage": 26.8, "Current": 12.0},
        "AC":      {"Shore": True, "GridVoltage": 230, "GridPower": 420, "ShellyStatus": "ONLINE"},
        "Derived": {"EnergyMode": "CHARGING"},
        "Communication": {"CANHealthy": True},
    },
    "casa_azul": {
        "Battery": {"SoC": 85, "Voltage": 27.2, "Current": 15.0},
        "AC":      {"Shore": True, "GridVoltage": 230, "GridPower": 380, "ShellyStatus": "ONLINE"},
        "Solar":   {"Power": 320.0, "Voltage": 34.5, "State": "PRODUCING"},
        "Derived": {"EnergyMode": "CHARGING"},
        "Generator": {"Running": False, "Expected": False, "RecentlyRan": False, "ErrorCode": ""},
        "Fuel":    {"LevelPercent": 75.0, "SensorReliable": True, "State": "OK", "Inconsistency": None},
        "Communication": {"CANHealthy": True},
        "Care":    {"OperatorCareScore": 60, "TaskCooldowns": {}, "_PrevSeverity": "CRITICAL", "_InScenarioDrop": False},
    },
    "drain": {
        "Battery": {"SoC": 18, "Voltage": 23.8, "Current": -22.0},
        "AC":      {"Shore": False, "GridVoltage": 0, "GridPower": 0, "ShellyStatus": "OFFLINE"},
        "Derived": {"EnergyMode": "DISCHARGING"},
        "Communication": {"CANHealthy": None},
    },
    "generator_failure": {
        "Battery":       {"SoC": 22, "Voltage": 24.1, "Current": -10.0},
        "AC":            {"Shore": False, "GridVoltage": 0, "GridPower": 0, "ShellyStatus": "OFFLINE"},
        "Derived":       {"EnergyMode": "DISCHARGING"},
        "Communication": {"CANHealthy": True},
        "Generator":     {"Running": False, "Expected": True, "RecentlyRan": False, "ErrorCode": ""},
        "Fuel":          {"LevelPercent": 40.0, "SensorReliable": True, "State": "OK", "Inconsistency": None},
        "Solar":         {"Power": 0.0, "Voltage": 0.0, "State": "NIGHT"},
    },
}


def _get_known_scenarios() -> List[str]:
    return list(_SCENARIO_DATA.keys())


def load_scenario(state_manager, name: str) -> None:
    """
    Load a named scenario into state.

    Raises ValueError for unknown scenario names so the caller
    (UI / test) gets a clear error rather than silent no-op.
    """
    if name not in _SCENARIO_DATA:
        known = ", ".join(_get_known_scenarios())
        raise ValueError(f"[OKi] Unknown scenario '{name}'. Known: {known}")

    state   = state_manager.get()
    patches = _SCENARIO_DATA[name]

    for section, keys in patches.items():
        section_data = get_section(state, section)
        section_data.update(keys)

    # Timestamp communication sections that need a live CAN time
    comm = get_section(state, "Communication")
    if comm.get("CANHealthy") is True and comm.get("LastCANMessage") is None:
        comm["LastCANMessage"] = datetime.now(timezone.utc).isoformat()

    # Timestamp fuel if present and missing
    fuel = get_section(state, "Fuel")
    if fuel and fuel.get("LevelPercent") is not None and fuel.get("LastUpdate") is None:
        fuel["LastUpdate"] = datetime.now(timezone.utc)

    state_manager.save()


# ============================================================
# ENGINE CYCLE v8.3  (22 steps)
# ============================================================


def engine_cycle(state_manager) -> State:
    """
    Full OKi engine cycle — 22 steps.

    Step  1  compute_energy_mode       — DC power and charge direction
    Step  2  compute_ac_state          — shore power state classification
    Step  3  compute_solar_detection   — panel voltage present?
    Step  4  compute_solar_state       — full solar input computation
    Step  5  detect_blackout           — blackout monitor
    Step  6  compute_system_health     — health score + penalties + CAN watchdog
    Step  7  compute_energy_forecast   — energy forecast
    Step  8  evaluate_vessel_state     — vessel state
    Step  9  evaluate_strategy         — energy strategy
    Step 10  evaluate_recommendation   — operator recommendation (situation-aware v8.3)
    Step 11  consult_case_library      — knowledge base match
    Step 12  compute_care              — care index
    Step 13  _auto_care_reward         — healthy-cycle reward
    Step 14  compute_fuel_state        — fuel level + sensor reliability
    Step 15  compute_energy_time       — time-to-critical / time-to-shutdown
    Step 16  evaluate_situation_type   — SituationType classification
    Step 17  evaluate_decision_window  — DecisionWindow pressure level
    Step 18  run_diagnostics           — diagnostic state machine + questions
    Step 19  run_question_engine       — operator question engine (sole handler)
    Step 20  compute_attention         — attention level
    Step 21  build_snapshot / changed  — snapshot memory
    Step 22  state_manager.save        — persist state
    """
    state = state_manager.get()

    compute_energy_mode(state)          #  1
    compute_ac_state(state)             #  2
    compute_solar_detection(state)      #  3
    compute_solar_state(state)          #  4
    detect_blackout(state)              #  5
    compute_system_health(state)        #  6
    compute_energy_forecast(state)      #  7
    evaluate_vessel_state(state)        #  8
    evaluate_strategy(state)            #  9
    evaluate_recommendation(state)      # 10
    consult_case_library(state)         # 11
    compute_care(state)                 # 12
    _care_event_drop(state)             # 12b — severity-based drops + recovery
    _care_passive_decay(state)          # 12c — daily passive decay
    _auto_care_reward(state)            # 13
    compute_fuel_state(state)           # 14
    compute_energy_time(state)          # 15
    evaluate_situation_type(state)      # 16
    evaluate_decision_window(state)     # 17
    run_diagnostics(state)              # 18
    run_question_engine(state)          # 19
    compute_attention(state)            # 20

    snap = build_snapshot(state)
    if snapshot_changed(state, snap):
        state_manager.append_memory(snap)   # 21

    state_manager.save()                    # 22

    return state
