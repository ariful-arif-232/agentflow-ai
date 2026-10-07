export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AnomalyStatus = "NORMAL" | "WATCH" | "ANOMALOUS";

export interface Meta {
  as_of: string;
  data_label: string;
  currency: string;
  horizon_hours: number;
}

export interface AgentSummary {
  agent_id: string;
  district: string;
  location_cluster: string;
  agent_type: string;
  agent_volume_segment: string;
  cash_balance: number;
  pred_cash_demand_6h: number;
  pred_net_requirement_6h: number;
  pred_net_requirement_p90_6h: number;
  expected_shortfall: number;
  expected_surplus: number;
  coverage_ratio: number | null;
  risk_score: number;
  risk_level: RiskLevel;
  anomaly_status: AnomalyStatus;
  anomaly_score: number;
  review_priority: string;
  synthetic_latitude: number;
  synthetic_longitude: number;
}

export interface RiskSnapshot {
  risk_score: number;
  risk_level: RiskLevel;
  coverage_ratio: number | null;
}

/** Phase-2 synthetic operational cost proxy (not a measured upay cost). */
export interface LogisticsCost {
  travel_distance_km: number;
  distance_multiplier: number;
  billable_distance_km: number;
  travel_time_minutes: number;
  handling_time_minutes: number;
  base_handling_bdt: number;
  distance_cost_bdt: number;
  time_cost_bdt: number;
  cash_in_transit_cost_bdt: number;
  total_estimated_cost_bdt: number;
  assumption_label: string;
}

export type ReplenishmentCost =
  | ({ available: true; hub: string; hub_assumption: string; replenishment_amount_bdt: number } & LogisticsCost)
  | { available: false; unavailable_reason: string; hub_assumption: string; assumption_label: string };

export interface LogisticsAssumptions {
  assumption_label: string;
  deployment_note: string;
  hub_assumption: string;
  formula: string;
  phase1_formula: string;
  override: string;
  assumptions: Record<string, number>;
}

export interface PlanLogistics extends LogisticsAssumptions {
  peer_transfer_cost_bdt: number;
  peer_cash_in_transit_cost_bdt: number;
  average_cost_per_transfer_bdt: number | null;
  escalation_replenishment_cost_bdt: number;
  escalation_cash_in_transit_cost_bdt: number;
  escalations_costed: number;
  escalations_cost_unavailable: number;
  total_operational_cost_bdt: number;
}

export interface Recommendation {
  id: string;
  source_agent: string;
  destination_agent: string;
  recommended_amount: number;
  district: string;
  distance_km: number;
  /** Phase-1 estimate (BDT 150 + BDT 25/km), kept for auditability. */
  estimated_cost_bdt: number;
  logistics_cost: LogisticsCost;
  donor_rank: number;
  source_cash_before: number;
  source_cash_after: number;
  source_protected_level: number;
  destination_cash_before: number;
  destination_cash_after: number;
  destination_requirement_p50: number;
  destination_requirement_p90: number;
  legs_for_destination: number;
  destination_risk_before: RiskSnapshot;
  destination_risk_after: RiskSnapshot;
  source_risk_before: RiskSnapshot;
  source_risk_after: RiskSnapshot;
  reason: string;
  // V2-only evidence
  policy?: "v1" | "v2";
  donor_margin_after_plan?: number;
  destination_target_cash?: number;
  expected_benefit?: {
    risk_score_before: number;
    risk_score_after: number;
    risk_level_before: RiskLevel;
    risk_level_after: RiskLevel;
    shortfall_reduction_bdt: number;
    gate_reason: string;
  };
  candidate_rank_key?: {
    covers_remaining_need: boolean;
    risk_points_per_bdt100_cost: number;
    donor_margin_ratio_after: number;
    distance_km: number;
    ranking_cost_bdt?: number;
    ranking_cost_model?: "logistics_proxy" | "phase1_simple";
  };
}

export interface Escalation {
  agent_id: string;
  district: string;
  risk_score: number;
  unresolved_need: number;
  replenishment_cost?: ReplenishmentCost;
  reason: string;
}

export interface HeldForReview {
  agent_id: string;
  risk_score: number;
  need: number;
  reason: string;
}

export interface PlanSummary {
  n_recommendations: number;
  total_recommended_amount: number;
  recipients_supported: number;
  n_escalations: number;
  escalated_amount: number;
  n_held_for_review: number;
  estimated_cost_bdt: number;
  logistics?: PlanLogistics;
}

export type PolicyName = "v1" | "v2";

export interface Plan extends Meta {
  policy: PolicyName;
  default_policy: PolicyName;
  available_policies: PolicyName[];
  recommendations: Recommendation[];
  escalations: Escalation[];
  held_for_review: HeldForReview[];
  summary: PlanSummary;
  simulation_only: boolean;
}

export interface TrendPoint {
  timestamp: string;
  cash_out: number;
  cash_in: number;
  unmet: number;
  forecast_6h: number;
  actual_6h: number | null;
}

export interface Overview extends Meta {
  kpis: {
    active_agents: number;
    at_risk_agents: number;
    critical_agents: number;
    medium_risk_agents: number;
    anomaly_watch_agents: number;
    projected_service_availability_pct: number;
    projected_service_availability_after_plan_pct: number;
    forecast_cash_demand_6h: number;
    forecast_net_requirement_6h: number;
    total_expected_shortfall: number;
    recommended_rebalancing_value: number;
    n_recommendations: number;
    escalated_amount: number;
    rebalancing_policy: PolicyName;
  };
  kpi_definitions: Record<string, string>;
  risk_distribution: { level: RiskLevel; count: number }[];
  top_at_risk: AgentSummary[];
  urgent_recommendations: Recommendation[];
  demand_trend: TrendPoint[];
  districts: { district: string; agents: number; at_risk: number; expected_shortfall: number; forecast_demand: number }[];
}

export interface AgentsResponse extends Meta {
  count: number;
  agents: AgentSummary[];
  filters: { districts: string[]; clusters: string[]; segments: string[] };
}

export interface Reason {
  code: string;
  component: string;
  points: number;
  text: string;
  text_bn: string;
  evidence: Record<string, number | boolean | null>;
}

export interface HistoryPoint {
  timestamp: string;
  cash_balance: number;
  cash_out_amount: number;
  cash_in_amount: number;
  unmet_cash_out: number;
  transaction_count: number;
  future_6h_cash_demand: number | null;
  future_6h_net_cash_demand: number | null;
  pred_cash_demand_6h: number | null;
  pred_net_requirement_6h: number | null;
  anomaly_score: number | null;
}

export interface AnomalyDriver {
  feature: string;
  description: string;
  robust_z: number;
  ratio_vs_usual: number | null;
}

export interface AgentDetail extends Meta {
  agent: {
    agent_id: string;
    district: string;
    location_cluster: string;
    agent_type: string;
    agent_volume_segment: string;
    synthetic_latitude: number;
    synthetic_longitude: number;
  };
  liquidity: { cash_balance: number; efloat_balance: number; morning_target_cash: number; cash_out_last_6h: number };
  forecast: {
    pred_cash_demand_6h: number;
    pred_net_requirement_6h: number;
    pred_net_requirement_p90_6h: number;
    expected_shortfall: number;
    expected_surplus: number;
    seasonal_same_window_avg7: number;
    source: string;
  };
  risk: {
    risk_score: number;
    risk_level: RiskLevel;
    coverage_ratio: number | null;
    coverage_ratio_p90: number | null;
    components: Record<string, number>;
    component_max: Record<string, number>;
    source: string;
  };
  explanation: Reason[];
  anomaly: { status: AnomalyStatus; score: number; peak_time: string | null; drivers: AnomalyDriver[]; note: string };
  review_priority: string;
  recommended_action: { type: string; summary: string };
  recommendations: {
    as_destination: Recommendation[];
    as_source: Recommendation[];
    escalation: Escalation[];
    held: HeldForReview[];
  };
  history: HistoryPoint[];
  model_context: {
    cash_demand_mae_ml: number | null;
    cash_demand_mae_naive: number | null;
    net_requirement_mae_ml: number | null;
    p90_coverage: number | null;
  };
}

export interface SimulationResult extends Meta {
  simulation_id: string;
  /** true when the same approval was submitted before: the original audit record is returned. */
  replayed?: boolean;
  record_hash?: string;
  audit_note?: string;
  created_at: string;
  recommendation_ids: string[];
  total_amount: number;
  reviewer_note: string | null;
  status: string;
  simulation_only: boolean;
  agents: {
    agent_id: string;
    role: "source" | "destination";
    cash_before: number;
    cash_after: number;
    risk_score_before: number;
    risk_score_after: number;
    risk_level_before: RiskLevel;
    risk_level_after: RiskLevel;
    coverage_before: number | null;
    coverage_after: number | null;
  }[];
  portfolio_before: Portfolio;
  portfolio_after: Portfolio;
}

export interface Portfolio {
  at_risk_agents: number;
  critical_agents: number;
  total_expected_shortfall: number;
  projected_service_availability_pct: number;
}

export interface PolicyMetrics {
  shortage_events: number;
  unmet_cash_demand_bdt: number;
  agents_with_shortage: number;
  service_availability_pct: number;
  demand_fill_rate_pct: number;
  interventions: number;
  total_rebalanced_bdt: number;
  estimated_logistics_cost_bdt: number;
  donor_shortage_events_after_transfer?: number;
  unnecessary_interventions_pct?: number;
  escalated_need_bdt?: number;
  unmet_avoided_bdt?: number;
  unmet_avoided_per_transfer_bdt?: number | null;
  unmet_avoided_per_1000_cost_bdt?: number | null;
  shortage_events_avoided_per_100_transfers?: number | null;
}

export interface VsStatusQuo {
  shortage_events_reduction_pct: number;
  unmet_demand_reduction_pct: number;
  unmet_demand_avoided_bdt: number;
  service_availability_gain_pp: number;
}

export interface ImpactResponse {
  label: string;
  period: { start: string; end: string; hours: number; agents: number };
  assumptions: Record<string, unknown>;
  metric_definitions: Record<string, string>;
  policies: Record<"status_quo" | "naive_rebalancing" | "agentflow" | "agentflow_v2", PolicyMetrics>;
  agentflow_vs_status_quo: VsStatusQuo;
  agentflow_v2_vs_status_quo: VsStatusQuo;
  deployment_decision: {
    rule: string;
    retention_vs_v1: number;
    checks: Record<string, boolean>;
    strictly_better: Record<string, boolean>;
    default_policy: PolicyName;
  };
  daily: Record<string, number | string>[];
  groups: Record<string, Record<string, Record<string, { unmet_cash_demand_bdt: number; shortage_events: number }>>>;
  phase2_logistics?: Phase2Logistics;
}

export interface Phase2PolicyLogistics {
  interventions: number;
  peer_transfer_logistics_cost_bdt: number;
  average_cost_per_transfer_bdt: number | null;
  peer_cost_components_bdt: { base_handling_bdt: number; distance_cost_bdt: number; time_cost_bdt: number; cash_in_transit_cost_bdt: number };
  peer_cash_in_transit_cost_bdt: number;
  distributor_escalation_cost_proxy_bdt: number;
  distributor_escalation_events_costed: number;
  distributor_escalation_events_unavailable: number;
  total_operational_logistics_cost_proxy_bdt: number;
  unmet_avoided_bdt: number;
  unmet_avoided_per_1000_peer_logistics_cost_bdt: number | null;
  unmet_avoided_per_1000_total_logistics_cost_bdt: number | null;
}

export interface Phase2Logistics {
  label: string;
  version: string;
  assumptions: LogisticsAssumptions;
  metric_definitions: Record<string, string>;
  serving_v2_ranking_cost_model: "phase1_simple";
  experiment_ranking_cost_model: "logistics_proxy";
  experiment_status: string;
  v2_parameters_note: string;
  policies: {
    naive_rebalancing: Phase2PolicyLogistics;
    agentflow: Phase2PolicyLogistics;
    /** Serving V2 (proven Phase-1 ranking), costed with the Phase-2 proxy. */
    agentflow_v2: Phase2PolicyLogistics;
    /** Experiment, not adopted: V2 ranked by the logistics-cost proxy. */
    agentflow_v2_logistics_ranking_experiment: Phase2PolicyLogistics & PolicyMetrics;
  };
  v2_ranking_change: {
    phase1_ranking: Partial<PolicyMetrics>;
    logistics_proxy_ranking: Partial<PolicyMetrics>;
    transfer_legs_changed: number;
    v2_vs_status_quo: Record<"phase1_ranking" | "logistics_proxy_ranking", { shortage_events_reduction_pct: number; unmet_demand_reduction_pct: number }>;
  };
  deployment_rule_recheck: { default_policy: PolicyName; checks: Record<string, boolean>; note: string };
}

export interface RegressionMetrics {
  mae: number;
  rmse: number;
  wape: number;
  bias: number;
  n: number;
}

export interface AlertMetrics {
  alerts: number;
  alert_rate: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number;
}

export interface MetricsResponse {
  label: string;
  metrics: {
    forecast: {
      test_start: string;
      test_end: string;
      n_test_rows: number;
      targets: Record<
        string,
        {
          target: string;
          ml_model: RegressionMetrics;
          baselines: Record<string, RegressionMetrics>;
          best_baseline: string;
          improvement_vs_best_baseline: { mae_pct: number; rmse_pct: number };
          improvement_vs_naive: { mae_pct: number; rmse_pct: number };
        }
      >;
      quantile_p90: { empirical_coverage: number; nominal_coverage: number; mean_band_width: number };
      group_consistency: Record<string, Record<string, { ml_mae: number; ml_wape: number; naive_mae: number; naive_wape: number; n: number }>>;
      feature_importance_cash_demand: { feature: string; mae_increase: number; std: number }[];
    };
    anomaly: {
      roc_auc: number;
      average_precision: number;
      prevalence: number;
      n_labelled_anomalies: number;
      by_status: Record<string, { flagged: number; true_positives: number; precision: number; recall: number }>;
      recall_by_type_watch_or_higher: Record<string, number>;
      components: Record<string, { roc_auc: number; average_precision: number }>;
    };
    risk_alerts: {
      n_decisions: number;
      shortage_prevalence: number;
      variants: Record<string, AlertMetrics>;
      calibration_by_level: Record<string, { share_of_decisions: number; observed_shortage_rate: number | null }>;
      group_consistency: Record<string, Record<string, { alert_rate: number; precision: number; recall: number; f1: number; shortage_prevalence: number }>>;
    };
  };
  training: { n_train_rows: number; train_start: string; train_end: string; algorithm: string; features: string[] };
  dataset: { n_agents: number; n_rows: number; start: string; end: string; test_start: string };
}

export interface ScenarioSummary {
  risk_distribution: Record<RiskLevel, number>;
  at_risk_agents: number;
  total_expected_shortfall: number;
  projected_service_availability_pct: number;
  recommended_rebalancing_value: number;
  n_recommendations: number;
  escalated_amount: number;
}

export interface ScenarioResponse extends Meta {
  inputs: { demand_shock_pct: number; district: string | null; regional_shock_pct: number };
  baseline: ScenarioSummary;
  scenario: ScenarioSummary;
  note: string;
}

// ---------------------------------------------------------------- Morning Liquidity Plan (proactive, full day)
export type MorningResource = "cash" | "efloat";
export type MorningReviewCode = "large_allocation_decrease" | "low_volume_review" | "rural_efloat_review" | "p90_not_covered";

export interface MorningPlanMeta {
  information_cutoff: string;
  allocation_time: string;
  horizon: string;
  synthetic_data: true;
  simulation_only: true;
  world_version: string;
  assumptions_version: string;
  demo_seed: number;
  frozen_model_spec_commit: string;
  source_research_commit: string;
  signal: string;
  floors_bdt: Record<MorningResource, number>;
  labels: { synthetic: string; human_review: string; same_working_capital: string; no_money_moves: string };
  note: string;
}

export interface MorningPlanDates extends MorningPlanMeta {
  dates: string[];
  default_date: string;
}

export interface MorningResourceSummary {
  status_quo_total_bdt: number;
  recommended_total_bdt: number;
  difference_bdt: number;
  agents_increased: number;
  agents_decreased: number;
  agents_unchanged: number;
  repositioned_bdt: number;
  p90_need_total_bdt: number;
  agents_p90_covered_before: number;
  agents_p90_covered_after: number;
}

export interface MorningPlanDistrict {
  district: string;
  agents: number;
  cash_budget_bdt: number;
  cash_recommended_bdt: number;
  cash_difference_bdt: number;
  cash_p90_need_bdt: number;
  efloat_budget_bdt: number;
  efloat_recommended_bdt: number;
  efloat_difference_bdt: number;
  efloat_p90_need_bdt: number;
  conserved: boolean;
  agents_with_meaningful_change: number;
}

export interface MorningPlanAgent {
  agent_id: string;
  district: string;
  location_cluster: string;
  agent_volume_segment: "low" | "medium" | "high";
  status_quo_cash: number;
  recommended_cash: number;
  cash_delta: number;
  cash_p50: number;
  cash_p90: number;
  cash_coverage_before: number | null;
  cash_coverage_after: number | null;
  status_quo_efloat: number;
  recommended_efloat: number;
  efloat_delta: number;
  efloat_p50: number;
  efloat_p90: number;
  efloat_coverage_before: number | null;
  efloat_coverage_after: number | null;
  review_flags: { code: MorningReviewCode; label: string }[];
  explanation: { cash: string; efloat: string; constraint: string; safety: string };
}

export type MorningFocusAgent = Pick<
  MorningPlanAgent,
  "agent_id" | "district" | "location_cluster" | "agent_volume_segment" | "cash_delta" | "efloat_delta" |
  "status_quo_cash" | "status_quo_efloat" | "recommended_cash" | "recommended_efloat"
>;

export interface MorningPlan {
  date: string;
  meta: MorningPlanMeta;
  network: Record<MorningResource, MorningResourceSummary> & {
    agents: number;
    conserved: boolean;
    extra_working_capital_bdt: number;
    matches_frozen_demo_fixture_allocation: boolean;
    flag_counts: Record<MorningReviewCode, number>;
  };
  districts: MorningPlanDistrict[];
  agents: MorningPlanAgent[];
  review_focus: {
    conserved: boolean;
    largest_cuts: MorningFocusAgent[];
    low_volume_cuts: MorningFocusAgent[];
    low_volume_cuts_total: number;
    rural_efloat_cuts: MorningFocusAgent[];
    rural_efloat_cuts_total: number;
    note: string;
  };
}

export interface MorningPlanEvidence {
  label: string;
  display_note: string;
  synthetic_data: true;
  world_family: string;
  audit_seeds: number[];
  comparison: string;
  worlds_improved: number;
  worlds_total: number;
  pre_registered_bar_passed: boolean;
  combined_unmet_reduction_pct: { median: number; min: number; max: number };
  cash_unmet_reduction_pct_median: number;
  efloat_unmet_reduction_pct_median: number;
  exact_resource_conservation: boolean;
  extra_working_capital_bdt: number;
  pooled_p90_coverage: { cash: number; efloat: number; nominal: number };
  historical_signal_coverage_range: Record<string, Record<MorningResource, [number, number]>>;
  forecast_mae_improvement_vs_mean7_median_pct: Record<MorningResource, number>;
  caveats: string[];
  research_path: string[];
}

export interface MorningPlanSimulation {
  simulation_id: string;
  created_at: string;
  date: string;
  status: string;
  simulation_only: true;
  money_moved: false;
  cash_repositioned_bdt: number;
  efloat_repositioned_bdt: number;
  conservation: {
    conserved: boolean;
    extra_working_capital_bdt: number;
    network: Record<MorningResource, { status_quo_total_bdt: number; recommended_total_bdt: number; difference_bdt: number }>;
  };
}

/** Phase-2 business-impact layer. Synthetic simulated estimate — not measured upay performance. */
export interface BizEconomics {
  agent_commission_bps: number;
  illustrative_commission_protected_bdt: number;
  operational_logistics_cost_bdt: number;
  net_illustrative_value_bdt: number;
  benefit_cost_ratio: number | null;
  break_even_commission_bps: number | null;
}

export interface BizPolicy {
  customer: {
    requested_cash_out_bdt: number;
    served_cash_out_bdt: number;
    unmet_cash_out_bdt: number;
    demand_fill_rate_pct: number | null;
    shortage_agent_hours: number;
    requested_cash_out_transactions: number;
    estimated_failed_transactions: number;
    estimated_failed_transactions_method_b: number;
  };
  operations: {
    peer_transfers: number;
    cash_moved_by_peer_transfers_bdt: number;
    peer_logistics_cost_bdt: number;
    average_cost_per_peer_transfer_bdt: number | null;
    escalation_events: number;
    escalated_agent_days: number;
    escalated_need_bdt: number;
    distributor_cost_proxy_every_escalation_bdt: number;
    distributor_cost_proxy_one_trip_per_agent_day_bdt: number;
    distributor_trips_cost_unavailable: number;
  };
}

export interface BizVsStatusQuo {
  customer: {
    cash_out_value_protected_bdt: number;
    shortage_agent_hours_avoided: number;
    estimated_transactions_protected: number;
    estimated_transactions_protected_range: [number, number];
    fill_rate_gain_pp: number;
  };
  agent: { cash_out_value_protected_bdt: number; agent_commission_bps: number; illustrative_commission_protected_bdt: number; label: string };
  distributor: {
    trips_one_per_escalated_agent_day: number;
    logistics_cost_proxy_bdt: number;
    break_even_fee_per_trip_bdt: number | null;
    assumed_fee_per_trip_bdt: number | null;
    illustrative_margin_bdt: number | null;
    margin_note: string | null;
  };
  economics: {
    peer_transfers_only: BizEconomics;
    including_distributor_trips: BizEconomics;
    peer_cost_per_estimated_transaction_protected_bdt: number | null;
    peer_cost_per_bdt_1000_protected: number | null;
    roi: null;
    roi_note: string;
    label: string;
  };
}

export interface BusinessImpact {
  label: string;
  version: string;
  synthetic_data: true;
  simulated_estimate: true;
  product_story: string;
  assumptions: { agent_commission_bps: number; distributor_fee_per_trip_bdt: number | null; label: string; agent_commission_note: string };
  methodology: { transaction_estimate: string; roi_note: string; fallback_ticket_share_of_status_quo_unmet_pct: number };
  metric_definitions: Record<string, string>;
  calculations: {
    policies: Record<"status_quo" | "agentflow_v1" | "agentflow_v2" | "agentflow_v2_logistics_ranking_experiment", BizPolicy>;
    vs_status_quo: Record<"agentflow_v1" | "agentflow_v2" | "agentflow_v2_logistics_ranking_experiment", BizVsStatusQuo>;
  };
  sensitivity: Record<"agentflow_v1" | "agentflow_v2", { grid: (BizEconomics & { cost_multiplier: number })[]; break_even_commission_bps_by_cost_multiplier: { cost_multiplier: number; break_even_commission_bps: number | null }[] }>;
  limitations: string[];
}
