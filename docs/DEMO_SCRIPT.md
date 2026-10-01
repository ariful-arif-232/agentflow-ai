# Demo Script — AgentFlow AI (3–5 minutes)

**One-line story:** *AgentFlow predicts where an MFS agent may run short of liquidity before
customers are affected, explains why, and recommends a safe, human-reviewed rebalancing action.*

## Before you start (2 minutes, once)

```bash
python ml/scripts/run_pipeline.py              # only if ml/models is empty
cd apps/api && uvicorn app.main:app --port 8000
cd apps/web && npm run dev                     # open http://localhost:3000
```

* Decision time in the top bar: **Mon, 31 Aug · 13:00** (default; click *Reset* if changed).
* Restart the API right before recording so the simulation audit log is empty.
* Backup: screenshots of each step + a screen recording; `ml/artifacts/*.json` hold every number.

All values below are from the default decision time and are deterministic.

---

## 1. Command Center — "what is likely to happen?" (≈ 40 s)

Say:
> "It's 1 pm on a salary-period Monday across a network of 200 synthetic agents. AgentFlow has
> forecast every agent's cash needs for the next 6 hours."

Point at:
* **25 at-risk agents, 7 critical**, 32 more at MEDIUM.
* **Projected service readiness 71.5% → 77.5% with the recommended plan** (rebalancing policy V2).
* **Recommended rebalancing BDT 4.7 lakh** across 14 peer transfers; BDT 5.0 lakh escalated.
* The 48-hour chart: the blue 6-hour forecast line tracks the dotted actual line.
* Tags on each card: *ML prediction* vs. *deterministic calculation*.

## 2. Agent Intelligence — one high-risk agent (≈ 60 s)

Agents → filter **HIGH** → open **AG-0171** (Rangpur, urban periphery).

> "AG-0171 still has cash and no customer has been turned away yet. That's the point: we see it coming."

* Current cash **BDT 20,640**.
* Forecast 6-hour cash-out demand **BDT 82,200**; forecast *peak cash requirement* **BDT 38,675**
  (P90 scenario **BDT 59,387**).
* Expected shortfall **BDT 18,035**, coverage **53%**, risk **53 / 100 — HIGH**.

## 3. "Why this risk?" (≈ 30 s)

Read the evidence list (generated from the numbers, not a chatbot):
1. Forecast peak requirement BDT 38,675 (P90 BDT 59,387).
2. Current cash covers about 53%.
3. Expected shortfall BDT 18,035.
4. In a P90 scenario the gap widens to BDT 38,747.
5. Short of cash in 18.5% of operating hours historically.
Context: this window historically sees 58% more cash-out than average; salary period.

Point at the component bars: coverage 25.8 / 45, tail 13.0 / 20, deficit 9.0 / 20, history 5 / 5.
> "Anomalies don't change this score; unusual activity changes the review route, not the liquidity math."

Click **বাংলায় ব্যাখ্যা করুন**: the same evidence rendered deterministically in Bangla for field and
agent-facing staff, with no language model involved.

## 4. Safe rebalancing recommendation (≈ 40 s)

Click **Review recommendation** → Rebalancing Center (policy **V2**, the default; AG-0171 row
highlighted) → **Review Recommendation** on **RB-013** (AG-0181 → AG-0171, BDT 38,500, 12.2 km, Rangpur).

Explain why this donor was chosen and why it stays safe:
* one transfer covers the whole need, taking AG-0171 **HIGH 53 → LOW 5** and cutting the expected shortfall
  by BDT 18,035, so it passes the minimum-benefit gate;
* the donor is LOW risk, in the same district, and stays LOW; the red marker is its **dynamic protected
  reserve** (BDT 48,420), which grows with forecast uncertainty, velocity and shortage history. It keeps
  BDT 4,430 above it;
* toggle to **V1** for comparison: V1 needs two transfers (RB-019 + RB-020, from the nearest donors) to
  reach the same result.

## 5. Approve Simulation (≈ 20 s)

Tick *"I have reviewed the evidence above"* → **Approve Simulation**.
> "Nothing moved. This is a what-if, written to the audit log with my note. A human stays accountable."

## 6. Risk before vs. estimated risk after (≈ 15 s)

The simulation card shows AG-0171 and AG-0181 cash and risk before → after, plus portfolio
at-risk agents, expected shortfall and service readiness before → after.

Optional (10 s): move the decision time to **19:00** and reopen AG-0171 — without action its cash hits
**BDT 0 at 19:00 and BDT 11,830 of cash-out is turned away** (red bar), exactly inside the 6-hour
window flagged at 13:00.

## 7. Impact page — "what measurable outcome improves?" (≈ 45 s)

Open **Impact & Model Health**.
> "We replayed the last 14 days — never seen in training — hour by hour with identical customer
> demand and identical total cash."

* With the default policy V2: shortage events **2,017 → 1,223 (−39.4%)**.
* Unmet cash demand **−40.3%, BDT 38.5 lakh avoided**, with **BDT 0** extra cash injected.
* Service availability **96.76% → 97.95%**.
* Policy comparison: the naive forecast reaches only 1,483 events, so the ML matters. V2 vs V1: slightly
  more benefit with **345 vs 501 transfers**, **14 vs 25 donor shortages** and **BDT 1.15 vs 1.58 lakh**
  logistics cost. V2's settings were chosen on training-period practice windows only.
* Be upfront: 24.3% of V2's transfers weren't strictly needed (V1: 21.4%), and donors still ran short
  14 times.

## 8. Baseline vs. ML (≈ 20 s)

Scroll to Model health:
* cash-demand MAE **BDT 6,138** vs. 9,691 naive / 7,890 seasonal (**−22%** vs. the best baseline);
* P90 band covers **89.5%** (target 90%);
* HIGH+ alerts: **81.5% precision**, ROC-AUC 0.935.

## 9. Close — responsible AI (≈ 20 s)

> "Synthetic data, no PII. Every risk is explained from evidence. Every action is human-reviewed and
> only simulated. Unusual activity is routed to manual review, never labelled fraud. The pipeline is
> reproducible and ready for validation on real, consented data in shadow mode."

Optional if time allows: **Scenario Lab** → +25% demand shock → at-risk agents 25 → 31 and escalated
need grows; this shows where peer rebalancing stops being enough.
