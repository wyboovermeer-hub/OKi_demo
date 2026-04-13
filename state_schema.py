# ============================================================
# OKi STATE SCHEMA v4.1
# Canonical Supervisory State Structure
# ============================================================
#
# Changelog v4.1
# ---------------
# • Added missing domains so StateManager.bulk_update() never KeyErrors:
#     Blackout, VesselState, EnergyForecast, Strategy,
#     Attention, Fuel, Energy, Diagnostic, Generator, GPS,
#     Environment, Location
# • System domain extended: SituationType, DecisionWindow, Mode,
#   ShorePower, SensorConfidence
# • Solar domain extended: State, InputWatts
# • All v4.0 keys preserved exactly
#
# ============================================================

STATE_SCHEMA = {

    # ---------------------------------------------------------
    # BATTERY
    # ---------------------------------------------------------
    "Battery": {
        "SoC":              None,
        "Voltage":          None,
        "Current":          None,
        "Temperature":      None,
        "ContactorState":   None,
    },

    # ---------------------------------------------------------
    # AC SYSTEM
    # ---------------------------------------------------------
    "AC": {
        "Shore":            None,
        "GridVoltage":      None,
        "GridCurrent":      None,
        "GridPower":        None,
        "GridEnergyTotal":  None,
        "ShellyStatus":     None,
    },

    # ---------------------------------------------------------
    # SOLAR SYSTEM
    # ---------------------------------------------------------
    "Solar": {
        "Power":        None,
        "Voltage":      None,
        "Current":      None,
        "Detected":     False,
        "State":        None,      # ACTIVE / LIMITED / DECLINING / NIGHT
        "InputWatts":   None,      # alias used by situation_classifier
    },

    # ---------------------------------------------------------
    # CHARGER
    # ---------------------------------------------------------
    "Charger": {
        "ChargeCurrent":    None,
        "State":            None,
    },

    # ---------------------------------------------------------
    # INVERTER
    # ---------------------------------------------------------
    "Inverter": {
        "On":       None,
        "ACLoad":   None,
    },

    # ---------------------------------------------------------
    # DERIVED VALUES
    # ---------------------------------------------------------
    "Derived": {
        "DCPower":          None,
        "EnergyMode":       None,
        "CausalConfidence": 0.9,
    },

    # ---------------------------------------------------------
    # COMMUNICATION
    # ---------------------------------------------------------
    "Communication": {
        "LastCANMessage":   None,
        "CANHealthy":       False,
    },

    # ---------------------------------------------------------
    # CARE SYSTEM
    # ---------------------------------------------------------
    "Care": {
        "SystemCareScore":  100,
        "OperatorCareScore":80,
        "CareIndex":        None,
        "LastCareAction":   None,
        "LastCareTimestamp":None,
    },

    # ---------------------------------------------------------
    # OPERATOR INTERACTION
    # ---------------------------------------------------------
    "Operator": {
        "InteractionState":  None,
        "ActiveQuestionText":None,
        "OptionA":           None,
        "OptionB":           None,
        "OptionC":           None,
        "LastAnswerText":    None,
        "AnswerTimestamp":   None,
    },

    # ---------------------------------------------------------
    # SYSTEM
    # ---------------------------------------------------------
    "System": {
        "PiTemperature":        None,
        "DevMode":              False,
        "SystemHealth":         100,
        "Inconsistency":        None,
        "Advisory":             None,
        "Severity":             None,
        "Recommendation":       None,
        "RecommendationReason": None,
        "RecommendationRule":   None,
        # v4.1 additions
        "SituationType":        "NORMAL",
        "DecisionWindow":       "OPEN",
        "Mode":                 "NORMAL",
        "ShorePower":           False,
        "SensorConfidence":     {},
    },

    # ---------------------------------------------------------
    # BLACKOUT MONITOR  [v4.1]
    # ---------------------------------------------------------
    "Blackout": {
        "BlackoutMode":             False,
        "BlackoutConfirmed":        False,
        "BlackoutStartTime":        None,
        "BlackoutDurationSec":      0.0,
        "BlackoutCount":            0,
        "UPSRemainingWh":           480.0,
        "UPSRemainingHours":        48.0,
        "UPSRemainingMinutes":      2880,
        "UPSDisplayString":         None,
        "UPSWarningLevel":          None,
        "OperatorMessage":          None,
        "StatusLine":               None,
        "_PowerLossStart":          None,
        "LastBlackoutRecoveryTime": None,
    },

    # ---------------------------------------------------------
    # VESSEL STATE  [v4.1]
    # ---------------------------------------------------------
    "VesselState": {
        "MovementState":            "UNKNOWN",
        "SpeedKnots":               None,
        "LocationContext":          "UNKNOWN",
        "ShorePowerPossible":       False,
        "AvailableSources":         [],
        "SurvivalMode":             False,
        "SurvivalPrimaryMessage":   None,
        "SurvivalTimeString":       None,
        "NeedsLocationQuestion":    False,
        "LastLocationConfirmed":    None,
        "ExpectingShorePower":      False,
    },

    # ---------------------------------------------------------
    # ENERGY FORECAST  [v4.1]
    # ---------------------------------------------------------
    "EnergyForecast": {
        "TimeToShutdownH":  None,
        "TimeToCriticalH":  None,
        "NetPowerW":        None,
        "ConsumptionW":     None,
    },

    # ---------------------------------------------------------
    # ENERGY — time-aware module  [v4.1]
    # ---------------------------------------------------------
    "Energy": {
        "TimeToCriticalHours":  None,
        "TimeToShutdownHours":  None,
        "PostBlackoutHours":    48.0,
        "DischargeRate":        None,
    },

    # ---------------------------------------------------------
    # STRATEGY  [v4.1]
    # ---------------------------------------------------------
    "Strategy": {
        "Selected":         "NONE",
        "Status":           "NONE",
        "FollowUpNeeded":   False,
    },

    # ---------------------------------------------------------
    # ATTENTION ENGINE OUTPUT  [v4.1]
    # ---------------------------------------------------------
    "Attention": {
        "Priority":         5,
        "PriorityLabel":    "STABLE",
        "PrimaryState":     "System operating normally.",
        "SecondaryContext": [],
        "ActiveQuestion":   None,
        "Silence":          True,
    },

    # ---------------------------------------------------------
    # FUEL TANK  [v4.1]
    # ---------------------------------------------------------
    "Fuel": {
        "LevelPercent":     None,
        "State":            "UNKNOWN",
        "SensorReliable":   False,
        "LastUpdate":       None,
        "Inconsistency":    None,
    },

    # ---------------------------------------------------------
    # DIAGNOSTIC ENGINE  [v4.1]
    # ---------------------------------------------------------
    "Diagnostic": {
        "PrimaryState":     "",
        "SecondaryContext": None,
        "ActiveQuestion":   None,
        "Options":          [],
        "Step":             "",
        "DiagnosticState":  "",
        "OperatorResponse": "",
    },

    # ---------------------------------------------------------
    # GENERATOR  [v4.1]
    # ---------------------------------------------------------
    "Generator": {
        "Running":      False,
        "Expected":     False,
        "RecentlyRan":  False,
        "ErrorCode":    "",
    },

    # ---------------------------------------------------------
    # GPS  [v4.1]
    # ---------------------------------------------------------
    "GPS": {
        "SpeedKnots":   None,
        "Latitude":     None,
        "Longitude":    None,
        "Fix":          False,
    },

    # ---------------------------------------------------------
    # ENVIRONMENT  [v4.1]
    # ---------------------------------------------------------
    "Environment": {
        "TimeUTC":                  None,
        "EngineRoomTempCelsius":    None,
    },

    # ---------------------------------------------------------
    # LOCATION  [v4.1]
    # ---------------------------------------------------------
    "Location": {
        "Latitude":     None,
        "Longitude":    None,
    },

    # ---------------------------------------------------------
    # SYSTEM MEMORY
    # ---------------------------------------------------------
    "Memory": [],
}
