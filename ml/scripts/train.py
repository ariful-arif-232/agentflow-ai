"""Train AgentFlow models on the training period only.

Usage:  python ml/scripts/train.py
(Generates the synthetic dataset first if it does not exist.)
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from agentflow import config, data_gen, features, forecast


def main() -> None:
    if not config.DATASET_PATH.exists():
        print("Dataset not found - generating ...")
        data_gen.save(data_gen.generate())
    data = data_gen.load()
    feats = features.build_features(data.hourly, data.agents)
    train_df, test_df = features.time_split(feats)
    print(f"train rows={len(train_df):,} ({train_df.timestamp.min()} .. {train_df.timestamp.max()})")
    print(f"test rows={len(test_df):,} ({test_df.timestamp.min()} .. {test_df.timestamp.max()}) [not used]")

    bundle = forecast.train(train_df)
    bundle.save()
    forecast.write_json(config.ARTIFACTS_DIR / "training_metadata.json",
                        {**bundle.metadata, "features": bundle.features})
    print("forecast models saved ->", forecast.MODEL_PATH)
    print("fit seconds:", bundle.metadata["fit_seconds"])


if __name__ == "__main__":
    main()
