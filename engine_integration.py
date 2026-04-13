"""
OKi — engine.py integration snippet  (v2)
Adds energy-time awareness and situation classification to the existing cycle.
Drop these imports and the four call lines into engine.py in the shown order.
"""

# ── Imports (add to top of engine.py) ────────────────────────────────────────
from fuel_tank_module      import compute_fuel_state
from energy_time_module    import compute_energy_time
from situation_classifier  import evaluate_situation_type
from diagnostic_engine     import run_diagnostics


# ── Engine cycle (correct insertion order) ───────────────────────────────────
def run_engine_cycle(state: dict) -> None:

    # … your existing steps …
    # energy_forecast.update(state)
    # system_health.check(state)

    # ── Phase 1: sensor / measurement enrichment ──────────────────────────────
    compute_fuel_state(state)           # always; enriches state["Fuel"]
    compute_energy_time(state)          # always; enriches state["Energy"]

    # ── Phase 2: classification (needs Energy already populated) ──────────────
    evaluate_situation_type(state)      # writes state["System"]["SituationType"]

    # ── Phase 3: reasoning (needs SituationType for tone decisions) ───────────
    run_diagnostics(state)              # conditional; writes state["Diagnostic"]

    # ── Continues … ──────────────────────────────────────────────────────────
    # attention_engine.evaluate(state)  ← reads SituationType + Diagnostic
    # …


# ── Attention engine priority reference ──────────────────────────────────────
# Import and use ATTENTION_PRIORITY from situation_classifier.py:
#
#   from situation_classifier import ATTENTION_PRIORITY
#
#   def attention_engine_sort_key(item):
#       return ATTENTION_PRIORITY.get(item["SituationType"], 99)
#
# ATTENTION_PRIORITY maps:
#   CRITICAL_COUNTDOWN → 0   (highest)
#   RECOVERY_FAILURE   → 1
#   DIAGNOSTIC         → 2
#   LOW_ENERGY         → 3
#   NORMAL             → 4


# ── Feeding operator responses back into diagnostic state ─────────────────────
# When your input layer receives an operator response (A / B / C),
# write it before the next engine cycle runs:
#
#   state["Diagnostic"]["OperatorResponse"] = "B"
#
# The diagnostic engine reads this on the next cycle and advances accordingly.
# Clear it after processing if you want explicit acknowledgement tracking:
#
#   state["Diagnostic"]["OperatorResponse"] = ""
