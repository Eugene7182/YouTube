import importlib
import sys
from pathlib import Path

# Ensure the project root is on sys.path so top-level modules can be imported
# when this script is executed from the `scripts/` directory.
PRJ_ROOT = Path(__file__).resolve().parent.parent
if str(PRJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PRJ_ROOT))

modules = [
    "generate_script",
    "tts",
    "scripts.render_short",
    "core.generate",
    "core.scheduler",
]

errs = []
for m in modules:
    try:
        importlib.import_module(m)
        print("OK:", m)
    except Exception as e:
        print("ERR:", m, "->", repr(e))
        errs.append((m, str(e)))

if errs:
    print("\nTotal errors:", len(errs))
    sys.exit(2)
else:
    print("\nSmoke test passed")
