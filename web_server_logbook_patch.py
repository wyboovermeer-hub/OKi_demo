"""
web_server_logbook_patch.py
===========================
OKi Web Server v21.28 — Vessel Logbook additions.
Add these routes and the HTML to your existing web_server.py.

CHANGES:
1. Import logbook at top
2. Add /log GET endpoint
3. Add /api/log GET endpoint (JSON)
4. Add /api/log/clear POST endpoint (dev only)
5. Add logbook button to main UI
6. Add LOG_PAGE_HTML constant
"""

# ─── IMPORT (add to existing imports) ────────────────────────────────────────
import logbook as lb

# ─── ROUTES (add to existing FastAPI app) ────────────────────────────────────

from fastapi import Query
from fastapi.responses import HTMLResponse, JSONResponse

@app.get("/log", response_class=HTMLResponse)
async def logbook_page():
    return LOG_PAGE_HTML

@app.get("/api/log")
async def api_log(
    limit: int = Query(default=200, ge=1, le=2000),
    level: str = Query(default=None),
    category: str = Query(default=None)
):
    categories = [category] if category else None
    entries = lb.get_all_entries(limit=limit, categories=categories, min_level=level)
    deep_cycles = lb.get_deep_cycle_count()
    return JSONResponse({
        "entries": entries,
        "total": len(entries),
        "deep_cycle_count": deep_cycles
    })

@app.post("/api/log/clear")
async def api_log_clear():
    lb.clear_all()
    return {"status": "cleared"}


# ─── LOG PAGE HTML ────────────────────────────────────────────────────────────

LOG_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OKi — Vessel Logbook</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;400;600;700&display=swap');

  :root {
    --bg:        #05070A;
    --wmc-blue:  #548bac;
    --wmc-light: #cad8e3;
    --wmc-mid:   #81a4c4;
    --plasma-1:  #ff2d78;
    --plasma-2:  #ff9f0a;
    --plasma-3:  #30d158;
    --plasma-4:  #0a84ff;
    --plasma-5:  #bf5af2;
    --mono:      'Share Tech Mono', monospace;
    --body:      'Exo 2', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--wmc-light);
    font-family: var(--body);
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── Star field ── */
  #stars {
    position: fixed; inset: 0; pointer-events: none; z-index: 0;
  }

  /* ── Plasma border on page ── */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background:
      linear-gradient(90deg, var(--plasma-1) 0%, var(--plasma-2) 25%,
        var(--plasma-3) 50%, var(--plasma-4) 75%, var(--plasma-5) 100%);
    mask: linear-gradient(#000 0 0) content-box,
          linear-gradient(#000 0 0);
    mask-composite: exclude;
    padding: 1px;
    pointer-events: none;
    z-index: 1;
    opacity: 0.6;
    animation: plasma-shift 8s linear infinite;
  }

  @keyframes plasma-shift {
    0%   { filter: hue-rotate(0deg); }
    100% { filter: hue-rotate(360deg); }
  }

  /* ── Layout ── */
  .page {
    position: relative; z-index: 2;
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 20px 60px;
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 28px;
    padding-bottom: 16px;
    border-bottom: 1px solid rgba(84,139,172,0.25);
  }

  .header-left {
    display: flex; align-items: center; gap: 14px;
  }

  .header-left a {
    color: var(--wmc-mid);
    text-decoration: none;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    opacity: 0.7;
    transition: opacity 0.2s;
  }
  .header-left a:hover { opacity: 1; color: var(--wmc-light); }

  .title {
    font-family: var(--mono);
    font-size: 22px;
    letter-spacing: 0.15em;
    color: var(--wmc-light);
    text-transform: uppercase;
  }

  .title span {
    background: linear-gradient(90deg, var(--plasma-4), var(--plasma-5));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .subtitle {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--wmc-mid);
    opacity: 0.6;
    margin-top: 3px;
    letter-spacing: 0.1em;
  }

  /* ── Stats bar ── */
  .stats-bar {
    display: flex;
    gap: 16px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }

  .stat-pill {
    background: rgba(84,139,172,0.08);
    border: 1px solid rgba(84,139,172,0.2);
    border-radius: 20px;
    padding: 6px 14px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--wmc-mid);
    display: flex; align-items: center; gap: 6px;
  }

  .stat-pill .num {
    font-size: 14px;
    font-weight: 600;
    color: var(--wmc-light);
  }

  .stat-pill.deep { border-color: rgba(255,45,120,0.4); }
  .stat-pill.deep .num { color: var(--plasma-1); }
  .stat-pill.soh  { border-color: rgba(48,209,88,0.4); }
  .stat-pill.soh  .num { color: var(--plasma-3); }

  /* ── Filters ── */
  .filters {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;
  }

  .filter-label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--wmc-mid);
    opacity: 0.6;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-right: 4px;
  }

  .filter-btn {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(84,139,172,0.2);
    border-radius: 4px;
    padding: 5px 12px;
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    color: var(--wmc-mid);
    cursor: pointer;
    transition: all 0.15s;
    text-transform: uppercase;
  }

  .filter-btn:hover {
    border-color: var(--wmc-blue);
    color: var(--wmc-light);
  }

  .filter-btn.active {
    border-color: var(--wmc-blue);
    background: rgba(84,139,172,0.15);
    color: var(--wmc-light);
  }

  /* ── Log table ── */
  .log-table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 12px;
  }

  .log-table thead th {
    text-align: left;
    padding: 8px 12px;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--wmc-mid);
    opacity: 0.6;
    border-bottom: 1px solid rgba(84,139,172,0.2);
  }

  .log-row {
    border-bottom: 1px solid rgba(84,139,172,0.08);
    transition: background 0.15s;
    animation: row-in 0.3s ease forwards;
    opacity: 0;
  }

  @keyframes row-in {
    from { opacity: 0; transform: translateX(-6px); }
    to   { opacity: 1; transform: translateX(0); }
  }

  .log-row:hover { background: rgba(84,139,172,0.05); }

  .log-row td {
    padding: 10px 12px;
    vertical-align: top;
  }

  /* ── Timestamp ── */
  .col-time {
    color: var(--wmc-mid);
    opacity: 0.55;
    white-space: nowrap;
    font-size: 11px;
    width: 155px;
  }

  /* ── Level badge ── */
  .level-badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.1em;
    font-weight: 700;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .level-INFO     { background: rgba(84,139,172,0.15); color: #81a4c4; border: 1px solid rgba(84,139,172,0.3); }
  .level-WARNING  { background: rgba(255,159,10,0.12); color: #ff9f0a; border: 1px solid rgba(255,159,10,0.3); }
  .level-ALERT    { background: rgba(255,159,10,0.18); color: #ffcc00; border: 1px solid rgba(255,204,0,0.4); }
  .level-CRITICAL { background: rgba(255,45,120,0.15); color: #ff2d78; border: 1px solid rgba(255,45,120,0.4); }
  .level-MAYDAY   { background: rgba(191,90,242,0.18); color: #bf5af2; border: 1px solid rgba(191,90,242,0.5);
                    animation: mayday-pulse 1.4s ease-in-out infinite; }

  @keyframes mayday-pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(191,90,242,0); }
    50%     { box-shadow: 0 0 8px 2px rgba(191,90,242,0.4); }
  }

  /* ── Category badge ── */
  .cat-badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .cat-BATTERY  { color: #30d158; border: 1px solid rgba(48,209,88,0.3); }
  .cat-SEVERITY { color: #ff9f0a; border: 1px solid rgba(255,159,10,0.3); }
  .cat-CARE     { color: #0a84ff; border: 1px solid rgba(10,132,255,0.3); }
  .cat-SCENARIO { color: #bf5af2; border: 1px solid rgba(191,90,242,0.3); }
  .cat-SYSTEM   { color: #81a4c4; border: 1px solid rgba(84,139,172,0.3); }

  /* ── Title + detail ── */
  .col-title { color: var(--wmc-light); font-size: 12px; }
  .col-detail {
    color: var(--wmc-mid);
    font-size: 11px;
    opacity: 0.65;
    margin-top: 3px;
  }

  /* ── Value ── */
  .col-value {
    text-align: right;
    white-space: nowrap;
    color: var(--wmc-mid);
    font-size: 12px;
    width: 80px;
  }

  .val-soh { color: #30d158; }
  .val-soc { color: var(--wmc-blue); }
  .val-low { color: #ff2d78; }

  /* ── Battery tag ── */
  .batt-tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.08em;
    background: rgba(48,209,88,0.08);
    color: #30d158;
    border: 1px solid rgba(48,209,88,0.2);
    margin-top: 3px;
  }

  /* ── Empty state ── */
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--wmc-mid);
    opacity: 0.4;
    font-family: var(--mono);
    font-size: 13px;
    letter-spacing: 0.1em;
  }

  /* ── Loading ── */
  .loading {
    text-align: center;
    padding: 40px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--wmc-mid);
    opacity: 0.5;
    letter-spacing: 0.1em;
  }

  /* ── Refresh button ── */
  .refresh-btn {
    background: rgba(84,139,172,0.1);
    border: 1px solid rgba(84,139,172,0.3);
    border-radius: 4px;
    padding: 7px 16px;
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--wmc-mid);
    cursor: pointer;
    text-transform: uppercase;
    transition: all 0.15s;
  }
  .refresh-btn:hover {
    border-color: var(--wmc-blue);
    color: var(--wmc-light);
    background: rgba(84,139,172,0.18);
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(84,139,172,0.3); border-radius: 2px; }

  /* ── Animation delays for rows ── */
  .log-row:nth-child(1)  { animation-delay: 0.02s; }
  .log-row:nth-child(2)  { animation-delay: 0.04s; }
  .log-row:nth-child(3)  { animation-delay: 0.06s; }
  .log-row:nth-child(4)  { animation-delay: 0.08s; }
  .log-row:nth-child(5)  { animation-delay: 0.10s; }
  .log-row:nth-child(6)  { animation-delay: 0.12s; }
  .log-row:nth-child(7)  { animation-delay: 0.14s; }
  .log-row:nth-child(8)  { animation-delay: 0.16s; }
  .log-row:nth-child(9)  { animation-delay: 0.18s; }
  .log-row:nth-child(10) { animation-delay: 0.20s; }
</style>
</head>
<body>

<canvas id="stars"></canvas>

<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <a href="/">← OKi Home</a>
      <div>
        <div class="title">OKi <span>VESSEL LOGBOOK</span></div>
        <div class="subtitle">PERSISTENT EVENT RECORD — ALL TIME</div>
      </div>
    </div>
    <button class="refresh-btn" onclick="loadLog()">↺ Refresh</button>
  </div>

  <!-- Stats bar -->
  <div class="stats-bar" id="stats-bar">
    <div class="stat-pill">
      <span>Total events</span>
      <span class="num" id="stat-total">—</span>
    </div>
    <div class="stat-pill deep">
      <span>Deep cycles</span>
      <span class="num" id="stat-deep">—</span>
    </div>
    <div class="stat-pill soh">
      <span>SoH readings</span>
      <span class="num" id="stat-soh">—</span>
    </div>
    <div class="stat-pill" id="stat-last-pill">
      <span>Last event</span>
      <span class="num" id="stat-last">—</span>
    </div>
  </div>

  <!-- Filters -->
  <div class="filters">
    <span class="filter-label">Category</span>
    <button class="filter-btn active" data-filter="cat" data-val="">All</button>
    <button class="filter-btn" data-filter="cat" data-val="BATTERY">Battery</button>
    <button class="filter-btn" data-filter="cat" data-val="SEVERITY">Severity</button>
    <button class="filter-btn" data-filter="cat" data-val="CARE">Care</button>
    <button class="filter-btn" data-filter="cat" data-val="SCENARIO">Scenario</button>
    <button class="filter-btn" data-filter="cat" data-val="SYSTEM">System</button>

    <span class="filter-label" style="margin-left:12px">Min Level</span>
    <button class="filter-btn active" data-filter="level" data-val="">All</button>
    <button class="filter-btn" data-filter="level" data-val="WARNING">Warning+</button>
    <button class="filter-btn" data-filter="level" data-val="ALERT">Alert+</button>
    <button class="filter-btn" data-filter="level" data-val="CRITICAL">Critical+</button>
  </div>

  <!-- Log table -->
  <div id="log-container">
    <div class="loading">Loading vessel memory...</div>
  </div>

</div>

<script>
  // ── Stars ──
  (function() {
    const c = document.getElementById('stars');
    const ctx = c.getContext('2d');
    let stars = [];
    function resize() {
      c.width = window.innerWidth;
      c.height = window.innerHeight;
      stars = Array.from({length: 180}, () => ({
        x: Math.random() * c.width,
        y: Math.random() * c.height,
        r: Math.random() * 1.2 + 0.2,
        o: Math.random() * 0.5 + 0.1
      }));
    }
    function draw() {
      ctx.clearRect(0,0,c.width,c.height);
      stars.forEach(s => {
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
        ctx.fillStyle = `rgba(202,216,227,${s.o})`;
        ctx.fill();
      });
    }
    resize();
    draw();
    window.addEventListener('resize', () => { resize(); draw(); });
  })();

  // ── State ──
  let allEntries = [];
  let currentCat   = '';
  let currentLevel = '';

  // ── Fetch ──
  async function loadLog() {
    document.getElementById('log-container').innerHTML =
      '<div class="loading">Retrieving vessel memory...</div>';
    try {
      const res = await fetch('/api/log?limit=2000');
      const data = await res.json();
      allEntries = data.entries || [];

      // Stats
      document.getElementById('stat-total').textContent = data.total || 0;
      document.getElementById('stat-deep').textContent  = data.deep_cycle_count || 0;
      const sohCount = allEntries.filter(e => e.title && e.title.includes('SoH recorded')).length;
      document.getElementById('stat-soh').textContent   = sohCount;

      if (allEntries.length > 0) {
        const latest = allEntries[0].timestamp;
        document.getElementById('stat-last').textContent = formatRelative(latest);
      }

      render();
    } catch(e) {
      document.getElementById('log-container').innerHTML =
        '<div class="empty">No logbook data available.<br>The vessel memory begins when OKi starts recording.</div>';
    }
  }

  // ── Render ──
  function render() {
    const filtered = allEntries.filter(e => {
      if (currentCat   && e.category !== currentCat)   return false;
      if (currentLevel) {
        const order = {INFO:0, WARNING:1, ALERT:2, CRITICAL:3, MAYDAY:4};
        if ((order[e.level]||0) < (order[currentLevel]||0)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      document.getElementById('log-container').innerHTML =
        '<div class="empty">No events match the current filter.</div>';
      return;
    }

    let rows = filtered.map((e, i) => {
      const ts  = formatTimestamp(e.timestamp);
      const val = e.value_num !== null && e.value_num !== undefined
        ? `<span class="${valueClass(e)}">${e.value_num.toFixed(1)}${e.value_unit ? ' ' + e.value_unit : ''}</span>`
        : '';
      const battTag = e.battery_id
        ? `<div class="batt-tag">${e.battery_id}</div>` : '';
      const detail = e.detail
        ? `<div class="col-detail">${e.detail}</div>` : '';

      return `<tr class="log-row">
        <td class="col-time">${ts}</td>
        <td><span class="level-badge level-${e.level}">${e.level}</span></td>
        <td><span class="cat-badge cat-${e.category}">${e.category}</span></td>
        <td class="col-title">
          ${e.title}
          ${detail}
          ${battTag}
        </td>
        <td class="col-value">${val}</td>
      </tr>`;
    }).join('');

    document.getElementById('log-container').innerHTML = `
      <table class="log-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Level</th>
            <th>Category</th>
            <th>Event</th>
            <th style="text-align:right">Value</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ── Value colour ──
  function valueClass(e) {
    if (!e.value_unit) return '';
    if (e.value_unit.includes('SoH') || e.title.includes('SoH')) return 'val-soh';
    if (e.value_unit.includes('SoC') && e.value_num < 30)        return 'val-low';
    return 'val-soc';
  }

  // ── Time formatting ──
  function formatTimestamp(iso) {
    try {
      const d = new Date(iso);
      const date = d.toLocaleDateString('en-GB', {day:'2-digit', month:'short', year:'numeric'});
      const time = d.toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
      return `${date} ${time}`;
    } catch { return iso; }
  }

  function formatRelative(iso) {
    try {
      const diff = Date.now() - new Date(iso).getTime();
      const m = Math.floor(diff/60000);
      if (m < 1) return 'just now';
      if (m < 60) return m + 'm ago';
      const h = Math.floor(m/60);
      if (h < 24) return h + 'h ago';
      return Math.floor(h/24) + 'd ago';
    } catch { return '—'; }
  }

  // ── Filter buttons ──
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const filter = btn.dataset.filter;
      document.querySelectorAll(`.filter-btn[data-filter="${filter}"]`)
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (filter === 'cat')   currentCat   = btn.dataset.val;
      if (filter === 'level') currentLevel = btn.dataset.val;
      render();
    });
  });

  // ── Auto-refresh every 30s ──
  loadLog();
  setInterval(loadLog, 30000);
</script>
</body>
</html>
"""
