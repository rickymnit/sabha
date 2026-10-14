"""Make the gold-set scripts importable. They are run as plain scripts (python eval/goldset/x.py),
so they import each other as top-level modules; P1.1 will turn eval/ into a workspace package."""

import sys
from pathlib import Path

GOLDSET_DIR = Path(__file__).resolve().parents[1]
if str(GOLDSET_DIR) not in sys.path:
    sys.path.insert(0, str(GOLDSET_DIR))
