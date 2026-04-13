# ============================================================
# OKi STATE MANAGER v4.0 – Canonical Persistent Authority
# ============================================================

import json
import os
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

from state_schema import STATE_SCHEMA


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_STATE_FILE = "oki_state.json"
DEFAULT_MEMORY_LIMIT = 500


# ============================================================
# STATE MANAGER
# ============================================================

class StateManager:
    """
    Canonical supervisory state authority for OKi.

    Responsibilities
    ----------------
    • Schema-aligned state initialization
    • Persistent disk storage
    • Thread-safe read/write access
    • Controlled state mutation
    • Memory window management
    • Corruption protection
    • Snapshot support
    • Schema integrity validation
    """

# ------------------------------------------------------------
# INIT
# ------------------------------------------------------------

    def __init__(
        self,
        data_path: str = DEFAULT_STATE_FILE,
        memory_limit: int = DEFAULT_MEMORY_LIMIT
    ):

        self.data_path = data_path
        self.memory_limit = memory_limit

        # Reentrant lock for thread safety
        self._lock = threading.RLock()

        # Load or initialize state
        self.state = self._initialize_state()


# ------------------------------------------------------------
# INITIALIZATION
# ------------------------------------------------------------

    def _initialize_state(self) -> Dict[str, Any]:
        """
        Load state from disk if available.
        Otherwise create new schema-aligned state.
        """

        if os.path.exists(self.data_path):

            try:

                with open(self.data_path, "r") as f:
                    loaded = json.load(f)

                return self._align_to_schema(loaded)

            except Exception:

                print("State file corrupted — rebuilding from schema")

                return self._create_empty_state()

        else:

            return self._create_empty_state()


    def _create_empty_state(self) -> Dict[str, Any]:
        """
        Create new clean state aligned to schema.
        """

        return deepcopy(STATE_SCHEMA)


    def _align_to_schema(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        """
        Align loaded state with schema structure.

        Missing keys are injected.
        Extra keys are preserved.
        """

        aligned = deepcopy(STATE_SCHEMA)

        for domain, values in loaded.items():

            if domain not in aligned:

                aligned[domain] = values
                continue

            if isinstance(values, dict):

                for key, val in values.items():

                    aligned[domain][key] = val

            else:

                aligned[domain] = values

        if "Memory" not in aligned:

            aligned["Memory"] = []

        return aligned


# ------------------------------------------------------------
# PUBLIC ACCESS
# ------------------------------------------------------------

    def get(self) -> Dict[str, Any]:
        """
        Thread-safe state access.

        Returns live state reference.
        Use only for READ operations.
        """

        with self._lock:

            return self.state


    def snapshot(self) -> Dict[str, Any]:
        """
        Return deep copy of state.

        Safe for external processing.
        """

        with self._lock:

            return deepcopy(self.state)


# ------------------------------------------------------------
# SAFE UPDATE OPERATIONS
# ------------------------------------------------------------

    def update(self, domain: str, key: str, value: Any):
        """
        Update a single state value.

        Enforces schema integrity.
        """

        with self._lock:

            if domain not in self.state:

                raise KeyError(f"Invalid state domain: {domain}")

            if key not in self.state[domain]:

                raise KeyError(f"Invalid key '{key}' in domain '{domain}'")

            self.state[domain][key] = value


    def bulk_update(self, updates: Dict[str, Dict[str, Any]]):
        """
        Atomically update multiple fields.

        Example
        -------

        bulk_update({
            "AC": {
                "GridVoltage": 230,
                "GridCurrent": 3
            },
            "Battery": {
                "Voltage": 25.6
            }
        })
        """

        with self._lock:

            for domain, keys in updates.items():

                if domain not in self.state:

                    raise KeyError(f"Invalid domain: {domain}")

                for key, value in keys.items():

                    if key not in self.state[domain]:

                        raise KeyError(
                            f"Invalid key '{key}' in domain '{domain}'"
                        )

                    self.state[domain][key] = value


# ------------------------------------------------------------
# MEMORY MANAGEMENT
# ------------------------------------------------------------

    def append_memory(self, entry: Dict[str, Any]):
        """
        Append snapshot to rolling memory window.

        Enforces memory size limit.
        """

        with self._lock:

            if "timestamp" not in entry:

                entry["timestamp"] = datetime.utcnow().isoformat()

            self.state["Memory"].append(entry)

            if len(self.state["Memory"]) > self.memory_limit:

                self.state["Memory"] = self.state["Memory"][
                    -self.memory_limit:
                ]


    def clear_memory(self):

        with self._lock:

            self.state["Memory"] = []


# ------------------------------------------------------------
# RESET
# ------------------------------------------------------------

    def reset(self):
        """
        Reset entire state to schema baseline.
        """

        with self._lock:

            self.state = self._create_empty_state()


# ------------------------------------------------------------
# PERSISTENCE
# ------------------------------------------------------------

    def save(self):
        """
        Persist state safely to disk.
        """

        with self._lock:

            try:

                with open(self.data_path, "w") as f:

                    json.dump(
                        self.state,
                        f,
                        indent=2,
                        default=self._json_serializer
                    )

            except Exception as e:

                raise RuntimeError(f"State save failed: {e}")


    def _json_serializer(self, obj):

        if isinstance(obj, datetime):

            return obj.isoformat()

        return str(obj)


# ------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------

    def validate_schema_integrity(self) -> bool:
        """
        Validate state structure against schema.
        """

        with self._lock:

            for domain in STATE_SCHEMA:

                if domain not in self.state:

                    return False

                if isinstance(STATE_SCHEMA[domain], dict):

                    for key in STATE_SCHEMA[domain]:

                        if key not in self.state[domain]:

                            return False

            return True