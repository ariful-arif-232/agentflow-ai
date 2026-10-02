# Demo Script — AgentFlow AI (final)

**One-line story:** *AgentFlow predicts where an MFS agent may run short of liquidity before
customers are affected, explains why, and recommends a safe, human-reviewed rebalancing action.*

All numbers below are the live outputs at the **default snapshot (Mon 31 Aug 2026, 13:00, policy V2)**.
They are deterministic, so you will see exactly these values.

---

## Before you start (once, 2 minutes)

| Check | How |
|---|---|
| Dashboard loads | open **https://agentflow-ai-nine.vercel.app** (local: `npm run dev` in `apps/web`) |
| API is up | **https://agentflow-api-production.up.railway.app/health** returns `"status":"ok"` |
| Clean demo state | click **Reset demo** (top right). This sets 13:00 and policy V2, opens the **Judge demo** guide, and returns to the Command Center. It changes nothing on the server. |
| Projector | 1366×768 or larger; browser zoom 100%. The layout is tested at 1366×768 and 1440×900. |
| Backup | screenshots of every step plus a short screen recording on the laptop desktop |

The **Judge demo** strip (6 steps, live values) is your route map. Click a step to jump to its page.

**Don't** explain the decision-time selector, Scenario Lab, Agents table filters or anomaly scores unless asked.

---

## A. 90-second emergency demo

| # | Page / click | Say | Point at |
|---|---|---|---|
| 1 | **Command Center** | "200 synthetic agents, 6 hours ahead. 25 are HIGH or CRITICAL right now." | *At-risk agents 25* |
| 2 | Guide step **2 · Open AG-0171** | "This agent still has cash, so no customer has been turned away yet. But its forecast need is almost double what it holds." | *Current cash BDT 20,640* vs *peak requirement BDT 38,675*; **HIGH 53** |
| 3 | Same page, red **Without action** strip | "If nothing happens, about BDT 18,035 of withdrawals may fail in the next 6 hours." | *Without action* strip |
| 4 | **Review recommendation →** then **Review Recommendation** on **RB-013** | "Policy V2 picks one nearby donor that stays LOW risk and keeps BDT 4,430 above its safety reserve. AG-0171 goes from HIGH to LOW." | *Why this recipient / Why this donor* boxes |
| 5 | Tick the box → **Approve Simulation** | "A person approves. It's a simulation only — no money moves." | *Simulation approved — no money moved* |
| 6 | Guide step **6 · Measure impact** | "On 14 held-out days: 40% less unmet cash demand, with 31% fewer transfers than our first policy. Synthetic simulation, not real upay results." | *V1 vs V2 at a glance* |

**Don't** explain the risk formula, the models or V1 in detail.

---

## B. 3-minute standard demo

**1. Command Center (30 s).** The flow strip says *Predict → Explain → Rebalance → Human review → Measure*.
> "AgentFlow forecasts every agent's cash needs for the next 6 hours."

Point at: **25 at-risk, 7 critical**, **projected service readiness 71.5% → 77.5% with the V2 plan**,
**14 peer transfers, BDT 4.7 lakh**.
*Transition:* "That's intraday risk. But AgentFlow also acts before the day starts."

**1b. Morning Plan (25 s)** (guide step 2). Open **Morning Plan**, dated Mon 31 Aug 2026.
> "At 07:00 a full-day model forecasts each agent's cash *and* e-float need. At 08:00 it proposes where
> the same working capital should sit. Look: budget and recommendation match exactly, BDT 0 extra."

Point at the **Review focus** panel: "Hard cases are surfaced for a person, such as big cuts, low-volume
agents and rural e-float." Do **not** quote 20.6% as this date's saving. It is historical synthetic
evidence, shown at the bottom with its caveats.

*Transition:* "Now let's look at one agent under intraday pressure."

**2. AG-0171 (45 s)** (guide step 2).
> "AG-0171 in Rangpur has BDT 20,640. Our ML forecast says it will need BDT 38,675 at peak in the
> next 6 hours, and BDT 59,387 in a cautious scenario. That's 53% coverage, so risk is HIGH, 53/100."

Point at the red **Without action** strip: about **BDT 18,035** of cash-out may go unserved.
*Transition:* "And it tells us why."

**3. Why this risk? (30 s).** Read reasons 1–3. Point at the component bars (coverage 25.8/45).
> "Every sentence is generated from the numbers — no chatbot. The risk score is a fixed, auditable formula."

Optional: click **বাংলায় ব্যাখ্যা করুন** for two seconds.
*Transition:* "So what should operations do?"

**4. V2 recommendation (45 s).** **Review recommendation →** opens the Rebalancing Center with AG-0171
highlighted, policy V2. Click **Review Recommendation** on **RB-013**.
- *Why this recipient?* HIGH 53 → LOW 5; expected shortfall BDT 18,035 → 0; P90 coverage 35% → 100%.
- *Why this donor?* AG-0181 stays LOW; dynamic reserve BDT 48,420; **BDT 4,430 margin left** after the whole plan.
- *Why this amount?* need BDT 38,747 → one transfer of BDT 38,500 covers it; about 12 km, est. BDT 456.
*Transition:* "A human has to approve it."

**5. Approve Simulation (15 s).** Tick *"I have reviewed the evidence above"* → **Approve Simulation**.
> "Simulation approved — nothing moved; it's recorded in the audit log."

Point at AG-0171 **HIGH 53 → LOW 5** and network at-risk **25 → 24**.

**6. Impact (35 s)** (guide step 6). Point at *V1 vs V2 at a glance*:
> "We replayed 14 held-out days with identical demand and identical total cash. V2 cuts unmet demand
> to BDT 56.9 lakh, from 95.4 without AgentFlow, with 345 transfers instead of V1's 501, 14 donor
> shortages instead of 25, and lower logistics cost. One honest caveat: a slightly larger share of V2's
> transfers turn out unnecessary — 24.3% vs 21.4% — though fewer in number."

**Close (10 s):**
> "Synthetic data, explainable risk, human-approved simulations, and a held-out evaluation we can reproduce."

**Don't** spend time on: the anomaly panel, Scenario Lab, the 48-h chart axes, fairness tables.

---

## C. 5-minute full demo

Do B, then add:

1. **Without action, proven (20 s).** Set decision time to **19:00** and reopen AG-0171. Without
   action its cash hits **BDT 0 at 19:00** and **BDT 11,830** of cash-out is turned away (red bar),
   inside the window flagged at 13:00. Then click **Reset demo**.
2. **V1 vs V2 on the same agent (20 s).** In the Rebalancing Center click **V1 — nearest donor**. V1
   needs **two** transfers (RB-019 + RB-020, est. BDT 305 + 343) for the same result. V2 uses one
   (BDT 456). Click **V2** again.
3. **Model health (40 s).** Impact page → *Model health*: cash-demand MAE **BDT 6,138** vs 7,890 for
   the best simple rule (−22%). P90 band covers **89.5%** (target 90%). HIGH+ alerts are right
   **81.5%** of the time (ROC-AUC 0.935).
4. **Held for review (15 s).** Rebalancing Center → *Held for manual review*: **AG-0111** has unusual
   activity, so no automatic support is proposed. "Anomaly is not fraud; it means a person looks first."
5. **Scenario Lab (20 s, optional).** Apply **+25%** demand: at-risk agents **25 → 31**, and more need
   is escalated to the distributor.

---

## IF INTERNET / API FAILS

1. **The page says "Live decision service is temporarily unavailable. Your data has not changed."**
   Click **Retry** once. Say: *"The live API is a hosted prototype; let me reconnect."*
2. **Still failing after about 20 seconds:** switch to the local copy (`uvicorn app.main:app --port 8000`
   in `apps/api`, `npm run dev` in `apps/web`). It shows the same deterministic numbers.
3. **No laptop network at all:** use the backup screenshots or recording, and say so clearly:
   *"These are recorded screens of the same build."*
4. **Never** claim recorded screens are live, and never improvise numbers. Use the ones in this script.

There is deliberately no fake "offline mode": the app never presents cached numbers as live data.

---

## If a judge interrupts and asks…

| Question | Short, accurate answer |
|---|---|
| Is this real upay data? | No. It's synthetic data from our own seeded generator, with no personal information. |
| Why ML? | Demand depends on hour, weekday, salary days and agent history together. ML cuts 6-hour cash-demand error by 22% versus the best simple rule. |
| Why not a simple rule? | We tested that. The same V1 decision engine fed a simple seasonal forecast leaves BDT 67.6 lakh unmet, versus 58.3 lakh with the ML forecast. |
| Why V2? | V1 picked the nearest donor. V2 adds a benefit gate, a safer dynamic donor reserve and cost-aware ranking: 345 vs 501 transfers, 14 vs 25 donor shortages, lower cost, slightly more benefit. |
| Is this fraud detection? | No. Anomalies mean "unusual for this agent". They route the case to manual review and never label fraud. |
| Does it transfer money? | No. Approval runs a simulation and writes an audit entry. No payment instruction exists. |
| What if the forecast is wrong? | We plan for a cautious P90 scenario, donors keep a reserve, and a person reviews. It still happens: 14 donor shortage events in 345 simulated transfers. |
| Why is unnecessary-transfer % higher in V2? | V2 makes fewer, larger transfers. The number of unnecessary ones fell (107 → 84) but their share rose (21.4% → 24.3%). The gate removes low-value moves; it can't fix forecast false alarms. |
| How did you avoid tuning on the test set? | V2 settings were chosen on two earlier validation windows inside the training period, with forecast models retrained on even earlier data. The 14-day test window was used once, with a decision rule written beforehand. |
| What is the Morning Plan? | A proactive 08:00 plan: a full-day forecast of cash and e-float needs, and the same district budgets repositioned (BDT 0 extra). A person reviews it; approval only simulates. |
| Does the ML really matter there? | In fresh synthetic audit worlds it beat strong cautious historical rules (7-day q90 and max) in 5 of 5, with a median 20.6% lower unmet demand. That is synthetic evidence, not upay results, and low-volume agents did worse than q90 in 4 of 5. |
| Why not peer cash/e-float swaps? | We tested it: safe, nearby, same-time complementary agents were too rare, so we rejected it. |
| What is the biggest limitation? | It's all synthetic. Real data would need re-validation, a shadow pilot with operations staff, and re-tuning. |

---

## What NOT to say

- "This is upay's data" / "upay uses this" / "this is in production".
- "It moves money automatically" / "transfer completed".
- "Fraud detected".
- "V2 is better on every metric".
- "Proven in the real world".
- "The Morning Plan will save 20.6% today" (it is historical synthetic evidence, not a per-date saving).
