# AgentFlow AI

**Explainable Predictive Liquidity Orchestration for MFS Agent Networks**

> Predict. Explain. Rebalance.

AgentFlow predicts where a Mobile Financial Services (MFS) agent may run short of
liquidity before customers are affected, explains why, and recommends a safe,
human-reviewed rebalancing action.

Built for the **AI DEV FEST 2026 AI Hackathon** (DIU CPC × upay).

> ⚠️ All data in this repository is **synthetic data for hackathon prototyping — not
> production upay data**. AgentFlow is a decision-support prototype: it never moves real money.

---

## Status

🚧 Under active development during the hackathon window. Sections below are filled in
as each milestone lands.

## Repository structure

```
agentflow-ai/
  apps/
    api/        FastAPI service (prediction, risk, rebalancing, impact APIs)
    web/        Next.js + TypeScript + Tailwind operations dashboard
  ml/
    agentflow/  Core Python package: data generation, features, models, risk, rebalancing, impact
    scripts/    Reproducible CLI entry points (generate, train, evaluate)
    data/       Generated synthetic data (git-ignored, reproducible)
    models/     Trained model binaries (git-ignored, reproducible)
    artifacts/  Machine-readable evaluation results (committed)
  docs/         Architecture, data card, model card, evaluation, demo script
  tests/        Backend / ML test-suite (pytest)
```

## Quick start

```bash
pip install -r requirements.txt          # Python 3.11+
cd apps/web && npm install               # Node 20+
```

Detailed run, training, evaluation and testing instructions are added as the
corresponding milestones are completed.
