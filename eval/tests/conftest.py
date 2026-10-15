"""Make the eval scripts importable. They run as plain scripts (python eval/wer.py), so they import each other as
top-level modules from eval/ and eval/goldset/."""

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
for path in (EVAL_DIR, EVAL_DIR / "goldset"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
