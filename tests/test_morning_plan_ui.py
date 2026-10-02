"""Morning Plan frontend: TypeScript contract vs. API, labels, safety wording, states and page wiring."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
PAGE = (WEB / "app" / "morning-plan" / "page.tsx").read_text()
EVIDENCE = (WEB / "components" / "MorningEvidence.tsx").read_text()
TYPES = (WEB / "lib" / "types.ts").read_text()


def _iface(name: str) -> str:
    m = re.search(rf"export (?:interface|type) {name}\b[^{{]*{{(.*?)\n}}", TYPES, re.S)
    assert m, name
    return m.group(1)


def test_typescript_contract_covers_api_response():
    from app.morning_plan import MorningPlanService
    mp = MorningPlanService()
    plan = mp.plan(mp.default_date)
    agent_t, district_t, res_t = _iface("MorningPlanAgent"), _iface("MorningPlanDistrict"), _iface("MorningResourceSummary")
    for k in plan["agents"][0]:
        assert re.search(rf"\b{k}\??:", agent_t), f"MorningPlanAgent missing {k}"
    for k in plan["districts"][0]:
        assert re.search(rf"\b{k}\??:", district_t), f"MorningPlanDistrict missing {k}"
    for k in plan["network"]["cash"]:
        assert re.search(rf"\b{k}\??:", res_t), f"MorningResourceSummary missing {k}"
    plan_t = _iface("MorningPlan")
    for k in ("conserved", "extra_working_capital_bdt", "matches_frozen_demo_fixture_allocation", "flag_counts", "review_focus"):
        assert k in plan_t
    ev_t = _iface("MorningPlanEvidence")
    for k in mp.evidence():
        if k not in ("source_research_commit", "frozen_model_spec_commit"):
            assert re.search(rf"\b{k}\??:", ev_t), f"MorningPlanEvidence missing {k}"
    for code in ("large_allocation_decrease", "low_volume_review", "rural_efloat_review", "p90_not_covered"):
        assert code in TYPES


def test_page_title_subtitle_and_trust_labels():
    assert 'title="Morning Liquidity Plan"' in PAGE
    assert "Pre-position physical cash and e-float before demand arrives — using the same working capital." in PAGE
    for chip in ("Synthetic demo", "Human-reviewed", "Same working capital", "No money moves"):
        assert f'"{chip}"' in PAGE
    assert "07:00 Predict" in PAGE and "08:00 Position" in PAGE and "Intraday monitor" in PAGE
    assert "extra working capital" in PAGE and "matches budget exactly" in PAGE


def test_conservation_and_review_ui_is_present():
    for text in ("District budgets — conservation proof", "BDT 0 difference", "Review focus", "Largest allocation cuts",
                 "Low-volume agents receiving cuts", "Rural agents with large e-float reductions", "Every district conserved exactly"):
        assert text in PAGE, text
    assert "Future outcomes are unknown at 07:00" in PAGE
    assert "will be harmed" not in PAGE.lower()
    assert "matches_frozen_demo_fixture_allocation" in PAGE and "matches the frozen serving fixture exactly" in PAGE
    assert "by at most BDT 1 due to forecast rounding" in PAGE


def test_loading_error_retry_empty_and_date_switching_states():
    assert "<ErrorState" in PAGE and "onRetry={plan.reload}" in PAGE and "onRetry={dates.reload}" in PAGE
    assert "<Loading" in PAGE and "No Morning Plan dates are available." in PAGE
    assert 'aria-label="Plan date"' in PAGE and "setDate(" in PAGE
    assert "No agents match this filter on this date." in PAGE


def test_human_review_is_simulation_only():
    assert '"/api/morning-plan/simulate"' in PAGE and "reviewer_acknowledged: true" in PAGE
    assert "disabled={!ack || busy}" in PAGE and "Approve Simulation" in PAGE
    assert "Nothing is transferred." in PAGE
    assert 'role="dialog"' in PAGE and 'aria-modal="true"' in PAGE and "Escape" in PAGE


def test_evidence_panel_wording_and_caveats():
    assert "Does ML add value beyond simple cautious rules?" in EVIDENCE
    for caveat in ("not upay data", "not a guaranteed saving", "nominal 90%", "Low-volume agents did worse than the q90 rule",
                   "rural e-float allocations can fall", "not an expected saving for the selected date"):
        assert caveat in EVIDENCE, caveat
    assert "q90" in EVIDENCE and "same synthetic world family" in EVIDENCE


def test_navigation_command_center_rebalancing_impact_rai_and_guide():
    shell = (WEB / "components" / "Shell.tsx").read_text()
    assert '{ href: "/morning-plan", label: "Morning Plan"' in shell
    home = (WEB / "app" / "page.tsx").read_text()
    assert "Before the day starts:" in home and "Open Morning Plan" in home and "same working capital" in home
    reb = (WEB / "app" / "rebalancing" / "page.tsx").read_text()
    assert "proactive full-day positioning" in reb and "reactive" in reb and "does not optimise e-float" in reb
    imp = (WEB / "app" / "impact" / "page.tsx").read_text()
    assert "Full-day Morning Plan — research evidence" in imp and "must not be combined with the V1/V2 tables" in imp
    rai = (WEB / "app" / "responsible-ai" / "page.tsx").read_text()
    for t in ("low-volume", "rural e-float", "about 85%", "Real-data shadow validation", "no customer PII"):
        assert t in rai, t
    guide = (WEB / "components" / "DemoGuide.tsx").read_text()
    assert 'title: "Morning Plan"' in guide and 'href: "/morning-plan"' in guide
    assert len(re.findall(r"\n\s+n: \d+,", guide)) == 6  # demo stays short
