# ============================================================
# OKi – Onboard Knowledge Interface
# ENTERPRISE WEB LAYER v21.14
# ============================================================
#
# Changelog v21.14
# -----------------
# • OPERATOR BUTTONS — distinct colours in all three UI modes:
#     - Normal:      Expected (green), Investigating (amber), Unexpected (red)
#     - Wicked:      Expected (neon green), Investigating (amber), Unexpected (red)
#     - Psychedelic: unchanged (already had named classes from v21.12)
# • Named classes .op-button-b and .op-button-c added to render_supervisory_view
#   (both visible and hidden-state placeholders) — nth-child bug permanently resolved
#   across all three UI modes
#
# Changelog v20.7
# ----------------
# • TWO EASTER EGGS:
#     - WICKED MODE: 7 taps on OKi logo → sci-fi Orbitron neon theme
#       (was PSYCHEDELIC_MODE, renamed to WICKED_MODE)
#     - PSYCHEDELIC MODE: 7s hold on OKi logo → true psychedelic
#       cosmic mode with animated neon borders, particle field,
#       color-cycling panels, energy flow, cinematic transition
# • Logo enlarged slightly and aligned with DEMO toggle
# • Progress ring SVG feedback during 15s hold
# • Cinematic CSS transition on psychedelic activation
# • New endpoints: /api/toggle-wicked, /api/toggle-psychedelic (updated)
# • render_layout: psychedelic > wicked > normal priority
#
# Changelog v20.6
# ----------------
# • KNOWLEDGE BASE — full implementation of /knowledge page:
#     - All cases listed with title, symptoms as tags, root cause snippet
#     - Live JS search/filter by keyword (no reload)
#     - Case detail page at /knowledge/<case_id> showing full
#       root cause, solution, symptoms, conditions, actions
#     - Case count and system grouping by case_id prefix
#     - Consistent OKi visual style, Back navigation
#
# Changelog v20.5
# ----------------
# • TOGGLE FIX — FOCUS, DEV, DEMO, PSYCHEDELIC toggles no longer cause
#     page reload or scroll jump. JS intercepts toggle onChange, calls
#     fetch('/api/toggle-*'), then fetches '/api/content' to swap the
#     .content div in place. Header re-rendered via '/api/header'.
# • FOCUS VIEW IDs — all live data elements in render_focus_view now
#     carry the same IDs as supervisory view. applyState() updates
#     focus view data live, no reload needed.
# • New endpoints: GET /api/toggle-focus, /api/toggle-dev,
#     /api/toggle-demo, /api/toggle-psychedelic (return JSON),
#     GET /api/content (returns rendered content HTML for current view),
#     GET /api/header (returns rendered header HTML)
#
# Changelog v20.4
# ----------------
# • SCROLL FIX — replaced location.reload() with fetch-based live update
#     - New GET /api/state endpoint returns full state as JSON
#     - JS polls /api/state every 3s and updates DOM in place
#     - No page reload = no scroll jump, ever
#     - Header LEDs, SoC, health, recommendation, all panels update live
#     - Clock continues to update independently (unchanged)
#     - Toggle/button navigation unchanged (href redirects as before)
#
# Changelog v20.3
# ----------------
# • DEV mode block fully implemented — raw state data displayed:
#     - Raw Vessel Data (Battery, Solar, AC, Generator, Fuel, Derived)
#     - System Intelligence (SituationType, DecisionWindow, Severity,
#       HealthCategories, Diagnostic state)
#     - Last 10 Memory snapshots from the engine
#     - Scenario buttons (anchor, casa, drain, generator_failure)
# • Boat name subtitle corrected: "OKi" branding (O and K caps, i lower)
# • StateManager self-initialises on Render (no main.py needed)
# • get_state() crash-safe fallback to schema defaults
#
# ============================================================

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import sys
import os
from pathlib import Path

# ── Engine import — safe guard ────────────────────────────────────────────────
try:
    from engine import process_operator_response, load_scenario, toggle_dev_mode, apply_care_task, CARE_TASKS
    _ENGINE_AVAILABLE = True
except Exception as _engine_err:
    print(f"[OKi] Warning — engine import failed: {_engine_err}")
    _ENGINE_AVAILABLE = False
    def process_operator_response(*a, **kw): pass
    def load_scenario(*a, **kw): pass
    def toggle_dev_mode(*a, **kw): pass
    def apply_care_task(*a, **kw): return {"ok": False, "points": 0, "message": "Engine unavailable."}
    CARE_TASKS = []

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

FOCUS_MODE       = False
PSYCHEDELIC_MODE = False
WICKED_MODE      = False
DEMO_MODE        = False

# ── Knowledge path ─────────────────────────────────────────────────────────────
# Pi layout:  15_OKi/05_OKi_Engine/ ← parents[0], 02_OKi_Knowledge ← parents[1]
# Render layout: flat — all files in same directory
KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "02_OKi_Knowledge"
if KNOWLEDGE_PATH.exists() and str(KNOWLEDGE_PATH) not in sys.path:
    sys.path.insert(0, str(KNOWLEDGE_PATH))
elif not KNOWLEDGE_PATH.exists():
    _flat = Path(__file__).resolve().parent
    if str(_flat) not in sys.path:
        sys.path.insert(0, str(_flat))

try:
    from case_library import CASE_LIBRARY
    _KNOWLEDGE_AVAILABLE = True
except Exception as _klib_err:
    print(f"[OKi] Warning — case_library import failed: {_klib_err}")
    _KNOWLEDGE_AVAILABLE = False
    class _EmptyLibrary:
        cases = {}
        def search_cases(self, *a, **kw): return []
        def all_cases(self): return []
    CASE_LIBRARY = _EmptyLibrary()

# ── Startup — initialise state_manager and load demo ──────────────────────────
@app.on_event("startup")
def _startup():
    # Always boot in normal mode — Easter eggs must be re-activated each session
    global PSYCHEDELIC_MODE, WICKED_MODE, FOCUS_MODE
    PSYCHEDELIC_MODE = False
    WICKED_MODE      = False
    FOCUS_MODE       = False

    if not hasattr(app.state, "state_manager") or app.state.state_manager is None:
        try:
            from state_manager import StateManager
            app.state.state_manager = StateManager()
            print("[OKi] StateManager initialised")
        except Exception as _sme:
            print(f"[OKi] Warning — StateManager init failed: {_sme}")
            app.state.state_manager = None

    if _ENGINE_AVAILABLE and app.state.state_manager is not None:
        try:
            load_scenario(app.state.state_manager, "casa_azul")
            print("[OKi] Demo scenario loaded: casa_azul")
        except Exception as _se:
            print(f"[OKi] Demo scenario skipped: {_se}")

# ── State access ──────────────────────────────────────────────────────────────
def get_state():
    try:
        return app.state.state_manager.get()
    except Exception:
        from state_schema import STATE_SCHEMA
        from copy import deepcopy
        return deepcopy(STATE_SCHEMA)

# ── Safe value helpers ────────────────────────────────────────────────────────
def safe_float(value, default="—"):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return default

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def v(val, unit="", default="—"):
    """Format a value with optional unit, safe default."""
    if val is None:
        return default
    try:
        return f"{round(float(val), 1)}{unit}"
    except (TypeError, ValueError):
        return str(val)

# ── Visual helpers ────────────────────────────────────────────────────────────
def soc_bar_html(soc, mode):
    mode_upper = (mode or "").upper()
    is_charging    = "CHARG" in mode_upper
    is_discharging = "DISCHARG" in mode_upper
    if is_discharging:
        bar_color       = "#ff5252" if soc < 15 else "#ffb300" if soc < 30 else "#4caf50"
        animation_class = "soc-bar-discharging"
    elif is_charging:
        bar_color       = "#4caf50"
        animation_class = "soc-bar-charging"
    else:
        bar_color       = "#ff5252" if soc < 15 else "#ffb300" if soc < 30 else "#4caf50"
        animation_class = ""
    return f'<div class="soc-bar-outer"><div class="soc-bar-fill {animation_class}" style="width:{soc}%; background:{bar_color};"></div></div>'

def soc_css_class(soc):
    if soc < 15:   return "soc-number soc-red"
    elif soc < 30: return "soc-number soc-amber"
    return "soc-number soc-green"

def bar_color_for_health(health):
    if health < 50: return "red"
    elif health < 75: return "amber"
    return "green"

# ══════════════════════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════════════════════

OKi_Normal_UI = """<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-user-select:none;-moz-user-select:none;user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%}
body{background:#0f1115;color:#cad8e3;font-family:Segoe UI,sans-serif;display:flex;justify-content:center;align-items:stretch;min-height:100dvh;padding:6px}
.outer{width:100%;max-width:720px;display:flex;flex-direction:column}
.frame{flex:1;border:3px solid #cad8e3;border-radius:16px;padding:10px 12px 6px 12px;display:flex;flex-direction:column;overflow:hidden;background:#0f1115}
.header{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin-bottom:6px;gap:6px}
.header-left{display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.header-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.title-block{text-align:center}
.title-oki{font-size:clamp(22px,5vw,32px);font-weight:bold;color:#1f6fb5;letter-spacing:0.1em;line-height:1}
.title-sub{font-size:clamp(8px,1.4vw,10px);color:#4a7a9a;letter-spacing:0.15em;text-transform:uppercase;margin-top:2px}
.boat-name-center{font-size:clamp(9px,1.8vw,11px);color:#4a8aaa;letter-spacing:0.12em;text-transform:uppercase;margin-top:3px}
.clock{font-size:clamp(14px,3vw,19px);color:#cad8e3;letter-spacing:0.06em;text-align:right;font-weight:bold}
.clock-date{font-size:clamp(9px,1.8vw,11px);color:#6a8aa0;text-align:right}
.led-strip{display:flex;gap:5px;align-items:center}
.led{width:9px;height:9px;border-radius:50%}
.led-green{background:#4caf50}
.led-amber{background:#ffb300;animation:pulse-amber 2s ease-in-out infinite}
.led-red{background:#ff5252;animation:pulse-red 1.2s ease-in-out infinite}
.led-off{background:#2b313c;border:1px solid #3a4255}
@keyframes pulse-amber{0%,100%{opacity:1}50%{opacity:0.4}}
@keyframes pulse-red{0%,100%{opacity:1}50%{opacity:0.3}}
.toggle-box{display:flex;flex-direction:column;align-items:center;gap:3px;touch-action:manipulation;cursor:pointer;padding:4px}
.toggle-label{font-size:clamp(8px,1.5vw,10px);color:#9aa8b5;letter-spacing:0.08em;font-weight:600}
.switch{position:relative;display:inline-block;width:44px;height:26px;touch-action:manipulation}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#444;transition:.3s;border-radius:18px}
.slider:before{position:absolute;content:"";height:18px;width:18px;left:2px;bottom:2px;background:white;transition:.3s;border-radius:50%}
input:checked+.slider{background:#1f6fb5}
input:checked+.slider:before{transform:translateX(18px);background:#fff}
.divider{height:1px;background:#2b313c;margin:4px 0 6px 0;flex-shrink:0}
.content{flex:1;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#2b313c #0f1115;touch-action:pan-y}
.soc-display{text-align:center;padding:4px 0 4px 0}
.soc-number{font-size:clamp(32px,7vw,48px);font-weight:bold;line-height:1}
.soc-green{color:#4caf50}.soc-amber{color:#ffb300}.soc-red{color:#ff5252}
.soc-label{font-size:clamp(8px,1.6vw,10px);color:#6a8aa0;letter-spacing:0.2em;text-transform:uppercase;margin-top:2px}
.soc-bar-outer{width:100%;height:28px;background:#222;border-radius:14px;overflow:hidden;margin-top:10px;border:1px solid #333}
.soc-bar-fill{height:100%;border-radius:14px;transition:width 0.6s ease}
@keyframes flash-red{0%,100%{opacity:1}50%{opacity:0.25}}
@keyframes pulse-green-charge{0%,100%{opacity:1}50%{opacity:0.55}}
.soc-bar-discharging{animation:flash-red 1.2s ease-in-out infinite}
.soc-bar-charging{animation:pulse-green-charge 1.8s ease-in-out infinite}
.bar-container{width:100%;height:12px;background:#222;border-radius:6px;overflow:hidden;margin-top:6px}
.bar-fill{height:100%;border-radius:6px;transition:width 0.6s ease}
.bar-green{background:#4caf50}.bar-amber{background:#ffb300}.bar-red{background:#ff5252}.bar-blue{background:#1f6fb5}
.panel{background:#1a1d23;padding:clamp(8px,2vw,12px);border-radius:10px;margin-bottom:6px}
.panel-title{margin-bottom:8px;font-size:clamp(13px,2.5vw,16px);color:#1f6fb5;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.badge{font-size:10px;padding:2px 8px;border-radius:8px;font-weight:bold}
.badge-warning{background:#ffb300;color:#000}.badge-critical{background:#ff5252;color:#fff}.badge-ok{background:#4caf50;color:#fff}
.button{display:block;width:92%;margin:7px auto;padding:clamp(14px,2.8vw,18px);background:#2b313c;color:#cad8e3;text-decoration:none;border-radius:24px;text-align:center;font-size:clamp(13px,2.5vw,15px);transition:background 0.2s;cursor:pointer;border:none;touch-action:manipulation;min-height:48px}
.button:hover,.button:active{background:#3a4255}
.op-button{display:block;width:92%;margin:6px auto;padding:clamp(14px,2.8vw,18px);background:#1a2e1a;color:#4caf50;text-decoration:none;border-radius:24px;text-align:center;font-size:clamp(13px,2.5vw,15px);border:1px solid #2a4a2a;cursor:pointer;transition:background 0.2s;touch-action:manipulation;min-height:48px}
.op-button:hover,.op-button:active{background:#243824}
.op-button-b{background:#2e2a14;color:#ffb300;border-color:#4a3e10}
.op-button-b:hover,.op-button-b:active{background:#3a3318}
.op-button-c{background:#2e1a1a;color:#ff5252;border-color:#4a2222}
.op-button-c:hover,.op-button-c:active{background:#3a2222}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-size:clamp(12px,2.2vw,14px)}
.grid2 .label{color:#9aa8b5;font-size:clamp(10px,1.8vw,12px)}.grid2 .value{color:#cad8e3}
.advisory{font-size:clamp(10px,1.8vw,12px);color:#ffb300;margin-top:8px;padding:6px 10px;background:#2a2000;border-radius:6px;border-left:3px solid #ffb300}
.reason{font-size:clamp(10px,1.8vw,11px);color:#6a8aa0;margin-top:5px}
.refresh-note{text-align:center;font-size:9px;color:#333;margin-bottom:4px;flex-shrink:0}

.footer{text-align:center;padding-top:4px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:6px}
.footer-demo{display:flex;flex-direction:column;align-items:center;gap:4px;margin-bottom:2px}
.footer-demo-label{font-size:clamp(9px,1.6vw,11px);color:#6a8aa0;letter-spacing:0.1em;font-weight:600}
.demo-section{border-top:1px solid #2b313c;margin-top:8px;padding-top:8px}
.demo-label{text-align:center;font-size:10px;color:#6a8aa0;margin-bottom:8px;letter-spacing:0.12em;font-weight:bold}
.demo-scenario-btn{display:inline-block;margin:5px;padding:10px 20px;background:#1a2030;color:#7ab8d4;border:1px solid #2b3a50;border-radius:20px;font-size:clamp(11px,2vw,13px);text-decoration:none;cursor:pointer;font-weight:600}
.demo-scenario-btn:hover{background:#2b3a50;color:#cad8e3}
.footer img{width:clamp(72px,14vw,96px);opacity:0.85;cursor:pointer;-webkit-tap-highlight-color:transparent}
.dev-section{border-top:2px solid #1f6fb5;margin-top:10px;padding-top:8px}
.dev-label{text-align:center;font-size:10px;color:#1f6fb5;margin-bottom:8px;letter-spacing:0.15em;font-weight:bold}
.dev-panel{background:#111318;border:1px solid #2b313c;border-radius:8px;padding:10px;margin-bottom:8px}
.dev-panel-title{font-size:clamp(9px,1.6vw,11px);color:#1f6fb5;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;font-weight:bold}
.dev-grid{display:grid;grid-template-columns:1fr 1fr;gap:3px 10px;font-size:clamp(10px,1.8vw,12px)}
.dev-grid .dk{color:#6a8aa0;font-size:clamp(9px,1.5vw,11px)}.dev-grid .dv{color:#cad8e3;font-family:monospace}
.dev-memory{font-size:clamp(9px,1.5vw,11px);color:#6a8aa0;font-family:monospace;line-height:1.6}
.dev-memory span{color:#cad8e3}
.dev-scenario-btn{display:inline-block;margin:4px;padding:6px 14px;background:#1a2030;color:#7ab8d4;border:1px solid #2b3a50;border-radius:16px;font-size:clamp(10px,1.8vw,12px);text-decoration:none;cursor:pointer}
.dev-scenario-btn:hover{background:#2b3a50;color:#cad8e3}
@media(max-width:400px){.button,.op-button{width:100%}}
.kb-search{width:100%;padding:10px 14px;background:#1a1d23;border:1px solid #2b313c;border-radius:24px;color:#cad8e3;font-size:clamp(12px,2.2vw,14px);outline:none;margin-bottom:10px;box-sizing:border-box}
.kb-search:focus{border-color:#1f6fb5}
.kb-search::placeholder{color:#4a5a6a}
.kb-case{background:#0f1115;border-radius:10px;padding:10px 12px;margin-bottom:6px;cursor:pointer;border:1px solid #1a1d23;transition:border-color 0.15s;text-decoration:none;display:block}
.kb-case:hover{border-color:#1f6fb5}
.kb-case-id{font-size:clamp(9px,1.5vw,10px);color:#4a7a9a;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:2px}
.kb-case-title{font-size:clamp(12px,2.2vw,14px);color:#cad8e3;font-weight:600;margin-bottom:5px}
.kb-case-snippet{font-size:clamp(10px,1.8vw,11px);color:#6a8aa0;margin-bottom:6px;line-height:1.5}
.kb-tags{display:flex;flex-wrap:wrap;gap:4px}
.kb-tag{font-size:clamp(9px,1.5vw,10px);padding:2px 8px;background:#0a1420;color:#548bac;border:1px solid #1a3048;border-radius:10px}
.kb-empty{text-align:center;color:#4a5a6a;padding:20px;font-size:clamp(11px,2vw,13px)}
.kb-detail-section{margin-bottom:14px}
.kb-detail-label{font-size:clamp(9px,1.6vw,10px);color:#4a7a9a;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:5px;font-weight:600}
.kb-detail-text{font-size:clamp(11px,2vw,13px);color:#cad8e3;line-height:1.7}
.kb-detail-list{list-style:none;padding:0;margin:0}
.kb-detail-list li{font-size:clamp(11px,2vw,12px);color:#cad8e3;padding:3px 0 3px 14px;position:relative;line-height:1.5}
.kb-detail-list li::before{content:"–";position:absolute;left:0;color:#548bac}
.kb-count{font-size:clamp(9px,1.6vw,10px);color:#4a7a9a;letter-spacing:0.08em;margin-bottom:10px}
.kb-no-results{display:none}
#psych-overlay{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;opacity:0;background:radial-gradient(ellipse at center,rgba(255,0,255,0.4),rgba(0,212,255,0.2),transparent);transition:opacity 0.4s ease}
#psych-overlay.flash{animation:psych-flash 0.8s ease-out forwards}
@keyframes psych-flash{0%{opacity:0}30%{opacity:1}100%{opacity:0}}
</style>"""

OKi_Wicked_UI = """<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Exo+2:wght@300;400;600&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-user-select:none;-moz-user-select:none;user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%}
body{background:radial-gradient(ellipse at top,#0a1628 0%,#050810 60%,#000 100%);color:#cad8e3;font-family:'Exo 2',sans-serif;display:flex;justify-content:center;align-items:stretch;min-height:100dvh;padding:6px}
.outer{width:100%;max-width:720px;display:flex;flex-direction:column}
.frame{flex:1;border:2px solid #1f6fb5;border-radius:16px;padding:10px 12px 6px 12px;display:flex;flex-direction:column;overflow:hidden;background:linear-gradient(180deg,#0d1520 0%,#080c14 100%);box-shadow:0 0 30px rgba(31,111,181,0.15);position:relative}
.frame::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent 0%,#1f6fb5 20%,#00d4ff 50%,#1f6fb5 80%,transparent 100%)}
.header{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin-bottom:6px;gap:6px}
.header-left{display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.header-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.title-block{text-align:center}
.title-oki{font-family:'Orbitron',monospace;font-size:clamp(24px,5.5vw,36px);font-weight:900;color:#1f6fb5;letter-spacing:0.18em;line-height:1;text-shadow:0 0 20px rgba(31,111,181,0.8),0 0 40px rgba(31,111,181,0.4)}
.title-sub{font-size:clamp(8px,1.4vw,10px);color:#3a5a7a;letter-spacing:0.2em;text-transform:uppercase;margin-top:2px}
.boat-name-center{font-family:'Orbitron',monospace;font-size:clamp(9px,1.8vw,11px);color:#00d4ff;letter-spacing:0.2em;text-transform:uppercase;margin-top:3px;text-shadow:0 0 10px rgba(0,212,255,0.6)}
.clock{font-family:'Orbitron',monospace;font-size:clamp(14px,3vw,20px);color:#00d4ff;text-shadow:0 0 12px rgba(0,212,255,0.8);letter-spacing:0.1em;text-align:right}
.clock-date{font-size:clamp(9px,1.8vw,11px);color:#5a8aaa;text-align:right}
.led-strip{display:flex;gap:5px;align-items:center}
.led{width:10px;height:10px;border-radius:50%}
.led-green{background:#00ff44;box-shadow:0 0 6px #00ff44,0 0 12px rgba(0,255,68,0.5);animation:pg 2s ease-in-out infinite}
.led-amber{background:#ffb300;box-shadow:0 0 6px #ffb300;animation:pa 1.5s ease-in-out infinite}
.led-red{background:#ff3333;box-shadow:0 0 8px #ff3333;animation:pr 1s ease-in-out infinite}
.led-off{background:#1a2030}
@keyframes pg{0%,100%{opacity:1}50%{opacity:0.6}}@keyframes pa{0%,100%{opacity:1}50%{opacity:0.4}}@keyframes pr{0%,100%{opacity:1}50%{opacity:0.3}}
.toggle-box{display:flex;flex-direction:column;align-items:center;gap:3px;touch-action:manipulation;cursor:pointer;padding:4px}
.toggle-label{font-size:clamp(8px,1.5vw,10px);color:#3a6a8a;letter-spacing:0.1em;font-weight:600;font-family:'Orbitron',monospace}
.switch{position:relative;display:inline-block;width:44px;height:26px;touch-action:manipulation}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#1a2030;border:1px solid #2a4060;transition:.4s;border-radius:18px}
.slider:before{position:absolute;content:"";height:18px;width:18px;left:2px;bottom:2px;background:#3a5a7a;transition:.4s;border-radius:50%}
input:checked+.slider{background:#0a3060;border-color:#1f6fb5;box-shadow:0 0 8px rgba(31,111,181,0.6)}
input:checked+.slider:before{transform:translateX(18px);background:#00d4ff}
.divider{height:1px;background:linear-gradient(90deg,transparent,#1f3a5a 20%,#1f6fb5 50%,#1f3a5a 80%,transparent);margin:4px 0 6px 0;flex-shrink:0}
.content{flex:1;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#1f3a5a #080c14;touch-action:pan-y}
.soc-display{text-align:center;padding:4px 0 4px 0}
.soc-number{font-family:'Orbitron',monospace;font-size:clamp(32px,7vw,48px);font-weight:900;line-height:1}
.soc-green{color:#00ff44;text-shadow:0 0 20px rgba(0,255,68,0.8),0 0 40px rgba(0,255,68,0.4)}
.soc-amber{color:#ffb300;text-shadow:0 0 20px rgba(255,179,0,0.8)}
.soc-red{color:#ff3333;text-shadow:0 0 20px rgba(255,51,51,0.8)}
.soc-label{font-family:'Orbitron',monospace;font-size:clamp(8px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.3em;margin-top:2px}
.soc-bar-outer{width:100%;height:28px;background:#080c14;border-radius:14px;overflow:hidden;margin-top:10px;border:1px solid #1a2a3a}
.soc-bar-fill{height:100%;border-radius:14px;transition:width 0.6s ease}
@keyframes flash-red{0%,100%{opacity:1}50%{opacity:0.25}}
@keyframes pulse-green-charge{0%,100%{opacity:1}50%{opacity:0.55}}
.soc-bar-discharging{animation:flash-red 1.2s ease-in-out infinite}
.soc-bar-charging{animation:pulse-green-charge 1.8s ease-in-out infinite}
.bar-container{width:100%;height:12px;background:#080c14;border-radius:6px;overflow:hidden;margin-top:6px;border:1px solid #1a2a3a}
.bar-fill{height:100%;border-radius:6px;transition:width 0.8s ease}
.bar-green{background:linear-gradient(90deg,#006622,#00ff44);box-shadow:0 0 8px rgba(0,255,68,0.5)}
.bar-amber{background:linear-gradient(90deg,#7a5500,#ffb300)}
.bar-red{background:linear-gradient(90deg,#7a0000,#ff3333)}
.bar-blue{background:linear-gradient(90deg,#0a2a5a,#1f6fb5)}
.panel{background:linear-gradient(135deg,#0d1825 0%,#080c14 100%);padding:clamp(8px,2vw,12px);border-radius:10px;margin-bottom:6px;border:1px solid #1a2a3a;position:relative;overflow:hidden}
.panel::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%;background:linear-gradient(180deg,#1f6fb5,#00d4ff,#1f6fb5);border-radius:3px 0 0 3px}
.panel-title{margin-bottom:8px;font-size:clamp(11px,2.2vw,14px);color:#4a9fd4;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-family:'Orbitron',monospace;letter-spacing:0.06em;text-transform:uppercase}
.badge{font-size:10px;padding:2px 8px;border-radius:8px;font-weight:bold}
.badge-warning{background:#7a5500;color:#ffb300;border:1px solid #ffb300}
.badge-critical{background:#7a0000;color:#ff3333;border:1px solid #ff3333}
.badge-ok{background:#006622;color:#00ff44;border:1px solid #00ff44}
.button{display:block;width:92%;margin:7px auto;padding:clamp(14px,2.8vw,18px);background:linear-gradient(135deg,#0d1e35,#0a1525);color:#7ab8d4;text-decoration:none;border-radius:10px;text-align:center;font-size:clamp(12px,2.3vw,15px);font-family:'Orbitron',monospace;letter-spacing:0.15em;transition:all 0.15s ease;cursor:pointer;border:1px solid #1f4a6a;text-transform:uppercase;touch-action:manipulation;min-height:48px}
.button:hover,.button:active{background:linear-gradient(135deg,#1a3a5a,#0d2040);border-color:#1f6fb5;color:#00d4ff}
.op-button{display:block;width:92%;margin:6px auto;padding:clamp(14px,2.8vw,18px);background:linear-gradient(135deg,#1a2a1a,#0d1a0d);color:#4aff80;text-decoration:none;border-radius:10px;text-align:center;font-size:clamp(12px,2.3vw,14px);font-family:'Orbitron',monospace;letter-spacing:0.1em;border:1px solid #1a4a2a;cursor:pointer;transition:all 0.15s ease;touch-action:manipulation;min-height:48px}
.op-button:hover,.op-button:active{background:linear-gradient(135deg,#2a4a2a,#1a2a1a);border-color:#00ff44}
.op-button-b{background:linear-gradient(135deg,#2a2210,#1a1608);color:#ffb300;border-color:#4a3a10}
.op-button-b:hover,.op-button-b:active{background:linear-gradient(135deg,#3a3018,#2a2210);border-color:#ffb300}
.op-button-c{background:linear-gradient(135deg,#2a1010,#1a0808);color:#ff3333;border-color:#4a1a1a}
.op-button-c:hover,.op-button-c:active{background:linear-gradient(135deg,#3a1818,#2a1010);border-color:#ff3333}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-size:clamp(12px,2.2vw,14px)}
.grid2 .label{color:#3a6a8a;font-size:clamp(10px,1.8vw,12px)}.grid2 .value{color:#cad8e3;font-family:'Orbitron',monospace;font-size:clamp(11px,2vw,13px)}
.advisory{font-size:clamp(10px,1.8vw,12px);color:#ffb300;margin-top:8px;padding:6px 10px;background:linear-gradient(135deg,#2a1500,#1a0d00);border-radius:6px;border-left:2px solid #ffb300}
.reason{font-size:clamp(10px,1.8vw,11px);color:#3a6a8a;margin-top:5px}
.refresh-note{text-align:center;font-size:9px;color:#1a3a5a;margin-bottom:4px;flex-shrink:0}

.footer{text-align:center;padding-top:4px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:6px}
.footer-demo{display:flex;flex-direction:column;align-items:center;gap:4px;margin-bottom:2px}
.footer-demo-label{font-size:clamp(9px,1.6vw,11px);color:#6a8aa0;letter-spacing:0.1em;font-weight:600}
.demo-section{border-top:1px solid #2b313c;margin-top:8px;padding-top:8px}
.demo-label{text-align:center;font-size:10px;color:#6a8aa0;margin-bottom:8px;letter-spacing:0.12em;font-weight:bold}
.demo-scenario-btn{display:inline-block;margin:5px;padding:10px 20px;background:#1a2030;color:#7ab8d4;border:1px solid #2b3a50;border-radius:20px;font-size:clamp(11px,2vw,13px);text-decoration:none;cursor:pointer;font-weight:600}
.demo-scenario-btn:hover{background:#2b3a50;color:#cad8e3}
.footer img{width:clamp(72px,14vw,96px);opacity:0.85;filter:drop-shadow(0 0 6px rgba(31,111,181,0.4));cursor:pointer;-webkit-tap-highlight-color:transparent}
.dev-section{border-top:2px solid #1f6fb5;margin-top:10px;padding-top:8px}
.dev-label{text-align:center;font-size:10px;color:#1f6fb5;margin-bottom:8px;letter-spacing:0.15em;font-weight:bold;font-family:'Orbitron',monospace}
.dev-panel{background:#050810;border:1px solid #1a2a3a;border-radius:8px;padding:10px;margin-bottom:8px}
.dev-panel-title{font-size:clamp(9px,1.6vw,11px);color:#4a9fd4;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;font-weight:bold;font-family:'Orbitron',monospace}
.dev-grid{display:grid;grid-template-columns:1fr 1fr;gap:3px 10px;font-size:clamp(10px,1.8vw,12px)}
.dev-grid .dk{color:#3a6a8a;font-size:clamp(9px,1.5vw,11px)}.dev-grid .dv{color:#cad8e3;font-family:monospace}
.dev-memory{font-size:clamp(9px,1.5vw,11px);color:#3a6a8a;font-family:monospace;line-height:1.6}
.dev-memory span{color:#cad8e3}
.dev-scenario-btn{display:inline-block;margin:4px;padding:6px 14px;background:#0a1525;color:#7ab8d4;border:1px solid #1f4a6a;border-radius:16px;font-size:clamp(10px,1.8vw,12px);text-decoration:none;cursor:pointer;font-family:'Orbitron',monospace;letter-spacing:0.08em}
.dev-scenario-btn:hover{background:#1a3a5a;color:#00d4ff}
@media(max-width:400px){.button,.op-button{width:100%}}
.kb-search{width:100%;padding:10px 14px;background:#0a1020;border:1px solid #1a2a3a;border-radius:24px;color:#cad8e3;font-size:clamp(12px,2.2vw,14px);outline:none;margin-bottom:10px;box-sizing:border-box;font-family:'Exo 2',sans-serif}
.kb-search:focus{border-color:#1f6fb5;box-shadow:0 0 8px rgba(31,111,181,0.3)}
.kb-search::placeholder{color:#2a4a6a}
.kb-case{background:#080c14;border-radius:10px;padding:10px 12px;margin-bottom:6px;cursor:pointer;border:1px solid #1a2a3a;transition:border-color 0.15s;text-decoration:none;display:block}
.kb-case:hover{border-color:#1f6fb5;box-shadow:0 0 8px rgba(31,111,181,0.15)}
.kb-case-id{font-size:clamp(9px,1.5vw,10px);color:#3a6a8a;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:2px;font-family:'Orbitron',monospace}
.kb-case-title{font-size:clamp(12px,2.2vw,14px);color:#cad8e3;font-weight:600;margin-bottom:5px}
.kb-case-snippet{font-size:clamp(10px,1.8vw,11px);color:#3a6a8a;margin-bottom:6px;line-height:1.5}
.kb-tags{display:flex;flex-wrap:wrap;gap:4px}
.kb-tag{font-size:clamp(9px,1.5vw,10px);padding:2px 8px;background:#050a14;color:#4a9fd4;border:1px solid #1a3a5a;border-radius:10px;font-family:'Orbitron',monospace;letter-spacing:0.05em}
.kb-empty{text-align:center;color:#2a4a6a;padding:20px;font-size:clamp(11px,2vw,13px)}
.kb-detail-section{margin-bottom:14px}
.kb-detail-label{font-size:clamp(9px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:5px;font-weight:600;font-family:'Orbitron',monospace}
.kb-detail-text{font-size:clamp(11px,2vw,13px);color:#cad8e3;line-height:1.7}
.kb-detail-list{list-style:none;padding:0;margin:0}
.kb-detail-list li{font-size:clamp(11px,2vw,12px);color:#cad8e3;padding:3px 0 3px 14px;position:relative;line-height:1.5}
.kb-detail-list li::before{content:"–";position:absolute;left:0;color:#4a9fd4}
.kb-count{font-size:clamp(9px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.1em;margin-bottom:10px;font-family:'Orbitron',monospace}
.kb-no-results{display:none}
#psych-overlay{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;opacity:0;background:radial-gradient(ellipse at center,rgba(255,0,255,0.4),rgba(0,212,255,0.2),transparent);transition:opacity 0.4s ease}
#psych-overlay.flash{animation:psych-flash 0.8s ease-out forwards}
@keyframes psych-flash{0%{opacity:0}30%{opacity:1}100%{opacity:0}}
</style>"""

OKi_Psychedelic_UI = """<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Exo+2:wght@300;400;600&display=swap');
/* Keyframes — flowing border, subtle pulse, slide-in, panel border sweep */
@keyframes border-flow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes border-flow-x{0%{background-position:0% 0%}100%{background-position:400% 0%}}
@keyframes neon-glow-pulse{0%,100%{opacity:0.85;box-shadow:0 0 10px rgba(0,255,170,0.4)}50%{opacity:1;box-shadow:0 0 20px rgba(0,255,170,0.7)}}
@keyframes slide-in{0%{opacity:0;transform:scale(0.97) translateY(8px)}100%{opacity:1;transform:scale(1) translateY(0)}}
@keyframes led-pulse{0%,100%{opacity:0.7}50%{opacity:1}}
@keyframes psych-flash{0%{opacity:0}20%{opacity:1}60%{opacity:0.6}100%{opacity:0}}
@keyframes panel-border-anim{0%{background-position:0% 0%}100%{background-position:0% 400%}}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-user-select:none;-moz-user-select:none;user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%}
/* Deep space background — no hue-rotation */
body{background:radial-gradient(ellipse at 25% 20%,#08031a 0%,#02000c 50%,#000005 100%);color:#c8e8ff;font-family:'Exo 2',sans-serif;display:flex;justify-content:center;align-items:stretch;min-height:100dvh;padding:6px}
.outer{width:100%;max-width:720px;display:flex;flex-direction:column;animation:slide-in 0.5s ease-out}
/* Outer frame — flowing full neon border (gradient border-box trick) */
.frame{flex:1;border-radius:16px;padding:10px 12px 6px 12px;display:flex;flex-direction:column;overflow:hidden;position:relative;border:2px solid transparent;background:linear-gradient(#03000e,#03000e) padding-box,linear-gradient(135deg,#00e5ff,#cc00ff,#ff5500,#aaff00,#ff00aa,#00e5ff) border-box;background-size:300% 300%;animation:border-flow 5s ease infinite;box-shadow:0 0 40px rgba(0,229,255,0.12),0 0 80px rgba(204,0,255,0.07),inset 0 0 60px rgba(0,0,15,0.9)}
/* Outer frame top energy sweep line */
.frame::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#00e5ff,#cc00ff,#ff5500,#aaff00,#ff00aa,#00e5ff);background-size:400% 100%;animation:border-flow-x 3s linear infinite;border-radius:16px 16px 0 0;opacity:1;z-index:2}
/* Outer frame bottom energy sweep line */
.frame::after{content:'';position:absolute;bottom:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#aaff00,#ff5500,#cc00ff,#00e5ff,#ff00aa,#aaff00);background-size:400% 100%;animation:border-flow-x 3s linear infinite reverse;border-radius:0 0 16px 16px;opacity:1;z-index:2}
.header{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin-bottom:6px;gap:6px}
.header-left{display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.header-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.title-block{text-align:center}
/* OKi title — cyan with glow */
.title-oki{font-family:'Orbitron',monospace;font-size:clamp(24px,5.5vw,36px);font-weight:900;color:#00e5ff;letter-spacing:0.18em;line-height:1;text-shadow:0 0 14px rgba(0,229,255,0.9),0 0 28px rgba(0,229,255,0.5)}
.title-sub{font-size:clamp(8px,1.4vw,10px);color:#4a8aaa;letter-spacing:0.2em;text-transform:uppercase;margin-top:2px}
.boat-name-center{font-family:'Orbitron',monospace;font-size:clamp(9px,1.8vw,11px);color:#00e5ff;letter-spacing:0.2em;text-transform:uppercase;margin-top:3px;text-shadow:0 0 8px rgba(0,229,255,0.7)}
/* Clock — cyan glow, large */
.clock{font-family:'Orbitron',monospace;font-size:clamp(16px,3.2vw,22px);color:#00e5ff;letter-spacing:0.1em;text-align:right;text-shadow:0 0 12px rgba(0,229,255,0.8),0 0 24px rgba(0,229,255,0.4);font-weight:700}
.clock-date{font-size:clamp(9px,1.8vw,11px);color:#5a7a9a;text-align:right}
/* LEDs */
.led-strip{display:flex;gap:5px;align-items:center}
.led{width:10px;height:10px;border-radius:50%}
.led-green{background:#00ff88;box-shadow:0 0 7px #00ff88,0 0 14px rgba(0,255,136,0.5);animation:led-pulse 2s ease-in-out infinite}
.led-amber{background:#ffaa00;box-shadow:0 0 7px #ffaa00,0 0 14px rgba(255,170,0,0.4);animation:led-pulse 1.5s ease-in-out infinite}
.led-red{background:#ff2255;box-shadow:0 0 7px #ff2255,0 0 14px rgba(255,34,85,0.4);animation:led-pulse 1s ease-in-out infinite}
.led-off{background:#0a0a1a;border:1px solid #1a1a30}
/* Toggles */
.toggle-box{display:flex;flex-direction:column;align-items:center;gap:3px;touch-action:manipulation;cursor:pointer;padding:4px}
.toggle-label{font-size:clamp(8px,1.5vw,10px);color:#4a7a9a;letter-spacing:0.1em;font-weight:600;font-family:'Orbitron',monospace}
.switch{position:relative;display:inline-block;width:44px;height:26px;touch-action:manipulation}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#080018;border:1px solid #1a2040;transition:.3s;border-radius:18px}
.slider:before{position:absolute;content:"";height:18px;width:18px;left:2px;bottom:2px;background:#2a3a5a;transition:.3s;border-radius:50%}
input:checked+.slider{background:#001a35;border-color:#00e5ff;box-shadow:0 0 10px rgba(0,229,255,0.5)}
input:checked+.slider:before{transform:translateX(18px);background:#00e5ff}
/* Divider — neon spectrum sweep */
.divider{height:1px;background:linear-gradient(90deg,transparent,#00e5ff 20%,#cc00ff 50%,#ff5500 80%,transparent);margin:4px 0 6px 0;flex-shrink:0;background-size:300% 100%;animation:border-flow 4s ease infinite}
.content{flex:1;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#00e5ff #03000e;touch-action:pan-y}
/* SoC number — bright green glow */
.soc-display{text-align:center;padding:4px 0 4px 0}
.soc-number{font-family:'Orbitron',monospace;font-size:clamp(32px,7vw,52px);font-weight:900;line-height:1}
.soc-green{color:#00ff88;text-shadow:0 0 18px rgba(0,255,136,0.8),0 0 36px rgba(0,255,136,0.4)}
.soc-amber{color:#ffaa00;text-shadow:0 0 18px rgba(255,170,0,0.8)}
.soc-red{color:#ff2255;text-shadow:0 0 18px rgba(255,34,85,0.8)}
.soc-label{font-family:'Orbitron',monospace;font-size:clamp(8px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.3em;margin-top:2px}
/* SoC bar — thin luminous green→cyan energy beam */
.soc-bar-outer{width:100%;height:8px;background:#020008;border-radius:4px;overflow:hidden;margin-top:10px;border:1px solid rgba(0,229,255,0.15)}
.soc-bar-fill{height:100%;border-radius:4px;transition:width 0.6s ease;background:linear-gradient(90deg,#00cc55,#00ffaa,#00e5ff)!important;box-shadow:0 0 8px rgba(0,255,170,0.6),0 0 16px rgba(0,229,255,0.3)}
.soc-bar-discharging{background:linear-gradient(90deg,#00cc55,#00ffaa,#00e5ff)!important}
.soc-bar-charging{background:linear-gradient(90deg,#00cc55,#00ffaa,#00e5ff)!important;animation:neon-glow-pulse 1.5s ease-in-out infinite}
/* Health/care bars */
.bar-container{width:100%;height:12px;background:#02000a;border-radius:6px;overflow:hidden;margin-top:6px;border:1px solid rgba(0,229,255,0.08)}
.bar-fill{height:100%;border-radius:6px;transition:width 0.8s ease}
.bar-green{background:linear-gradient(90deg,#00cc66,#00ffaa,#00e5ff);box-shadow:0 0 8px rgba(0,255,170,0.4)}
.bar-amber{background:linear-gradient(90deg,#cc6600,#ffaa00);box-shadow:0 0 6px rgba(255,170,0,0.3)}
.bar-red{background:linear-gradient(90deg,#cc0033,#ff2255);box-shadow:0 0 6px rgba(255,34,85,0.3)}
.bar-blue{background:linear-gradient(90deg,#0044cc,#00e5ff);box-shadow:0 0 6px rgba(0,229,255,0.3)}
/* Panels — each has its own full animated neon border */
.panel{background:rgba(3,0,12,0.93);padding:clamp(8px,2vw,12px);border-radius:12px;margin-bottom:6px;position:relative;border:1.5px solid transparent;background-clip:padding-box;overflow:visible}
.panel::before{content:'';position:absolute;inset:-1.5px;border-radius:13px;background:linear-gradient(135deg,#00e5ff,#cc00ff,#ff5500,#aaff00,#ff00aa,#00e5ff);background-size:300% 300%;animation:border-flow 5s ease infinite;z-index:-1}
/* Panel inner background to cover the gradient border */
.panel::after{content:'';position:absolute;inset:1.5px;border-radius:11px;background:rgba(3,0,12,0.95);z-index:-1}
/* Panel titles — cyan, Orbitron */
.panel-title{margin-bottom:8px;font-size:clamp(11px,2.2vw,14px);color:#00e5ff;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-family:'Orbitron',monospace;letter-spacing:0.08em;text-transform:uppercase;text-shadow:0 0 10px rgba(0,229,255,0.6);position:relative;z-index:1}
.badge{font-size:10px;padding:2px 8px;border-radius:8px;font-weight:bold}
.badge-warning{background:#2a1800;color:#ffaa00;border:1px solid #ffaa00}
.badge-critical{background:#2a0010;color:#ff2255;border:1px solid #ff2255}
.badge-ok{background:#002a10;color:#00ff88;border:1px solid #00ff88}
/* Regular buttons — cyan pill */
.button{display:block;width:92%;margin:7px auto;padding:clamp(14px,2.8vw,18px);background:rgba(0,18,35,0.85);color:#00e5ff;text-decoration:none;border-radius:28px;text-align:center;font-size:clamp(12px,2.3vw,15px);font-family:'Orbitron',monospace;letter-spacing:0.12em;cursor:pointer;border:2px solid rgba(0,229,255,0.7);text-transform:uppercase;touch-action:manipulation;min-height:48px;box-shadow:0 0 14px rgba(0,229,255,0.25),inset 0 0 14px rgba(0,229,255,0.06)}
.button:hover,.button:active{box-shadow:0 0 24px rgba(0,229,255,0.55)}
/* Operator buttons — large pill neon bars: green / lime / pink */
.op-button{display:block;width:92%;margin:6px auto;padding:clamp(14px,2.8vw,18px);text-decoration:none;border-radius:28px;text-align:center;font-size:clamp(12px,2.3vw,14px);font-family:'Orbitron',monospace;letter-spacing:0.1em;cursor:pointer;touch-action:manipulation;min-height:52px;background:rgba(0,14,4,0.88);color:#00ff88;border:2px solid rgba(0,255,136,0.7);box-shadow:0 0 14px rgba(0,255,136,0.25),inset 0 0 12px rgba(0,255,136,0.05)}
.op-button-b{background:rgba(10,12,0,0.88);color:#aaff00;border-color:rgba(170,255,0,0.7);box-shadow:0 0 14px rgba(170,255,0,0.25),inset 0 0 12px rgba(170,255,0,0.05)}
.op-button-c{background:rgba(14,0,7,0.88);color:#ff44aa;border-color:rgba(255,68,170,0.7);box-shadow:0 0 14px rgba(255,68,170,0.25),inset 0 0 12px rgba(255,68,170,0.05)}
.op-button:hover,.op-button:active{filter:brightness(1.25)}
/* Grid data values */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-size:clamp(12px,2.2vw,14px);position:relative;z-index:1}
.grid2 .label{color:#3a6a8a;font-size:clamp(10px,1.8vw,12px)}.grid2 .value{color:#c8e8ff;font-family:'Orbitron',monospace;font-size:clamp(11px,2vw,13px)}
.advisory{font-size:clamp(10px,1.8vw,12px);color:#ffaa00;margin-top:8px;padding:6px 10px;background:rgba(40,18,0,0.7);border-radius:8px;border-left:2px solid #ffaa00}
.reason{font-size:clamp(10px,1.8vw,11px);color:#3a6a8a;margin-top:5px}
.refresh-note{text-align:center;font-size:9px;color:#0a1a2a;margin-bottom:4px;flex-shrink:0}
.footer{text-align:center;padding-top:4px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:6px}
.footer-demo{display:flex;flex-direction:column;align-items:center;gap:4px;margin-bottom:2px}
.footer-demo-label{font-size:clamp(9px,1.6vw,11px);color:#3a6a8a;letter-spacing:0.1em;font-weight:600}
.demo-section{border-top:1px solid rgba(0,229,255,0.12);margin-top:8px;padding-top:8px}
.demo-label{text-align:center;font-size:10px;color:#3a6a8a;margin-bottom:8px;letter-spacing:0.12em;font-weight:bold}
.demo-scenario-btn{display:inline-block;margin:5px;padding:10px 20px;background:rgba(0,18,35,0.85);color:#00e5ff;border:1px solid rgba(0,229,255,0.45);border-radius:20px;font-size:clamp(11px,2vw,13px);text-decoration:none;cursor:pointer}
.demo-scenario-btn:hover{background:rgba(0,35,60,0.9);box-shadow:0 0 12px rgba(0,229,255,0.3)}
.footer img{width:clamp(72px,14vw,96px);opacity:0.85;filter:drop-shadow(0 0 8px rgba(0,229,255,0.5)) drop-shadow(0 0 4px rgba(204,0,255,0.35));cursor:pointer;-webkit-tap-highlight-color:transparent}
.dev-section{border-top:2px solid rgba(0,229,255,0.3);margin-top:10px;padding-top:8px}
.dev-label{text-align:center;font-size:10px;color:#00e5ff;margin-bottom:8px;letter-spacing:0.15em;font-weight:bold;font-family:'Orbitron',monospace}
.dev-panel{background:rgba(2,0,10,0.95);border:1px solid rgba(0,229,255,0.2);border-radius:8px;padding:10px;margin-bottom:8px}
.dev-panel-title{font-size:clamp(9px,1.6vw,11px);color:#00e5ff;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;font-weight:bold;font-family:'Orbitron',monospace}
.dev-grid{display:grid;grid-template-columns:1fr 1fr;gap:3px 10px;font-size:clamp(10px,1.8vw,12px)}
.dev-grid .dk{color:#3a6a8a;font-size:clamp(9px,1.5vw,11px)}.dev-grid .dv{color:#c8e8ff;font-family:monospace}
.dev-memory{font-size:clamp(9px,1.5vw,11px);color:#3a6a8a;font-family:monospace;line-height:1.6}
.dev-memory span{color:#c8e8ff}
.dev-scenario-btn{display:inline-block;margin:4px;padding:6px 14px;background:rgba(0,18,35,0.85);color:#00e5ff;border:1px solid rgba(0,229,255,0.4);border-radius:16px;font-size:clamp(10px,1.8vw,12px);text-decoration:none;cursor:pointer;font-family:'Orbitron',monospace;letter-spacing:0.08em}
.dev-scenario-btn:hover{background:rgba(0,35,60,0.9);box-shadow:0 0 10px rgba(0,229,255,0.3)}
@media(max-width:400px){.button,.op-button{width:100%}}
.kb-search{width:100%;padding:10px 14px;background:rgba(2,0,10,0.95);border:1px solid rgba(0,229,255,0.3);border-radius:24px;color:#c8e8ff;font-size:clamp(12px,2.2vw,14px);outline:none;margin-bottom:10px;box-sizing:border-box;font-family:'Exo 2',sans-serif}
.kb-search:focus{border-color:rgba(0,229,255,0.7);box-shadow:0 0 10px rgba(0,229,255,0.2)}
.kb-search::placeholder{color:#2a4a6a}
.kb-case{background:rgba(2,0,10,0.95);border-radius:10px;padding:10px 12px;margin-bottom:6px;cursor:pointer;border:1px solid rgba(0,229,255,0.15);transition:border-color 0.2s;text-decoration:none;display:block}
.kb-case:hover{border-color:rgba(0,229,255,0.5);box-shadow:0 0 12px rgba(0,229,255,0.1)}
.kb-case-id{font-size:clamp(9px,1.5vw,10px);color:#3a6a8a;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:2px;font-family:'Orbitron',monospace}
.kb-case-title{font-size:clamp(12px,2.2vw,14px);color:#c8e8ff;font-weight:600;margin-bottom:5px}
.kb-case-snippet{font-size:clamp(10px,1.8vw,11px);color:#3a6a8a;margin-bottom:6px;line-height:1.5}
.kb-tags{display:flex;flex-wrap:wrap;gap:4px}
.kb-tag{font-size:clamp(9px,1.5vw,10px);padding:2px 8px;background:rgba(0,18,35,0.85);color:#00e5ff;border:1px solid rgba(0,229,255,0.3);border-radius:10px;font-family:'Orbitron',monospace;letter-spacing:0.05em}
.kb-empty{text-align:center;color:#2a4a6a;padding:20px;font-size:clamp(11px,2vw,13px)}
.kb-detail-section{margin-bottom:14px}
.kb-detail-label{font-size:clamp(9px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:5px;font-weight:600;font-family:'Orbitron',monospace}
.kb-detail-text{font-size:clamp(11px,2vw,13px);color:#c8e8ff;line-height:1.7}
.kb-detail-list{list-style:none;padding:0;margin:0}
.kb-detail-list li{font-size:clamp(11px,2vw,12px);color:#c8e8ff;padding:3px 0 3px 14px;position:relative;line-height:1.5}
.kb-detail-list li::before{content:"–";position:absolute;left:0;color:#00e5ff}
.kb-count{font-size:clamp(9px,1.6vw,10px);color:#3a6a8a;letter-spacing:0.1em;margin-bottom:10px;font-family:'Orbitron',monospace}
.kb-no-results{display:none}
#psych-overlay{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;opacity:0;background:radial-gradient(ellipse at center,rgba(0,229,255,0.3),rgba(204,0,255,0.2),transparent);transition:opacity 0.4s ease}
#psych-overlay.flash{animation:psych-flash 0.8s ease-out forwards}
</style>"""

SCRIPTS = """<script>
// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock(){
  var now=new Date();
  var h=String(now.getHours()).padStart(2,'0');
  var m=String(now.getMinutes()).padStart(2,'0');
  var s=String(now.getSeconds()).padStart(2,'0');
  var days=['SUN','MON','TUE','WED','THU','FRI','SAT'];
  var months=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  var el=document.getElementById('clock');
  var del=document.getElementById('clock-date');
  if(el) el.textContent=h+':'+m+':'+s;
  if(del) del.textContent=days[now.getDay()]+' '+String(now.getDate()).padStart(2,'0')+' '+months[now.getMonth()]+' '+now.getFullYear();
}
setInterval(updateClock,1000);

// ── UI Mode State ─────────────────────────────────────────────────────────────
// uiMode: 'normal' | 'wicked' | 'psychedelic'
var uiMode='normal';

window.onload=function(){
  updateClock();
  // Sync mode from server on load
  fetch('/api/state').then(function(r){return r.json();}).then(function(d){
    if(d.psychedelic) uiMode='psychedelic';
    else if(d.wicked) uiMode='wicked';
    else uiMode='normal';
  }).catch(function(){});
};

// ── Navigation helper — black cover then replace ──────────────────────────────
function navigateTo(url, delay){
  document.documentElement.style.background='#000';
  document.body.style.background='#000';
  var cover=document.createElement('div');
  cover.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:#000;z-index:99999;';
  document.body.appendChild(cover);
  setTimeout(function(){ window.location.replace(url); }, delay||200);
}

// ── EASTER EGG 1: WICKED MODE — 7 clicks on OKi logo ─────────────────────────
var _tapCount=0;
var _tapResetTimer=null;

function logoTap(){
  if(_wasHold){_wasHold=false;return;}

  // Visual tap feedback — brief glow pulse
  var img=document.getElementById('oki-logo-img');
  if(img){
    img.style.filter='drop-shadow(0 0 10px #00e5ff) drop-shadow(0 0 5px #fff)';
    setTimeout(function(){
      if(!_holdActive) img.style.filter='drop-shadow(0 0 4px rgba(31,111,181,0.5))';
      img.style.opacity='0.85';
    },120);
  }

  _tapCount++;

  // Reset tap counter after 3 seconds of inactivity
  clearTimeout(_tapResetTimer);
  _tapResetTimer=setTimeout(function(){ _tapCount=0; },3000);

  if(_tapCount>=7){
    _tapCount=0;
    clearTimeout(_tapResetTimer);
    if(uiMode==='wicked'){
      wickedDeactivate();
    } else {
      // If psychedelic is active, turn it off first then go wicked
      if(uiMode==='psychedelic'){
        fetch('/api/toggle-psychedelic').then(function(){ return fetch('/api/toggle-wicked'); }).then(function(){ navigateTo('/',250); });
      } else {
        wickedActivate();
      }
    }
  }
}

function wickedActivate(){
  uiMode='wicked';
  var overlay=document.getElementById('psych-overlay');
  if(overlay){overlay.style.background='radial-gradient(ellipse at center,rgba(0,229,255,0.4),transparent)';overlay.classList.add('flash');}
  fetch('/api/toggle-wicked').then(function(){
    navigateTo('/',250);
  });
}

function wickedDeactivate(){
  uiMode='normal';
  fetch('/api/toggle-wicked').then(function(){
    navigateTo('/',200);
  });
}

// ── EASTER EGG 2: PSYCHEDELIC MODE — 7 second press-and-hold on OKi logo ─────
var _holdTimer=null,_holdInterval=null,_holdStart=null,_wasHold=false,_holdActive=false;
var HOLD_DURATION=7000;   // 7s to activate psychedelic
var _holdThreshold=200;   // ms to distinguish hold from tap

function logoPress(e){
  _holdStart=Date.now();
  _wasHold=false;
  _holdActive=false;

  _holdTimer=setTimeout(function(){
    _wasHold=true;
    _holdActive=true;
    _tapCount=0;
    clearTimeout(_tapResetTimer);
    var ring=document.getElementById('ring-arc');
    var ringEl=document.getElementById('logo-ring');
    var img=document.getElementById('oki-logo-img');

    if(ringEl) ringEl.style.opacity='1';
    if(img) img.style.opacity='1';

    _holdInterval=setInterval(function(){
      var elapsed=Date.now()-_holdStart;
      var progress=Math.min(elapsed/HOLD_DURATION,1);
      if(ring) ring.style.strokeDashoffset=389.6*(1-progress);
      var glow=Math.round(progress*22)+4;
      if(img) img.style.filter='drop-shadow(0 0 '+glow+'px #ff00ff) drop-shadow(0 0 '+Math.round(glow/2)+'px #00d4ff)';
    },40);

    var remaining=HOLD_DURATION-_holdThreshold;
    _holdTimer=setTimeout(function(){
      clearInterval(_holdInterval);
      _holdInterval=null;
      _holdActive=false;
      if(uiMode==='psychedelic'){
        psychedelicDeactivate();
      } else {
        cinematicActivate();
      }
    },remaining);
  },_holdThreshold);
}

function logoRelease(){
  if(_holdInterval){
    clearTimeout(_holdTimer);
    clearInterval(_holdInterval);
    _holdTimer=null; _holdInterval=null; _holdActive=false;
    // Reset ring and logo
    var ring=document.getElementById('ring-arc');
    var ringEl=document.getElementById('logo-ring');
    var img=document.getElementById('oki-logo-img');
    if(ring) ring.style.strokeDashoffset='389.6';
    if(ringEl) setTimeout(function(){ringEl.style.opacity='0';},300);
    if(img){img.style.filter='drop-shadow(0 0 4px rgba(31,111,181,0.5))';img.style.opacity='0.85';}
  } else {
    clearTimeout(_holdTimer);
    _holdTimer=null;
  }
  _holdStart=null;
}

function cinematicActivate(){
  var wasWicked=(uiMode==='wicked');
  uiMode='psychedelic';
  document.documentElement.style.background='#000';
  document.body.style.background='#000';
  var cover=document.createElement('div');
  cover.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:#000;z-index:99999;';
  document.body.appendChild(cover);
  var overlay=document.getElementById('psych-overlay');
  if(overlay) overlay.classList.add('flash');
  var p1=wasWicked ? fetch('/api/toggle-wicked') : Promise.resolve();
  p1.then(function(){ return fetch('/api/toggle-psychedelic'); })
    .then(function(){ setTimeout(function(){ window.location.replace('/'); },600); });
}

function psychedelicDeactivate(){
  uiMode='normal';
  fetch('/api/toggle-psychedelic').then(function(){
    navigateTo('/',300);
  });
}

// ── okiToggle — for FOCUS/DEV/DEMO toggles (no full reload needed) ────────────
function okiToggle(input, overrideRoute){
  var route=overrideRoute||(input&&input.getAttribute('data-toggle-route'));
  if(!route) return;
  fetch(route).then(function(r){return r.json();}).then(function(d){
    return fetch('/api/content').then(function(r){return r.text();}).then(function(html){
      var c=document.querySelector('.content');
      if(c) c.innerHTML=html;
      return fetch('/api/header').then(function(r){return r.text();}).then(function(hhtml){
        var hdr=document.querySelector('.header');
        if(hdr) hdr.outerHTML=hhtml;
      });
    });
  }).catch(function(e){
    if(input) window.location.href=route.replace('/api/','/')+'-legacy';
  });
}
</script>"""

# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def led_classes_system(health, severity):
    if severity == "CRITICAL" or health < 50:
        return ("led led-off", "led led-off", "led led-red")
    elif severity == "WARNING" or health < 75:
        return ("led led-off", "led led-amber", "led led-off")
    else:
        return ("led led-green", "led led-off", "led led-off")

def led_classes_battery(soc):
    if soc < 20:   return ("led led-off", "led led-off", "led led-red")
    elif soc < 50: return ("led led-off", "led led-amber", "led led-off")
    else:          return ("led led-green", "led led-off", "led led-off")

def render_led_strip(g, a, r, prefix=""):
    if prefix:
        return (f'<div class="led-strip">'
                f'<div id="{prefix}0" class="{g}"></div>'
                f'<div id="{prefix}1" class="{a}"></div>'
                f'<div id="{prefix}2" class="{r}"></div>'
                f'</div>')
    return f'<div class="led-strip"><div class="{g}"></div><div class="{a}"></div><div class="{r}"></div></div>'

def render_toggle(label, checked, route):
    flag = "checked" if checked else ""
    return (f'<div class="toggle-box"><span class="toggle-label">{label}</span>'
            f'<label class="switch"><input type="checkbox" {flag} '
            f'data-toggle-route="/api/{route}" onchange="okiToggle(this)">'
            f'<span class="slider"></span></label></div>')

def render_panel(title, content, badge=None):
    badge_html = ""
    if badge:
        css = "badge-warning" if badge == "WARNING" else "badge-critical" if badge == "CRITICAL" else "badge-ok"
        badge_html = f'<span class="badge {css}">{badge}</span>'
    return f'<div class="panel"><div class="panel-title">{title}{badge_html}</div>{content}</div>'

def render_button(label, href):
    return f'<a class="button" href="{href}">{label}</a>'

def render_op_button(label, href):
    return f'<a class="op-button" href="{href}">{label}</a>'

def render_bar(pct, color):
    pct = max(0, min(100, pct))
    return f'<div class="bar-container"><div class="bar-fill bar-{color}" style="width:{pct}%"></div></div>'

def render_header():
    state    = get_state()
    dev_mode = state["System"].get("DevMode", False)
    health   = safe_int(state["System"].get("SystemHealth"), 0)
    severity = state["System"].get("Severity")
    soc      = safe_int(state.get("Battery", {}).get("SoC"), 0)
    sg, sa, sr = led_classes_system(health, severity)
    bg, ba, br = led_classes_battery(soc)
    return f"""<div class="header">
  <div class="header-left">{render_led_strip(sg,sa,sr,"led-s")}{render_toggle("FOCUS",FOCUS_MODE,"toggle-focus")}</div>
  <div class="title-block">
    <div class="title-oki">OKi</div>
    <div class="title-sub">Onboard Knowledge Interface</div>
    <div class="boat-name-center">&#9875; Casa Azul</div>
  </div>
  <div class="header-right">{render_led_strip(bg,ba,br,"led-b")}{render_toggle("DEV",dev_mode,"toggle-dev")}<div class="clock" id="clock">--:--:--</div><div class="clock-date" id="clock-date">--- -- --- ----</div></div>
</div>"""

def render_footer():
    demo_checked = "checked" if DEMO_MODE else ""
    toggle = (f'<label class="switch"><input type="checkbox" {demo_checked} '
              f'data-toggle-route="/api/toggle-demo" onchange="okiToggle(this)">'
              f'<span class="slider"></span></label>')
    return (
        '<div id="psych-overlay"></div>'
        '<div class="footer">'
        '<div class="footer-demo">'
        '<div class="footer-demo-label">DEMO</div>'
        + toggle +
        '</div>'
        # Logo — 7 taps = wicked (onclick), 7s hold = psychedelic (onmousedown/touch)
        '<div id="logo-wrap" style="position:relative;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none;"'
        ' onmousedown="logoPress(event)" onmouseup="logoRelease()" onmouseleave="logoRelease()" onclick="logoTap()"'
        ' ontouchstart="logoPress(event)" ontouchend="logoRelease();logoTap();" ontouchcancel="logoRelease()">'
        # Progress ring SVG
        '<svg id="logo-ring" width="140" height="140" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;opacity:0;transition:opacity 0.3s;">'
        '<circle cx="70" cy="70" r="62" fill="none" stroke-width="3" stroke="url(#ringGrad)" stroke-linecap="round"'
        ' stroke-dasharray="389.6" stroke-dashoffset="389.6" id="ring-arc"'
        ' style="transform:rotate(-90deg);transform-origin:70px 70px;transition:stroke-dashoffset 0.05s linear"/>'
        '<defs><linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
        '<stop offset="0%" stop-color="#ff00ff"/>'
        '<stop offset="50%" stop-color="#00d4ff"/>'
        '<stop offset="100%" stop-color="#00ff88"/>'
        '</linearGradient></defs>'
        '</svg>'
        '<img id="oki-logo-img" src="/static/oki_logo.png" alt="OKi"'
        ' style="width:clamp(120px,20vw,144px);opacity:0.85;display:block;transition:filter 0.3s,opacity 0.3s;filter:drop-shadow(0 0 4px rgba(31,111,181,0.5));">'
        '</div>'
        '</div>'
    )

# ══════════════════════════════════════════════════════════════════════════════
# DEV BLOCK — raw state data
# ══════════════════════════════════════════════════════════════════════════════

def render_dev_block(state: dict) -> str:
    """
    Full raw data block shown when DEV mode is ON.
    Sections:
      1. Raw Vessel Data    — Battery, Solar, AC, Generator, Fuel, Derived
      2. System Intelligence — SituationType, DecisionWindow, Health, Diagnostic
      3. Memory             — last 10 snapshots
      4. Scenarios          — quick-load buttons
    """

    def row(key, val):
        return f'<div class="dk">{key}</div><div class="dv">{val}</div>'

    def dev_panel(title, inner):
        return (
            f'<div class="dev-panel">'
            f'<div class="dev-panel-title">{title}</div>'
            f'{inner}'
            f'</div>'
        )

    # ── 1. Raw Vessel Data ────────────────────────────────────────────────────
    bat  = state.get("Battery", {})
    sol  = state.get("Solar", {})
    ac   = state.get("AC", {})
    gen  = state.get("Generator", {})
    fuel = state.get("Fuel", {})
    der  = state.get("Derived", {})
    comm = state.get("Communication", {})

    vessel_html = '<div class="dev-grid">'
    vessel_html += row("BAT SoC",      f'<span id="dv-bat-soc">{v(bat.get("SoC"), "%")}</span>')
    vessel_html += row("BAT Voltage",  f'<span id="dv-bat-v">{v(bat.get("Voltage"), " V")}</span>')
    vessel_html += row("BAT Current",  f'<span id="dv-bat-a">{v(bat.get("Current"), " A")}</span>')
    vessel_html += row("BAT Temp",     f'<span id="dv-bat-t">{v(bat.get("Temperature"), " °C")}</span>')
    vessel_html += row("DC Power",     f'<span id="dv-dc-power">{v(der.get("DCPower"), " W")}</span>')
    vessel_html += row("Energy Mode",  f'<span id="dv-energy-mode">{der.get("EnergyMode") or "—"}</span>')
    vessel_html += row("Solar Power",  f'<span id="dv-sol-power">{v(sol.get("Power"), " W")}</span>')
    vessel_html += row("Solar State",  f'<span id="dv-sol-state">{sol.get("State") or "—"}</span>')
    vessel_html += row("Solar V",      f'<span id="dv-sol-v">{v(sol.get("Voltage"), " V")}</span>')
    vessel_html += row("AC Voltage",   f'<span id="dv-ac-v">{v(ac.get("GridVoltage"), " V")}</span>')
    vessel_html += row("AC Power",     f'<span id="dv-ac-p">{v(ac.get("GridPower"), " W")}</span>')
    vessel_html += row("AC State",     f'<span id="dv-ac-state">{ac.get("State") or "—"}</span>')
    vessel_html += row("Shore",        f'<span id="dv-ac-shore">{str(ac.get("Shore") or "—")}</span>')
    vessel_html += row("Shelly",       f'<span id="dv-ac-shelly">{ac.get("ShellyStatus") or "—"}</span>')
    vessel_html += row("Generator",    f'<span id="dv-gen-run">{"ON" if gen.get("Running") else "OFF"}</span>')
    vessel_html += row("Gen Expected", f'<span id="dv-gen-exp">{str(gen.get("Expected", "—"))}</span>')
    vessel_html += row("Gen Error",    f'<span id="dv-gen-err">{gen.get("ErrorCode") or "none"}</span>')
    vessel_html += row("Fuel Level",   f'<span id="dv-fuel-lvl">{v(fuel.get("LevelPercent"), "%")}</span>')
    vessel_html += row("Fuel State",   f'<span id="dv-fuel-state">{fuel.get("State") or "—"}</span>')
    vessel_html += row("Fuel Sensor",  f'<span id="dv-fuel-sensor">{"OK" if fuel.get("SensorReliable") else "unreliable"}</span>')
    vessel_html += row("CAN Healthy",  f'<span id="dv-can">{str(comm.get("CANHealthy") or "—")}</span>')
    vessel_html += '</div>'

    if fuel.get("Inconsistency"):
        vessel_html += f'<div id="dv-fuel-inc" class="reason" style="margin-top:6px;">&#9888; {fuel["Inconsistency"]}</div>'
    else:
        vessel_html += '<div id="dv-fuel-inc" class="reason" style="display:none;"></div>'

    # ── 2. System Intelligence ────────────────────────────────────────────────
    sys    = state.get("System", {})
    energy = state.get("Energy", {})
    diag   = state.get("Diagnostic", {})
    vessel = state.get("VesselState", {})
    cats   = sys.get("HealthCategories") or {}

    intel_html = '<div class="dev-grid">'
    intel_html += row("Situation",      f'<span id="dv-situation">{sys.get("SituationType") or "—"}</span>')
    intel_html += row("Decision Win.",  f'<span id="dv-decwin">{sys.get("DecisionWindow") or "—"}</span>')
    intel_html += row("System Mode",    f'<span id="dv-mode">{sys.get("Mode") or "—"}</span>')
    intel_html += row("Severity",       f'<span id="dv-sev">{sys.get("Severity") or "none"}</span>')
    intel_html += row("Health Score",   f'<span id="dv-health">{sys.get("SystemHealth") or "—"}%</span>')
    intel_html += row("Cat A (Integrity)", f'<span id="dv-catA">-{cats.get("A_SystemIntegrity", 0)}pt</span>')
    intel_html += row("Cat B (Energy)",    f'<span id="dv-catB">-{cats.get("B_EnergyBattery", 0)}pt</span>')
    intel_html += row("Cat C (Stress)",    f'<span id="dv-catC">-{cats.get("C_OperationalStress", 0)}pt</span>')
    intel_html += row("Cat F (Power)",     f'<span id="dv-catF">-{cats.get("F_PowerContinuity", 0)}pt</span>')
    intel_html += row("Time→Critical",  f'<span id="dv-ttc">{v(energy.get("TimeToCriticalHours"), " h")}</span>')
    intel_html += row("Time→Shutdown",  f'<span id="dv-tts">{v(energy.get("TimeToShutdownHours"), " h")}</span>')
    intel_html += row("Discharge Rate", f'<span id="dv-drate">{v(energy.get("DischargeRate"), " %/h")}</span>')
    intel_html += row("Vessel Move",    f'<span id="dv-vmove">{vessel.get("MovementState") or "—"}</span>')
    intel_html += row("Location",       f'<span id="dv-loc">{vessel.get("LocationContext") or "—"}</span>')
    intel_html += row("Survival Mode",  f'<span id="dv-surv">{"YES" if vessel.get("SurvivalMode") else "no"}</span>')
    intel_html += row("Diag Step",      f'<span id="dv-dstep">{diag.get("Step") or "—"}</span>')
    intel_html += row("Diag State",     f'<span id="dv-dstate">{diag.get("DiagnosticState") or "—"}</span>')
    intel_html += row("Diag Primary",   f'<span id="dv-dprim">{(diag.get("PrimaryState") or "—")[:30]}</span>')
    intel_html += row("Active Q",       f'<span id="dv-dactq">{"yes" if diag.get("ActiveQuestion") else "none"}</span>')
    intel_html += '</div>'

    penalties = sys.get("HealthPenalties") or []
    if penalties:
        intel_html += '<div id="dv-penalties" style="margin-top:6px;">'
        for p in penalties[:5]:
            intel_html += f'<div class="reason">&#9888; {p}</div>'
        intel_html += '</div>'
    else:
        intel_html += '<div id="dv-penalties"></div>'

    # ── 3. Memory — last 10 snapshots ─────────────────────────────────────────
    memory = state.get("Memory", [])
    last10 = memory[-10:] if memory else []

    if last10:
        mem_html = '<div class="dev-memory" id="dv-memory-rows">'
        for entry in reversed(last10):
            ts    = str(entry.get("timestamp", ""))[:19].replace("T", " ")
            mode  = entry.get("Mode") or "—"
            hlth  = entry.get("Health") or "—"
            sev   = entry.get("Severity") or "ok"
            mem_html += f'<div>{ts} &nbsp; <span>{mode}</span> &nbsp; health:<span>{hlth}%</span> &nbsp; <span>{sev}</span></div>'
        mem_html += '</div>'
    else:
        mem_html = '<div class="dev-memory" id="dv-memory-rows">No memory snapshots yet.</div>'

    # ── 4. Scenarios ──────────────────────────────────────────────────────────
    scenarios_html = (
        '<div style="text-align:center;padding-top:4px;">'
        '<a class="dev-scenario-btn" href="/scenario/casa">Casa Azul</a>'
        '<a class="dev-scenario-btn" href="/scenario/anchor">Anchor</a>'
        '<a class="dev-scenario-btn" href="/scenario/drain">Drain</a>'
        '<a class="dev-scenario-btn" href="/scenario/generator_failure">Gen Failure</a>'
        '</div>'
    )

    # ── Assemble ──────────────────────────────────────────────────────────────
    return (
        '<div id="dev-section" class="dev-section">'
        '<div class="dev-label">&#128295; DEV — RAW STATE DATA</div>'
        + dev_panel("&#9889; Vessel Data", vessel_html)
        + dev_panel("&#129302; System Intelligence", intel_html)
        + dev_panel("&#128257; Memory — Last 10 Snapshots", mem_html)
        + dev_panel("&#127918; Load Scenario", scenarios_html)
        + '</div>'
    )



# ══════════════════════════════════════════════════════════════════════════════
# DEMO BLOCK — scenario loader
# ══════════════════════════════════════════════════════════════════════════════

def render_demo_block() -> str:
    """Shown when DEMO mode is ON. Centered scenario buttons."""
    return (
        '<div class="demo-section">'
        '<div class="demo-label">&#127918; DEMO — Load Scenario</div>'
        '<div style="text-align:center;">'
        '<a class="demo-scenario-btn" href="/scenario/casa">&#128211; Casa Azul</a>'
        '<a class="demo-scenario-btn" href="/scenario/anchor">&#9875; Anchor</a>'
        '<a class="demo-scenario-btn" href="/scenario/drain">&#9889; Suspicious Drain</a>'
        '<a class="demo-scenario-btn" href="/scenario/generator_failure">&#128268; Generator Failure</a>'
        '</div>'
        '</div>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE VIEWS
# ══════════════════════════════════════════════════════════════════════════════

def render_supervisory_view(state):
    content  = ""
    dev_mode = state["System"].get("DevMode", False)
    operator = state["Operator"]

    # Silence rule — only show question when attention engine says not silent
    attention        = state.get("Attention", {})
    is_silent        = attention.get("Silence", False)
    has_active_q     = operator.get("InteractionState") == "AwaitingResponse"

    if has_active_q and not is_silent:
        q  = f"<div id='question-text' style='font-size:clamp(12px,2.5vw,14px);margin-bottom:8px;color:#cad8e3;'><b>{operator['ActiveQuestionText']}</b></div>"
        q += f'<a id="q-opt-a" class="op-button" href="/answer/A">{operator["OptionA"]}</a>'
        q += f'<a id="q-opt-b" class="op-button op-button-b" href="/answer/B">{operator["OptionB"]}</a>'
        q += f'<a id="q-opt-c" class="op-button op-button-c" href="/answer/C">{operator["OptionC"]}</a>'
        content += f'<div id="question-panel"><div class="panel"><div class="panel-title">Operator Confirmation Required</div>{q}</div></div>'
    else:
        content += '<div id="question-panel" style="display:none;"><div class="panel"><div class="panel-title">Operator Confirmation Required</div><div id="question-text"></div><a id="q-opt-a" class="op-button" href="/answer/A"></a><a id="q-opt-b" class="op-button op-button-b" href="/answer/B"></a><a id="q-opt-c" class="op-button op-button-c" href="/answer/C"></a></div></div>'

    battery = state.get("Battery", {})
    derived = state.get("Derived", {})
    soc     = safe_int(battery.get("SoC"), 0)
    voltage = safe_float(battery.get("Voltage"))
    current = safe_float(battery.get("Current"))
    power   = safe_float(derived.get("DCPower"))
    mode    = derived.get("EnergyMode") or "—"

    battery_html = f"""<div class="soc-display"><div id="soc-number" class="{soc_css_class(soc)}">{soc}%</div><div class="soc-label">State of Charge</div></div>
<div class="soc-bar-outer"><div id="soc-bar-fill" class="soc-bar-fill {('soc-bar-discharging' if 'DISCHARG' in (mode or '').upper() else 'soc-bar-charging' if 'CHARG' in (mode or '').upper() else '')}" style="width:{soc}%; background:{('#ff5252' if soc < 15 else '#ffb300' if soc < 30 else '#4caf50')};"></div></div>
<div class="grid2" style="margin-top:10px;">
  <div class="label">Voltage</div><div id="bat-voltage" class="value">{voltage} V</div>
  <div class="label">Current</div><div id="bat-current" class="value">{current} A</div>
  <div class="label">Power</div><div id="bat-power" class="value">{power} W</div>
  <div class="label">Mode</div><div id="bat-mode" class="value">{mode}</div>
</div>"""
    content += render_panel("Battery", battery_html)

    rec = state["System"].get("Recommendation")
    if rec:
        reason   = state["System"].get("RecommendationReason")
        advisory = state["System"].get("Advisory")
        advisory_case = state["System"].get("AdvisoryCase")
        r = f"<div style='font-size:clamp(12px,2vw,13px);'>{rec}</div>"
        if reason:   r += f'<div class="reason">Reason: {reason}</div>'
        if advisory:
            if advisory_case:
                r += f'<div class="advisory">&#128203; {advisory} &nbsp;<a href="/knowledge/{advisory_case}" style="color:#ffb300;text-decoration:underline;font-size:clamp(10px,1.8vw,11px);">View case →</a></div>'
            else:
                r += f'<div class="advisory">&#128203; {advisory}</div>'
        content += f'<div id="rec-panel"><div class="panel"><div class="panel-title">Recommendation</div><div id="rec-inner">{r}</div></div></div>'
    else:
        content += '<div id="rec-panel" style="display:none;"><div class="panel"><div class="panel-title">Recommendation</div><div id="rec-inner"></div></div></div>'

    health   = safe_int(state["System"].get("SystemHealth"), 0)
    severity = state["System"].get("Severity")
    badge_html = ""
    if severity:
        css = "badge-warning" if severity == "WARNING" else "badge-critical" if severity == "CRITICAL" else "badge-ok"
        badge_html = f'<span id="health-badge" class="badge {css}">{severity}</span>'
    else:
        badge_html = '<span id="health-badge" class="badge badge-ok" style="display:none;"></span>'
    h = (f'<div id="health-number" style="font-size:clamp(20px,4vw,28px);font-weight:bold;color:#cad8e3;">{health}%</div>'
         f'<div class="bar-container"><div id="health-bar-fill" class="bar-fill bar-{bar_color_for_health(health)}" style="width:{health}%"></div></div>')
    issues = state["System"].get("Inconsistency")
    if issues:
        h += f'<div id="health-issues" class="reason" style="margin-top:5px;">&#9888; {" | ".join(issues)}</div>'
    else:
        h += '<div id="health-issues" style="display:none;"></div>'
    content += f'<div class="panel"><div class="panel-title">System Health{badge_html}</div>{h}</div>'

    care        = state["Care"]
    care_score  = safe_int(care.get("CareScore"), 0)
    care_color  = "#4caf50" if care_score >= 75 else "#ffb300" if care_score >= 50 else "#ff5252"
    c = f"""<div style="display:flex;justify-content:space-between;align-items:center;">
  <div class="label">Care Score</div>
  <div id="care-index" class="value" style="color:{care_color};font-weight:bold;">{care_score}%</div>
</div><div class="bar-container" style="margin-top:6px;"><div id="care-bar-fill" class="bar-fill bar-blue" style="width:{care_score}%"></div></div>"""
    content += render_panel("OKi Care", c)
    content += render_button("CARE", "/care")
    content += render_button("KNOWLEDGE", "/knowledge")

    # DEMO block — scenario loader
    if DEMO_MODE:
        content += render_demo_block()

    # DEV block — full raw data
    if dev_mode:
        content += render_dev_block(state)

    return content

def render_focus_view(state):
    battery = state.get("Battery", {})
    derived = state.get("Derived", {})
    system  = state.get("System", {})
    soc     = safe_int(battery.get("SoC"), 0)
    voltage = safe_float(battery.get("Voltage"))
    current = safe_float(battery.get("Current"))
    power   = safe_float(derived.get("DCPower"))
    mode    = derived.get("EnergyMode") or "—"
    health  = safe_int(system.get("SystemHealth"), 0)

    mode_upper  = (mode or "").upper()
    is_charging = "CHARG" in mode_upper
    is_discharging = "DISCHARG" in mode_upper
    bar_anim    = "soc-bar-discharging" if is_discharging else "soc-bar-charging" if is_charging else ""
    bar_color   = "#ff5252" if soc < 15 else "#ffb300" if soc < 30 else "#4caf50"

    soc_html = f"""<div class="soc-display"><div id="soc-number" class="{soc_css_class(soc)}">{soc}%</div><div class="soc-label">State of Charge</div></div>
<div class="soc-bar-outer"><div id="soc-bar-fill" class="soc-bar-fill {bar_anim}" style="width:{soc}%; background:{bar_color};"></div></div>
<div class="grid2" style="margin-top:10px;">
  <div class="label">Voltage</div><div id="bat-voltage" class="value">{voltage} V</div>
  <div class="label">Current</div><div id="bat-current" class="value">{current} A</div>
  <div class="label">Power</div><div id="bat-power" class="value">{power} W</div>
  <div class="label">Mode</div><div id="bat-mode" class="value">{mode}</div>
</div>"""

    health_html = (f'<div id="health-number" style="font-size:clamp(20px,4vw,28px);font-weight:bold;color:#cad8e3;">{health}%</div>'
                   f'<div class="bar-container"><div id="health-bar-fill" class="bar-fill bar-{bar_color_for_health(health)}" style="width:{health}%"></div></div>')

    rec     = system.get("Recommendation", "")
    content = render_panel("Battery", soc_html)
    content += render_panel("System Health", health_html)
    if rec:
        content += f'<div id="rec-panel"><div class="panel"><div class="panel-title">Status</div><div id="rec-inner"><div style="font-size:clamp(12px,2vw,13px);">{rec}</div></div></div></div>'
    else:
        content += '<div id="rec-panel" style="display:none;"><div class="panel"><div class="panel-title">Status</div><div id="rec-inner"></div></div></div>'
    # DEMO block
    if DEMO_MODE:
        content += render_demo_block()

    # DEV block visible in focus mode too
    if system.get("DevMode", False):
        content += render_dev_block(state)

    return content

def render_care_page():
    from datetime import datetime, timezone
    state      = get_state()
    care       = state.get("Care", {})
    care_score = safe_int(care.get("CareScore"), 0)
    cooldowns  = care.get("TaskCooldowns") or {}
    now_ts     = datetime.now(timezone.utc).timestamp()
    cooldown_s = 24 * 3600

    # Care score color
    if care_score >= 75:
        score_color = "#4caf50"
    elif care_score >= 50:
        score_color = "#ffb300"
    else:
        score_color = "#ff5252"

    bar_color = "blue" if care_score >= 75 else "amber" if care_score >= 50 else "red"

    # Score summary panel
    summary = f"""<div style="text-align:center;padding:10px 0 6px 0;">
  <div style="font-size:clamp(32px,7vw,48px);font-weight:bold;color:{score_color};">{care_score}%</div>
  <div style="font-size:10px;color:#6a8aa0;letter-spacing:0.2em;text-transform:uppercase;margin-top:2px;">CARE SCORE</div>
</div>{render_bar(care_score, bar_color)}
<div class="reason" style="margin-top:10px;">
  Reflects how well the vessel is maintained. The system reads health, alerts and failures automatically.
  Log manual tasks below to raise your score.
</div>"""

    panel = render_panel("OKi Care", summary)

    # Task list
    tasks_html = ""
    for task_id, label, description, points in CARE_TASKS:
        last_done = cooldowns.get(task_id)
        on_cooldown = bool(last_done and (now_ts - float(last_done)) < cooldown_s)

        if on_cooldown:
            hours_left = int((cooldown_s - (now_ts - float(last_done))) / 3600) + 1
            tasks_html += f"""
<div style="background:#1a1d23;border-radius:10px;padding:12px 14px;margin-bottom:6px;opacity:0.5;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="color:#cad8e3;font-size:14px;">{label}</div>
      <div style="color:#6a8aa0;font-size:11px;margin-top:3px;">{description}</div>
    </div>
    <div style="text-align:right;flex-shrink:0;margin-left:12px;">
      <div style="color:#6a8aa0;font-size:11px;">+{points} pts</div>
      <div style="color:#6a8aa0;font-size:10px;margin-top:2px;">in {hours_left}h</div>
    </div>
  </div>
</div>"""
        else:
            tasks_html += f"""
<a href="/care/task/{task_id}" style="display:block;text-decoration:none;margin-bottom:6px;">
  <div style="background:#1a2e1a;border:1px solid #2a4a2a;border-radius:10px;padding:12px 14px;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background='#243824'" onmouseout="this.style.background='#1a2e1a'">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <div style="color:#4caf50;font-size:14px;">{label}</div>
        <div style="color:#6a8aa0;font-size:11px;margin-top:3px;">{description}</div>
      </div>
      <div style="text-align:right;flex-shrink:0;margin-left:12px;">
        <div style="color:#4caf50;font-size:13px;font-weight:bold;">+{points}</div>
        <div style="color:#6a8aa0;font-size:10px;">points</div>
      </div>
    </div>
  </div>
</a>"""

    panel += f'<div style="margin-top:8px;"><div style="color:#9aa8b5;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">Log a care task</div>{tasks_html}</div>'
    panel += render_button("← Back", "/")
    return panel

def _case_system_group(case_id: str) -> str:
    """Derive a human-readable system group from case_id prefix."""
    prefix = case_id.split("-")[0].upper() if "-" in case_id else case_id[:3].upper()
    mapping = {
        "BAT": "Battery", "SOL": "Solar", "GEN": "Generator", "AC": "AC Power",
        "FUEL": "Fuel", "CAN": "CAN Bus", "SYS": "System", "ENG": "Engine",
        "INV": "Inverter", "CHG": "Charger", "VES": "Vessel",
        "EVO": "Propulsion", "MOT": "Propulsion", "TRQ": "Propulsion",
        "NET": "Network", "NAV": "Navigation",
    }
    return mapping.get(prefix, "General")

def render_knowledge_page():
    cases = list(CASE_LIBRARY.cases.values()) if hasattr(CASE_LIBRARY, 'cases') else []
    total = len(cases)

    if not cases:
        content = "<div class='kb-empty'>No cases loaded yet.<br><span style='font-size:11px;'>Add JSON files to the cases/ directory.</span></div>"
        return render_panel("OKi Knowledge Base", content) + render_button("← Back", "/")

    # Build case cards — all rendered in HTML, JS handles filtering
    cards_html = ""
    for case in cases:
        case_id    = getattr(case, "case_id",    "?")
        title      = getattr(case, "title",      "") or case_id
        root_cause = getattr(case, "root_cause", "") or ""
        symptoms   = getattr(case, "symptoms",   []) or []
        conditions = getattr(case, "conditions", []) or []
        actions    = getattr(case, "actions",    []) or []
        solution   = getattr(case, "solution",   "") or ""
        snippet    = (root_cause[:100] + "…") if len(root_cause) > 100 else root_cause
        group      = _case_system_group(case_id)

        tags_html = "".join(
            f'<span class="kb-tag">{s}</span>'
            for s in (symptoms[:4])
        )
        if tags_html:
            tags_html = f'<div class="kb-tags">{tags_html}</div>'

        # data-search attribute enables JS filtering without re-rendering
        # Includes all fields: title, root_cause, solution, symptoms, conditions, actions
        searchable = " ".join([
            case_id, title, root_cause, solution,
            " ".join(symptoms), " ".join(conditions), " ".join(actions)
        ]).lower()
        cards_html += (
            f'<a class="kb-case" href="/knowledge/{case_id}" data-search="{searchable}">'
            f'<div class="kb-case-id">{group} · {case_id}</div>'
            f'<div class="kb-case-title">{title}</div>'
            f'<div class="kb-case-snippet">{snippet}</div>'
            f'{tags_html}'
            f'</a>'
        )

    search_js = """<script>
(function(){
  var inp=document.getElementById('kb-search-input');
  var cards=document.querySelectorAll('.kb-case');
  var noRes=document.getElementById('kb-no-results');
  if(!inp) return;
  inp.addEventListener('input',function(){
    var q=inp.value.trim().toLowerCase();
    var tokens=q.split(/\s+/).filter(function(t){return t.length>0;});
    var visible=0;
    cards.forEach(function(c){
      var text=c.getAttribute('data-search');
      var match=!q||tokens.every(function(t){return text.indexOf(t)!==-1;});
      c.style.display=match?'':'none';
      if(match) visible++;
    });
    if(noRes) noRes.style.display=(visible===0&&q)?'block':'none';
  });
})();
</script>"""

    content = (
        f'<div class="kb-count">{total} case{"s" if total != 1 else ""} in knowledge base</div>'
        f'<input id="kb-search-input" class="kb-search" type="text" placeholder="Search by symptom, system, keyword…" autocomplete="off">'
        f'<div id="kb-no-results" class="kb-empty kb-no-results">No cases match your search.</div>'
        + cards_html
        + search_js
    )

    panel  = render_panel("OKi Knowledge Base", content)
    panel += render_button("← Back", "/")
    return panel


def render_knowledge_detail(case_id: str):
    case = CASE_LIBRARY.get_case(case_id) if hasattr(CASE_LIBRARY, 'get_case') else None

    if not case:
        content = f"<div class='kb-empty'>Case <b>{case_id}</b> not found.</div>"
        panel   = render_panel("Case Not Found", content)
        panel  += render_button("← Knowledge Base", "/knowledge")
        return panel

    title      = getattr(case, "title",      "") or case_id
    root_cause = getattr(case, "root_cause", "") or ""
    solution   = getattr(case, "solution",   "") or ""
    symptoms   = getattr(case, "symptoms",   []) or []
    conditions = getattr(case, "conditions", []) or []
    actions    = getattr(case, "actions",    []) or []
    group      = _case_system_group(case_id)

    def detail_section(label, text):
        if not text: return ""
        return (f'<div class="kb-detail-section">'
                f'<div class="kb-detail-label">{label}</div>'
                f'<div class="kb-detail-text">{text}</div>'
                f'</div>')

    def detail_list(label, items):
        if not items: return ""
        lis = "".join(f"<li>{item}</li>" for item in items)
        return (f'<div class="kb-detail-section">'
                f'<div class="kb-detail-label">{label}</div>'
                f'<ul class="kb-detail-list">{lis}</ul>'
                f'</div>')

    def symptom_tags(items):
        if not items: return ""
        tags = "".join(f'<span class="kb-tag">{s}</span>' for s in items)
        return (f'<div class="kb-detail-section">'
                f'<div class="kb-detail-label">Symptoms</div>'
                f'<div class="kb-tags" style="margin-top:2px;">{tags}</div>'
                f'</div>')

    content  = f'<div class="kb-count">{group} · {case_id}</div>'
    content += detail_section("Root Cause", root_cause)
    content += symptom_tags(symptoms)
    content += detail_list("Conditions", conditions)
    content += detail_section("Solution", solution)
    content += detail_list("Actions", actions)

    panel  = render_panel(title, content)
    panel += render_button("← Knowledge Base", "/knowledge")
    return panel

def render_layout(content, auto_refresh=True):
    refresh_js = """<script>
(function(){
  function el(id){return document.getElementById(id);}
  function setClass(id,cls){var e=el(id);if(e)e.className=cls;}
  function setHTML(id,h){var e=el(id);if(e)e.innerHTML=h;}
  function setText(id,t){var e=el(id);if(e)e.textContent=t;}
  function show(id,vis){var e=el(id);if(e)e.style.display=vis?'':'none';}

  function applyState(d){
    // LEDs
    var sl=d.leds.sys, bl=d.leds.bat;
    setClass('led-s0',sl[0]); setClass('led-s1',sl[1]); setClass('led-s2',sl[2]);
    setClass('led-b0',bl[0]); setClass('led-b1',bl[1]); setClass('led-b2',bl[2]);

    // SoC number + label
    var socEl=el('soc-number');
    if(socEl){socEl.textContent=d.soc+'%'; socEl.className='soc-number '+d.socCss;}

    // SoC bar
    var fill=el('soc-bar-fill');
    if(fill){
      fill.style.width=d.soc+'%';
      fill.style.background=d.barColor;
      fill.className='soc-bar-fill'+(d.barAnim?' '+d.barAnim:'');
    }

    // Battery grid
    setText('bat-voltage', d.voltage+' V');
    setText('bat-current', d.current+' A');
    setText('bat-power',   d.power+' W');
    setText('bat-mode',    d.mode);

    // Recommendation panel
    var recPanel=el('rec-panel');
    if(recPanel){
      if(d.rec){
        var rh='<div style="font-size:clamp(12px,2vw,13px);">'+d.rec+'</div>';
        if(d.recReason) rh+='<div class="reason">Reason: '+d.recReason+'</div>';
        if(d.advisory){
          rh+='<div class="advisory">&#128203; '+d.advisory;
          if(d.advisoryCase) rh+=' &nbsp;<a href="/knowledge/'+d.advisoryCase+'" style="color:#ffb300;text-decoration:underline;font-size:clamp(10px,1.8vw,11px);">View case \u2192</a>';
          rh+='</div>';
        }
        setHTML('rec-inner',rh);
        recPanel.style.display='';
      } else {
        recPanel.style.display='none';
      }
    }

    // System health
    var hEl=el('health-number');
    if(hEl) hEl.textContent=d.health+'%';
    var hBar=el('health-bar-fill');
    if(hBar){hBar.style.width=d.health+'%'; hBar.className='bar-fill bar-'+d.healthColor;}
    var hBadge=el('health-badge');
    if(hBadge){
      if(d.severity){
        var css=d.severity==='WARNING'?'badge badge-warning':d.severity==='CRITICAL'?'badge badge-critical':'badge badge-ok';
        hBadge.className=css; hBadge.textContent=d.severity; hBadge.style.display='';
      } else { hBadge.style.display='none'; }
    }
    var issEl=el('health-issues');
    if(issEl){
      if(d.issues&&d.issues.length){
        issEl.innerHTML='<div class="reason" style="margin-top:5px;">&#9888; '+d.issues.join(' | ')+'</div>';
        issEl.style.display='';
      } else { issEl.style.display='none'; }
    }

    // Care
    setText('care-index',    d.careScore+'%');
    var cBar=el('care-bar-fill');
    if(cBar) cBar.style.width=d.careScore+'%';

    // Operator question
    var qPanel=el('question-panel');
    if(qPanel){
      if(d.showQuestion){
        setHTML('question-text','<b>'+d.questionText+'</b>');
        var qa=el('q-opt-a'), qb=el('q-opt-b'), qc=el('q-opt-c');
        if(qa) qa.textContent=d.optionA;
        if(qb) qb.textContent=d.optionB;
        if(qc) qc.textContent=d.optionC;
        qPanel.style.display='';
      } else { qPanel.style.display='none'; }
    }

    // DEV block (only update if panel present)
    var devSec=el('dev-section');
    if(devSec&&d.devMode){
      devSec.style.display='';
      var dv=d.dev,bat=dv.bat,der=dv.derived,sol=dv.solar,ac=dv.ac,gn=dv.generator,fu=dv.fuel,sys=dv.system;
      setText('dv-bat-soc',bat.soc); setText('dv-bat-v',bat.voltage); setText('dv-bat-a',bat.current); setText('dv-bat-t',bat.temp);
      setText('dv-dc-power',der.dcPower); setText('dv-energy-mode',der.energyMode);
      setText('dv-sol-power',sol.power); setText('dv-sol-state',sol.state); setText('dv-sol-v',sol.voltage);
      setText('dv-ac-v',ac.gridVoltage); setText('dv-ac-p',ac.gridPower); setText('dv-ac-state',ac.state); setText('dv-ac-shore',ac.shore); setText('dv-ac-shelly',ac.shelly);
      setText('dv-gen-run',gn.running); setText('dv-gen-exp',gn.expected); setText('dv-gen-err',gn.errorCode);
      setText('dv-fuel-lvl',fu.level); setText('dv-fuel-state',fu.state); setText('dv-fuel-sensor',fu.sensor);
      var fuInc=el('dv-fuel-inc'); if(fuInc){fuInc.textContent=fu.inconsistency||''; fuInc.style.display=fu.inconsistency?'':'none';}
      setText('dv-can',dv.comm.canHealthy);
      setText('dv-situation',sys.situation); setText('dv-decwin',sys.decisionWindow); setText('dv-mode',sys.systemMode); setText('dv-sev',sys.severity);
      setText('dv-health',sys.health); setText('dv-catA',sys.catA); setText('dv-catB',sys.catB); setText('dv-catC',sys.catC); setText('dv-catF',sys.catF);
      setText('dv-ttc',sys.timeToCritical); setText('dv-tts',sys.timeToShutdown); setText('dv-drate',sys.dischargeRate);
      setText('dv-vmove',sys.vesselMove); setText('dv-loc',sys.location); setText('dv-surv',sys.survivalMode);
      setText('dv-dstep',sys.diagStep); setText('dv-dstate',sys.diagState); setText('dv-dprim',sys.diagPrimary); setText('dv-dactq',sys.activeQ);
      var penEl=el('dv-penalties');
      if(penEl){var ph='';(sys.penalties||[]).forEach(function(p){ph+='<div class="reason">&#9888; '+p+'</div>';});penEl.innerHTML=ph;}
      var memEl=el('dv-memory-rows');
      if(memEl){var mh='';(dv.memory||[]).forEach(function(r){mh+='<div>'+r.ts+' &nbsp; <span>'+r.mode+'</span> &nbsp; health:<span>'+r.health+'%</span> &nbsp; <span>'+r.severity+'</span></div>';});memEl.innerHTML=mh||'No memory snapshots yet.';}
    } else if(devSec){ devSec.style.display='none'; }
  }

  function poll(){
    fetch('/api/state').then(function(r){return r.json();}).then(function(d){
      applyState(d);
    }).catch(function(){/* silent — keep polling */});
  }
  setInterval(poll,3000);
})();
</script>""" if auto_refresh else ""
    style   = OKi_Psychedelic_UI if PSYCHEDELIC_MODE else (OKi_Wicked_UI if WICKED_MODE else OKi_Normal_UI)
    return HTMLResponse(
        "<html style='background:#000'><head><title>OKi – Casa Azul</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=5'><meta name='mobile-web-app-capable' content='yes'>"
        + style + SCRIPTS + refresh_js +
        "</head><body style='background:#000'><div class='outer'><div class='frame'>"
        + render_header()
        + "<div class='divider'></div>"
        + '<div class="refresh-note">&#8635; auto-refresh every 3s</div>'
        + "<div class='content'>" + content + "</div>"
        + render_footer()
        + "</div></div></body></html>"
    )

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def home():
    state   = get_state()
    content = render_focus_view(state) if FOCUS_MODE else render_supervisory_view(state)
    return render_layout(content)

@app.get("/toggle-focus")
def toggle_focus():
    global FOCUS_MODE
    FOCUS_MODE = not FOCUS_MODE
    return RedirectResponse("/", 302)

@app.get("/toggle-dev")
def toggle_dev():
    toggle_dev_mode(app.state.state_manager)
    return RedirectResponse("/", 302)

@app.get("/toggle-demo")
def toggle_demo():
    global DEMO_MODE
    DEMO_MODE = not DEMO_MODE
    return RedirectResponse("/", 302)

@app.get("/toggle-psychedelic")
def toggle_psychedelic():
    global PSYCHEDELIC_MODE
    PSYCHEDELIC_MODE = not PSYCHEDELIC_MODE
    return RedirectResponse("/", 302)

@app.get("/toggle-wicked")
def toggle_wicked():
    global WICKED_MODE
    WICKED_MODE = not WICKED_MODE
    return RedirectResponse("/", 302)

@app.get("/scenario/{name}")
def scenario(name: str):
    load_scenario(app.state.state_manager, name)
    return RedirectResponse("/", 302)

@app.get("/answer/{choice}")
def answer(choice: str):
    process_operator_response(app.state.state_manager, choice)
    return RedirectResponse("/", 302)

@app.get("/care")
def care_page():
    return render_layout(render_care_page(), auto_refresh=False)

@app.get("/care/task/{task_id}")
def care_task(task_id: str):
    result = apply_care_task(app.state.state_manager, task_id)
    return RedirectResponse("/care", 302)

@app.get("/knowledge")
def knowledge_page():
    return render_layout(render_knowledge_page(), auto_refresh=False)

@app.get("/knowledge/{case_id}")
def knowledge_case(case_id: str):
    return render_layout(render_knowledge_detail(case_id), auto_refresh=False)

# ── JSON toggle endpoints — no redirect, called by okiToggle() JS ─────────────
@app.get("/api/toggle-focus")
def api_toggle_focus():
    from fastapi.responses import JSONResponse
    global FOCUS_MODE
    FOCUS_MODE = not FOCUS_MODE
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE})

@app.get("/api/toggle-dev")
def api_toggle_dev():
    from fastapi.responses import JSONResponse
    toggle_dev_mode(app.state.state_manager)
    state   = get_state()
    dev_mode = state["System"].get("DevMode", False)
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": dev_mode, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE})

@app.get("/api/toggle-demo")
def api_toggle_demo():
    from fastapi.responses import JSONResponse
    global DEMO_MODE
    DEMO_MODE = not DEMO_MODE
    # Reset care state when demo is turned on so tasks are fresh and score starts at 60
    if DEMO_MODE and _ENGINE_AVAILABLE and app.state.state_manager is not None:
        try:
            load_scenario(app.state.state_manager, "casa_azul")
        except Exception:
            pass
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE})

@app.get("/api/toggle-psychedelic")
def api_toggle_psychedelic():
    from fastapi.responses import JSONResponse
    global PSYCHEDELIC_MODE
    PSYCHEDELIC_MODE = not PSYCHEDELIC_MODE
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE, "wicked": WICKED_MODE})

@app.get("/api/toggle-wicked")
def api_toggle_wicked():
    from fastapi.responses import JSONResponse
    global WICKED_MODE
    WICKED_MODE = not WICKED_MODE
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE, "wicked": WICKED_MODE})

@app.get("/api/content")
def api_content():
    """Returns rendered .content div HTML for current view — used by okiToggle()"""
    from fastapi.responses import PlainTextResponse
    state   = get_state()
    content = render_focus_view(state) if FOCUS_MODE else render_supervisory_view(state)
    return PlainTextResponse(content, media_type="text/html")

@app.get("/api/header")
def api_header():
    """Returns rendered header HTML — used by okiToggle() to refresh LEDs/toggles"""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(render_header(), media_type="text/html")

# ── Live state API — used by fetch-based refresh (no page reload) ──────────────
@app.get("/api/state")
def api_state():
    from fastapi.responses import JSONResponse
    state    = get_state()
    battery  = state.get("Battery", {})
    derived  = state.get("Derived", {})
    system   = state.get("System", {})
    care     = state.get("Care", {})
    operator = state.get("Operator", {})
    attention = state.get("Attention", {})
    energy   = state.get("Energy", {})
    diag     = state.get("Diagnostic", {})
    vessel   = state.get("VesselState", {})
    sol      = state.get("Solar", {})
    ac       = state.get("AC", {})
    gen      = state.get("Generator", {})
    fuel     = state.get("Fuel", {})
    comm     = state.get("Communication", {})
    memory   = state.get("Memory", [])

    soc      = safe_int(battery.get("SoC"), 0)
    health   = safe_int(system.get("SystemHealth"), 0)
    severity = system.get("Severity")
    mode     = derived.get("EnergyMode") or "—"

    # LED classes
    sg, sa, sr = led_classes_system(health, severity)
    bg, ba, br = led_classes_battery(soc)

    # SoC bar
    mode_upper     = mode.upper()
    is_charging    = "CHARG" in mode_upper
    is_discharging = "DISCHARG" in mode_upper
    if is_discharging:
        bar_color   = "#ff5252" if soc < 15 else "#ffb300" if soc < 30 else "#4caf50"
        bar_anim    = "soc-bar-discharging"
    elif is_charging:
        bar_color   = "#4caf50"
        bar_anim    = "soc-bar-charging"
    else:
        bar_color   = "#ff5252" if soc < 15 else "#ffb300" if soc < 30 else "#4caf50"
        bar_anim    = ""

    soc_css = "soc-red" if soc < 15 else "soc-amber" if soc < 30 else "soc-green"

    # Health bar
    health_color = bar_color_for_health(health)

    # Operator question
    is_silent   = attention.get("Silence", False)
    has_q       = operator.get("InteractionState") == "AwaitingResponse"
    show_q      = has_q and not is_silent

    # Care
    care_score  = safe_int(care.get("CareScore"), 0)

    # Memory (last 10)
    last10 = memory[-10:] if memory else []
    mem_rows = []
    for entry in reversed(last10):
        ts   = str(entry.get("timestamp", ""))[:19].replace("T", " ")
        m    = entry.get("Mode") or "—"
        hlth = entry.get("Health") or "—"
        sev  = entry.get("Severity") or "ok"
        mem_rows.append({"ts": ts, "mode": m, "health": hlth, "severity": sev})

    # Health categories
    cats = system.get("HealthCategories") or {}

    return JSONResponse({
        "focusMode":  FOCUS_MODE,
        "demoMode":   DEMO_MODE,
        "psychedelic": PSYCHEDELIC_MODE,
        "wicked":     WICKED_MODE,

        # LEDs
        "leds": {
            "sys": [sg, sa, sr],
            "bat": [bg, ba, br],
        },
        "devMode": system.get("DevMode", False),

        # Battery / SoC
        "soc":        soc,
        "socCss":     soc_css,
        "barColor":   bar_color,
        "barAnim":    bar_anim,
        "voltage":    safe_float(battery.get("Voltage")),
        "current":    safe_float(battery.get("Current")),
        "power":      safe_float(derived.get("DCPower")),
        "mode":       mode,

        # System health
        "health":      health,
        "healthColor": health_color,
        "severity":    severity or "",
        "issues":      system.get("Inconsistency") or [],

        # Recommendation
        "rec":      system.get("Recommendation") or "",
        "recReason": system.get("RecommendationReason") or "",
        "advisory":  system.get("Advisory") or "",
        "advisoryCase": system.get("AdvisoryCase") or "",

        # Care
        "careScore":       care_score,

        # Operator question
        "showQuestion":   show_q,
        "questionText":   operator.get("ActiveQuestionText") or "",
        "optionA":        operator.get("OptionA") or "",
        "optionB":        operator.get("OptionB") or "",
        "optionC":        operator.get("OptionC") or "",

        # DEV — vessel data
        "dev": {
            "bat": {
                "soc": v(battery.get("SoC"), "%"),
                "voltage": v(battery.get("Voltage"), " V"),
                "current": v(battery.get("Current"), " A"),
                "temp": v(battery.get("Temperature"), " °C"),
            },
            "derived": {
                "dcPower": v(derived.get("DCPower"), " W"),
                "energyMode": derived.get("EnergyMode") or "—",
            },
            "solar": {
                "power": v(sol.get("Power"), " W"),
                "state": sol.get("State") or "—",
                "voltage": v(sol.get("Voltage"), " V"),
            },
            "ac": {
                "gridVoltage": v(ac.get("GridVoltage"), " V"),
                "gridPower": v(ac.get("GridPower"), " W"),
                "state": ac.get("State") or "—",
                "shore": str(ac.get("Shore") or "—"),
                "shelly": ac.get("ShellyStatus") or "—",
            },
            "generator": {
                "running": "ON" if gen.get("Running") else "OFF",
                "expected": str(gen.get("Expected", "—")),
                "errorCode": gen.get("ErrorCode") or "none",
            },
            "fuel": {
                "level": v(fuel.get("LevelPercent"), "%"),
                "state": fuel.get("State") or "—",
                "sensor": "OK" if fuel.get("SensorReliable") else "unreliable",
                "inconsistency": fuel.get("Inconsistency") or "",
            },
            "comm": {
                "canHealthy": str(comm.get("CANHealthy") or "—"),
            },
            "system": {
                "situation": system.get("SituationType") or "—",
                "decisionWindow": system.get("DecisionWindow") or "—",
                "systemMode": system.get("Mode") or "—",
                "severity": system.get("Severity") or "none",
                "health": f'{system.get("SystemHealth") or "—"}%',
                "catA": f'-{cats.get("A_SystemIntegrity", 0)}pt',
                "catB": f'-{cats.get("B_EnergyBattery", 0)}pt',
                "catC": f'-{cats.get("C_OperationalStress", 0)}pt',
                "catF": f'-{cats.get("F_PowerContinuity", 0)}pt',
                "timeToCritical": v(energy.get("TimeToCriticalHours"), " h"),
                "timeToShutdown": v(energy.get("TimeToShutdownHours"), " h"),
                "dischargeRate": v(energy.get("DischargeRate"), " %/h"),
                "vesselMove": vessel.get("MovementState") or "—",
                "location": vessel.get("LocationContext") or "—",
                "survivalMode": "YES" if vessel.get("SurvivalMode") else "no",
                "diagStep": diag.get("Step") or "—",
                "diagState": diag.get("DiagnosticState") or "—",
                "diagPrimary": (diag.get("PrimaryState") or "—")[:30],
                "activeQ": "yes" if diag.get("ActiveQuestion") else "none",
                "penalties": (system.get("HealthPenalties") or [])[:5],
            },
            "memory": mem_rows,
        },
    })

# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("web_server:app", host="0.0.0.0", port=port, reload=False)
