# OKi — Render Deployment Checklist

## Files added / changed

| File | Action |
|------|--------|
| `requirements.txt` | **New** — pip dependencies |
| `Procfile` | **New** — Render start command |
| `demo_scenario.py` | **New** — generator-failure demo state |
| `case_library_path_fix.py` | **Reference** — paste into `02_OKi_Knowledge/case_library.py` |
| `web_server_additions.py` | **Reference** — three sections to merge into `web_server.py` |

---

## Apply changes

### 1. `02_OKi_Knowledge/case_library.py`
Replace (or prepend) the path/loading logic with the contents of
`case_library_path_fix.py`. The key line is:

```python
_CASES_DIR = Path(__file__).resolve().parent / "cases"
```

### 2. `web_server.py`

Merge **three sections** from `web_server_additions.py`:

- **Section A** — safe imports + knowledge path guard → near top, after existing imports  
- **Section B** — `_build_initial_state()` + `app_state` init → before `app = FastAPI(...)`  
  Replace your existing global state initialisation with:
  ```python
  app_state: dict = _build_initial_state()
  ```
- **Section C** — `__main__` block → bottom of file

---

## Render service settings

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn web_server:app --host 0.0.0.0 --port 10000` |
| Environment variable (optional) | `PORT=10000` |

The `Procfile` handles the start command automatically if Render detects it.

---

## Expected demo behaviour on load

On first page load, after one engine cycle, the UI should surface:

```
Primary:   "Limited energy remaining"
Secondary: "Battery will reach critical level in ~2 hours.
            No charging source is currently active."
Question:  "Do you plan to restore charging?"
Options:   A: Start generator  B: Reduce consumption  C: Not yet
```

SituationType will be `CRITICAL_COUNTDOWN`, DecisionWindow `LIMITED`.

---

## Port note

The `__main__` block reads `$PORT` from the environment with a fallback of
`10000`, so Render can override it via env var if needed without a code change.
