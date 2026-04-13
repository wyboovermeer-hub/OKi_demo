"""
OKi — Fuel Tank Monitoring Module
Responsibilities: read fuel level, classify state, detect inconsistencies,
assess sensor reliability, and expose a clean is_fuel_available() helper.
"""

from datetime import datetime, timezone

# ── Thresholds ────────────────────────────────────────────────────────────────
LEVEL_FULL = 70.0
LEVEL_OK_MIN = 30.0
LEVEL_LOW_MIN = 10.0
SENSOR_STALE_SECONDS = 300  # 5 minutes without update → unreliable


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify_level(level_percent: float) -> str:
    if level_percent > LEVEL_FULL:
        return "FULL"
    if level_percent >= LEVEL_OK_MIN:
        return "OK"
    if level_percent >= LEVEL_LOW_MIN:
        return "LOW"
    return "CRITICAL"


def _sensor_is_stale(last_update) -> bool:
    """Return True if the last update timestamp is older than the stale threshold."""
    if last_update is None:
        return True
    now = datetime.now(timezone.utc)
    # Accept both aware and naive datetimes
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)
    return (now - last_update).total_seconds() > SENSOR_STALE_SECONDS


def _generator_recently_ran(state: dict) -> bool:
    """Return True if the generator has a recent runtime entry in state."""
    gen = state.get("Generator", {})
    return gen.get("Running", False) or gen.get("RecentlyRan", False)


# ── Core computation ──────────────────────────────────────────────────────────

def compute_fuel_state(state: dict) -> None:
    """
    Read fuel data from state, evaluate it, and write results back.

    Writes:
        state["Fuel"]["State"]            — FULL / OK / LOW / CRITICAL / UNKNOWN
        state["Fuel"]["SensorReliable"]   — bool
        state["Fuel"]["Inconsistency"]    — str | None
    """
    fuel = state.setdefault("Fuel", {})

    level = fuel.get("LevelPercent")
    last_update = fuel.get("LastUpdate")

    # ── Sensor reliability ────────────────────────────────────────────────────
    stale = _sensor_is_stale(last_update)
    sensor_reliable = (level is not None) and (not stale)
    fuel["SensorReliable"] = sensor_reliable

    # ── Level classification ──────────────────────────────────────────────────
    if level is None or not sensor_reliable:
        fuel["State"] = "UNKNOWN"
    else:
        fuel["State"] = _classify_level(float(level))

    # ── Inconsistency detection ───────────────────────────────────────────────
    inconsistency = None

    if sensor_reliable and level is not None and float(level) == 0.0:
        if _generator_recently_ran(state):
            inconsistency = (
                "Fuel reads 0% but generator recently active — "
                "sensor may be faulty or tank switch not open"
            )

    if stale and last_update is not None:
        inconsistency = (
            inconsistency or
            f"Fuel sensor data is stale (last update: {last_update.isoformat()})"
        )

    fuel["Inconsistency"] = inconsistency


# ── Public helper ─────────────────────────────────────────────────────────────

def is_fuel_available(state: dict) -> bool:
    """
    Return True only when fuel is above 10 % AND the sensor is reliable.
    Safe default is False — do not assume fuel when uncertain.
    """
    fuel = state.get("Fuel", {})
    level = fuel.get("LevelPercent")
    reliable = fuel.get("SensorReliable", False)

    if not reliable or level is None:
        return False
    return float(level) > LEVEL_LOW_MIN
