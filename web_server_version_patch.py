"""
web_server_version_patch.py
============================
OKi Web Server v21.28 — Firmware Version Endpoint
Apply these additions to web_server.py.

CHANGES:
1. Add FIRMWARE constant block near the top (after imports)
2. Add /version JSON endpoint
3. Add firmware string to the HTML footer of the UI (subtle, mono, bottom-right)

VERSION: OKi-FW-001.008.005.021.027
"""

# ─── 1. ADD NEAR TOP OF web_server.py (after imports, before app = FastAPI) ──

FIRMWARE = {
    "unit":           "001",
    "engine_major":   "008",
    "engine_minor":   "005",
    "ws_major":       "021",
    "ws_minor":       "027",
    "build_date":     "2026-04-19",
    "vessel":         "Casa Azul",
    "display":        "OKi 001 — v8.5 / ws21.27",
    "full":           "OKi-FW-001.008.005.021.027",
}


# ─── 2. ADD ROUTE (alongside other @app.get routes) ──────────────────────────

@app.get("/version")
async def version():
    """Return full firmware identity as JSON."""
    return FIRMWARE


# ─── 3. ADD TO HTML TEMPLATE ─────────────────────────────────────────────────
# Find the closing </body> tag in your HTML template string and insert this
# just before it. It injects a subtle firmware string bottom-right on every page.
#
# In the Python string, use f-string or .replace() to inject FIRMWARE["full"]
# and FIRMWARE["build_date"] at template render time.
#
# Example — find this in your render function:
#     html = HTML_TEMPLATE  (or however you build the page)
# Then do:
#     html = html.replace("</body>", FIRMWARE_FOOTER + "</body>")

FIRMWARE_FOOTER = f"""
<style>
  #fw-badge {{
    position: fixed;
    bottom: 10px;
    right: 14px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.10em;
    color: rgba(129, 164, 196, 0.35);
    pointer-events: none;
    user-select: none;
    z-index: 9999;
    transition: opacity 0.3s;
  }}
  #fw-badge:hover {{
    opacity: 0;
  }}
</style>
<div id="fw-badge">{FIRMWARE["full"]} &nbsp;·&nbsp; {FIRMWARE["build_date"]}</div>
"""


# ─── QUICK VERIFICATION ───────────────────────────────────────────────────────
# After deploying, confirm:
#   curl http://192.168.1.163:8000/version
#   curl http://100.66.110.127:8000/version   (Tailscale)
#
# Expected response:
# {
#   "unit": "001",
#   "engine_major": "008",
#   "engine_minor": "005",
#   "ws_major": "021",
#   "ws_minor": "027",
#   "build_date": "2026-04-19",
#   "vessel": "Casa Azul",
#   "display": "OKi 001 — v8.5 / ws21.27",
#   "full": "OKi-FW-001.008.005.021.027"
# }
#
# Also visible at: https://oki-demo.onrender.com/version
