"""
OKi — web_server.py additions
============================================================
DO NOT paste this file wholesale — apply each section to
your existing web_server.py at the positions indicated.
============================================================
"""

# ── SECTION A — add near the top of web_server.py, after existing imports ────

import os
from demo_scenario import load_generator_failure

# Safe import guard: if a module is missing on first deploy, OKi still starts.
try:
    from fuel_tank_module     import compute_fuel_state
    from energy_time_module   import compute_energy_time
    from situation_classifier import evaluate_situation_type, evaluate_decision_window
    from diagnostic_engine    import run_diagnostics
    _MODULES_AVAILABLE = True
except ImportError as _e:
    print(f"[OKi] Warning — one or more modules failed to import: {_e}")
    _MODULES_AVAILABLE = False

# Safe import for knowledge layer — missing folder must not crash startup
try:
    from pathlib import Path as _Path
    import sys as _sys
    _knowledge_path = _Path(__file__).resolve().parent / "02_OKi_Knowledge"
    if _knowledge_path.exists():
        _sys.path.insert(0, str(_knowledge_path))
    from case_library import load_case, list_cases        # noqa: F401
    _KNOWLEDGE_AVAILABLE = True
except Exception as _ke:
    print(f"[OKi] Knowledge layer unavailable: {_ke}")
    _KNOWLEDGE_AVAILABLE = False


# ── SECTION B — startup event (add or merge into your existing startup) ───────

# Place this BEFORE   app = FastAPI(...)   or merge into your existing
# @app.on_event("startup") handler.

def _build_initial_state() -> dict:
    """
    Load demo scenario and run one full engine cycle so the UI
    immediately shows a meaningful state — no blank screen on load.
    """
    state = load_generator_failure()

    if _MODULES_AVAILABLE:
        try:
            compute_fuel_state(state)
            compute_energy_time(state)
            evaluate_situation_type(state)
            evaluate_decision_window(state)
            run_diagnostics(state)
        except Exception as exc:
            print(f"[OKi] Engine cycle failed during startup: {exc}")

    return state


# Shared mutable state — replace or extend your existing state store.
# If you already have a global `state` dict, replace its initialisation:
#
#   state: dict = _build_initial_state()
#
app_state: dict = _build_initial_state()


# ── SECTION C — add at the very bottom of web_server.py ──────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
