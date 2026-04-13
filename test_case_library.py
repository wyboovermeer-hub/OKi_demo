from pathlib import Path
import sys

# Add 02_OKi_Knowledge to Python path
sys.path.append(
    str(Path(__file__).resolve().parents[1] / "02_OKi_Knowledge")
)

from case_library import CASE_LIBRARY

print("Loaded cases:")
print(CASE_LIBRARY.list_cases())

print("\nSearch for 'deep':")
results = CASE_LIBRARY.search_cases("deep")

for case in results:
    print(f"{case['case_id']} - {case['title']}")