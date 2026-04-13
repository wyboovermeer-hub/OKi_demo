"""
blackout_monitor.py — OKi Power Continuity & Blackout Monitor
Version: 1.0
Spec: OKi 002 Health Score & Power Continuity v0.3

Responsibilities:
    - Detect vessel power loss (blackout condition)
    - Ignore brief power interruptions (< GLITCH_THRESHOLD seconds)
    - Switch system to BLACKOUT_MODE when sustained loss confirmed
    - Calculate UPS remaining runtime continuously
    - Generate operator-facing messages with threshold warnings
    - Track blackout frequency for long-term health degradation

Called by engine_cycle() once per cycle, before compute_system_health().
Writes results to state["Blackout"] section.
health_engine.py reads state["Blackout"] to apply penalties.
"""

import time
from datetime import datetime
from typing import Optional

# ============================================================
# CONFIGURATION
# ============================================================

# Power loss must persist this long before blackout is declared
# Short glitches (e.g. switching shore to generator) are ignored
GLITCH_THRESHOLD_SECONDS = 5.0

# UPS parameters
UPS_CAPACITY_WH    = 480.0   # ~48Wh usable (conservative estimate for 48h @ <10W)
OKI_POWER_DRAW_W   = 10.0    # OKi maximum power consumption

# Runtime warning thresholds (hours)
THRESHOLD_ADVISORY  = 24.0
THRESHOLD_WARNING   = 12.0
THRESHOLD_CRITICAL  =  6.0
THRESHOLD_URGENT    =  1.0

# Long-term: penalty multiplier per repeated blackout event
# Tracked in state["Blackout"]["BlackoutCount"]
MAX_TRACKED_BLACKOUTS = 10


# ============================================================
# BLACKOUT DETECTION
# ============================================================

def detect_blackout(state: dict) -> None:
    """
    Main entry point. Called once per engine cycle.

    Reads:
        state["AC"]["GridVoltage"]      — shore power voltage
        state["Battery"]["Current"]     — DC bus current (negative = discharging)
        state["Blackout"]               — persistent blackout state

    Writes:
        state["Blackout"]["BlackoutMode"]        — bool
        state["Blackout"]["BlackoutConfirmed"]   — bool (past glitch threshold)
        state["Blackout"]["BlackoutStartTime"]   — ISO timestamp
        state["Blackout"]["BlackoutDurationSec"] — float
        state["Blackout"]["BlackoutCount"]       — int (lifetime events)
        state["Blackout"]["UPSRemainingWh"]      — float
        state["Blackout"]["UPSRemainingHours"]   — float
        state["Blackout"]["UPSRemainingMinutes"] — int (total minutes)
        state["Blackout"]["UPSDisplayString"]    — human string e.g. "36h 20m"
        state["Blackout"]["UPSWarningLevel"]     — None | "ADVISORY" | "WARNING" | "CRITICAL" | "URGENT"
        state["Blackout"]["OperatorMessage"]     — primary UI message
        state["Blackout"]["StatusLine"]          — short status line for header
    """

    blackout = _get_blackout(state)
    now      = time.time()

    # ----------------------------------------------------------------
    # Step 1 — Is vessel power present?
    # ----------------------------------------------------------------
    power_present = _vessel_power_present(state)

    if power_present:
        # Power is back — clear blackout state
        _clear_blackout(blackout, now)
        return

    # ----------------------------------------------------------------
    # Step 2 — Power is absent. Start or continue timing.
    # ----------------------------------------------------------------
    loss_start = blackout.get("_PowerLossStart")

    if loss_start is None:
        # First cycle with no power — start the clock
        blackout["_PowerLossStart"] = now
        blackout["BlackoutMode"]    = False   # not yet confirmed
        return

    elapsed = now - float(loss_start)

    # ----------------------------------------------------------------
    # Step 3 — Glitch suppression
    # ----------------------------------------------------------------
    if elapsed < GLITCH_THRESHOLD_SECONDS:
        blackout["BlackoutMode"] = False
        return

    # ----------------------------------------------------------------
    # Step 4 — Blackout confirmed
    # ----------------------------------------------------------------
    if not blackout.get("BlackoutConfirmed", False):
        # Transition into blackout — record the event
        blackout["BlackoutConfirmed"] = True
        blackout["BlackoutStartTime"] = datetime.utcnow().isoformat()
        blackout["BlackoutCount"]     = int(blackout.get("BlackoutCount") or 0) + 1

    blackout["BlackoutMode"]        = True
    blackout["BlackoutDurationSec"] = elapsed

    # ----------------------------------------------------------------
    # Step 5 — UPS runtime calculation
    # ----------------------------------------------------------------
    _calculate_ups_runtime(blackout, elapsed)

    # ----------------------------------------------------------------
    # Step 6 — Warning level and operator messages
    # ----------------------------------------------------------------
    _evaluate_warning_level(blackout)
    _build_operator_messages(blackout)


# ============================================================
# VESSEL POWER DETECTION
# ============================================================

def _vessel_power_present(state: dict) -> bool:
    """
    Returns True if vessel DC or AC power is confirmed present.

    Logic:
    - AC shore power voltage > 50V  → power present
    - DC bus current > 0 (charging) → power present (solar / generator)
    - Both absent or unknown        → power absent
    """
    ac      = state.get("AC") or {}
    battery = state.get("Battery") or {}

    grid_voltage = ac.get("GridVoltage")
    dc_current   = battery.get("Current")

    # Shore power
    if grid_voltage is not None and float(grid_voltage) > 50.0:
        return True

    # DC charging source (solar, generator via charger)
    if dc_current is not None and float(dc_current) > 0.5:
        return True

    return False


# ============================================================
# UPS RUNTIME CALCULATION
# ============================================================

def _calculate_ups_runtime(blackout: dict, elapsed_seconds: float) -> None:
    """
    Estimate remaining UPS runtime.

    Simple model:
        remaining_wh    = capacity - (power_draw * hours_elapsed)
        remaining_hours = remaining_wh / power_draw

    Future: replace with actual UPS SoC reading when hardware available.
    """
    hours_elapsed   = elapsed_seconds / 3600.0
    energy_used_wh  = OKI_POWER_DRAW_W * hours_elapsed
    remaining_wh    = max(0.0, UPS_CAPACITY_WH - energy_used_wh)
    remaining_hours = remaining_wh / OKI_POWER_DRAW_W

    remaining_total_minutes = int(remaining_hours * 60)
    display_hours   = int(remaining_hours)
    display_minutes = remaining_total_minutes - (display_hours * 60)

    if remaining_hours >= 1.0:
        display_string = f"{display_hours}h {display_minutes:02d}m"
    else:
        display_string = f"{remaining_total_minutes}m"

    blackout["UPSRemainingWh"]      = round(remaining_wh, 1)
    blackout["UPSRemainingHours"]   = round(remaining_hours, 2)
    blackout["UPSRemainingMinutes"] = remaining_total_minutes
    blackout["UPSDisplayString"]    = display_string


# ============================================================
# WARNING LEVEL
# ============================================================

def _evaluate_warning_level(blackout: dict) -> None:
    """
    Set UPSWarningLevel based on remaining runtime.
    Levels become progressively more prominent in UI.
    """
    hours = float(blackout.get("UPSRemainingHours") or 0.0)

    if hours < THRESHOLD_URGENT:
        level = "URGENT"
    elif hours < THRESHOLD_CRITICAL:
        level = "CRITICAL"
    elif hours < THRESHOLD_WARNING:
        level = "WARNING"
    elif hours < THRESHOLD_ADVISORY:
        level = "ADVISORY"
    else:
        level = None

    blackout["UPSWarningLevel"] = level


# ============================================================
# OPERATOR MESSAGES
# ============================================================

def _build_operator_messages(blackout: dict) -> None:
    """
    Build the two UI strings shown during blackout.

    OperatorMessage — full message for main display
    StatusLine      — short header line
    """
    display   = blackout.get("UPSDisplayString", "unknown")
    level     = blackout.get("UPSWarningLevel")
    duration  = float(blackout.get("BlackoutDurationSec") or 0.0)
    dur_str   = _format_duration(duration)

    # Status line (header / LED area)
    blackout["StatusLine"] = "⚠️ VESSEL POWER LOST — BACKUP ACTIVE"

    # Main operator message — escalates with warning level
    if level == "URGENT":
        blackout["OperatorMessage"] = (
            f"🔴 URGENT — OKi backup battery critical. "
            f"Estimated remaining: {display}. "
            f"Restore vessel power immediately or OKi will shut down."
        )
    elif level == "CRITICAL":
        blackout["OperatorMessage"] = (
            f"🔴 Vessel power lost for {dur_str}. "
            f"Running on OKi backup — {display} remaining. "
            f"Restore power as soon as possible."
        )
    elif level == "WARNING":
        blackout["OperatorMessage"] = (
            f"🟠 Vessel power lost for {dur_str}. "
            f"OKi backup battery: {display} remaining. "
            f"Plan to restore power."
        )
    elif level == "ADVISORY":
        blackout["OperatorMessage"] = (
            f"⚠️ Vessel power lost for {dur_str}. "
            f"Running on OKi backup battery — {display} remaining."
        )
    else:
        blackout["OperatorMessage"] = (
            f"⚠️ Vessel Power Lost — Running on OKi Backup. "
            f"Estimated remaining operation time: {display}."
        )


# ============================================================
# CLEAR BLACKOUT STATE
# ============================================================

def _clear_blackout(blackout: dict, now: float) -> None:
    """
    Power has returned. Clear active blackout flags.
    Preserve BlackoutCount for long-term health tracking.
    """
    was_confirmed = blackout.get("BlackoutConfirmed", False)

    blackout["BlackoutMode"]        = False
    blackout["BlackoutConfirmed"]   = False
    blackout["_PowerLossStart"]     = None
    blackout["BlackoutDurationSec"] = 0.0
    blackout["UPSWarningLevel"]     = None
    blackout["OperatorMessage"]     = None
    blackout["StatusLine"]          = None
    blackout["UPSRemainingWh"]      = UPS_CAPACITY_WH
    blackout["UPSRemainingHours"]   = UPS_CAPACITY_WH / OKI_POWER_DRAW_W
    blackout["UPSDisplayString"]    = None

    if was_confirmed:
        blackout["LastBlackoutRecoveryTime"] = datetime.utcnow().isoformat()


# ============================================================
# HELPERS
# ============================================================

def _get_blackout(state: dict) -> dict:
    """Return Blackout section, initialising if needed."""
    if "Blackout" not in state or state["Blackout"] is None:
        state["Blackout"] = {}
    return state["Blackout"]


def _format_duration(seconds: float) -> str:
    """Format elapsed seconds as human string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m:02d}m"


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("OKi blackout_monitor.py — Dev Test")
    print("=" * 60)

    def run_test(label: str, state: dict, cycles: int = 1, delay: float = 0):
        print(f"\n📋 {label}")
        for i in range(cycles):
            if delay:
                time.sleep(delay)
            detect_blackout(state)
        b = state.get("Blackout", {})
        print(f"   BlackoutMode    : {b.get('BlackoutMode')}")
        print(f"   Confirmed       : {b.get('BlackoutConfirmed')}")
        print(f"   UPS Remaining   : {b.get('UPSDisplayString')}")
        print(f"   Warning Level   : {b.get('UPSWarningLevel')}")
        if b.get("OperatorMessage"):
            print(f"   Message         : {b.get('OperatorMessage')}")

    # Test 1 — Normal operation, shore power present
    run_test("Shore power present — no blackout", {
        "AC": {"GridVoltage": 230},
        "Battery": {"Current": 12.0}
    })

    # Test 2 — Brief glitch (under threshold)
    state2 = {"AC": {"GridVoltage": 0}, "Battery": {"Current": -8.0}}
    run_test("Brief glitch — should NOT trigger blackout", state2)

    # Test 3 — Sustained blackout (simulate elapsed time by patching start)
    state3 = {"AC": {"GridVoltage": 0}, "Battery": {"Current": -8.0}, "Blackout": {}}
    state3["Blackout"]["_PowerLossStart"] = time.time() - 10   # 10s ago
    run_test("Sustained blackout — confirmed", state3)

    # Test 4 — Deep into blackout (simulate 38 hours elapsed)
    state4 = {"AC": {"GridVoltage": 0}, "Battery": {"Current": -8.0}, "Blackout": {}}
    state4["Blackout"]["_PowerLossStart"]   = time.time() - (38 * 3600)
    state4["Blackout"]["BlackoutConfirmed"] = True
    state4["Blackout"]["BlackoutCount"]     = 1
    run_test("38 hours into blackout — critical", state4)

    # Test 5 — 47.5 hours (urgent — under 1h remaining)
    state5 = {"AC": {"GridVoltage": 0}, "Battery": {"Current": -8.0}, "Blackout": {}}
    state5["Blackout"]["_PowerLossStart"]   = time.time() - (47.5 * 3600)
    state5["Blackout"]["BlackoutConfirmed"] = True
    state5["Blackout"]["BlackoutCount"]     = 1
    run_test("47.5 hours — URGENT", state5)

    print("\n" + "=" * 60)
    print("Test complete.")
