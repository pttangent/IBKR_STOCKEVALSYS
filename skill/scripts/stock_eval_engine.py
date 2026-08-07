#!/usr/bin/env python3
"""Compatibility CLI wrapper for the skill-root engine."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_eval_engine import main

if __name__ == "__main__":
    main()
