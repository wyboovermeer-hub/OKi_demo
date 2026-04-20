# ============================================================
# OKi – Onboard Knowledge Interface
# ENTERPRISE WEB LAYER v21.28
# ============================================================
#
# Changelog v21.28
# -----------------
# • FIRMWARE identity block — OKi-FW-001.008.005.021.027
#   Single source of truth for unit, engine, web server versions
# • /version endpoint — returns full firmware identity as JSON
# • Firmware badge — fixed bottom-right in UI, subtle mono text
#   shows OKi-FW-001.008.005.021.027 · 2026-04-19, fades on hover
#
# ============================================================
# APPLY THIS FILE AS A PATCH — do not replace your full web_server.py
# with this file. Instead apply the three marked sections below
# into your existing web_server.py at the indicated locations.
# ============================================================
#
# ── PATCH 1 ── After app = FastAPI() and mode flags, insert FIRMWARE block
# ── PATCH 2 ── In render_layout(), before closing </body></html>, inject badge
# ── PATCH 3 ── In ROUTES section, add @app.get("/version") route
#
# ============================================================

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PATCH 1 — FIRMWARE IDENTITY BLOCK                                      ║
# ║  Insert after: FOCUS_MODE = False / WICKED_MODE = False                 ║
# ║  (directly after app = FastAPI() and the three mode flag lines)         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

FIRMWARE = {
    "unit":         "001",
    "engine_major": "008",
    "engine_minor": "005",
    "ws_major":     "021",
    "ws_minor":     "027",
    "build_date":   "2026-04-19",
    "vessel":       "Casa Azul",
    "display":      "OKi 001 — v8.5 / ws21.27",
    "full":         "OKi-FW-001.008.005.021.027",
}

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PATCH 2 — FIRMWARE BADGE                                               ║
# ║  In render_layout(), find the return statement that ends with:          ║
# ║      + "</div></div></body></html>"                                      ║
# ║  Replace that closing string with:                                      ║
# ║      + _FIRMWARE_BADGE + "</div></div></body></html>"                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_FIRMWARE_BADGE = (
    '<style>'
    '#fw-badge {'
    '  position:fixed; bottom:10px; right:14px;'
    '  font-family:"Share Tech Mono",monospace;'
    '  font-size:9px; letter-spacing:0.10em;'
    '  color:rgba(129,164,196,0.30);'
    '  pointer-events:none; user-select:none; z-index:9999;'
    '  transition:opacity 0.4s;'
    '}'
    '#fw-badge:hover { opacity:0; }'
    '</style>'
    f'<div id="fw-badge">{FIRMWARE["full"]} &nbsp;·&nbsp; {FIRMWARE["build_date"]}</div>'
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PATCH 3 — /version ROUTE                                               ║
# ║  Add this route in the ROUTES section, alongside the other @app.get     ║
# ║  routes (e.g. after @app.get("/toggle-focus") or similar)               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# from fastapi.responses import JSONResponse  ← already imported if you use logbook
# If not already imported, add JSONResponse to your fastapi.responses import line

# @app.get("/version")
# def version():
#     """Return full OKi firmware identity as JSON."""
#     return JSONResponse(FIRMWARE)

# ════════════════════════════════════════════════════════════════════════════
# FULL PATCH INSTRUCTIONS
# ════════════════════════════════════════════════════════════════════════════
#
# STEP 1 — Open web_server.py
#
# STEP 2 — Find this block (around line 60-65):
#
#     app = FastAPI()
#     app.mount("/static", StaticFiles(directory="."), name="static")
#
#     FOCUS_MODE       = False
#     PSYCHEDELIC_MODE = False
#     WICKED_MODE      = False
#
#   Add FIRMWARE dict immediately after WICKED_MODE = False
#
# STEP 3 — Find render_layout() return statement (around line 1000):
#
#     return HTMLResponse(
#         "<!DOCTYPE html><html lang='en'><head>..."
#         + render_footer()
#         + "</div></div></body></html>"
#     )
#
#   Change the last line to:
#
#         + render_footer()
#         + _FIRMWARE_BADGE + "</div></div></body></html>"
#     )
#
# STEP 4 — Find the ROUTES section (starts with @app.get("/"))
#   Add after @app.get("/toggle-focus"):
#
#     @app.get("/version")
#     def version():
#         return JSONResponse(FIRMWARE)
#
#   Make sure JSONResponse is in your fastapi.responses import.
#
# STEP 5 — Add JSONResponse to imports if not already present:
#
#     from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
#
# STEP 6 — Save, SCP to Pi, restart:
#
#     scp web_server.py oki@oki.local:~/OKi/05_OKi_Engine/
#     sudo systemctl restart oki
#
# STEP 7 — Verify:
#     curl http://192.168.1.163:8000/version
#     curl http://100.66.110.127:8000/version
#     https://oki-demo.onrender.com/version
#
# Expected JSON response:
# {
#   "unit":         "001",
#   "engine_major": "008",
#   "engine_minor": "005",
#   "ws_major":     "021",
#   "ws_minor":     "027",
#   "build_date":   "2026-04-19",
#   "vessel":       "Casa Azul",
#   "display":      "OKi 001 — v8.5 / ws21.27",
#   "full":         "OKi-FW-001.008.005.021.027"
# }
#
# ════════════════════════════════════════════════════════════════════════════
# DIFF SUMMARY — exactly what changes in web_server.py
# ════════════════════════════════════════════════════════════════════════════
#
# + FIRMWARE = { ... }                          ← after WICKED_MODE = False
#
# + _FIRMWARE_BADGE = '...'                     ← after FIRMWARE dict
#
#   from fastapi.responses import HTMLResponse, RedirectResponse
# + from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
#
#       + render_footer()
# -     + "</div></div></body></html>"
# +     + _FIRMWARE_BADGE + "</div></div></body></html>"
#
# + @app.get("/version")
# + def version():
# +     return JSONResponse(FIRMWARE)
#
# ════════════════════════════════════════════════════════════════════════════
