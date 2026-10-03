"""Premium UI polish: product framing, trust signals, Morning Plan board, demo presets, V2 safety gate,
separated evidence, accessibility/motion safeguards and claim-safe wording."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"


def _read(*parts: str) -> str:
    return (WEB.joinpath(*parts)).read_text()


SHELL = _read("components", "Shell.tsx")
UI = _read("components", "ui.tsx")
HOME = _read("app", "page.tsx")
MORNING = _read("app", "morning-plan", "page.tsx")
AGENT = _read("app", "agents", "[id]", "page.tsx")
REBAL = _read("app", "rebalancing", "page.tsx")
IMPACT = _read("app", "impact", "page.tsx")
LAYOUT = _read("app", "layout.tsx")
CSS = _read("app", "globals.css")
ALL_TSX = "\n".join(p.read_text() for p in WEB.rglob("*.tsx"))


def test_full_product_tagline_and_scoped_intraday_line():
    tagline = "Same liquidity. Placed ahead of demand."
    assert f'PRODUCT_TAGLINE = "{tagline}"' in SHELL and "{PRODUCT_TAGLINE}" in SHELL
    assert tagline in LAYOUT and "PRODUCT_TAGLINE" in HOME
    # The old line is no longer the product-level brand ...
    assert "Predict. Explain. Rebalance." not in SHELL and "Predict. Explain. Rebalance." not in LAYOUT
    # ... and wherever it remains, it is explicitly scoped to the intraday system.
    for src in (HOME,):
        for m in re.finditer(r"Predict\. Explain\. Rebalance\.", src):
            window = src[max(0, m.start() - 200): m.end() + 200].lower()
            assert "intraday" in window


def test_trust_signals_are_persistent():
    for label in ("Synthetic data", "Human reviewed", "No money moves"):
        assert f'label: "{label}"' in UI
    assert "<TrustChips" in SHELL and "TRUST_SIGNALS" in SHELL
    assert "simulation only — no money moves" in ALL_TSX.lower()


def test_command_center_answers_the_first_ten_seconds():
    for text in ("07:00 Predict", "08:00 Position cash + e-float", "Monitor 6-hour cash pressure", "Recommend V2 recovery",
                 "Human review", "Attention", "Recommendation", "Action", "Where is risk?"):
        assert text in HOME, text
    assert 'value="BDT 0"' in HOME and 'value="Cash + E-float"' in HOME and 'value="Human reviewed"' in HOME
    assert "never combined" in HOME  # the two environments are not presented as one evaluation
    # every original KPI is still shown
    for k in ("active_agents", "at_risk_agents", "critical_agents", "projected_service_availability_pct",
              "forecast_cash_demand_6h", "recommended_rebalancing_value", "escalated_amount", "total_expected_shortfall"):
        assert f"k.{k}" in HOME, k


def test_morning_plan_placement_board_and_separate_resources():
    assert "Liquidity placement board" in MORNING and "Same amount. Different placement." in MORNING
    assert "AgentFlow plan" in MORNING and "Current" in MORNING
    assert '"serves cash-out"' in UI and '"serves cash-in"' in UI
    assert "conserved <b" in MORNING and "separately</b>" in MORNING and "never converts one into the other" in MORNING
    assert "--color-cash-600" in CSS and "--color-efloat-600" in CSS


def test_district_pressure_is_display_only_and_derived_from_the_response():
    assert "P90 need / available district budget" in MORNING
    assert "Display-only" in MORNING and "not a model metric" in MORNING
    assert "cash_p90_need_bdt / d.cash_budget_bdt" in MORNING and "efloat_p90_need_bdt / d.efloat_budget_bdt" in MORNING
    assert "PRESSURE_BANDS" in MORNING and "NOT model, risk or allocator thresholds" in MORNING
    for state in ('"Covered"', '"Tight"', '"Constrained"'):
        assert state in MORNING


def test_normal_and_stress_demo_presets_are_navigation_only():
    assert '{ label: "Normal day", date: "2026-08-24" }' in MORNING
    assert '{ label: "Stress day", date: "2026-08-31" }' in MORNING
    assert "not an average day" in MORNING
    assert "dates.includes(p.date)" in MORNING  # only offered when the API actually serves that date


def test_review_focus_requires_human_attention_with_all_flags():
    assert "Human attention required" in MORNING
    for code in ("large_allocation_decrease", "low_volume_review", "rural_efloat_review", "p90_not_covered"):
        assert code in MORNING
    assert "largest cuts first" in MORNING


def test_agent_decision_card_groups_now_expected_gap_risk_and_why_action_safety():
    for step in ('step="Now"', 'step="Expected"', 'step="Gap"', 'step="Risk"'):
        assert step in AGENT, step
    for section in ('title="Why"', 'title="Action"', 'title="Safety"'):
        assert section in AGENT, section
    assert 'id="why"' in AGENT and "text_bn" in AGENT  # anchor and Bangla explanation preserved
    assert "Simulation only — no money moves." in AGENT


def test_v2_safety_gate_uses_existing_recommendation_fields():
    for label in ("Recipient needs help", "Donor remains safe", "Transfer materially helps", "Logistics considered",
                  "Human review required"):
        assert f'label: "{label}"' in REBAL, label
    for field in ("destination_risk_before", "source_risk_after", "donor_margin_after_plan", "gate_reason",
                  "distance_km", "estimated_cost_bdt"):
        assert field in REBAL, field
    assert "<SafetyGate" in REBAL and "Approve Simulation" in REBAL and "Simulation only — no money moves." in REBAL


def test_impact_separates_intraday_and_morning_evidence():
    assert "Intraday V1/V2 evidence" in IMPACT and "Morning Plan evidence" in IMPACT
    assert IMPACT.count("Synthetic held-out evaluation") >= 2
    assert "not measured upay performance" in IMPACT
    assert "never combined into one experiment" in IMPACT
    assert "We kept the experiments that failed." in IMPACT
    assert "pre-registered decision rule" not in IMPACT and "legacy cash-only" not in IMPACT


def test_no_unsupported_claims_in_the_ui():
    text = ALL_TSX.lower()
    # negated disclaimers ("not a guaranteed saving") are required caveats, not claims
    text = re.sub(r"\b(not an?|no)\s+guaranteed savings?", "", text)
    for phrase in ("guaranteed saving", "real upay data", "autonomous transfer", "fraud detected",
                   "money transferred", "transfer completed", "proven in production", "will be harmed"):
        assert phrase not in text, phrase


def test_motion_respects_reduced_motion_and_focus_is_visible():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert ":focus-visible" in CSS
    assert 'role="dialog"' in MORNING and 'role="dialog"' in REBAL
    assert 'aria-current={active ? "page" : undefined}' in SHELL
