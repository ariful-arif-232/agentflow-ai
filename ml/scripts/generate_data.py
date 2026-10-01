"""Generate the deterministic synthetic MFS agent dataset.

Usage:  python ml/scripts/generate_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import config, data_gen  # noqa: E402


def main() -> None:
    data = data_gen.generate()
    data_gen.save(data)
    h = data.hourly
    summary = {
        "label": "Synthetic data for hackathon prototyping — not production upay data",
        "seed": config.SEED,
        "n_agents": int(data.agents.shape[0]),
        "n_rows": int(h.shape[0]),
        "start": str(h["timestamp"].min()),
        "end": str(h["timestamp"].max()),
        "test_start": str(config.TEST_START),
        "shortage_agent_hours": int(h["liquidity_shortage"].sum()),
        "anomaly_rows": int(h["known_anomaly_label"].sum()),
        "anomaly_types": {k: int(v) for k, v in h.loc[h["known_anomaly_label"] == 1, "anomaly_type"].value_counts().items()},
        "agents_by_cluster": data.agents["location_cluster"].value_counts().to_dict(),
        "agents_by_segment": data.agents["agent_volume_segment"].value_counts().to_dict(),
        "agents_by_district": data.agents["district"].value_counts().to_dict(),
    }
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.ARTIFACTS_DIR / "dataset_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
