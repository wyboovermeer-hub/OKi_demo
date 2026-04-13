"""
OKi — case_library path fix
Drop this at the top of 02_OKi_Knowledge/case_library.py
(replace any existing hard-coded or relative path logic).

Works correctly whether the process is started from the project root,
a subdirectory, or a cloud runner with an arbitrary working directory.
"""

from pathlib import Path

# Resolve the directory that THIS file lives in — always correct on any OS
# and in any working-directory context (local, Render, Docker, etc.)
_CASES_DIR = Path(__file__).resolve().parent / "cases"


def get_cases_dir() -> Path:
    """Return the absolute path to the cases/ folder next to this file."""
    return _CASES_DIR


def load_case(filename: str) -> str:
    """
    Load a case file by name from the cases/ directory.
    Returns empty string if the file does not exist — never raises.
    """
    target = _CASES_DIR / filename
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


def list_cases() -> list[str]:
    """
    Return a sorted list of case filenames.
    Returns empty list if the cases/ directory is missing — never raises.
    """
    if not _CASES_DIR.exists():
        return []
    return sorted(p.name for p in _CASES_DIR.iterdir() if p.is_file())
