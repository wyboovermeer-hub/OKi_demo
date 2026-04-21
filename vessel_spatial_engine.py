# ============================================================
# OKi VESSEL SPATIAL ENGINE v1.1
# Vessel-aware location resolution for advisory output
# ============================================================
#
# Changelog v1.1
# ---------------
# • Path resolution hardened — searches multiple locations
#   handles systemd working directory on Raspberry Pi
#
# Changelog v1.0
# ---------------
# • Loads vessel_profile.json from same directory as this file
# • resolve_location(system_id) — returns plain-language location string
# • resolve_deck(system_id) — returns deck key ("main" / "lower")
# • resolve_zone(system_id) — returns zone ID with GA coordinates
# • resolve_breaker(system_id) — returns breaker label and panel location
# • get_systems_on_deck(deck) — returns all system IDs on a given deck
# • get_systems_by_type(type) — returns all system IDs of a given type
# • VESSEL_SPATIAL singleton — imported throughout the engine
#
# ============================================================

import json
from pathlib import Path

# Search for vessel_profile.json in multiple locations — handles systemd
# working directory differences on Raspberry Pi deployments
def _find_profile() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "vessel_profile.json",
        Path("/home/oki/OKi/05_OKi_Engine/vessel_profile.json"),
        Path.cwd() / "vessel_profile.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # return first even if missing — error handled in _load()

_PROFILE_PATH = _find_profile()


class VesselSpatialEngine:

    def __init__(self):
        self.profile   = {}
        self.systems   = {}
        self.zones     = {}
        self.breakers  = {}
        self.vessel    = {}
        self.decks     = {}
        self._loaded   = False
        self._load()

    # ──────────────────────────────────────────────────────────
    # LOAD
    # ──────────────────────────────────────────────────────────

    def _load(self):
        if not _PROFILE_PATH.exists():
            print(f"[OKi Spatial] vessel_profile.json not found at {_PROFILE_PATH} — spatial engine disabled")
            return

        try:
            with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
                self.profile  = json.load(f)
            self.vessel   = self.profile.get("vessel",   {})
            self.systems  = self.profile.get("systems",  {})
            self.zones    = self.profile.get("zones",    {})
            self.breakers = self.profile.get("breakers", {})
            self.decks    = self.profile.get("decks",    {})
            self._loaded  = True
            vessel_name   = self.vessel.get("name", "unknown vessel")
            print(f"[OKi Spatial] Loaded vessel profile: {vessel_name} ({len(self.systems)} systems)")
        except Exception as e:
            print(f"[OKi Spatial] Failed to load vessel_profile.json: {e}")

    # ──────────────────────────────────────────────────────────
    # CORE RESOLVERS
    # ──────────────────────────────────────────────────────────

    def resolve_location(self, system_id: str) -> str | None:
        """Return plain-language location string for a system ID."""
        if not self._loaded:
            return None
        system = self.systems.get(system_id)
        if not system:
            return None
        return system.get("location")

    def resolve_label(self, system_id: str) -> str | None:
        """Return human label for a system ID."""
        if not self._loaded:
            return None
        system = self.systems.get(system_id)
        if not system:
            return None
        return system.get("label")

    def resolve_deck(self, system_id: str) -> str | None:
        """Return deck key ('main' or 'lower') for a system ID."""
        if not self._loaded:
            return None
        system = self.systems.get(system_id)
        if not system:
            return None
        return system.get("deck")

    def resolve_zone(self, system_id: str) -> dict | None:
        """Return zone dict (label + GA coordinates) for a system ID."""
        if not self._loaded:
            return None
        system = self.systems.get(system_id)
        if not system:
            return None
        zone_id = system.get("zone")
        if not zone_id:
            return None
        return self.zones.get(zone_id)

    def resolve_breaker(self, system_id: str) -> dict | None:
        """Return breaker info dict for a system ID."""
        if not self._loaded:
            return None
        system = self.systems.get(system_id)
        if not system:
            return None
        breaker_id = system.get("breaker")
        if not breaker_id:
            return None
        breaker = self.breakers.get(breaker_id, {})
        breaker["id"] = breaker_id
        return breaker

    def resolve_ga_coordinates(self, system_id: str) -> dict | None:
        """Return {deck, x, y} for placing a marker on the GA SVG."""
        zone = self.resolve_zone(system_id)
        deck = self.resolve_deck(system_id)
        if not zone or not deck:
            return None
        return {
            "deck": deck,
            "x":    zone.get("ga_x"),
            "y":    zone.get("ga_y"),
            "zone": zone.get("label"),
        }

    # ──────────────────────────────────────────────────────────
    # ADVISORY STRING — formatted for attention engine output
    # ──────────────────────────────────────────────────────────

    def location_advisory(self, system_id: str) -> str | None:
        """
        Return a formatted location advisory string for the attention engine.
        Example: "Forward water heater — lower deck, port side forward. Tap to see location."
        """
        if not self._loaded:
            return None
        label    = self.resolve_label(system_id)
        location = self.resolve_location(system_id)
        if not label or not location:
            return None
        return f"{label} — {location}. Tap to see location."

    def breaker_advisory(self, system_id: str) -> str | None:
        """
        Return a formatted breaker location string.
        Example: "Breaker CB-HW-FWD (Hot Water — Forward) on AC panel."
        """
        if not self._loaded:
            return None
        breaker = self.resolve_breaker(system_id)
        if not breaker:
            return None
        bid   = breaker.get("id", "")
        blabel = breaker.get("label", "")
        panel  = breaker.get("panel", "")
        row    = breaker.get("row", "")
        pos    = breaker.get("position", "")
        parts  = [f"Breaker {bid}"]
        if blabel:
            parts.append(f"({blabel})")
        if panel:
            parts.append(f"on {panel}")
        if row and row != "TBC":
            parts.append(f"row {row}")
        if pos and pos != "TBC":
            parts.append(f"position {pos}")
        return " ".join(parts) + "."

    # ──────────────────────────────────────────────────────────
    # QUERIES
    # ──────────────────────────────────────────────────────────

    def get_systems_on_deck(self, deck: str) -> list:
        """Return list of system IDs on the given deck."""
        if not self._loaded:
            return []
        return [sid for sid, s in self.systems.items() if s.get("deck") == deck]

    def get_systems_by_type(self, system_type: str) -> list:
        """Return list of system IDs of the given type."""
        if not self._loaded:
            return []
        return [sid for sid, s in self.systems.items() if s.get("type") == system_type]

    def get_vessel_name(self) -> str:
        return self.vessel.get("name", "Unknown Vessel")

    def is_loaded(self) -> bool:
        return self._loaded

    def all_systems(self) -> dict:
        return self.systems


# ── Singleton ─────────────────────────────────────────────────────────────────
VESSEL_SPATIAL = VesselSpatialEngine()
