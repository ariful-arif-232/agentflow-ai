"""End-to-end reproducible pipeline: generate data -> train -> evaluate.

Usage:  python ml/scripts/run_pipeline.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    for step in ("generate_data.py", "train.py", "evaluate.py"):
        print(f"\n=== {step} ===")
        runpy.run_path(str(HERE / step), run_name="__main__")
