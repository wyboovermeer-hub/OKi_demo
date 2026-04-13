# ============================================================
# OKi – Onboard Knowledge Interface
# ENTERPRISE WEB LAYER v20.1
# ============================================================
#
# Changelog v20.1
# ----------------
# • Engine import wrapped in try/except — never crashes on Render
# • KNOWLEDGE_PATH uses parents[1] — correct for 05_OKi_Engine/ sibling layout
# • Startup event loads "generator_failure" demo scenario
# • render_knowledge_page() uses correct Case fields: root_cause, solution
# • render_supervisory_view() checks Attention["Silence"] before rendering
#   operator question — questions no longer leak through on stable state
# • __main__ block added — reads $PORT env var, falls back to 10000
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

FOCUS_MODE      = False
PSYCHEDELIC_MODE = False

# ── Knowledge path ─────────────────────────────────────────────────────────────
# Layout:  15_OKi/
#          ├── 05_OKi_Engine/   ← this file  (parents[0])
#          └── 02_OKi_Knowledge/              (parents[1] / "02_OKi_Knowledge")
KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "02_OKi_Knowledge"

if KNOWLEDGE_PATH.exists() and str(KNOWLEDGE_PATH) not in sys.path:
    sys.path.insert(0, str(KNOWLEDGE_PATH))
elif not KNOWLEDGE_PATH.exists():
    # Flat-layout fallback (all files in same directory)
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
    # Create state_manager if it doesn't exist (Render / standalone deployment)
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

def get_state():
    try:
        return app.state.state_manager.get()
    except Exception:
        from state_schema import STATE_SCHEMA
        from copy import deepcopy
        return deepcopy(STATE_SCHEMA)

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
    if soc < 15:  return "soc-number soc-red"
    elif soc < 30: return "soc-number soc-amber"
    return "soc-number soc-green"

def bar_color_for_health(health):
    if health < 50: return "red"
    elif health < 75: return "amber"
    return "green"

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
.footer{text-align:center;padding-top:4px;flex-shrink:0}
.footer img{width:clamp(50px,10vw,70px);opacity:0.7;cursor:pointer;-webkit-tap-highlight-color:transparent}
.dev-section{border-top:1px solid #2b313c;margin-top:6px;padding-top:6px}
.dev-label{text-align:center;font-size:10px;color:#444;margin-bottom:4px}
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
.footer{text-align:center;padding-top:4px;flex-shrink:0}
.footer img{width:clamp(50px,10vw,70px);opacity:0.7;filter:drop-shadow(0 0 6px rgba(31,111,181,0.4));cursor:pointer;-webkit-tap-highlight-color:transparent}
.dev-section{border-top:1px solid #1a2a3a;margin-top:6px;padding-top:6px}
.dev-label{text-align:center;font-size:9px;color:#2a4a6a;margin-bottom:4px;font-family:'Orbitron',monospace}
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
  if(_taps>=7){_taps=0;window.location.href='/toggle-psychedelic';}
}
</script>"""

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

def render_led_strip(g, a, r):
    return f'<div class="led-strip"><div class="{g}"></div><div class="{a}"></div><div class="{r}"></div></div>'

def render_toggle(label, checked, route):
    flag = "checked" if checked else ""
    return f'<div class="toggle-box"><span class="toggle-label">{label}</span><label class="switch"><input type="checkbox" {flag} onchange="window.location.href=\'/{route}\'"><span class="slider"></span></label></div>'

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
  <div class="header-left">{render_led_strip(sg,sa,sr)}{render_toggle("FOCUS",FOCUS_MODE,"toggle-focus")}</div>
  <div class="title-block"><div class="title-oki">OKi</div><div class="title-sub">Onboard Knowledge Interface</div><div class="boat-name-center">&#9875; Casa Azul</div></div>
  <div class="header-right">{render_led_strip(bg,ba,br)}{render_toggle("DEV",dev_mode,"toggle-dev")}<div class="clock" id="clock">--:--:--</div><div class="clock-date" id="clock-date">--- -- --- ----</div></div>
</div>"""

def render_footer():
    return '<div class="footer"><a href="/" onclick="logoTap(); return false;"><img src="/static/oki_logo.png" alt="OKi"></a></div>'

def render_supervisory_view(state):
    content  = ""
    dev_mode = state["System"].get("DevMode", False)
    operator = state["Operator"]

    # ── Silence rule — only show question when attention engine says not silent ──
    # Check Attention["Silence"] first; fall back to legacy InteractionState check.
    attention = state.get("Attention", {})
    is_silent = attention.get("Silence", False)
    has_active_question = operator.get("InteractionState") == "AwaitingResponse"

    if has_active_question and not is_silent:
        q  = f"<div style='font-size:clamp(12px,2.5vw,14px);margin-bottom:8px;color:#cad8e3;'><b>{operator['ActiveQuestionText']}</b></div>"
        q += render_op_button(operator["OptionA"], "/answer/A")
        q += render_op_button(operator["OptionB"], "/answer/B")
        q += render_op_button(operator["OptionC"], "/answer/C")
        content += render_panel("Operator Confirmation Required", q)

    battery = state.get("Battery", {})
    derived = state.get("Derived", {})
    soc     = safe_int(battery.get("SoC"), 0)
    voltage = safe_float(battery.get("Voltage"))
    current = safe_float(battery.get("Current"))
    power   = safe_float(derived.get("DCPower"))
    mode    = derived.get("EnergyMode") or "—"

    battery_html = f"""<div class="soc-display"><div class="{soc_css_class(soc)}">{soc}%</div><div class="soc-label">State of Charge</div></div>
{soc_bar_html(soc, mode)}
<div class="grid2" style="margin-top:10px;">
  <div class="label">Voltage</div><div class="value">{voltage} V</div>
  <div class="label">Current</div><div class="value">{current} A</div>
  <div class="label">Power</div><div class="value">{power} W</div>
  <div class="label">Mode</div><div class="value">{mode}</div>
</div>"""
    content += render_panel("Battery", battery_html)

    rec = state["System"].get("Recommendation")
    if rec:
        reason  = state["System"].get("RecommendationReason")
        advisory= state["System"].get("Advisory")
        r = f"<div style='font-size:clamp(12px,2vw,13px);'>{rec}</div>"
        if reason:   r += f'<div class="reason">Reason: {reason}</div>'
        if advisory: r += f'<div class="advisory">&#128203; {advisory}</div>'
        content += render_panel("Recommendation", r)

    health   = safe_int(state["System"].get("SystemHealth"), 0)
    severity = state["System"].get("Severity")
    h = f'<div style="font-size:clamp(20px,4vw,28px);font-weight:bold;color:#cad8e3;">{health}%</div>{render_bar(health, bar_color_for_health(health))}'
    issues = state["System"].get("Inconsistency")
    if issues: h += f'<div class="reason" style="margin-top:5px;">&#9888; {" | ".join(issues)}</div>'
    content += render_panel("System Health", h, badge=severity)

    care       = state["Care"]
    care_index = safe_int(care.get("CareIndex"), 0)
    c = f"""<div class="grid2">
  <div class="label">System Care</div><div class="value">{safe_int(care.get('SystemCareScore'))}%</div>
  <div class="label">Operator Care</div><div class="value">{safe_int(care.get('OperatorCareScore'))}%</div>
  <div class="label">Care Index</div><div class="value"><b>{care_index}%</b></div>
</div>{render_bar(care_index, "blue")}"""
    content += render_panel("OKi Care", c)
    content += render_button("CARE", "/care")
    content += render_button("KNOWLEDGE", "/knowledge")

    if dev_mode:
        content += '<div class="dev-section"><div class="dev-label">DEV — Scenarios</div>'
        content += render_button("Scenario: Anchor", "/scenario/anchor")
        content += render_button("Scenario: Casa Azul", "/scenario/casa")
        content += render_button("Scenario: Suspicious Drain", "/scenario/drain")
        content += render_button("Scenario: Generator Failure", "/scenario/generator_failure")
        content += "</div>"

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

    soc_html = f"""<div class="soc-display"><div class="{soc_css_class(soc)}">{soc}%</div><div class="soc-label">State of Charge</div></div>
{soc_bar_html(soc, mode)}
<div class="grid2" style="margin-top:10px;">
  <div class="label">Voltage</div><div class="value">{voltage} V</div>
  <div class="label">Current</div><div class="value">{current} A</div>
  <div class="label">Power</div><div class="value">{power} W</div>
  <div class="label">Mode</div><div class="value">{mode}</div>
</div>"""
    health_html = f'<div style="font-size:clamp(20px,4vw,28px);font-weight:bold;color:#cad8e3;">{health}%</div>{render_bar(health, bar_color_for_health(health))}'
    rec     = system.get("Recommendation", "")
    content = render_panel("Battery", soc_html)
    content += render_panel("System Health", health_html)
    if rec:
        content += render_panel("Status", f"<div style='font-size:clamp(12px,2vw,13px);'>{rec}</div>")
    content += render_button("CARE", "/care")
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
    # Case fields: case_id, title, root_cause, solution, symptoms, conditions, actions
    cases = list(CASE_LIBRARY.cases.values()) if hasattr(CASE_LIBRARY, 'cases') else []
    if not cases:
        content = "<div style='color:#6a8aa0;'>No cases loaded yet.</div>"
    else:
        content = f"<div class='reason' style='margin-bottom:10px;'>{len(cases)} cases loaded</div>"
        for case in cases[:10]:
            case_id    = getattr(case, "case_id",    "?")
            title      = getattr(case, "title",      "?")
            root_cause = getattr(case, "root_cause", "") or ""
            # Show root_cause as the description snippet (correct field name)
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
    refresh = '<meta http-equiv="refresh" content="3">' if auto_refresh else ""
    style   = PSYCH_STYLE if PSYCHEDELIC_MODE else PROF_STYLE
    return HTMLResponse(
        "<html><head><title>OKi – Casa Azul</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=5'>"
        + refresh + style + SCRIPTS +
        "</head><body><div class='outer'><div class='frame'>"
        + render_header()
        + "<div class='divider'></div>"
        + '<div class="refresh-note">&#8635; auto-refresh every 3s</div>'
        + "<div class='content'>" + content + "</div>"
        + render_footer()
        + "</div></div></body></html>"
    )

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

# ── Entrypoint — reads $PORT env var, falls back to 10000 ─────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("web_server:app", host="0.0.0.0", port=port, reload=False)
