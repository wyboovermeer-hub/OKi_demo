"""
OKi — Demo Scenario: generator_failure
Loaded automatically on startup to produce an immediate, meaningful demo state.

State mirrors:
  - SoC 22 % → below 25 % diagnostic trigger
  - Discharging at ~10 A from a 200 Ah bank → ~2 h to critical (15 %)
  - No shore power, no solar, generator expected but not running
  - Fuel sensor reliable, level 40 % → rules out fuel as immediate cause

After one engine cycle the system will surface:
  Primary:   "Limited energy remaining"
  Secondary: "Battery will reach critical level in ~X hours.
              No charging source is currently active."
"""

from datetime import datetime, timezone


def load_generator_failure() -> dict:
    """Return a fully populated state dict for the generator-failure demo."""
    return {
        "Battery": {
            "SoC": 22.0,             # % — below 25 % threshold
            "Voltage": 24.1,         # V
            "CurrentA": 10.0,        # A discharging (positive = discharging convention)
            "Status": "DISCHARGING",
            "CapacityAh": 200.0,
        },
        "Solar": {
            "InputWatts": 0.0,
        },
        "System": {
            "ShorePower": False,
            "Mode": "NORMAL",
            "SituationType": "NORMAL",
            "DecisionWindow": "OPEN",
            "SensorConfidence": {},
        },
        "Generator": {
            "Running": False,
            "Expected": True,        # system expects generator to be available
            "RecentlyRan": False,
            "ErrorCode": "",
        },
        "Fuel": {
            "LevelPercent": 40.0,    # fuel present — isolates gen fault
            "LastUpdate": datetime.now(timezone.utc),
            "SensorReliable": True,
            "State": "OK",
            "Inconsistency": None,
        },
        "Diagnostic": {
            "PrimaryState": "",
            "SecondaryContext": "",
            "ActiveQuestion": None,
            "Options": [],
            "Step": "",
            "DiagnosticState": "",
            "OperatorResponse": "",
        },
        "Energy": {
            "TimeToCriticalHours": None,
            "TimeToShutdownHours": None,
            "PostBlackoutHours": 48.0,
            "DischargeRate": None,
        },
    }
