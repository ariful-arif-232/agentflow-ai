# Model Drift & Data Quality (Phase 2)

**Synthetic monitoring prototype - not live upay telemetry.** This is a read-only,
retrospective comparison of six existing intraday forecast inputs, not a live
accuracy monitor. Morning Plan and all serving decisions are unchanged.

## What is checked

Latest cash-out, historical same-window cash-out, 7-day average cash-out, recent
cash-in, 3-hour transaction count and transaction velocity. The reference uses
training inputs after seven days of feature warm-up and before the six-hour split
gap; the comparison uses held-out inputs, including final hours whose future
outcomes are not yet known. Missing values remain in quality denominators.

PSI = sum((current proportion - reference proportion) * ln(current/reference)).
Up to ten quantile bins are fitted on the reference only, duplicate edges are
collapsed, constant references are isolated, and tails are open-ended. Each bin
proportion receives 1e-6 smoothing and is normalised. Under 100 valid values in
either window yields INSUFFICIENT_DATA. Review thresholds (STABLE <0.10, WATCH
0.10 to <0.25, DRIFT >=0.25) are illustrative, not calibrated operator thresholds.

Missing, invalid/non-finite, negative and fractional-count cells are reported
separately. These are cell counts, not unique customer or agent counts. Drift or
quality issues recommend human review only. Input shift does not prove concept
drift, lost accuracy or fraud; seasonality and agent mix can also cause shifts.
No live freshness/missing-hour checks, automatic alerts, retraining or transfers.

## Reproduce and show

`python ml/scripts/model_monitoring.py` reads generated data and writes only
`ml/artifacts/model_monitoring.json` (version `phase2-monitoring-1`). It does not
load, fit or save models. The full pipeline and Docker build also generate it.
`GET /api/model-monitoring` reads that artifact, never recomputes on a request,
and returns an explicit unavailable error when missing/corrupt rather than a
healthy badge. The Impact page appends the card without changing existing cards.

Tests cover deterministic output, constant-reference shifts, training-only bins,
quality counts, missing columns, split boundaries, read-only API and unavailable
states. All pre-existing regression tests still apply. The feature adds no
external dependency, infrastructure, secrets or real operator data.
