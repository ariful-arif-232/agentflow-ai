"""Central configuration: paths, seeds and dataset/time-split constants."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ML_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_DIR.parent
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
ARTIFACTS_DIR = ML_DIR / "artifacts"

DATASET_PATH = DATA_DIR / "agent_hourly.parquet"
AGENTS_PATH = DATA_DIR / "agents.parquet"

SEED = 2026
N_AGENTS = 200
START = pd.Timestamp("2026-06-17 00:00")
N_DAYS = 76  # 2026-06-17 .. 2026-08-31 inclusive
HORIZON_H = 6  # forecast horizon in hours

# Time-based split. Everything before TEST_START is training data; the last
# 14 days (~18% of the timeline) are held out for evaluation and impact simulation.
TEST_START = pd.Timestamp("2026-08-18 00:00")

CURRENCY = "BDT"
