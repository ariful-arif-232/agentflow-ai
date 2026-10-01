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
* **Projected service readiness 71.5% → 77.0% with the recommended plan.**
* **Recommended rebalancing BDT 4.0 lakh** across 21 peer transfers; BDT 5.8 lakh escalated.
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

Click **Review recommendation** → Rebalancing Center (AG-0171 rows highlighted) → **Review
Recommendation** on **RB-019** (AG-0183 → AG-0171, BDT 22,500, 6.2 km, Rangpur).

Explain why the donor stays safe:
* donor is LOW risk, same district, nearest eligible surplus agent;
* the red marker = donor protected level (110% of its own P90 requirement) — never crossed;
* together with RB-020 (AG-0178, BDT 16,000) AG-0171 goes **HIGH 53 → LOW 5**.

## 5. Approve Simulation (≈ 20 s)

Tick *"I have reviewed the evidence above"* → **Approve Simulation**.
> "Nothing moved. This is a what-if, written to the audit log with my note. A human stays accountable."

## 6. Risk before vs. estimated risk after (≈ 15 s)

The simulation card shows AG-0171 and AG-0183 cash and risk before → after, plus portfolio
at-risk agents, expected shortfall and service readiness before → after.

Optional (10 s): move the decision time to **19:00** and reopen AG-0171 — without action its cash hits
**BDT 0 at 19:00 and BDT 11,830 of cash-out is turned away** (red bar), exactly inside the 6-hour
window flagged at 13:00.

## 7. Impact page — "what measurable outcome improves?" (≈ 45 s)

Open **Impact & Model Health**.
> "We replayed the last 14 days — never seen in training — hour by hour with identical customer
> demand and identical total cash."

* Shortage events **2,017 → 1,255 (−37.8%)**.
* Unmet cash demand **−38.9%, BDT 37.1 lakh avoided** — with **BDT 0** extra cash injected.
* Service availability **96.76% → 97.92%**.
* Middle column: the same engine with a naive forecast only reaches 1,483 events → the ML matters.
* Be upfront: ~21% of transfers weren't strictly needed; 25 donor shortage events in 501 transfers.

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
