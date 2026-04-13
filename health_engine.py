"""
health_engine.py — OKi System Health Score Engine
Version: 1.1
Spec: OKi 002 Health Score Design v0.1 + Power Continuity v0.3

Architecture:
    Standalone module. Called by engine.py.
    Returns a HealthResult dataclass with:
        - score (int, 5–100)
        - category scores
        - active penalties list
        - advisory messages list

Scoring model:
    Start at 100.
    Apply penalties by category (A → F).
    Clamp: never below 5, never above 100.

Categories:
    A — System Integrity       (Critical layer)
    B — Energy & Battery       (Abuse tracking)
    C — Operational Stress     (Load / discharge rate)
    D — Environmental/Thermal  (Temperature)
    E — Minor Issues           (Firmware, small warnings)
    F — Power Continuity       (Blackout events — NEW v1.1)

Changelog v1.1:
    - Category F added: Blackout / power continuity penalties
    - Blackout confirmed → immediate large penalty (health drops to 10–20%)
    - Repeated blackouts accumulate long-term reliability degradation
    - Network loss distinguished from power loss (spec v0.3 §7)
    - HealthInput extended: blackout_active, blackout_count, local_network_loss
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Penalty weights — tunable constants
# All values are percentage points subtracted from 100.
# ---------------------------------------------------------------------------

# Category A — System Integrity (Critical)
PENALTY_BMS_OFFLINE         = 40   # BMS communication lost
PENALTY_CAN_OFFLINE         = 30   # CAN bus communication lost
PENALTY_CRITICAL_SYS_OFFLINE = 25  # Navigation-critical system offline

# Category B — Energy & Battery
PENALTY_SOC_BELOW_15        = 20   # SoC critically low right now
PENALTY_SOC_BELOW_20        = 8    # SoC in advisory zone right now
PENALTY_DEEP_DISCHARGE_EVENT = 12  # Each recorded deep discharge event
DEEP_DISCHARGE_MAX_PENALTY  = 40   # Cap on accumulated discharge history

# Category C — Operational Stress
PENALTY_HIGH_LOAD           = 10   # Sustained high AC/DC load
PENALTY_AGGRESSIVE_DISCHARGE = 8   # Discharge rate beyond normal threshold

# Category D — Environmental / Thermal
PENALTY_HIGH_TEMP_CRITICAL  = 20   # Temperature in danger zone
PENALTY_HIGH_TEMP_WARNING   = 8    # Temperature elevated but not critical

# Category E — Minor Issues
PENALTY_FIRMWARE_OUTDATED   = 2    # Non-critical, barely affects score
PENALTY_MINOR_WARNING       = 1    # Any other small issue

# Category F — Power Continuity (Blackout)
PENALTY_BLACKOUT_ACTIVE     = 75   # Vessel power lost — confirmed blackout
PENALTY_BLACKOUT_REPEAT     = 8    # Per additional historical blackout event
BLACKOUT_REPEAT_MAX_PENALTY = 20   # Cap on accumulated repeat penalty
PENALTY_LOCAL_NETWORK_LOSS  = 5    # Local network failure (data visibility reduced)

# Hard floor
HEALTH_MINIMUM              = 5    # Never show 0%


# ---------------------------------------------------------------------------
# Input data container
# engine.py builds this from state_manager and passes it in.
# All fields are Optional — missing data is treated as degraded, not clean.
# ---------------------------------------------------------------------------

@dataclass
class HealthInput:
    # --- Category A: System Integrity ---
    bms_online: Optional[bool] = None          # True = communicating
    can_online: Optional[bool] = None          # True = CAN bus active
    critical_systems_online: Optional[bool] = None  # CZone nav lights etc.

    # --- Category B: Energy & Battery ---
    soc_percent: Optional[float] = None        # 0–100
    deep_discharge_count: int = 0             # historical count this session

    # --- Category C: Operational Stress ---
    high_load_detected: bool = False           # from Shelly / engine logic
    aggressive_discharge: bool = False         # from current draw analysis

    # --- Category D: Environmental ---
    battery_temp_celsius: Optional[float] = None
    engine_room_temp_celsius: Optional[float] = None

    # --- Category E: Minor ---
    firmware_outdated: bool = False
    minor_warnings: int = 0                   # count of small advisory items

    # --- Category F: Power Continuity ---
    blackout_active: bool = False             # confirmed vessel power loss
    blackout_count: int = 0                   # lifetime blackout events (repeat penalty)
    local_network_loss: bool = False          # local LAN down (minor penalty)


# ---------------------------------------------------------------------------
# Output data container
# ---------------------------------------------------------------------------

@dataclass
class HealthResult:
    score: int = 100                          # final clamped score
    category_a_penalty: int = 0
    category_b_penalty: int = 0
    category_c_penalty: int = 0
    category_d_penalty: int = 0
    category_e_penalty: int = 0
    category_f_penalty: int = 0
    active_penalties: list = field(default_factory=list)   # human-readable reasons
    advisories: list = field(default_factory=list)         # warnings before damage


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def calculate_health(data: HealthInput) -> HealthResult:
    """
    Calculate OKi System Health Score from a HealthInput snapshot.

    Returns HealthResult with score and full penalty breakdown.
    Missing data (None) is treated as system degradation per Rule 4:
    'If communication is lost, treat as system degradation, not missing data.'
    """

    result = HealthResult()
    penalties = []
    advisories = []
    total_penalty = 0

    # -----------------------------------------------------------------------
    # CATEGORY A — System Integrity (Critical Layer)
    # -----------------------------------------------------------------------
    cat_a = 0

    # BMS
    if data.bms_online is False:
        cat_a += PENALTY_BMS_OFFLINE
        penalties.append("🔴 BMS offline — battery management system not communicating")
    elif data.bms_online is None:
        cat_a += PENALTY_BMS_OFFLINE
        penalties.append("🔴 BMS status unknown — treating as offline")

    # CAN bus
    if data.can_online is False:
        cat_a += PENALTY_CAN_OFFLINE
        penalties.append("🔴 CAN bus offline — vessel data network not communicating")
    elif data.can_online is None:
        cat_a += PENALTY_CAN_OFFLINE
        penalties.append("🔴 CAN bus status unknown — treating as offline")

    # Critical systems (navigation, lights, etc.)
    if data.critical_systems_online is False:
        cat_a += PENALTY_CRITICAL_SYS_OFFLINE
        penalties.append("🔴 Critical system offline — navigation systems unavailable")
    elif data.critical_systems_online is None:
        # Unknown is less severe than confirmed offline for nav systems
        cat_a += round(PENALTY_CRITICAL_SYS_OFFLINE * 0.5)
        penalties.append("🟠 Critical system status unknown")

    result.category_a_penalty = cat_a
    total_penalty += cat_a

    # -----------------------------------------------------------------------
    # CATEGORY B — Energy & Battery Health
    # -----------------------------------------------------------------------
    cat_b = 0

    if data.soc_percent is not None:
        soc = data.soc_percent

        if soc < 15:
            cat_b += PENALTY_SOC_BELOW_15
            penalties.append(f"🔴 Battery critically low at {soc:.0f}% — connect shore power or reduce loads immediately")
        elif soc < 20:
            cat_b += PENALTY_SOC_BELOW_20
            advisories.append(f"⚠️ Battery at {soc:.0f}% — avoid going below 20% to preserve battery life")

        if soc <= 20 and soc > 15:
            # Advisory zone — warn before damage (Rule 3)
            advisories.append("💡 Tip: Repeated discharge below 20% reduces long-term battery capacity")

    # Historical deep discharge events — accumulating penalty
    if data.deep_discharge_count > 0:
        discharge_penalty = min(
            data.deep_discharge_count * PENALTY_DEEP_DISCHARGE_EVENT,
            DEEP_DISCHARGE_MAX_PENALTY
        )
        cat_b += discharge_penalty
        penalties.append(
            f"🟠 {data.deep_discharge_count} deep discharge event(s) recorded — "
            f"battery health degraded ({discharge_penalty}pt penalty)"
        )

    result.category_b_penalty = cat_b
    total_penalty += cat_b

    # -----------------------------------------------------------------------
    # CATEGORY C — Operational Stress
    # -----------------------------------------------------------------------
    cat_c = 0

    if data.high_load_detected:
        cat_c += PENALTY_HIGH_LOAD
        penalties.append("🟠 High load detected — verify connected equipment")

    if data.aggressive_discharge:
        cat_c += PENALTY_AGGRESSIVE_DISCHARGE
        penalties.append("🟠 Aggressive discharge rate — abnormal power draw")

    result.category_c_penalty = cat_c
    total_penalty += cat_c

    # -----------------------------------------------------------------------
    # CATEGORY D — Environmental / Thermal
    # -----------------------------------------------------------------------
    cat_d = 0

    # Battery temperature
    if data.battery_temp_celsius is not None:
        temp = data.battery_temp_celsius
        if temp > 45:
            cat_d += PENALTY_HIGH_TEMP_CRITICAL
            penalties.append(f"🔴 Battery temperature critical at {temp:.0f}°C")
        elif temp > 35:
            cat_d += PENALTY_HIGH_TEMP_WARNING
            penalties.append(f"🟠 Battery temperature elevated at {temp:.0f}°C")
            advisories.append("⚠️ High battery temperature reduces charge efficiency and lifespan")

    # Engine room temperature
    if data.engine_room_temp_celsius is not None:
        temp = data.engine_room_temp_celsius
        if temp > 60:
            cat_d += PENALTY_HIGH_TEMP_CRITICAL
            penalties.append(f"🔴 Engine room temperature critical at {temp:.0f}°C")
        elif temp > 45:
            cat_d += PENALTY_HIGH_TEMP_WARNING
            penalties.append(f"🟠 Engine room temperature elevated at {temp:.0f}°C")

    result.category_d_penalty = cat_d
    total_penalty += cat_d

    # -----------------------------------------------------------------------
    # CATEGORY E — Minor / Non-Critical Issues
    # -----------------------------------------------------------------------
    cat_e = 0

    if data.firmware_outdated:
        cat_e += PENALTY_FIRMWARE_OUTDATED
        penalties.append("🟡 Firmware update available — non-critical")

    if data.minor_warnings > 0:
        cat_e += data.minor_warnings * PENALTY_MINOR_WARNING
        # Cap category E so it never meaningfully dents the score
        cat_e = min(cat_e, 5)

    result.category_e_penalty = cat_e
    total_penalty += cat_e

    # -----------------------------------------------------------------------
    # CATEGORY F — Power Continuity (Blackout)
    # -----------------------------------------------------------------------
    cat_f = 0

    if data.blackout_active:
        # Confirmed vessel power loss — large immediate penalty
        cat_f += PENALTY_BLACKOUT_ACTIVE
        penalties.append("🔴 Vessel power lost — OKi running on backup battery")

        # Repeat blackout penalty — reliability degradation over time
        if data.blackout_count > 1:
            repeat_events   = data.blackout_count - 1   # first event already penalised above
            repeat_penalty  = min(repeat_events * PENALTY_BLACKOUT_REPEAT, BLACKOUT_REPEAT_MAX_PENALTY)
            cat_f          += repeat_penalty
            penalties.append(
                f"🟠 {data.blackout_count} blackout events recorded — "
                f"vessel reliability degraded ({repeat_penalty}pt)"
            )

    elif data.blackout_count > 1:
        # Power is currently present but vessel has a history of blackouts
        repeat_events  = data.blackout_count - 1
        repeat_penalty = min(repeat_events * PENALTY_BLACKOUT_REPEAT, BLACKOUT_REPEAT_MAX_PENALTY)
        cat_f         += repeat_penalty
        penalties.append(
            f"🟠 {data.blackout_count} previous blackout event(s) — "
            f"long-term reliability penalty ({repeat_penalty}pt)"
        )

    if data.local_network_loss:
        cat_f += PENALTY_LOCAL_NETWORK_LOSS
        penalties.append("🟡 Local network degraded — data visibility reduced")

    result.category_f_penalty = cat_f
    total_penalty += cat_f

    # -----------------------------------------------------------------------
    # Final score
    # -----------------------------------------------------------------------
    raw_score = 100 - total_penalty
    result.score = max(raw_score, HEALTH_MINIMUM)   # Rule 1: never below 5%
    result.active_penalties = penalties
    result.advisories = advisories

    return result


# ---------------------------------------------------------------------------
# Convenience function — for engine.py integration
# ---------------------------------------------------------------------------

def score_from_state(state: dict) -> HealthResult:
    """
    Build a HealthInput from OKi state dict and return HealthResult.

    engine.py calls this with the current state snapshot.

    Expected state keys (all optional — missing = degraded):
        bms_online, can_online, critical_systems_online,
        soc_percent, deep_discharge_count,
        high_load_detected, aggressive_discharge,
        battery_temp_celsius, engine_room_temp_celsius,
        firmware_outdated, minor_warnings
    """

    data = HealthInput(
        bms_online              = state.get("bms_online"),
        can_online              = state.get("can_online"),
        critical_systems_online = state.get("critical_systems_online"),
        soc_percent             = state.get("soc_percent"),
        deep_discharge_count    = state.get("deep_discharge_count", 0),
        high_load_detected      = state.get("high_load_detected", False),
        aggressive_discharge    = state.get("aggressive_discharge", False),
        battery_temp_celsius    = state.get("battery_temp_celsius"),
        engine_room_temp_celsius= state.get("engine_room_temp_celsius"),
        firmware_outdated       = state.get("firmware_outdated", False),
        minor_warnings          = state.get("minor_warnings", 0),
        blackout_active         = state.get("blackout_active", False),
        blackout_count          = state.get("blackout_count", 0),
        local_network_loss      = state.get("local_network_loss", False),
    )

    return calculate_health(data)


# ---------------------------------------------------------------------------
# Dev / test — run directly to verify scoring
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("OKi health_engine.py — Dev Test")
    print("=" * 60)

    scenarios = {

        "Healthy vessel — all systems nominal": {
            "bms_online": True,
            "can_online": True,
            "critical_systems_online": True,
            "soc_percent": 75.0,
            "deep_discharge_count": 0,
        },

        "Suspicious drain — SoC at 18%, no CAN": {
            "bms_online": True,
            "can_online": False,
            "critical_systems_online": True,
            "soc_percent": 18.0,
            "deep_discharge_count": 1,
        },

        "Critical failure — BMS and CAN both offline": {
            "bms_online": False,
            "can_online": False,
            "critical_systems_online": False,
            "soc_percent": 12.0,
            "deep_discharge_count": 3,
            "high_load_detected": True,
        },

        "Advisory state — SoC 19%, all comms live": {
            "bms_online": True,
            "can_online": True,
            "critical_systems_online": True,
            "soc_percent": 19.0,
            "deep_discharge_count": 0,
        },

        "Unknown state — no data from BMS or CAN": {
            # None values simulate lost communication
            "bms_online": None,
            "can_online": None,
            "soc_percent": 55.0,
        },
    }

    for name, state in scenarios.items():
        result = score_from_state(state)
        print(f"\n📋 Scenario: {name}")
        print(f"   Score : {result.score}%")
        print(f"   Cat A : -{result.category_a_penalty}pt  "
              f"B: -{result.category_b_penalty}pt  "
              f"C: -{result.category_c_penalty}pt  "
              f"D: -{result.category_d_penalty}pt  "
              f"E: -{result.category_e_penalty}pt")
        if result.active_penalties:
            print("   Penalties:")
            for p in result.active_penalties:
                print(f"     {p}")
        if result.advisories:
            print("   Advisories:")
            for a in result.advisories:
                print(f"     {a}")

    print("\n" + "=" * 60)
    print("Test complete.")
