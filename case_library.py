# ============================================================
# OKi CASE LIBRARY v1.1
# Knowledge Case Loader and Search Engine
# ============================================================
#
# Changelog v1.1
# ---------------
# • Path fixed: uses Path(__file__).resolve().parent / "cases"
#   — works correctly on any OS and any cloud runner (Render, Docker, etc.)
# • Missing cases/ folder is handled gracefully — never crashes startup
# • CASE_LIBRARY singleton preserved for all existing callers
#
# ============================================================

import json
from pathlib import Path
from dataclasses import dataclass, asdict

# ── Path — always resolved from this file's location, never from cwd ──────────
_CASES_DIR = Path(__file__).resolve().parent / "cases"


# ============================================================
# CASE DATA CLASS
# ============================================================

@dataclass
class Case:
    case_id:    str
    title:      str = ""
    root_cause: str = ""
    solution:   str = ""
    symptoms:   list = None
    conditions: list = None
    actions:    list = None

    def to_dict(self):
        return asdict(self)


# ============================================================
# CASE LIBRARY CLASS
# ============================================================

class CaseLibrary:

    def __init__(self):
        self.cases = {}
        print("\nOKi Knowledge System Initializing")
        self.load_cases()
        print(f"OKi Knowledge System Ready ({len(self.cases)} cases loaded)\n")

    # ──────────────────────────────────────────────────────────
    # LOAD
    # ──────────────────────────────────────────────────────────

    def load_cases(self):
        # Safe guard — missing folder never crashes startup
        if not _CASES_DIR.exists():
            print(f"[OKi] cases/ folder not found at {_CASES_DIR} — continuing without cases")
            return

        json_files = list(_CASES_DIR.glob("*.json"))

        if not json_files:
            print("No case files found in knowledge directory.")
            return

        for file in json_files:
            try:
                if file.stat().st_size == 0:
                    print(f"Skipping empty case file: {file.name}")
                    continue

                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for item in data:
                    case_id = item.get("case_id")
                    if not case_id:
                        print(f"Skipping case without case_id in file: {file.name}")
                        continue

                    self.cases[case_id] = Case(
                        case_id    = case_id,
                        title      = item.get("title", ""),
                        root_cause = item.get("root_cause", ""),
                        solution   = item.get("solution", ""),
                        symptoms   = item.get("symptoms", []),
                        conditions = item.get("conditions", []),
                        actions    = item.get("actions", []),
                    )

            except json.JSONDecodeError:
                print(f"Invalid JSON in case file: {file.name}")
            except Exception as e:
                print(f"Error reading case file {file.name}: {e}")

    # ──────────────────────────────────────────────────────────
    # SEARCH
    # ──────────────────────────────────────────────────────────

    def search_cases(self, text):
        if not text:
            return []

        tokens = [t for t in text.lower().split() if t]
        if not tokens:
            return []

        scored = []

        for case in self.cases.values():
            searchable = " ".join([
                case.title      or "",
                case.root_cause or "",
                case.solution   or "",
                " ".join(case.symptoms   or []),
                " ".join(case.conditions or []),
                " ".join(case.actions    or []),
            ]).lower()

            # Require ALL tokens to appear somewhere in the searchable text
            hits = sum(1 for t in tokens if t in searchable)
            if hits == len(tokens):
                scored.append((hits, case))

        # Sort by score descending (most relevant first)
        scored.sort(key=lambda x: x[0], reverse=True)
        return [case for _, case in scored]

    # ──────────────────────────────────────────────────────────
    # GET / LIST
    # ──────────────────────────────────────────────────────────

    def get_case(self, case_id):
        return self.cases.get(case_id)

    def list_cases(self):
        """Return list of all case_ids — for test_case_library.py compatibility."""
        return list(self.cases.keys())

    def all_cases(self):
        return list(self.cases.values())


# ── Singleton — imported as CASE_LIBRARY throughout the engine ────────────────
CASE_LIBRARY = CaseLibrary()
