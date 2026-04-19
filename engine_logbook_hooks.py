"""
engine_logbook_hooks.py
=======================
OKi Engine v8.6 — Logbook Integration Patch
These are the additions to make to engine.py to wire up logbook.py.
Not a standalone file — apply these changes into your existing engine.py.

CHANGES SUMMARY
───────────────
1. Import logbook at the top
2. Track previous attention state to detect changes
3. Call logbook hooks at the right points in the 16-step cycle

"""

# ─── 1. ADD TO IMPORTS (top of engine.py) ────────────────────────────────────

import logbook as lb

# ─── 2. ADD TO ENGINE __init__ ────────────────────────────────────────────────

# Track previous state for change detection
self._prev_attention_state = None
self._prev_soh = {}          # {battery_id: float}
self._deep_cycle_tracking = {}  # {battery_id: float}  — low-water SoC per battery

lb.log_system("OKi Engine v8.6 started", lb.EventLevel.INFO)


# ─── 3. SEVERITY CHANGE DETECTION ─────────────────────────────────────────────
# Add this near the end of the orchestration cycle, after attention_engine runs.
# 'current_state' is whatever your attention engine returns as the primary state.

current_state = attention_output.get("primary_state", "OK")

if current_state != self._prev_attention_state:
    if self._prev_attention_state is not None:
        # Only log ALERT and above — skip INFO→INFO noise
        alert_levels = {"ALERT", "CRITICAL", "MAYDAY", "SURVIVAL"}
        if current_state.upper() in alert_levels or \
           (self._prev_attention_state and
            self._prev_attention_state.upper() in alert_levels):
            lb.log_severity_change(
                old_state=self._prev_attention_state,
                new_state=current_state,
                reason=attention_output.get("context_line_1", None)
            )
    self._prev_attention_state = current_state


# ─── 4. BATTERY SoH LOGGING ───────────────────────────────────────────────────
# Call this once per cycle for each battery you have SoH data for.
# Replace the dict with your actual battery data structure.
# Log SoH only when it changes by >1% to avoid flooding the log.

battery_states = vessel_data.get("batteries", {})
# Expected structure: {"house_bank": {"soh": 88.5, "soc": 74.2, ...}, ...}

for batt_id, batt_data in battery_states.items():
    soh = batt_data.get("soh")
    if soh is None:
        continue
    prev_soh = self._prev_soh.get(batt_id)
    if prev_soh is None or abs(soh - prev_soh) >= 1.0:
        lb.log_battery_soh(
            battery_id=batt_id,
            soh_percent=soh,
            note=f"SoC at time of reading: {batt_data.get('soc', '?')}%"
        )
        self._prev_soh[batt_id] = soh


# ─── 5. DEEP CYCLE DETECTION ──────────────────────────────────────────────────
# Detect when SoC drops below 30% (configurable threshold).
# Detect recovery and log the full cycle.

DEEP_CYCLE_THRESHOLD = 30.0   # % SoC — below this = deep cycle territory
RECOVERY_THRESHOLD   = 80.0   # % SoC — above this = recovered

for batt_id, batt_data in battery_states.items():
    soc = batt_data.get("soc")
    if soc is None:
        continue

    if soc < DEEP_CYCLE_THRESHOLD:
        # Track the lowest point
        prev_low = self._deep_cycle_tracking.get(batt_id)
        if prev_low is None or soc < prev_low:
            self._deep_cycle_tracking[batt_id] = soc
            lb.log_deep_cycle(battery_id=batt_id, soc_at_low=soc)

    elif soc >= RECOVERY_THRESHOLD and batt_id in self._deep_cycle_tracking:
        # Battery recovered — log the full event
        low_point = self._deep_cycle_tracking.pop(batt_id)
        lb.log_deep_cycle(
            battery_id=batt_id,
            soc_at_low=low_point,
            soc_recovered=soc
        )


# ─── 6. SCENARIO ACTIVATION ───────────────────────────────────────────────────
# Add this where scenarios are activated/changed in energy_strategy_engine output.

if scenario_changed:
    lb.log_scenario(
        scenario_name=current_scenario,
        activated=True,
        note=f"Previous: {prev_scenario}"
    )


# ─── 7. CARE TASK EVENTS ──────────────────────────────────────────────────────
# Add this when care tasks are marked complete or become overdue.

# On task completion (called from your care task handler):
def on_care_task_completed(task_name: str, care_score_after: float):
    lb.log_care_task(task_name, "completed", score_after=care_score_after)

# On care score drop (called when score drops due to WARNING/CRITICAL/MAYDAY):
def on_care_score_drop(reason: str, care_score_after: float):
    lb.log_care_task(reason, "score_drop", score_after=care_score_after)
