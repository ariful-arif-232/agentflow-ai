"""Morning Liquidity Plan serving layer (proactive, full-day, dual-resource).

Loads only two compact JSON artifacts, never the Dual World dataset or any model:

* ``ml/artifacts/morning_plan_demo.json``: a deterministic SYNTHETIC demo fixture (Dual World v2, seed
  2036) holding the frozen full-day ML forecasts (spec 3128176) and status-quo allocations. It contains
  decision-time information only: no realised demand, targets, outcomes or oracle values.
* ``ml/artifacts/morning_plan_evidence.json``: aggregate historical research evidence and caveats.

The allocation is recomputed LIVE with the validated deterministic allocator (need-first by full-day P90,
BDT 5,000 floors, fixed district budgets, integer BDT, ties by agent_id). Conservation is asserted at
runtime. Approval only runs a simulation: no money moves.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

ARTIFACTS = Path(__file__).resolve().parents[3] / "ml" / "artifacts"
FIXTURE_PATH = ARTIFACTS / "morning_plan_demo.json"
EVIDENCE_PATH = ARTIFACTS / "morning_plan_evidence.json"

FLOOR_BDT = {"cash": 5_000, "efloat": 5_000}
MEANINGFUL_CHANGE_BDT = 5_000
# Review-flag rules (fixed UI rules on the plan itself; they never use outcomes).
LARGE_CUT_BDT, LARGE_CUT_SHARE = 20_000, 0.50       # large allocation decrease
LOW_VOLUME_CUT_BDT, LOW_VOLUME_CUT_SHARE = 5_000, 0.25
RURAL_EFLOAT_CUT_SHARE = 0.50
MIN_COVERAGE_REQUIREMENT_BDT = 1_000
RES_LABEL = {"cash": "Physical cash", "efloat": "E-float"}
SIMULATION_STATUS = "Simulation approved — no money moved."
LABELS = {
    "synthetic": "Synthetic demo — Dual-Liquidity World v2, not real upay data",
    "human_review": "Human-reviewed decision support — nothing executes automatically",
    "same_working_capital": "Same working capital — district cash and e-float budgets are unchanged",
    "no_money_moves": "No money moves — approval only runs a simulation",
}
REVIEW_FLAGS = {
    "large_allocation_decrease": "Large allocation decrease",
    "low_volume_review": "Low-volume review",
    "rural_efloat_review": "Rural e-float review",
    "p90_not_covered": "Below full-day P90 need",
}
# Fields that would leak future information; the operational response must never contain them.
FORBIDDEN_FIELDS = ("future", "actual", "realised", "realized", "unmet", "oracle", "target_requirement", "outcome")


def bdt_in(x: float) -> str:
    """Whole BDT with South-Asian digit grouping (e.g. 1,39,000), matching the dashboard."""
    n = int(round(float(x)))
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts + [tail])


# ---------------------------------------------------------------- allocator (port of the validated research code)
def largest_remainder(total: int, weights: np.ndarray) -> np.ndarray:
    total = int(total)
    w = np.maximum(np.asarray(weights, float), 0.0)
    if total <= 0:
        return np.zeros(len(w), dtype=np.int64)
    if w.sum() <= 0:
        w = np.ones(len(w))
    exact = total * w / w.sum()
    base = np.floor(exact).astype(np.int64)
    rem = total - int(base.sum())
    if rem > 0:
        frac = exact - base
        base[np.lexsort((np.arange(len(w)), -frac))[:rem]] += 1
    return base


def allocate_resource(budget: int, p90: np.ndarray, status_quo: np.ndarray, floor: int) -> np.ndarray:
    """Need-first allocation of one district budget (agents in agent_id order)."""
    n = len(status_quo)
    if budget < n * floor:  # documented edge case: split in proportion to status quo
        return largest_remainder(budget, status_quo)
    alloc = np.full(n, floor, dtype=np.int64)
    remaining = int(budget) - n * floor
    need = np.ceil(np.maximum(np.asarray(p90, float) - floor, 0.0)).astype(np.int64)
    for i in np.lexsort((np.arange(n), -need)):  # largest need first, ties by agent_id
        if remaining <= 0:
            break
        give = min(int(need[i]), remaining)
        alloc[i] += give
        remaining -= give
    if remaining > 0:
        alloc += largest_remainder(remaining, status_quo)
    return alloc


# ---------------------------------------------------------------- service
class MorningPlanService:
    def __init__(self, fixture_path: Path = FIXTURE_PATH, evidence_path: Path = EVIDENCE_PATH) -> None:
        self.fixture = json.loads(fixture_path.read_text()) if fixture_path.exists() else {"meta": {}, "agents": [], "dates": {}}
        self.evidence_doc = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        agents = sorted(self.fixture["agents"], key=lambda a: a["agent_id"])
        assert [a["agent_id"] for a in agents] == [a["agent_id"] for a in self.fixture["agents"]], "fixture agents must be sorted"
        self.agents = agents
        self.dates = sorted(self.fixture["dates"])
        self._lock = threading.Lock()
        self.audit_log: list[dict] = []
        self._cache: dict[str, dict] = {}

    @property
    def available(self) -> bool:
        return bool(self.dates and self.agents)

    @property
    def default_date(self) -> str | None:
        return self.dates[-1] if self.dates else None

    def meta(self) -> dict:
        m = self.fixture.get("meta", {})
        return {"information_cutoff": m.get("information_cutoff", "07:00"), "allocation_time": m.get("allocation_time", "08:00"),
                "horizon": m.get("horizon", "08:00-23:59"), "synthetic_data": True, "simulation_only": True,
                "world_version": m.get("world_version"), "assumptions_version": m.get("assumptions_version"),
                "demo_seed": m.get("seed"), "frozen_model_spec_commit": m.get("frozen_model_spec_commit"),
                "source_research_commit": m.get("source_research_commit"), "signal": m.get("signal"),
                "floors_bdt": FLOOR_BDT, "labels": LABELS,
                "note": "Demo fixture from a synthetic world. The plan is decision support; it is not an expected saving."}

    def dates_payload(self) -> dict:
        return {"dates": self.dates, "default_date": self.default_date, **self.meta()}

    # ------------------------------------------------------------ plan
    def plan(self, date: str) -> dict:
        if date not in self.fixture["dates"]:
            raise KeyError(date)
        with self._lock:
            if date not in self._cache:
                self._cache[date] = self._build(date)
            return self._cache[date]

    def _build(self, date: str) -> dict:
        day = self.fixture["dates"][date]
        n = len(self.agents)
        sq = {"cash": np.array([a["status_quo_cash"] for a in self.agents], np.int64),
              "efloat": np.array([a["status_quo_efloat"] for a in self.agents], np.int64)}
        p50 = {"cash": np.array(day["cash_p50"], float), "efloat": np.array(day["efloat_p50"], float)}
        p90 = {"cash": np.array(day["cash_p90"], float), "efloat": np.array(day["efloat_p90"], float)}
        assert all(len(v) == n for v in (*p50.values(), *p90.values())), "fixture length mismatch"
        districts = np.array([a["district"] for a in self.agents])
        rec = {r: np.zeros(n, np.int64) for r in ("cash", "efloat")}
        for d in sorted(set(districts)):
            idx = np.where(districts == d)[0]
            for r in ("cash", "efloat"):
                rec[r][idx] = allocate_resource(int(sq[r][idx].sum()), p90[r][idx], sq[r][idx], FLOOR_BDT[r])
        # ---- runtime conservation and safety assertions (exact integer BDT)
        dist_rows = []
        for d in sorted(set(districts)):
            idx = np.where(districts == d)[0]
            row = {"district": d, "agents": int(len(idx))}
            for r in ("cash", "efloat"):
                budget, total = int(sq[r][idx].sum()), int(rec[r][idx].sum())
                if total != budget:
                    raise RuntimeError(f"conservation violated: {d} {r} {total} != {budget}")
                row[f"{r}_budget_bdt"], row[f"{r}_recommended_bdt"] = budget, total
                row[f"{r}_difference_bdt"] = total - budget
                row[f"{r}_p90_need_bdt"] = float(round(p90[r][idx].sum(), 2))
            row["conserved"] = row["cash_difference_bdt"] == 0 and row["efloat_difference_bdt"] == 0
            delta_any = np.maximum(np.abs(rec["cash"][idx] - sq["cash"][idx]), np.abs(rec["efloat"][idx] - sq["efloat"][idx]))
            row["agents_with_meaningful_change"] = int((delta_any >= MEANINGFUL_CHANGE_BDT).sum())
            dist_rows.append(row)
        for r in ("cash", "efloat"):
            if (rec[r] < 0).any():
                raise RuntimeError("negative allocation")
            if (rec[r] < FLOOR_BDT[r]).any() and all(row[f"{r}_budget_bdt"] >= row["agents"] * FLOOR_BDT[r] for row in dist_rows):
                raise RuntimeError("floor violated")
        parity = all(np.array_equal(rec[r], np.array(day[f"recommended_{r}"], np.int64)) for r in ("cash", "efloat"))

        budgets = {d["district"]: d for d in dist_rows}
        agents_out = []
        for i, a in enumerate(self.agents):
            row = {"agent_id": a["agent_id"], "district": a["district"], "location_cluster": a["location_cluster"],
                   "agent_volume_segment": a["agent_volume_segment"]}
            for r in ("cash", "efloat"):
                s, rc, q50, q90 = int(sq[r][i]), int(rec[r][i]), float(p50[r][i]), float(p90[r][i])
                row[f"status_quo_{r}"], row[f"recommended_{r}"], row[f"{r}_delta"] = s, rc, rc - s
                row[f"{r}_p50"], row[f"{r}_p90"] = q50, q90
                ok = q90 >= MIN_COVERAGE_REQUIREMENT_BDT
                row[f"{r}_coverage_before"] = s / q90 if ok else None
                row[f"{r}_coverage_after"] = rc / q90 if ok else None
            row["review_flags"] = self._flags(row)
            row["explanation"] = self._explain(row, budgets[a["district"]])
            agents_out.append(row)

        net = {}
        for r in ("cash", "efloat"):
            d = rec[r] - sq[r]
            net[r] = {"status_quo_total_bdt": int(sq[r].sum()), "recommended_total_bdt": int(rec[r].sum()),
                      "difference_bdt": int(rec[r].sum() - sq[r].sum()), "agents_increased": int((d > 0).sum()),
                      "agents_decreased": int((d < 0).sum()), "agents_unchanged": int((d == 0).sum()),
                      "repositioned_bdt": int(d[d > 0].sum()), "p90_need_total_bdt": float(round(p90[r].sum(), 2)),
                      "agents_p90_covered_before": int((sq[r] >= p90[r]).sum()),
                      "agents_p90_covered_after": int((rec[r] >= p90[r]).sum())}
        conserved = all(row["conserved"] for row in dist_rows) and all(v["difference_bdt"] == 0 for v in net.values())
        plan = {"date": date, "meta": self.meta(),
                "network": {**net, "agents": n, "conserved": conserved, "extra_working_capital_bdt": 0,
                            "matches_frozen_demo_fixture_allocation": parity,
                            "flag_counts": {k: sum(k in [f["code"] for f in x["review_flags"]] for x in agents_out)
                                            for k in REVIEW_FLAGS}},
                "districts": dist_rows, "agents": agents_out, "review_focus": self._focus(agents_out, conserved)}
        _assert_no_future_fields(plan)
        return plan

    @staticmethod
    def _flags(row: dict) -> list[dict]:
        flags = []
        cuts = {r: -row[f"{r}_delta"] for r in ("cash", "efloat")}
        if any(cuts[r] >= LARGE_CUT_BDT and cuts[r] >= LARGE_CUT_SHARE * row[f"status_quo_{r}"] for r in cuts):
            flags.append("large_allocation_decrease")
        if row["agent_volume_segment"] == "low" and any(
                cuts[r] >= LOW_VOLUME_CUT_BDT and cuts[r] >= LOW_VOLUME_CUT_SHARE * row[f"status_quo_{r}"] for r in cuts):
            flags.append("low_volume_review")
        if (row["location_cluster"] == "rural" and cuts["efloat"] >= MEANINGFUL_CHANGE_BDT
                and cuts["efloat"] >= RURAL_EFLOAT_CUT_SHARE * row["status_quo_efloat"]):
            flags.append("rural_efloat_review")
        if any(row[f"recommended_{r}"] < row[f"{r}_p90"] for r in ("cash", "efloat")):
            flags.append("p90_not_covered")
        return [{"code": c, "label": REVIEW_FLAGS[c]} for c in flags]

    @staticmethod
    def _explain(row: dict, district: dict) -> dict:
        out = {}
        for r in ("cash", "efloat"):
            name, s, rc, q90 = RES_LABEL[r], row[f"status_quo_{r}"], row[f"recommended_{r}"], row[f"{r}_p90"]
            d = rc - s
            floor_note = f" It is held at the BDT {bdt_in(FLOOR_BDT[r])} minimum floor." if rc == FLOOR_BDT[r] else ""
            if d > 0 and q90 > s:
                text = (f"{name} increased by BDT {bdt_in(d)} because the full-day P90 requirement (BDT {bdt_in(q90)}) exceeds the "
                        f"current morning allocation (BDT {bdt_in(s)}) while the district budget remains fixed.")
            elif d > 0:
                text = (f"{name} increased by BDT {bdt_in(d)}. The full-day P90 requirement (BDT {bdt_in(q90)}) is already within the "
                        f"current allocation (BDT {bdt_in(s)}); this is its share of the {row['district']} budget left over after "
                        "every agent's P90 need is covered.")
            elif d < 0 and q90 < s:
                text = (f"{name} reduced by BDT {bdt_in(-d)}: the full-day P90 requirement (BDT {bdt_in(q90)}) is below the current "
                        f"allocation (BDT {bdt_in(s)}), so the surplus is repositioned to higher-need agents in {row['district']} "
                        f"within the same district budget.{floor_note}")
            elif d < 0:
                text = (f"{name} reduced by BDT {bdt_in(-d)}: the {row['district']} budget cannot cover every agent's full-day P90 "
                        f"need, and agents with a larger uncovered need were served first.{floor_note}")
            else:
                text = f"{name} unchanged at BDT {bdt_in(s)}."
            if rc > q90 and d != 0 and not (d > 0 and q90 <= s):
                text += (" After all P90 needs in the district are covered, the remaining budget is shared in proportion "
                         "to status-quo allocations.")
            elif rc < q90 and not (d < 0 and q90 >= s):
                text += (" The fixed district budget does not cover this agent's full P90 need; agents with a larger "
                         "uncovered need were served first.")
            out[r] = text
        out["constraint"] = (f"{row['district']} budgets stay fixed (cash BDT {bdt_in(district['cash_budget_bdt'])}, e-float "
                             f"BDT {bdt_in(district['efloat_budget_bdt'])}). Every agent keeps at least BDT 5,000 of each resource. "
                             "Allocation is need-first by full-day P90 requirement, ties broken by agent ID.")
        out["safety"] = "Human review required. Synthetic decision support. No automatic transfer; approval only simulates."
        return out

    @staticmethod
    def _focus(agents: list[dict], conserved: bool) -> dict:
        def cut(a):
            return max(-a["cash_delta"], -a["efloat_delta"])
        slim = lambda a: {k: a[k] for k in ("agent_id", "district", "location_cluster", "agent_volume_segment",  # noqa: E731
                                            "cash_delta", "efloat_delta", "status_quo_cash", "status_quo_efloat",
                                            "recommended_cash", "recommended_efloat")}
        has = lambda a, c: any(f["code"] == c for f in a["review_flags"])  # noqa: E731
        largest = sorted([a for a in agents if cut(a) > 0], key=lambda a: (-cut(a), a["agent_id"]))[:5]
        low = sorted([a for a in agents if has(a, "low_volume_review")], key=lambda a: (-cut(a), a["agent_id"]))
        rural = sorted([a for a in agents if has(a, "rural_efloat_review")], key=lambda a: (a["efloat_delta"], a["agent_id"]))
        return {"conserved": conserved, "largest_cuts": [slim(a) for a in largest],
                "low_volume_cuts": [slim(a) for a in low[:5]], "low_volume_cuts_total": len(low),
                "rural_efloat_cuts": [slim(a) for a in rural[:5]], "rural_efloat_cuts_total": len(rural),
                "note": "Review indicators describe the plan itself; future outcomes are unknown at decision time."}

    # ------------------------------------------------------------ evidence and simulation
    def evidence(self) -> dict:
        return {**self.evidence_doc, "synthetic_data": True,
                "display_note": "Historical synthetic research evidence. It is not an expected saving for the selected date."}

    def simulate(self, date: str, note: str | None) -> dict:
        plan = self.plan(date)
        net = plan["network"]
        entry = {"simulation_id": f"MLP-{uuid.uuid4().hex[:8].upper()}",
                 "created_at": datetime.now(timezone.utc).isoformat(), "date": date, "reviewer_note": note,
                 "status": SIMULATION_STATUS, "cash_repositioned_bdt": net["cash"]["repositioned_bdt"],
                 "efloat_repositioned_bdt": net["efloat"]["repositioned_bdt"]}
        with self._lock:
            self.audit_log.insert(0, entry)
            del self.audit_log[200:]
        return {**entry, "simulation_only": True, "money_moved": False,
                "conservation": {"conserved": net["conserved"], "extra_working_capital_bdt": 0,
                                 "network": {r: {k: net[r][k] for k in ("status_quo_total_bdt", "recommended_total_bdt", "difference_bdt")}
                                             for r in ("cash", "efloat")},
                                 "districts": [{k: d[k] for k in ("district", "cash_budget_bdt", "cash_recommended_bdt",
                                                                  "efloat_budget_bdt", "efloat_recommended_bdt", "conserved")}
                                               for d in plan["districts"]]},
                "audit_note": "Recorded in the in-memory Morning Plan audit log (resets when the API restarts)."}


def _assert_no_future_fields(obj, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(t in str(k).lower() for t in FORBIDDEN_FIELDS):
                raise RuntimeError(f"future/outcome field in operational response: {path}.{k}")
            _assert_no_future_fields(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for v in obj[:3]:
            _assert_no_future_fields(v, path)


@lru_cache(maxsize=1)
def get_morning_plan() -> MorningPlanService:
    return MorningPlanService()
