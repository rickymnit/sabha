"""Make the rater scripts importable; they run as plain scripts (python eval/raters/x.py)."""

import sys
from pathlib import Path

RATERS_DIR = Path(__file__).resolve().parents[1]
if str(RATERS_DIR) not in sys.path:
    sys.path.insert(0, str(RATERS_DIR))
