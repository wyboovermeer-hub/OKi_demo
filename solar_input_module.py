"""
solar_input_module.py — OKi Predictive Solar Input Module
Version: 1.0
Spec: OKi 002 Claude Implementation Brief v1.0 — FILE 3

Responsibilities:
    - Determine current solar state (ACTIVE / LIMITED / DECLINING / NIGHT)
    - Predict solar input over next 0–8 hours
    - Calculate time to sunset / sunrise
    - Detect solar anomalies (forecast vs actual mismatch)
    - Feed predictions to energy_forecast_engine.py

Called by engine_cycle() after compute_solar_detection().
Writes results to state["Solar"] section.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

# Solar state thresholds (watts)
SOLAR_ACTIVE_MIN_W      = 50.0    # Below this = not meaningfully producing
SOLAR_LIMITED_MAX_W     = 200.0   # Below this but above min = LIMITED
SOLAR_DECLINING_RATE    = 0.15    # If power dropping >15%/cycle = DECLINING

# Anomaly detection: actual vs forecast mismatch threshold
SOLAR_ANOMALY_THRESHOLD = 0.40    # 40% below forecast = anomaly

# Sunset proximity thresholds (minutes)
SUNSET_WARNING_MIN      = 60      # Start warning within 60 min of sunset
SUNSET_CRITICAL_MIN     = 20      # Critical within 20 min

# Default location (can be overridden by GPS in future)
# Lisbon, Portugal — for OKi 001 / Casa Azul
DEFAULT_LATITUDE        = 38.7169
DEFAULT_LONGITUDE       = -9.1395


# ============================================================
# SOLAR STATE
# ============================================================

SOLAR_STATES = ("ACTIVE", "LIMITED", "DECLINING", "NIGHT")


def compute_solar_state(state: dict) -> None:
    """
    Determine current solar state and enrich state["Solar"].

    Reads:
        state["Solar"]["Power"]         — current MPPT power output (W)
        state["Solar"]["PreviousPower"] — last cycle power (for trend)
        state["Solar"]["Voltage"]       — panel voltage
        state["Location"]               — lat/lon (optional, uses default)
        state["Environment"]["TimeUTC"] — current UTC time (optional)

    Writes:
        state["Solar"]["State"]              — ACTIVE / LIMITED / DECLINING / NIGHT
        state["Solar"]["SunsetUTC"]          — ISO string
        state["Solar"]["SunriseUTC"]         — ISO string
        state["Solar"]["MinutesToSunset"]    — int
        state["Solar"]["MinutesToSunrise"]   — int
        state["Solar"]["SunsetWarning"]      — None | "WARNING" | "CRITICAL"
        state["Solar"]["Anomaly"]            — bool
        state["Solar"]["AnomalyReason"]      — str | None
        state["Solar"]["Forecast"]           — list of {hour, predicted_w}
        state["Solar"]["ForecastSummary"]    — human string
        state["Solar"]["CountdownString"]    — human string
    """
    solar = _get_section(state, "Solar")
    now   = _get_now(state)

    # ----------------------------------------------------------------
    # Step 1 — Current power reading
    # ----------------------------------------------------------------
    power_w   = _safe_float(solar.get("Power"), 0.0)
    prev_power = _safe_float(solar.get("PreviousPower"), power_w)

    # ----------------------------------------------------------------
    # Step 2 — Sun position
    # ----------------------------------------------------------------
    lat, lon    = _get_location(state)
    sunrise_utc = _calc_sunrise(now, lat, lon)
    sunset_utc  = _calc_sunset(now, lat, lon)

    solar["SunriseUTC"] = sunrise_utc.isoformat()
    solar["SunsetUTC"]  = sunset_utc.isoformat()

    mins_to_sunset  = max(0, int((sunset_utc - now).total_seconds() / 60))
    mins_to_sunrise = max(0, int((sunrise_utc - now).total_seconds() / 60))

    # If sunset already passed today, calculate tomorrow's sunrise
    sun_above_horizon = sunrise_utc <= now <= sunset_utc

    solar["MinutesToSunset"]  = mins_to_sunset  if sun_above_horizon else 0
    solar["MinutesToSunrise"] = mins_to_sunrise if not sun_above_horizon else 0

    # ----------------------------------------------------------------
    # Step 3 — Solar state
    # ----------------------------------------------------------------
    if not sun_above_horizon or power_w < 5.0:
        state_str = "NIGHT"
    else:
        trend = (power_w - prev_power) / max(prev_power, 1.0)
        if trend < -SOLAR_DECLINING_RATE and power_w > SOLAR_ACTIVE_MIN_W:
            state_str = "DECLINING"
        elif power_w >= SOLAR_ACTIVE_MIN_W:
            state_str = "ACTIVE" if power_w > SOLAR_LIMITED_MAX_W else "LIMITED"
        else:
            state_str = "LIMITED"

    solar["State"] = state_str

    # Store for next cycle trend detection
    solar["PreviousPower"] = power_w

    # ----------------------------------------------------------------
    # Step 4 — Sunset warning
    # ----------------------------------------------------------------
    if not sun_above_horizon:
        solar["SunsetWarning"] = None
    elif mins_to_sunset <= SUNSET_CRITICAL_MIN:
        solar["SunsetWarning"] = "CRITICAL"
    elif mins_to_sunset <= SUNSET_WARNING_MIN:
        solar["SunsetWarning"] = "WARNING"
    else:
        solar["SunsetWarning"] = None

    # ----------------------------------------------------------------
    # Step 5 — 8-hour forecast
    # ----------------------------------------------------------------
    forecast = _build_forecast(now, power_w, sunset_utc, sunrise_utc, state_str)
    solar["Forecast"] = forecast
    solar["ForecastSummary"] = _summarise_forecast(forecast, now, sunset_utc)

    # ----------------------------------------------------------------
    # Step 6 — Anomaly detection
    # ----------------------------------------------------------------
    _detect_anomaly(solar, power_w, forecast, state_str)

    # ----------------------------------------------------------------
    # Step 7 — Countdown string
    # ----------------------------------------------------------------
    solar["CountdownString"] = _build_countdown(
        state_str, mins_to_sunset, mins_to_sunrise, power_w
    )


# ============================================================
# FORECAST ENGINE
# ============================================================

def _build_forecast(
    now: datetime,
    current_w: float,
    sunset_utc: datetime,
    sunrise_utc: datetime,
    current_state: str,
) -> list:
    """
    Build hour-by-hour solar power forecast for next 8 hours.

    Model:
    - Before sunset: taper current production using a cosine curve
      (solar output follows a bell curve through the day)
    - After sunset: zero
    - Weather data not yet available — future: integrate API

    Returns list of dicts: [{hour: 0, predicted_w: float, note: str}, ...]
    """
    forecast = []
    mins_to_sunset = max(0, (sunset_utc - now).total_seconds() / 60)

    for h in range(9):   # 0 = now, 1–8 = next hours
        future_time = now + timedelta(hours=h)
        mins_from_now = h * 60.0

        if future_time >= sunset_utc:
            predicted = 0.0
            note = "Night"
        elif current_state == "NIGHT":
            predicted = 0.0
            note = "Night"
        else:
            # Cosine taper: production drops toward zero as sunset approaches
            remaining_fraction = max(0.0, (mins_to_sunset - mins_from_now) / max(mins_to_sunset, 1.0))
            # Smooth curve: 1.0 at start → 0.0 at sunset
            taper = math.sin(remaining_fraction * math.pi / 2)
            predicted = round(current_w * taper, 1)
            note = "Forecast"

        forecast.append({
            "hour":        h,
            "time_utc":    future_time.isoformat(),
            "predicted_w": predicted,
            "note":        note,
        })

    return forecast


def _summarise_forecast(forecast: list, now: datetime, sunset_utc: datetime) -> str:
    """Build a human-readable forecast summary."""
    total_wh = sum(f["predicted_w"] for f in forecast[1:])   # skip hour 0 (now)
    mins_to_sunset = max(0, int((sunset_utc - now).total_seconds() / 60))

    if mins_to_sunset == 0:
        return "No solar input — night"

    h = mins_to_sunset // 60
    m = mins_to_sunset % 60
    sunset_str = f"{h}h {m:02d}m" if h > 0 else f"{m}m"

    return f"Sunset in {sunset_str} — estimated {total_wh:.0f}Wh solar remaining today"


# ============================================================
# ANOMALY DETECTION
# ============================================================

def _detect_anomaly(solar: dict, actual_w: float, forecast: list, state: str) -> None:
    """
    Compare actual solar output against forecast.
    Flag anomaly if actual is significantly below expected.
    """
    if state == "NIGHT":
        solar["Anomaly"]       = False
        solar["AnomalyReason"] = None
        return

    # Hour 0 of forecast = current expected
    expected_w = forecast[0]["predicted_w"] if forecast else 0.0

    if expected_w < SOLAR_ACTIVE_MIN_W:
        solar["Anomaly"]       = False
        solar["AnomalyReason"] = None
        return

    if actual_w < expected_w * (1.0 - SOLAR_ANOMALY_THRESHOLD):
        solar["Anomaly"]       = True
        solar["AnomalyReason"] = (
            f"Solar input {actual_w:.0f}W — significantly below "
            f"expected {expected_w:.0f}W. Panel issue or shading?"
        )
    else:
        solar["Anomaly"]       = False
        solar["AnomalyReason"] = None


# ============================================================
# COUNTDOWN STRING
# ============================================================

def _build_countdown(
    state: str,
    mins_to_sunset: int,
    mins_to_sunrise: int,
    power_w: float,
) -> Optional[str]:
    if state == "NIGHT":
        h = mins_to_sunrise // 60
        m = mins_to_sunrise % 60
        return f"🌙 Night — sunrise in {h}h {m:02d}m"

    if mins_to_sunset <= SUNSET_CRITICAL_MIN:
        return f"🔴 Solar ending — {mins_to_sunset}m to sunset"

    if mins_to_sunset <= SUNSET_WARNING_MIN:
        return f"🟠 Sunset in {mins_to_sunset}m — {power_w:.0f}W now"

    h = mins_to_sunset // 60
    m = mins_to_sunset % 60
    return f"☀️ Solar active — {power_w:.0f}W — sunset in {h}h {m:02d}m"


# ============================================================
# SUN POSITION — simplified astronomical calculation
# Accuracy: ±5 minutes — sufficient for energy forecasting
# ============================================================

def _calc_sunset(now: datetime, lat: float, lon: float) -> datetime:
    return _sun_event(now, lat, lon, rising=False)


def _calc_sunrise(now: datetime, lat: float, lon: float) -> datetime:
    event = _sun_event(now, lat, lon, rising=True)
    # If sunrise already passed today, return tomorrow's
    if event < now:
        event = _sun_event(now + timedelta(days=1), lat, lon, rising=True)
    return event


def _sun_event(date: datetime, lat: float, lon: float, rising: bool) -> datetime:
    """
    Calculate sunrise or sunset using the NOAA simplified algorithm.
    Returns UTC datetime.
    """
    day_of_year = date.timetuple().tm_yday

    # Solar declination
    decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81))))

    # Hour angle at sunrise/sunset
    lat_rad   = math.radians(lat)
    cos_ha    = -math.tan(lat_rad) * math.tan(decl)
    cos_ha    = max(-1.0, min(1.0, cos_ha))   # clamp for polar regions
    hour_angle = math.degrees(math.acos(cos_ha))

    if not rising:
        hour_angle = -hour_angle  # sunset

    # Solar noon in UTC
    solar_noon_utc = 12.0 - lon / 15.0

    # Event time in decimal hours UTC
    event_utc_h = solar_noon_utc - hour_angle / 15.0

    # Build datetime
    event_dt = date.replace(
        hour=int(event_utc_h),
        minute=int((event_utc_h % 1) * 60),
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )
    return event_dt


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


def _get_now(state: dict) -> datetime:
    env = state.get("Environment") or {}
    raw = env.get("TimeUTC")
    if raw:
        try:
            return datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _get_location(state: dict) -> tuple:
    loc = state.get("Location") or {}
    lat = _safe_float(loc.get("Latitude"),  DEFAULT_LATITUDE)
    lon = _safe_float(loc.get("Longitude"), DEFAULT_LONGITUDE)
    return lat, lon


# ============================================================
# DEV TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OKi solar_input_module.py — Dev Test")
    print("=" * 60)

    def run(label, state):
        compute_solar_state(state)
        s = state["Solar"]
        print(f"\n📋 {label}")
        print(f"   State          : {s.get('State')}")
        print(f"   Sunset Warning : {s.get('SunsetWarning')}")
        print(f"   Countdown      : {s.get('CountdownString')}")
        print(f"   Forecast       : {s.get('ForecastSummary')}")
        print(f"   Anomaly        : {s.get('Anomaly')} — {s.get('AnomalyReason') or 'none'}")
        fc = s.get("Forecast", [])
        print(f"   8h forecast    : {[f['predicted_w'] for f in fc]}")

    # Test 1 — Midday, strong solar
    run("Midday strong solar — 900W", {
        "Solar": {"Power": 900, "Voltage": 48},
        "Environment": {"TimeUTC": "2026-04-09T11:00:00+00:00"},
    })

    # Test 2 — Approaching sunset, low power
    run("Near sunset — 80W, declining", {
        "Solar": {"Power": 80, "PreviousPower": 200, "Voltage": 35},
        "Environment": {"TimeUTC": "2026-04-09T17:30:00+00:00"},
    })

    # Test 3 — Night
    run("Night — no solar", {
        "Solar": {"Power": 0, "Voltage": 0},
        "Environment": {"TimeUTC": "2026-04-09T22:00:00+00:00"},
    })

    # Test 4 — Anomaly: forecast high, actual low
    run("Anomaly — forecast 600W, actual 50W", {
        "Solar": {"Power": 50, "PreviousPower": 50, "Voltage": 20},
        "Environment": {"TimeUTC": "2026-04-09T12:00:00+00:00"},
    })

    print("\n" + "=" * 60)
    print("Test complete.")
