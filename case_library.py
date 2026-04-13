# ============================================================
# OKi CASE LIBRARY
# Knowledge Case Loader and Search Engine
# ============================================================

import json
from pathlib import Path
from dataclasses import dataclass, asdict


# ============================================================
# CASE DATA CLASS
# ============================================================

@dataclass
class Case:
    case_id: str
    title: str = ""
    root_cause: str = ""
    solution: str = ""
    symptoms: list = None
    conditions: list = None
    actions: list = None

    def to_dict(self):
        return asdict(self)


# ============================================================
# CASE LIBRARY CLASS
# ============================================================

class CaseLibrary:

    def __init__(self):

        # Dictionary containing all loaded cases
        self.cases = {}

        # ── Path fix ──────────────────────────────────────────────────────────
        # Path(__file__).resolve().parent always points to the 02_OKi_Knowledge/
        # folder regardless of working directory, OS, or cloud runner.
        # This replaces any previous use of os.getcwd() or relative "../" paths.
        self.knowledge_dir = Path(__file__).resolve().parent / "cases"

        print("\nOKi Knowledge System Initializing")

        # Load cases on startup
        self.load_cases()

        print(f"OKi Knowledge System Ready ({len(self.cases)} cases loaded)\n")

    # ============================================================
    # LOAD CASE FILES
    # ============================================================

    def load_cases(self):

        # Safe guard: if cases/ folder is missing, log and continue — never crash
        if not self.knowledge_dir.exists():
            print(f"[OKi] cases/ folder not found at {self.knowledge_dir} — continuing without cases")
            return

        json_files = list(self.knowledge_dir.glob("*.json"))

        if not json_files:
            print("No case files found in knowledge directory.")
            return

        for file in json_files:

            try:

                # Skip empty files
                if file.stat().st_size == 0:
                    print(f"Skipping empty case file: {file.name}")
                    continue

                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # data is a list of case dictionaries
                for item in data:
                    case_id = item.get("case_id")

                    if not case_id:
                        print(f"Skipping case without case_id in file: {file.name}")
                        continue

                    case = Case(
                        case_id=case_id,
                        title=item.get("title", ""),
                        root_cause=item.get("root_cause", ""),
                        solution=item.get("solution", ""),
                        symptoms=item.get("symptoms", []),
                        conditions=item.get("conditions", []),
                        actions=item.get("actions", []),
                    )

                    self.cases[case_id] = case

            except json.JSONDecodeError:
                print(f"Invalid JSON in case file: {file.name}")
                continue

            except Exception as e:
                print(f"Error reading case file {file.name}: {e}")
                continue

    # ============================================================
    # SEARCH CASES
    # ============================================================

    def search_cases(self, text):

        if not text:
            return []

        text = text.lower()

        results = []

        for case in self.cases.values():

            searchable_text = " ".join([
                case.title or "",
                case.root_cause or "",
                case.solution or "",
                " ".join(case.symptoms or []),
            ]).lower()

            if text in searchable_text:
                results.append(case)

        return results

    # ============================================================
    # GET SINGLE CASE
    # ============================================================

    def get_case(self, case_id):
        return self.cases.get(case_id)

    # ============================================================
    # GET ALL CASES
    # ============================================================

    def all_cases(self):
        return list(self.cases.values())


# ── Singleton — imported as CASE_LIBRARY throughout the engine ────────────────
CASE_LIBRARY = CaseLibrary()
