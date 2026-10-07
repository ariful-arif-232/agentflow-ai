# AgentFlow AI — Team Briefing

**For our registered teammates, to study before judging.**

Our team is a registered **3-member team**. All engineering on this repository was done by **one
primary implementer**, and the development workflow was organised around that. This briefing gives
the other two members everything they need to explain the project accurately.

> Golden rule: if you are not sure about a number or a feature, say *"Let me show you on the
> dashboard"* or *"Our primary implementer can answer that in detail"*. Never guess. Every number
> below comes from the current code and the files in `ml/artifacts/`.

---

## 1. The project in 30 seconds

**AgentFlow AI predicts where an MFS agent may run short of cash before customers are affected,
explains why, and recommends a safe, human-reviewed rebalancing action.**

It forecasts each agent's cash needs for the next 6 hours, gives every agent a risk score from 0 to
100 with plain-language reasons, and suggests moving spare cash from a nearby safe agent. A person must
review and approve each suggestion, and approval only runs a simulation. No real money ever moves.

## 2. The project in 60 seconds

MFS agents (the shops where customers cash out and cash in) need physical cash. Demand changes by hour
of day, by weekday, around salary days and on local market days. When an agent runs out of cash,
customers are turned away.

AgentFlow does four things:

1. **Predicts** each agent's cash demand and peak cash need for the next 6 hours using machine learning.
2. **Scores risk** (0–100, LOW / MEDIUM / HIGH / CRITICAL) with a transparent formula and lists the reasons.
3. **Recommends** moving cash from a nearby agent who has a safe surplus, with strict safety rules.
4. **Measures impact**: on 14 held-out days the model never saw, the default rebalancing policy (V2)
   cut shortage events by **39.4%** and unmet cash demand by **40.3%**, without adding any extra cash to
   the network. It used 345 transfers; the original policy V1 achieved −37.8% / −38.9% with 501.

All data is **synthetic** (computer-generated). These are simulation results, not real upay results.

## 3. The project in 3 minutes

**The problem.** An MFS agent's cash drawer is like a small ATM. In our simulated "status quo", each
agent's drawer is reset to a fixed amount every morning at 08:00. That fixed amount ignores salary
days, market days and sudden spikes, so many agents run dry in the afternoon or evening. Over the
14 test days, 140 of 200 agents ran short at least once, and BDT 95.4 lakh of cash-out requests
could not be served.

**What AgentFlow does: the loop.**
FORECAST → RISK → EXPLAIN → RECOMMEND → HUMAN REVIEW → SIMULATE → MEASURE IMPACT

1. **Forecast.** Machine-learning models predict, for every agent, the cash-out demand over the next
   6 hours and the *peak amount of cash the agent will need on hand* in that window, plus a
   cautious "90th-percentile" version.
2. **Risk.** A fixed, transparent formula compares the agent's current cash with that forecast and
   produces a 0–100 score.
3. **Explain.** The screen lists the reasons as sentences built from the numbers, for example
   "Current cash of BDT 20,640 covers about 53% of that requirement". A Bangla button shows the same
   reasons in Bangla.
4. **Recommend.** The system suggests moving cash from a nearby agent who has more than they need,
   in the same district and within 15 km. With the default **policy V2**, a transfer is only suggested
   if it really helps the recipient. The donor keeps a safety reserve that grows when its own forecast
   is uncertain or it is busier than usual, and it must stay LOW risk.
5. **Human review.** A reviewer opens the evidence, ticks "I have reviewed the evidence above", and
   clicks **Approve Simulation**. That runs a what-if calculation and writes an audit-log entry.
   Nothing is sent and no money moves.
6. **Measure.** We replayed the last 14 days hour by hour, with exactly the same customer demand,
   without AgentFlow and with each version of its rebalancing policy.

**Results (synthetic held-out simulation):**

| | Without AgentFlow | AgentFlow V1 | **AgentFlow V2 (default)** |
|---|---:|---:|---:|
| Shortage events (agent-hours) | 2,017 | 1,255 (−37.8%) | **1,223 (−39.4%)** |
| Unmet cash demand | BDT 95.4 lakh | BDT 58.3 lakh | **BDT 56.9 lakh (BDT 38.5 lakh avoided)** |
| Service availability | 96.76% | 97.92% | **97.95%** |
| Transfers | — | 501 | **345** |
| Extra cash added to the network | — | BDT 0 | BDT 0 |

**Why it is credible.** We compare the ML model against simple baselines and report where it is only
slightly better. We report the costs (unnecessary transfers, donor risk). Anyone can rerun everything
with one command. With the pinned project environment, the evaluated decision outputs,
business-impact metrics and demo values reproduce. Runtime timing metadata is excluded, and tiny
cross-machine floating-point variation may occur in internal anomaly thresholds.

---

## 4. The problem we solve

- Agents need **cash** to pay customers who cash out, and **e-float** (electronic balance) to serve
  customers who cash in.
- Demand is uneven: two daily peaks, a weekend dip (Friday/Saturday), higher demand around salary days
  (days 27–3), and weekly market days in rural areas.
- A fixed daily cash level cannot follow these swings, so shortages happen at predictable times.
- Today, rebalancing in such a setting tends to be reactive: someone notices *after* customers are
  turned away.

## 5. Why this matters for an MFS

- **Customers:** a failed cash-out is a direct service failure, often exactly when people need money
  (salary day).
- **Agents:** lost commission and lost trust.
- **The MFS provider:** lower service availability, more emergency logistics, more complaints.
- **Our framing:** a *future-ready capability* for any MFS network. We do **not** claim upay
  currently has this problem; we have no data about upay's operations.

## 6. Complete product flow (what you see on screen)

The top bar has a **Decision time** selector. The default is **Mon 31 Aug 2026, 13:00**. You can pick
any hour in the 14-day test period.

| Page | What it shows |
|---|---|
| **Command Center** | At the default time: 200 active agents, **25 at risk** (HIGH or CRITICAL), **7 critical**, 32 at MEDIUM, 15 with unusual activity. Projected service readiness **71.5% → 77.5%** with the recommended plan (policy V2). Recommended rebalancing **BDT 4.7 lakh** in **14 transfers**; BDT 5.0 lakh escalated to the distributor. (With policy V1 the same moment needs 21 transfers for BDT 4.0 lakh, reaching 77.0%.) Also a 48-hour forecast-vs-actual chart, a risk chart, top at-risk agents and a district table. |
| **Morning Plan** (new, proactive) | At 07:00 a full-day model forecasts each agent's **cash and e-float** needs for 08:00–23:59. At 08:00 it proposes where the **same** district working capital should sit: the budget and recommendation match exactly, with BDT 0 extra. It includes a review-focus panel (largest cuts, low-volume cuts, rural e-float reductions), an agent table with an explanation drawer, a district conservation proof, **Approve Simulation**, and the research evidence with caveats. It uses a separate synthetic demo world. |
| **Agents** | Table of all 200 agents; sort and filter by risk, behaviour, district, location type, volume and ID. |
| **Agent Intelligence** (click an agent) | Current cash, 6-hour forecasts, expected gap, risk score with its 5 parts, "Why this risk?" (with Bangla button), recommended action, unusual-activity panel, 72-hour history chart, model accuracy. |
| **Rebalancing Center** | Policy toggle (**V2**, the default, or **V1**). All recommended transfers → **Review Recommendation** → evidence drawer → tick acknowledgement → **Approve Simulation** → before/after results and audit log. Also lists escalations and agents held for manual review. |
| **Scenario Lab** | "What if demand rises 10/25/40%?" or "what if one district spikes?" Everything is recalculated live. Example: +25% demand → at-risk agents 25 → 31. |
| **Impact & Model Health** | Policy comparison (without AgentFlow / naive forecast / V1 / V2), daily chart, results by group, baseline vs. ML accuracy, alert accuracy, anomaly accuracy, fairness tables. |
| **Responsible AI** | Our principles and when *not* to trust the system blindly. |

**Demo agent: AG-0171** (Rangpur). At 13:00 it has BDT 20,640 cash, but the forecast peak need for
the next 6 hours is BDT 38,675, so coverage is 53% and risk is **HIGH (53/100)**. The V2 recommendation
is **RB-013**: BDT 38,500 from AG-0181 (12.2 km) in one transfer, which would take it to **LOW (5)**. The
donor stays LOW with BDT 4,430 above its safety reserve. (Policy V1 would use two transfers, BDT 22,500
from AG-0183 and BDT 16,000 from AG-0178, which reach the same result at a higher estimated logistics
cost.) Set the decision time to 19:00 and you can see that, without action, its cash hits zero
at 19:00 and BDT 11,830 of cash-out is turned away.

## 6a. Morning Plan vs. V2: two time scales

- **Morning Plan (proactive):** full-day cash **and** e-float positioning before the day starts.
- **V2 (reactive):** intraday **physical-cash** rebalancing when 6-hour risk appears. V2 does not
  handle e-float.
- **Two separate synthetic environments, never combined:**
  - V1/V2 are evaluated in the legacy intraday world, where e-float is tracked but not binding.
  - The Morning Plan is evaluated in Dual-Liquidity World v2, where cash **and** e-float are both
    binding.
- **One-line story:** *Same liquidity. Placed ahead of demand.*
  - Morning: predict and position cash and e-float.
  - Intraday: monitor cash pressure and recommend safe V2 recovery.
  - A human reviews every consequential action.
  - Each environment is measured separately.
- **The evidence, to quote exactly:**
  - *"In fresh synthetic worlds from the same world family, the frozen full-day ML policy reduced
    combined unmet demand by a median 20.6% versus the strongest cautious historical baseline,
    while conserving each district's cash and e-float budgets exactly. This is synthetic held-out
    evidence, not measured upay performance."*
  - The range across worlds was 13.7–29.8%, and 5 of 5 worlds improved.
  - The protocol and success bar were committed before the audit seeds were generated.
  - **Absolute example (audit world seed 2036, 14 days):** combined unmet fell from about BDT 49.7
    lakh (q90 rule) to about BDT 40.8 lakh (ML), −17.9% in that world. Cash-out fill went from 99.65%
    to 99.80%.
- **If asked "who moves the cash?":** nobody, in this prototype. AgentFlow recommends target levels
  and only simulates approval. A real deployment could hand approved targets to an existing
  distributor, field-officer or bank-deposit replenishment workflow. Whether targets can change
  daily is something real-world validation must answer.
- **Caveats to volunteer:**
  - cash P90 coverage is about 85% (nominal 90%);
  - low-volume agents did worse than the cautious q90 rule in 4 of 5 worlds;
  - rural e-float can fall materially.
- **The research story (negative results included):**
  1. peer cash/e-float swaps were rejected;
  2. the 6-hour ML was rejected for morning planning;
  3. the forecast horizon was aligned to the full day;
  4. the frozen model survived fresh cautious-baseline tests.

  See `docs/MORNING_PLAN.md`.

## 7. What the ML model actually predicts

For **each agent, at each hour**, using only information available up to that hour:

1. **Cash-out demand for the next 6 hours**: how much cash customers will ask to withdraw.
2. **Peak cash need for the next 6 hours**: the most cash the agent will need on hand at any point
   in the window, after counting cash-ins. If an agent starts the window with at least this
   amount, no customer is turned away. This is the main input to risk.
3. **A cautious (90th-percentile) version of #2**: a "bad but plausible" scenario. In testing, the
   real value was below this estimate **89.5%** of the time (the target is 90%).

- **Algorithm:** gradient-boosted decision trees (scikit-learn `HistGradientBoostingRegressor`).
  This is a standard, fast and accurate method for table data. It is not a neural network and not a chatbot.
- **Inputs:** 31 features: time of day, weekday, salary period, market day, agent type and location,
  and the agent's recent and same-time-on-previous-days cash-out and cash-in.
- **It does NOT use** the agent's cash balance as an input. Demand is treated as coming from
  customers; balance is used later by the risk formula.

## 8. What the anomaly detector does

- It looks for **unusual behaviour compared with the agent's own history**: sudden surges in
  cash-out, cash-in or number of transactions, unusual ticket sizes, cash-in and cash-out both spiking
  together, and activity at night (00:00–05:59).
- **Method:** two parts averaged together: an **Isolation Forest** (a standard unsupervised ML
  method) and a **simple robust-deviation rule**. Each is converted to a 0–1 score.
- **Labels:** NORMAL, WATCH (score in the top 1% of all training-period hours) and ANOMALOUS (top 0.3%).
- **What happens next:** it **does not change the liquidity risk score**. If an at-risk agent shows
  unusual activity, it is **held for manual review** instead of receiving a transfer recommendation.
  At the default time, 1 agent (AG-0111) is held this way.
- **It is not fraud detection.** An anomaly means "unusual, please review", nothing more.
- **Accuracy** (test period, against 204 deliberately injected unusual hours): ranking score
  (ROC-AUC) **0.981**; of hours flagged ANOMALOUS, **52.9%** were truly injected anomalies, and
  **67.2%** of injected anomaly hours were flagged. Honest note: the simple rule alone performs as
  well as the combined detector on this data.

## 9. How liquidity risk is calculated

Risk is a **fixed formula**, not a black box, and not invented by AI. It adds up five capped parts:

| Part | Max points | Meaning |
|---|---:|---|
| Coverage | 45 | How much of the forecast cash need the current cash covers (less coverage = more points) |
| Cautious-scenario gap | 20 | How far cash falls short of the 90th-percentile forecast |
| Shortfall size | 20 | Size of the expected shortfall in BDT (full points at BDT 40,000) |
| Velocity | 10 | Whether transactions in the last 3 hours are running above the agent's usual level |
| History | 5 | How often this agent ran short in the training period |

**Levels:** LOW < 25 ≤ MEDIUM < 50 ≤ HIGH < 75 ≤ CRITICAL.

- The forecast-based parts (coverage, gap, shortfall) can contribute up to **85 of 100** points.
- Less cash, or a bigger forecast, can **never lower** the score. This is checked by automated tests.
- **Does the score mean something?** In the test period, the share of decisions followed by a real
  shortage within 6 hours was: LOW 3.7%, MEDIUM 59.5%, HIGH 79.3%, CRITICAL 86.1%.

## 10. How explainability works

- Every "Why this risk?" sentence is **generated from the actual numbers**: the forecast, current
  cash, coverage, shortfall, cautious-scenario gap, recent velocity and past shortage rate. Context
  lines cover salary period, market day and how busy this time window usually is.
- The screen shows how many points each of the 5 risk parts contributed.
- The **Bangla button** shows the same evidence in Bangla using fixed sentence templates. **No AI
  language model** writes the text.
- Each number on screen carries a tag: *ML prediction*, *Deterministic calculation*,
  *Recommendation*, *Simulation only* or *Synthetic data*.
- For the model as a whole, the Impact page shows which inputs matter most. The top driver is
  "same 6-hour window, average of the last 7 days".

## 11. How rebalancing recommendations work

For agents at **HIGH or CRITICAL** risk:

There are two policies. **V2 is the default**; **V1** (the original) can still be selected for comparison.

**Rules shared by both:**

1. **How much is needed:** enough to reach the cautious (90th-percentile) forecast need. V2 uses the
   same target, because its selected setting λ = 1.0 means "go to the cautious forecast".
2. **Who can give:** only agents that are **LOW risk**, show **no unusual activity**, are in the
   **same district** and are **within 15 km**.
3. Amounts are in steps of BDT 500, at least BDT 2,000, and come from at most 2 donors per agent.
4. Highest-risk agents are served first.
5. **If no donor qualifies**, the remaining need is **escalated to the distributor** (a human process).
6. Each recommendation shows the reason, both agents' cash before and after, risk before and after,
   distance and an estimated logistics cost (assumed BDT 150 + BDT 25 per km).

**V1:** the donor keeps **110% of its own cautious forecast need** (minimum BDT 5,000); the *nearest*
donor is chosen first.

**V2 (default) adds four things:**

- **Bigger safety reserve when needed:** the donor's reserve grows if its own forecast is uncertain,
  if it is busier than usual right now, or if it has run short before. It is never smaller than V1's.
  The donor must still be **LOW risk** after all its transfers.
- **Minimum-benefit gate:** a transfer is only suggested if it lowers the recipient's risk level, or cuts
  its risk score by at least 20 points, or removes at least half its expected shortfall. Tiny "token"
  transfers are not suggested; the need is escalated instead.
- **Smarter donor choice:** first a donor who can cover the whole need alone (fewer trips); then the one
  that removes the most risk per taka of transport cost; then the one left with the biggest safety
  margin; then the nearest.
- **Evidence on screen:** expected risk drop for the recipient, and how much the donor keeps above its reserve.

**How V2's settings were chosen:** only on training data. We used two "practice" periods
(21 Jul–3 Aug and 4–17 Aug) with forecast models trained on even earlier data. The 14 test days were
used once, at the end, with a rule written down beforehand.

These are **peer-to-peer** moves, so the total cash in the network does not change.

## 12. Why transfers require human review

- Moving cash is a **consequential financial action**: real people carry real money, and errors cost money.
- Forecasts can be wrong; a person may know things the model does not (road closures, agent
  availability, security).
- Accountability: a named person approves, and the action is logged.
- In this prototype, **Approve Simulation only runs a what-if calculation** and adds an audit-log
  entry. **No payment instruction is created and no money moves.**

## 13. How the impact simulator works

- It replays the **14 test days** (18–31 Aug 2026) **hour by hour for all 200 agents**.
- Customer demand is **exactly the same** in every policy, which makes the comparison fair.
- Four policies are compared:
  1. **Without AgentFlow:** only the 08:00 daily reset. The replay reproduces the original data
     exactly, which shows the simulator is correct.
  2. **Rebalancing with a naive forecast:** the same risk and rebalancing engine (V1), but fed a simple
     forecast instead of ML.
  3. **AgentFlow V1:** ML forecast → risk → original rebalancing policy.
  4. **AgentFlow V2 (default):** ML forecast → risk → improved rebalancing policy.
- Decisions happen at 09, 11, 13, 15, 17 and 19 h; transfers arrive 1 hour later.
- Agents with unusual activity are held for review, not supported automatically.

| | Without | Naive forecast | AgentFlow V1 | **AgentFlow V2** |
|---|---:|---:|---:|---:|
| Shortage events | 2,017 | 1,483 | 1,255 | **1,223** |
| Unmet cash demand | BDT 95.4 lakh | BDT 67.6 lakh | BDT 58.3 lakh | **BDT 56.9 lakh** |
| Service availability | 96.76% | 97.64% | 97.92% | **97.95%** |
| Transfers | — | 384 | 501 | **345** |
| Transfers not strictly needed | — | 15.1% | **21.4%** | 24.3% |
| Donor shortages within 6 h of giving | — | 65 | 25 | **14** |
| Estimated logistics cost | — | BDT 1.22 lakh | BDT 1.58 lakh | **BDT 1.15 lakh** |
| Unmet demand avoided per BDT 1,000 cost | — | BDT 22,707 | BDT 23,410 | **BDT 33,340** |

- The naive-forecast column shows that the ML forecast adds value beyond the decision rules alone.
- **V2 vs V1:** slightly more benefit, with 31% fewer transfers, 27% lower cost and 44% fewer donor
  shortages.
- **But** a slightly higher *share* of V2's transfers turned out unnecessary (24.3% vs 21.4%), even
  though the *number* was lower (84 vs 107). V2 is also slightly worse than V1 for rural agents.
- V2 became the default because a rule written in advance said so: it keeps ≥ 95% of V1's benefit,
  has no more donor shortages, and is better on at least 2 of 3 efficiency/safety measures.

**Definitions:**
- *Shortage event* = an agent-hour where at least one cash-out request could not be served.
- *Service availability* = share of operating agent-hours (08:00–21:59) with demand where every
  cash-out request was served.

### 13b. Business impact (Phase 2, synthetic simulated estimate)

Say: *"synthetic simulated estimate, not measured upay performance."*
- **Measured in the simulation:** V2 served BDT 38.5 lakh of cash-out that was unmet without AgentFlow,
  and had 794 fewer shortage agent-hours.
- **Estimated:** about 2,466 transactions protected (unmet BDT ÷ average synthetic ticket size). The
  simulator works in BDT, not individual transactions, so this is an estimate, never an exact count.
- **Assumed:** the agent commission (50 bps) is an illustrative round number, not upay's rate. At that
  rate, commission protected (BDT 19,230) is far below the peer logistics cost proxy (BDT 2.09 lakh);
  break-even is about 545 bps. We say this openly.
- **Distributor:** 154 escalated agent-days (trips); break-even fee about BDT 1,524 per trip. We do not
  compute distributor profit because we have no real fee.
- **The honest pitch:** customers served, at lower logistics cost per protected transaction with V2
  (BDT 85) than V1 (BDT 116). **No ROI is claimed.**

### 13c. Logistics ranking and security safeguards (Phase 2)

- **Ranking:** V2 still ranks donors exactly as in Phase 1. We tried ranking by the richer logistics cost; it
  was slightly worse (1,229 vs 1,223 shortage events), so we did not adopt it. The richer cost is still used
  to *cost* every transfer.
- **Approval:** the server refuses a simulated approval unless the reviewer acknowledged the evidence. A
  repeated approval does not create a second audit record.
- **Audit:** every simulated approval is hash-chained, so editing a record is detectable. It is tamper-evident,
  not tamper-proof, and it is not a production audit store.
- **Rate limit:** simulation requests are limited per client (prototype, single process; not a WAF).
- **Gaming:** an agent that manufactures a large burst of transactions is flagged ANOMALOUS by the existing
  detector and held for review, so it is not sent cash. Smaller manipulation may not be flagged, and
  WATCH-level agents are not held: say so if asked.
- **Login:** there is none. Real identity and role-based approval are production requirements.

## 14. Why the dataset is synthetic

- We have **no access to upay data**, and real customer data should not be used in a hackathon
  prototype or placed in a public repository.
- A program creates the data with a **fixed random seed**, so the same data is produced every time.
- **Size:** 200 agents, 8 districts (Dhaka, Chattogram, Gazipur, Sylhet, Rajshahi, Khulna, Rangpur,
  Barishal), hourly for 76 days (17 Jun – 31 Aug 2026), 364,800 rows.
- **Built-in patterns:** daily peaks, Friday/Saturday weekend dip, salary-period increase (strongest
  in urban-periphery areas), rural market days, multi-day demand swings, short local spikes and
  random noise.
- **426 unusual-behaviour episodes** were deliberately inserted, with labels, so we can test the
  anomaly detector.
- **No personal information:** no names, phone numbers, IDs or accounts. Agents are just "AG-0001"
  and so on, and locations are random points near district centres. Automated tests check this.

## 15. Baseline vs. ML: why it matters

A **baseline** is a simple rule anyone could use without ML. If ML does not beat it, ML is not
needed. We used two:

- **Naive:** "the next 6 hours will look like the same 6 hours yesterday".
- **Seasonal average:** "the average of the same 6 hours over the last 7 days" (a strong rule).

All results are on the **14 test days the model never saw** (66,000 agent-hours).

| What we predict (next 6 h) | Naive | Seasonal avg | **ML** | ML vs. best simple rule |
|---|---:|---:|---:|---:|
| Cash-out demand, average error (MAE) | BDT 9,691 | BDT 7,890 | **BDT 6,138** | **22.2% lower error** |
| Peak cash need, average error (MAE) | BDT 6,972 | BDT 5,524 | **BDT 5,147** | **6.8% lower error** |

- For cash-out demand, ML is clearly better (36.7% lower error than naive).
- For peak cash need, ML is **only modestly** better than the strong seasonal rule. Say this
  honestly if asked.
- **Early warning:** when the risk engine raises a HIGH/CRITICAL alert, a real shortage followed
  within 6 hours **81.5%** of the time (precision). These alerts caught **41.7%** of all shortage
  windows (recall), compared with 31.3% when using the naive forecast.

**No data leakage:** the model was trained on the past and tested on the future, with a 6-hour gap
between them. An automated test confirms that no prediction uses future information.

## 16. Responsible AI and security

- **Privacy:** synthetic data only; tests check that no personal-data fields exist.
- **Explainability:** fixed risk formula; every reason is built from real numbers; source tags on screen.
- **Human oversight:** review + acknowledgement + "Approve Simulation"; simulation only; audit log.
- **Safety rules:** donors keep at least their protected reserve (V1: 110% of their own cautious forecast
  need; V2: a dynamic reserve that is never smaller than that) and, in V2, must stay LOW risk. There is
  never a negative balance, and a donor never gives more than its safe surplus. All of these are covered
  by automated tests.
- **Anomaly ≠ fraud:** unusual activity triggers manual review, never a fraud label.
- **Fairness checks:** results are compared across urban-core / urban-periphery / rural and
  low / medium / high volume. Forecast error is similar across groups (WAPE about 17–18%). Alerts
  catch fewer shortages for urban-core agents (26.4%), where shortages are rare (about 1.4%). Rural
  agents gain less from peer rebalancing than urban-periphery agents (unmet demand −26% vs −54% with
  V1; −24% vs −58% with V2), because rural donors are fewer and farther apart. V2 is slightly worse
  than V1 for rural agents.
- **Security:** no secrets in the code (`.env` is excluded from git); strict input checking; error
  messages never show internal code details; allowed website origins are configurable (CORS);
  basic web security headers; the server container runs as a non-root user.
- **Reproducible and tested:** 103 automated tests, and a GitHub Actions pipeline that rebuilds and
  checks everything on every change.

## 17. Limitations (be honest about these)

- **Synthetic data only.** The results show the method works on realistic simulated data. They do
  not prove real-world performance.
- The peak-cash-need forecast is only **6.8%** better than a strong simple rule.
- HIGH/CRITICAL alerts catch about **42%** of shortage windows; sudden spikes are hard to predict
  6 hours ahead.
- With the default policy V2, **24.3%** of simulated transfers were not strictly needed, and donors still
  ran short **14** times across 345 transfers (V1: 21.4% and 25 across 501). V2 reduced donor risk; it
  did not eliminate it, and it did not lower the share of unnecessary transfers.
- V2's settings were tuned on two 14-day practice periods of the same synthetic world. Real data would
  need re-tuning.
- The simulator assumes customers don't retry or go to another agent, transfers take 1 hour, and a
  simple cost model. In this legacy intraday world, e-float is tracked but not used as a limit; only
  the separate Morning Plan world treats it as binding.
- The number of agents with *at least one* shortage barely fell: 140 → 137 with V2, and 140 → 140 with
  V1. AgentFlow reduces how often and how badly agents run short, not whether stress ever happens.
- The approval audit log is kept in memory and resets when the server restarts.
- There is no login or user roles; that is out of scope for the prototype.

## 18. Future upay integration path

These are **future steps**, not done today:

1. Receive **hourly per-agent totals** (amounts and counts only, no customer data), including
   declined cash-out attempts.
2. Retrain and re-evaluate with the same pipeline and the same "past vs. future" testing.
3. Check the simulator against historical rebalancing records and real distributor constraints.
4. Run a **shadow pilot**: operations staff see recommendations, decide themselves, and outcomes are
   recorded, with no automation.
5. Add login and roles, store approvals in a database, and monitor model accuracy over time.
6. Only after approval, hand *approved* actions to existing field or distributor workflows.
   AgentFlow itself would still not move money.

---

## 19. Likely judge questions — short, accurate answers

1. **Is this real upay data?** No. It is synthetic data generated by our own program with a fixed
   seed. It contains no personal information.
2. **Why synthetic data?** We had no access to real data, real customer data must not be exposed,
   and synthetic data makes everything reproducible and publishable.
3. **What exactly does the ML predict?** For each agent and hour: next-6-hour cash-out demand, the
   peak cash it will need on hand in that window, and a cautious 90th-percentile version.
4. **Which algorithm?** Gradient-boosted decision trees (scikit-learn HistGradientBoostingRegressor),
   with 31 input features.
5. **Why not deep learning?** For table data, gradient boosting is accurate, fast, stable and easier
   to explain. We chose for reliability, not to look sophisticated.
6. **Does ML beat a simple rule?** Yes. Cash-out demand error is 22.2% lower than the best simple
   rule (36.7% lower than naive). For peak cash need it is only 6.8% lower; we report that openly.
7. **How did you avoid data leakage?** Time-based split (train on earlier dates, test on the last
   14 days), a 6-hour gap between them, features built only from past data, and an automated test
   that changes future data and confirms past features do not change.
8. **How accurate is the uncertainty estimate?** The 90th-percentile forecast covered the real value
   89.5% of the time (target 90%).
9. **How is the risk score calculated?** A fixed formula with five capped parts: coverage (45),
   cautious-scenario gap (20), shortfall size (20), velocity (10) and history (5). Levels: LOW below
   25, MEDIUM 25–49, HIGH 50–74, CRITICAL 75 and above.
10. **Is the risk score made by AI?** The forecasts are ML. The score itself is a transparent,
    deterministic formula on top of them, so it can be audited line by line.
11. **Does the risk score actually predict shortages?** On test data, the share followed by a real
    shortage within 6 hours rises from 3.7% (LOW) to 59.5% (MEDIUM), 79.3% (HIGH) and 86.1%
    (CRITICAL). HIGH+ alerts are right 81.5% of the time and catch 41.7% of shortages.
12. **Why does it miss more than half of shortages?** Many shortages come from sudden spikes that are
    hard to foresee 6 hours ahead. MEDIUM already has a 59.5% shortage rate, so an operator wanting
    to catch more could also act on MEDIUM, at the cost of more transfers.
13. **What does the anomaly detector do?** It flags behaviour that is unusual compared with the
    agent's own history (surges, odd ticket sizes, night activity, simultaneous in/out spikes),
    using Isolation Forest plus a robust-deviation rule.
14. **Is an anomaly fraud?** No. It means "unusual, please review". It does not change the risk score.
    It sends at-risk agents to manual review instead of automatic support.
15. **How good is anomaly detection?** On 204 injected anomalous hours in the test period, ROC-AUC is
    0.981. When we flag ANOMALOUS we are right 52.9% of the time and catch 67.2%. A simple rule alone
    scores about the same, and we say so.
16. **How are rebalancing donors chosen?** Always: LOW risk, no unusual activity, same district,
    within 15 km. With the default policy V2, the donor must keep a dynamic safety reserve and stay LOW
    risk. Donors are ranked first by whether one donor can cover the whole need, then by risk removed
    per taka of transport cost, then by the safety margin left, then by distance. V1 simply picks the
    nearest donor and keeps 110% of its cautious forecast need.
17. **Can a donor end up short?** Yes, sometimes, because forecasts can be wrong. In the 14-day
    simulation donors ran short 14 times across 345 transfers with V2 (25 across 501 with V1). We report
    this as a known risk.
18. **Does the system move money?** No. "Approve Simulation" only runs a what-if calculation and
    writes an audit-log entry. No instruction is sent.
19. **Why require a human?** Cash movement is consequential. A person can catch what the model
    cannot and remains accountable.
20. **How did you measure business impact?** By replaying the 14 test days hour by hour with
    identical demand: without AgentFlow, with naive-forecast rebalancing, with AgentFlow V1 and with
    AgentFlow V2.
21. **What were the impact results?** With the default policy V2: shortage events 2,017 → 1,223
    (−39.4%); unmet cash demand BDT 95.4 → 56.9 lakh (−40.3%, BDT 38.5 lakh avoided); service
    availability 96.76% → 97.95%. V1: −37.8% events, −38.9% unmet demand. No extra cash added. These are
    synthetic simulation results, not real-world results.
22. **Where does the improvement come from if no cash is added?** From moving existing cash from
    agents with surplus to agents who are forecast to need it, before they run out.
23. **What does it cost?** With V2: 345 simulated transfers moving BDT 75.1 lakh, estimated logistics cost
    BDT 1.15 lakh (assumed BDT 150 + BDT 25/km); 24.3% of transfers were not strictly needed. V1 needed 501
    transfers and BDT 1.58 lakh, and 21.4% were not strictly needed.
24. **Is it fair across areas?** Forecast error is similar across groups (WAPE about 17–18%). Alerts
    catch fewer shortages in urban-core areas, where shortages are rare. Rural agents gain less from
    peer rebalancing because donors are sparser. These differences are documented.
25. **Is an LLM or chatbot involved?** No. There is no language model in the decision path; the Bangla
    explanation uses fixed templates.
26. **Can others reproduce your results?** Yes. `python ml/scripts/run_pipeline.py` regenerates the
    data, retrains and re-evaluates. With the pinned project environment, the evaluated decision
    outputs, business-impact metrics and demo values reproduce. Runtime `fit_seconds` metadata is
    excluded, and tiny cross-machine floating-point variation may occur in internal anomaly
    thresholds. Do not claim byte-for-byte reproduction on every machine.
27. **How is it tested?** 103 automated tests (data, leakage, models, risk, rebalancing V1/V2 safety,
    simulation, API, frontend–backend contract). GitHub Actions also checks the frontend build.
28. **What is the tech stack?** Python (pandas, scikit-learn), FastAPI backend, Next.js + TypeScript +
    Tailwind dashboard. Deployed on Vercel (dashboard) and Railway (API).
29. **Could it scale to a real network?** The models train in seconds on our 262,800 training rows
    and predict all agents in one batch. A real deployment would move features to a data warehouse,
    retrain on a schedule, and add authentication and a database. Those are future steps.
30. **How would upay integrate it?** Provide hourly per-agent totals (no customer data), re-evaluate,
    run a shadow pilot with staff, and only then connect *approved* actions to existing workflows.
31. **What are the biggest limitations?** Synthetic data, a modest gain on peak cash need, about 42%
    shortage recall, some unnecessary transfers and donor risk, and a simplified logistics model.
32. **Who built it?** We are a registered 3-member team. One primary implementer did the engineering.
    AI-assisted development tools were used and are disclosed in the README.
33. **Why did you build V2, and did you tune it on the test data?** V1 made many small transfers and its
    donors sometimes ran short. V2 adds a benefit gate, a dynamic donor reserve and cost-aware donor
    choice. Its settings were chosen only on two earlier "practice" periods inside the training data. The
    test period was used once, with a decision rule written down in advance.

---

## 19b. If a judge interrupts and asks…

Keep answers to one or two sentences. The same table is in `docs/DEMO_SCRIPT.md`.

| Question | Short, accurate answer |
|---|---|
| Is this real upay data? | No. It's synthetic data from our own seeded generator, with no personal information. |
| Why ML? | Demand depends on hour, weekday, salary days and agent history together. ML cuts 6-hour cash-demand error by 22% versus the best simple rule. |
| Why not a simple rule? | We tested that. The same V1 decision engine fed a simple seasonal forecast leaves BDT 67.6 lakh unmet, versus 58.3 lakh with the ML forecast. |
| Why V2? | V1 picked the nearest donor. V2 adds a benefit gate, a safer dynamic donor reserve and cost-aware ranking: 345 vs 501 transfers, 14 vs 25 donor shortages, lower cost, slightly more benefit. |
| Is this fraud detection? | No. Anomalies mean "unusual for this agent". They route the case to manual review and never label fraud. |
| Does it transfer money? | No. Approval runs a simulation and writes an audit entry. No payment instruction exists. |
| What if the forecast is wrong? | We plan for a cautious P90 scenario, donors keep a reserve, and a person reviews. It still happens: 14 donor shortage events in 345 simulated transfers. |
| Why is unnecessary-transfer % higher in V2? | V2 makes fewer, larger transfers. The number of unnecessary ones fell (107 → 84) but their share rose (21.4% → 24.3%). |
| How did you avoid tuning on the test set? | V2 settings were chosen on two earlier validation windows inside the training period. The 14-day test window was used once, with a decision rule written beforehand. |
| What is the biggest limitation? | It's all synthetic. Real data would need re-validation, a shadow pilot and re-tuning. |

**Demo controls you may be asked to use:** **Reset demo** (top right) restores the default snapshot
(Mon 31 Aug, 13:00, policy V2) on this browser only. It changes no server data. **Judge demo** shows
or hides the six-step guide. If the page says *"Live decision service is temporarily unavailable"*,
click **Retry**; nothing was changed or approved.

## 20. Things teammates must NOT claim

- ❌ Do **not** claim we used real upay customer data, or any real data. It is all synthetic.
- ❌ Do **not** claim the synthetic simulation proves real-world performance. Say *"in a synthetic
  held-out simulation"*.
- ❌ Do **not** call behavioural anomalies confirmed fraud. They are *unusual activity for manual review*.
- ❌ Do **not** claim the system automatically transfers money. Approval only runs a simulation.
- ❌ Do **not** claim the system makes autonomous financial decisions. Every action needs human review.
- ❌ Do **not** claim features that are not implemented. In particular, there is **no** login or user
  roles, **no** real payment or upay integration, **no** chatbot or LLM, **no** map view, **no**
  mobile app and **no** database (data is stored in files).
- ❌ Do **not** invent or round up model metrics. Use only the numbers in this document, the
  dashboard or `docs/EVALUATION.md`.
- ❌ Do **not** claim upay currently has a liquidity problem. We present a *future-ready capability*.
- ❌ Do **not** claim the model is "99% accurate" or similar. Quote the specific metrics above.
- ❌ Do **not** claim the peak-cash forecast is much better than the baseline. It is 6.8% better.
- ❌ Do **not** claim shortages were eliminated. They fell by 39.4% with V2 (37.8% with V1), and 137
  agents (V1: 140) still had at least one shortage.
- ❌ Do **not** claim V2 reduced unnecessary transfers. Their *share* rose slightly (24.3% vs 21.4%); V2's
  gains are fewer transfers, lower cost and fewer donor shortages.
- ❌ Do **not** claim donors are now risk-free. There were still 14 donor shortage events with V2.
- ❌ Do **not** claim AgentFlow is in production or used by upay.
- ❌ Do **not** claim real upay revenue, commission, savings or ROI. Business-impact figures are synthetic
  simulated estimates; the 50 bps commission is illustrative, and "2,459 transactions" is an estimate.
- ❌ Do **not** claim enterprise or bank-grade security, a login system, or immutable audit storage. The
  safeguards are prototype controls.
- ❌ Do **not** claim AgentFlow pays for itself. Under the illustrative rates, commission protected does not
  cover the logistics cost proxy.
- ❌ Do **not** present 20.6% as the saving for the date shown on the Morning Plan page. It is
  historical synthetic research evidence.
- ❌ Do **not** say the Morning Plan "adds liquidity" or that V2 optimises e-float. The plan
  repositions the same working capital, and V2 is cash-only.
- ❌ Do **not** say an agent "will be harmed". Say the plan *flags it for review*.
- ❌ Do **not** say "it reproduces byte-for-byte on every machine". Use the pinned-environment
  wording above.
- ❌ Do **not** quote a commission rate or a taka figure for agent income. The only formula we use
  is illustrative: protected income ≈ avoided unmet transaction value × a *verified* commission
  rate.
- ❌ Do **not** describe how upay moves liquidity today. AgentFlow only recommends target levels and
  simulates approval.

**Safe phrases to use:**
- "In our synthetic held-out simulation…"
- "The model predicts…; the risk score is a transparent formula on top of that."
- "Unusual activity is flagged for manual review."
- "Approval runs a simulation only; no money moves."
- "Let me show you that on the dashboard."

## 21. Where to find more detail

| Topic | File |
|---|---|
| Full evaluation numbers | `docs/EVALUATION.md` |
| Data description | `docs/DATA_CARD.md` |
| Model details and limits | `docs/MODEL_CARD.md` |
| System design | `docs/ARCHITECTURE.md` |
| Demo walkthrough | `docs/DEMO_SCRIPT.md` |
| Report outline | `docs/PROJECT_REPORT.md` |
| Raw metrics | `ml/artifacts/metrics.json`, `ml/artifacts/impact.json` |
| Live dashboard | https://agentflow-ai-nine.vercel.app |
