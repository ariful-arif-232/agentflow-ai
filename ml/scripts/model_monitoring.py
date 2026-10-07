"""Generate only the retrospective input-monitoring artifact (no model training)."""
from __future__ import annotations

import json

import _bootstrap  # noqa: F401
from agentflow import config, data_gen, features, model_monitoring


def main() -> None:
    data = data_gen.load()
    feats = features.build_features(data.hourly, data.agents)
    report = model_monitoring.build_report(feats, config.TEST_START, config.HORIZON_H)
    path = config.ARTIFACTS_DIR / "model_monitoring.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print("[monitoring]", json.dumps(report["summary"], sort_keys=True))
    for item in report["features"]:
        print("[monitoring feature]", item["name"], item["status"], item["psi"])
    print("Monitoring ->", path, "(offline synthetic input monitoring; human review only)")


if __name__ == "__main__":
    main()
