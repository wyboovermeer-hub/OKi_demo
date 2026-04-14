# ============================================================
# OKi – Onboard Knowledge Interface
# ENTERPRISE WEB LAYER v20.5
# ============================================================
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
    from engine import process_operator_response, load_scenario, toggle_dev_mode, apply_care_task
    _ENGINE_AVAILABLE = True
except Exception as _engine_err:
    print(f"[OKi] Warning — engine import failed: {_engine_err}")
    _ENGINE_AVAILABLE = False
    def process_operator_response(*a, **kw): pass
    def load_scenario(*a, **kw): pass
    def toggle_dev_mode(*a, **kw): pass
    def apply_care_task(*a, **kw): pass

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

FOCUS_MODE       = False
PSYCHEDELIC_MODE = False
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
            load_scenario(app.state.state_manager, "generator_failure")
            print("[OKi] Demo scenario loaded: generator_failure")
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

PROF_STYLE = """<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
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
.toggle-box{display:flex;flex-direction:column;align-items:center;gap:3px}
.toggle-label{font-size:clamp(8px,1.5vw,10px);color:#9aa8b5;letter-spacing:0.08em;font-weight:600}
.switch{position:relative;display:inline-block;width:36px;height:18px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#444;transition:.3s;border-radius:18px}
.slider:before{position:absolute;content:"";height:12px;width:12px;left:2px;bottom:2px;background:white;transition:.3s;border-radius:50%}
input:checked+.slider{background:#1f6fb5}
input:checked+.slider:before{transform:translateX(18px)}
.divider{height:1px;background:#2b313c;margin:4px 0 6px 0;flex-shrink:0}
.content{flex:1;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#2b313c #0f1115}
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
.button{display:block;width:92%;margin:7px auto;padding:clamp(13px,2.8vw,17px);background:#2b313c;color:#cad8e3;text-decoration:none;border-radius:24px;text-align:center;font-size:clamp(13px,2.5vw,15px);transition:background 0.2s;cursor:pointer;border:none}
.button:hover,.button:active{background:#3a4255}
.op-button{display:block;width:92%;margin:6px auto;padding:clamp(13px,2.8vw,17px);background:#2b313c;color:#cad8e3;text-decoration:none;border-radius:24px;text-align:center;font-size:clamp(13px,2.5vw,15px);border:none;cursor:pointer;transition:background 0.2s}
.op-button:hover,.op-button:active{background:#3a4255}
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
.footer img{width:clamp(50px,10vw,70px);opacity:0.7;cursor:pointer;-webkit-tap-highlight-color:transparent}
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
</style>"""

PSYCH_STYLE = """<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Exo+2:wght@300;400;600&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
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
.toggle-box{display:flex;flex-direction:column;align-items:center;gap:3px}
.toggle-label{font-size:clamp(8px,1.5vw,10px);color:#3a6a8a;letter-spacing:0.1em;font-weight:600;font-family:'Orbitron',monospace}
.switch{position:relative;display:inline-block;width:36px;height:18px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#1a2030;border:1px solid #2a4060;transition:.4s;border-radius:18px}
.slider:before{position:absolute;content:"";height:12px;width:12px;left:2px;bottom:2px;background:#3a5a7a;transition:.4s;border-radius:50%}
input:checked+.slider{background:#0a3060;border-color:#1f6fb5;box-shadow:0 0 8px rgba(31,111,181,0.6)}
input:checked+.slider:before{transform:translateX(18px);background:#00d4ff}
.divider{height:1px;background:linear-gradient(90deg,transparent,#1f3a5a 20%,#1f6fb5 50%,#1f3a5a 80%,transparent);margin:4px 0 6px 0;flex-shrink:0}
.content{flex:1;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#1f3a5a #080c14}
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
.button{display:block;width:92%;margin:7px auto;padding:clamp(13px,2.8vw,17px);background:linear-gradient(135deg,#0d1e35,#0a1525);color:#7ab8d4;text-decoration:none;border-radius:10px;text-align:center;font-size:clamp(12px,2.3vw,15px);font-family:'Orbitron',monospace;letter-spacing:0.15em;transition:all 0.15s ease;cursor:pointer;border:1px solid #1f4a6a;text-transform:uppercase}
.button:hover,.button:active{background:linear-gradient(135deg,#1a3a5a,#0d2040);border-color:#1f6fb5;color:#00d4ff}
.op-button{display:block;width:92%;margin:6px auto;padding:clamp(13px,2.8vw,17px);background:linear-gradient(135deg,#1a2a1a,#0d1a0d);color:#4aff80;text-decoration:none;border-radius:10px;text-align:center;font-size:clamp(12px,2.3vw,14px);font-family:'Orbitron',monospace;letter-spacing:0.1em;border:1px solid #1a4a2a;cursor:pointer;transition:all 0.15s ease}
.op-button:hover,.op-button:active{background:linear-gradient(135deg,#2a4a2a,#1a2a1a);border-color:#00ff44}
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
.footer img{width:clamp(50px,10vw,70px);opacity:0.7;filter:drop-shadow(0 0 6px rgba(31,111,181,0.4));cursor:pointer;-webkit-tap-highlight-color:transparent}
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
</style>"""

SCRIPTS = """<script>
function updateClock(){
  const now=new Date();
  const h=String(now.getHours()).padStart(2,'0');
  const m=String(now.getMinutes()).padStart(2,'0');
  const s=String(now.getSeconds()).padStart(2,'0');
  const days=['SUN','MON','TUE','WED','THU','FRI','SAT'];
  const months=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  const el=document.getElementById('clock');
  const del=document.getElementById('clock-date');
  if(el) el.textContent=h+':'+m+':'+s;
  if(del) del.textContent=days[now.getDay()]+' '+String(now.getDate()).padStart(2,'0')+' '+months[now.getMonth()]+' '+now.getFullYear();
}
setInterval(updateClock,1000);
window.onload=updateClock;
var _taps=0,_tapTimer=null;
function logoTap(){
  _taps++;
  clearTimeout(_tapTimer);
  _tapTimer=setTimeout(function(){_taps=0;},3000);
  if(_taps>=7){_taps=0;okiToggle(null,'/api/toggle-psychedelic');}
}
function okiToggle(input, overrideRoute){
  var route = overrideRoute || (input && input.getAttribute('data-toggle-route'));
  if(!route) return;
  fetch(route).then(function(r){return r.json();}).then(function(d){
    // Swap content div
    return fetch('/api/content').then(function(r){return r.text();}).then(function(html){
      var c=document.querySelector('.content');
      if(c) c.innerHTML=html;
      // Update header LEDs and toggles
      return fetch('/api/header').then(function(r){return r.text();}).then(function(hhtml){
        var hdr=document.querySelector('.header');
        if(hdr) hdr.outerHTML=hhtml;
      });
    });
  }).catch(function(e){
    // Fallback to full navigation if fetch fails
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
        '<div class="footer">'
        '<div class="footer-demo">'
        '<div class="footer-demo-label">DEMO</div>'
        + toggle +
        '</div>'
        '<a href="/" onclick="logoTap(); return false;"><img src="/static/oki_logo.png" alt="OKi"></a>'
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
        q += f'<a id="q-opt-b" class="op-button" href="/answer/B">{operator["OptionB"]}</a>'
        q += f'<a id="q-opt-c" class="op-button" href="/answer/C">{operator["OptionC"]}</a>'
        content += f'<div id="question-panel"><div class="panel"><div class="panel-title">Operator Confirmation Required</div>{q}</div></div>'
    else:
        content += '<div id="question-panel" style="display:none;"><div class="panel"><div class="panel-title">Operator Confirmation Required</div><div id="question-text"></div><a id="q-opt-a" class="op-button" href="/answer/A"></a><a id="q-opt-b" class="op-button" href="/answer/B"></a><a id="q-opt-c" class="op-button" href="/answer/C"></a></div></div>'

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
        r = f"<div style='font-size:clamp(12px,2vw,13px);'>{rec}</div>"
        if reason:   r += f'<div class="reason">Reason: {reason}</div>'
        if advisory: r += f'<div class="advisory">&#128203; {advisory}</div>'
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

    care       = state["Care"]
    care_index = safe_int(care.get("CareIndex"), 0)
    c = f"""<div class="grid2">
  <div class="label">System Care</div><div id="care-system" class="value">{safe_int(care.get('SystemCareScore'))}%</div>
  <div class="label">Operator Care</div><div id="care-operator" class="value">{safe_int(care.get('OperatorCareScore'))}%</div>
  <div class="label">Care Index</div><div id="care-index" class="value"><b>{care_index}%</b></div>
</div><div class="bar-container"><div id="care-bar-fill" class="bar-fill bar-blue" style="width:{care_index}%"></div></div>"""
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
    content += render_button("CARE", "/care")

    # DEMO block
    if DEMO_MODE:
        content += render_demo_block()

    # DEV block visible in focus mode too
    if system.get("DevMode", False):
        content += render_dev_block(state)

    return content

def render_care_page():
    state      = get_state()
    care       = state.get("Care", {})
    care_index = safe_int(care.get("CareIndex"), 0)
    content = f"""<div class="grid2">
  <div class="label">System Care Score</div><div class="value">{safe_int(care.get('SystemCareScore'))}%</div>
  <div class="label">Operator Care Score</div><div class="value">{safe_int(care.get('OperatorCareScore'))}%</div>
  <div class="label">Care Index</div><div class="value"><b>{care_index}%</b></div>
</div>{render_bar(care_index, "blue")}
<div class="reason" style="margin-top:10px;">The Care Index rewards operators who keep their system healthy over time. A higher score means fewer surprises and better reliability.</div>"""
    panel  = render_panel("OKi Care", content)
    panel += render_button("+ Log Care Task", "/care/task")
    panel += render_button("← Back", "/")
    return panel

def render_knowledge_page():
    cases = list(CASE_LIBRARY.cases.values()) if hasattr(CASE_LIBRARY, 'cases') else []
    if not cases:
        content = "<div style='color:#6a8aa0;'>No cases loaded yet.</div>"
    else:
        content = f"<div class='reason' style='margin-bottom:10px;'>{len(cases)} cases loaded</div>"
        for case in cases[:10]:
            case_id    = getattr(case, "case_id",    "?")
            title      = getattr(case, "title",      "?")
            root_cause = getattr(case, "root_cause", "") or ""
            snippet    = root_cause[:120] + "..." if len(root_cause) > 120 else root_cause
            content += (
                f'<div style="margin-bottom:8px;padding:10px;background:#0f1115;border-radius:8px;">'
                f'<div style="color:#1f6fb5;font-size:clamp(11px,2vw,13px);">{case_id} — {title}</div>'
                f'<div style="font-size:clamp(10px,1.8vw,12px);color:#6a8aa0;margin-top:3px;">{snippet}</div>'
                f'</div>'
            )
    panel  = render_panel("OKi Knowledge Base", content)
    panel += render_button("← Back", "/")
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
        if(d.advisory)  rh+='<div class="advisory">&#128203; '+d.advisory+'</div>';
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
    setText('care-index',    d.careIndex+'%');
    setText('care-system',   d.systemCareScore+'%');
    setText('care-operator', d.operatorCareScore+'%');
    var cBar=el('care-bar-fill');
    if(cBar) cBar.style.width=d.careIndex+'%';

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
    style   = PSYCH_STYLE if PSYCHEDELIC_MODE else PROF_STYLE
    return HTMLResponse(
        "<html><head><title>OKi – Casa Azul</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=5'>"
        + style + SCRIPTS + refresh_js +
        "</head><body><div class='outer'><div class='frame'>"
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

@app.get("/care/task")
def care_task():
    apply_care_task(app.state.state_manager, increment=3)
    return RedirectResponse("/care", 302)

@app.get("/knowledge")
def knowledge_page():
    return render_layout(render_knowledge_page(), auto_refresh=False)

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
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE})

@app.get("/api/toggle-psychedelic")
def api_toggle_psychedelic():
    from fastapi.responses import JSONResponse
    global PSYCHEDELIC_MODE
    PSYCHEDELIC_MODE = not PSYCHEDELIC_MODE
    return JSONResponse({"ok": True, "focusMode": FOCUS_MODE, "devMode": False, "demoMode": DEMO_MODE, "psychedelic": PSYCHEDELIC_MODE})

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
    care_index  = safe_int(care.get("CareIndex"), 0)

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

        # Care
        "careIndex":       care_index,
        "systemCareScore": safe_int(care.get("SystemCareScore")),
        "operatorCareScore": safe_int(care.get("OperatorCareScore")),

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
