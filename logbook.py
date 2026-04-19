"""
OKi Vessel Logbook — logbook.py
Persistent SQLite-backed event logger for vessel intelligence events.
Records: severity changes, scenario activations, care task events,
deep cycle detections, battery SoH, MAYDAY/survival events.
"""

import sqlite3
import os
from datetime import datetime, timezone
from enum import Enum

DB_PATH = os.path.join(os.path.dirname(__file__), "oki_logbook.db")

# ─── Event Categories ────────────────────────────────────────────────────────

class EventCategory(str, Enum):
    SEVERITY    = "SEVERITY"
    BATTERY     = "BATTERY"
    CARE        = "CARE"
    SCENARIO    = "SCENARIO"
    SYSTEM      = "SYSTEM"

class EventLevel(str, Enum):
    INFO      = "INFO"
    WARNING   = "WARNING"
    ALERT     = "ALERT"
    CRITICAL  = "CRITICAL"
    MAYDAY    = "MAYDAY"

# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS logbook (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    category    TEXT NOT NULL,
    level       TEXT NOT NULL,
    title       TEXT NOT NULL,
    detail      TEXT,
    value_num   REAL,
    value_unit  TEXT,
    battery_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON logbook(timestamp);
CREATE INDEX IF NOT EXISTS idx_category  ON logbook(category);
CREATE INDEX IF NOT EXISTS idx_level     ON logbook(level);
"""

# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

_init_db()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _write(category: str, level: str, title: str,
           detail: str = None, value_num: float = None,
           value_unit: str = None, battery_id: str = None):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO logbook
           (timestamp, category, level, title, detail, value_num, value_unit, battery_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), category, level, title, detail, value_num, value_unit, battery_id)
    )
    conn.commit()
    conn.close()

# ─── Public API ───────────────────────────────────────────────────────────────

def log_severity_change(old_state: str, new_state: str, reason: str = None):
    """Log a change in system severity/attention state."""
    level_map = {
        "OK": EventLevel.INFO,
        "WARNING": EventLevel.WARNING,
        "ALERT": EventLevel.ALERT,
        "CRITICAL": EventLevel.CRITICAL,
        "MAYDAY": EventLevel.MAYDAY,
        "SURVIVAL": EventLevel.MAYDAY,
    }
    level = level_map.get(new_state.upper(), EventLevel.INFO)
    title = f"State changed: {old_state} → {new_state}"
    _write(EventCategory.SEVERITY, level, title, detail=reason)


def log_battery_soh(battery_id: str, soh_percent: float, note: str = None):
    """Log the State of Health reading for a specific battery."""
    level = EventLevel.INFO
    if soh_percent < 60:
        level = EventLevel.CRITICAL
    elif soh_percent < 75:
        level = EventLevel.WARNING
    elif soh_percent < 85:
        level = EventLevel.ALERT

    title = f"Battery SoH recorded: {battery_id} — {soh_percent:.1f}%"
    _write(EventCategory.BATTERY, level, title,
           detail=note, value_num=soh_percent, value_unit="%",
           battery_id=battery_id)


def log_deep_cycle(battery_id: str, soc_at_low: float, soc_recovered: float = None,
                   depth_ah: float = None):
    """Log a detected deep discharge cycle."""
    detail_parts = [f"Discharged to {soc_at_low:.1f}% SoC"]
    if soc_recovered is not None:
        detail_parts.append(f"recovered to {soc_recovered:.1f}%")
    if depth_ah is not None:
        detail_parts.append(f"depth {depth_ah:.1f} Ah")
    detail = " — ".join(detail_parts)

    level = EventLevel.CRITICAL if soc_at_low < 20 else EventLevel.ALERT
    title = f"Deep cycle detected: {battery_id}"
    _write(EventCategory.BATTERY, level, title,
           detail=detail, value_num=soc_at_low, value_unit="% SoC",
           battery_id=battery_id)


def log_battery_event(battery_id: str, event_type: str, value: float = None,
                      unit: str = None, note: str = None):
    """Log a general battery event (e.g. full charge, voltage spike, cell imbalance)."""
    title = f"Battery event: {battery_id} — {event_type}"
    level = EventLevel.INFO
    if any(w in event_type.lower() for w in ["critical", "fault", "fail", "imbalance"]):
        level = EventLevel.CRITICAL
    elif any(w in event_type.lower() for w in ["warning", "low", "alert"]):
        level = EventLevel.WARNING
    _write(EventCategory.BATTERY, level, title,
           detail=note, value_num=value, value_unit=unit, battery_id=battery_id)


def log_care_task(task_name: str, action: str, score_after: float = None,
                  note: str = None):
    """Log a care task completion or overdue event."""
    if action == "completed":
        level = EventLevel.INFO
        title = f"Care task completed: {task_name}"
    elif action == "overdue":
        level = EventLevel.WARNING
        title = f"Care task overdue: {task_name}"
    elif action == "score_drop":
        level = EventLevel.ALERT
        title = f"Care score dropped — {task_name}"
    else:
        level = EventLevel.INFO
        title = f"Care task: {task_name} — {action}"

    detail = f"Care score after: {score_after:.0f}%" if score_after is not None else note
    _write(EventCategory.CARE, level, title, detail=detail,
           value_num=score_after, value_unit="% care")


def log_scenario(scenario_name: str, activated: bool, note: str = None):
    """Log scenario activation or deactivation."""
    action = "activated" if activated else "deactivated"
    title = f"Scenario {action}: {scenario_name}"
    level = EventLevel.INFO
    if any(w in scenario_name.lower() for w in ["critical", "mayday", "survival", "drain"]):
        level = EventLevel.ALERT
    _write(EventCategory.SCENARIO, level, title, detail=note)


def log_system(message: str, level: str = EventLevel.INFO):
    """Log a system-level event (startup, shutdown, config change, etc.)."""
    _write(EventCategory.SYSTEM, level, message)


# ─── Query API ────────────────────────────────────────────────────────────────

def get_all_entries(limit: int = None, categories: list = None,
                    min_level: str = None) -> list:
    """
    Retrieve log entries, newest first.
    Optionally filter by category list and/or minimum severity level.
    """
    level_order = {
        EventLevel.INFO: 0,
        EventLevel.WARNING: 1,
        EventLevel.ALERT: 2,
        EventLevel.CRITICAL: 3,
        EventLevel.MAYDAY: 4,
    }

    conn = _get_conn()
    query = "SELECT * FROM logbook"
    params = []
    conditions = []

    if categories:
        placeholders = ",".join("?" * len(categories))
        conditions.append(f"category IN ({placeholders})")
        params.extend(categories)

    if min_level and min_level in level_order:
        min_val = level_order[min_level]
        allowed = [l for l, v in level_order.items() if v >= min_val]
        placeholders = ",".join("?" * len(allowed))
        conditions.append(f"level IN ({placeholders})")
        params.extend(allowed)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp DESC"

    if limit:
        query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_battery_soh_history(battery_id: str = None) -> list:
    """Get all SoH readings, optionally filtered by battery ID."""
    conn = _get_conn()
    if battery_id:
        rows = conn.execute(
            """SELECT * FROM logbook
               WHERE category = ? AND title LIKE '%SoH recorded%' AND battery_id = ?
               ORDER BY timestamp DESC""",
            (EventCategory.BATTERY, battery_id)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM logbook
               WHERE category = ? AND title LIKE '%SoH recorded%'
               ORDER BY timestamp DESC""",
            (EventCategory.BATTERY,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_deep_cycle_count(battery_id: str = None) -> int:
    """Return total number of deep cycles logged."""
    conn = _get_conn()
    if battery_id:
        count = conn.execute(
            "SELECT COUNT(*) FROM logbook WHERE title LIKE '%Deep cycle%' AND battery_id = ?",
            (battery_id,)
        ).fetchone()[0]
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM logbook WHERE title LIKE '%Deep cycle%'"
        ).fetchone()[0]
    conn.close()
    return count


def clear_all():
    """Wipe the logbook. For dev/demo use only."""
    conn = _get_conn()
    conn.execute("DELETE FROM logbook")
    conn.commit()
    conn.close()
