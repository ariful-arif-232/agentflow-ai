import sys
from pathlib import Path

import os

import pytest

# The suite makes many simulation calls from one test client; dedicated tests exercise the limiter with
# their own small limits. Audit stays in memory unless a test sets a path explicitly.
os.environ.setdefault("AGENTFLOW_RATE_LIMIT_SIMULATIONS", "10000")
os.environ.pop("AGENTFLOW_AUDIT_LOG_PATH", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from agentflow import data_gen, features  # noqa: E402


@pytest.fixture(scope="session")
def small_data():
    """A small (24-agent) but full-length deterministic dataset for fast tests."""
    return data_gen.generate(seed=7, n_agents=24)


@pytest.fixture(scope="session")
def small_features(small_data):
    return features.build_features(small_data.hourly, small_data.agents)


@pytest.fixture(scope="session")
def small_bundle(small_features):
    from agentflow import forecast
    train, _ = features.time_split(small_features)
    return forecast.train(train, max_iter=60)
