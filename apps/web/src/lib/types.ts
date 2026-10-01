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

export interface Recommendation {
  id: string;
  source_agent: string;
  destination_agent: string;
  recommended_amount: number;
  district: string;
  distance_km: number;
  estimated_cost_bdt: number;
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
}

export interface Escalation {
  agent_id: string;
  district: string;
  risk_score: number;
  unresolved_need: number;
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
}

export interface Plan extends Meta {
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
}

export interface ImpactResponse {
  label: string;
  period: { start: string; end: string; hours: number; agents: number };
  assumptions: Record<string, unknown>;
  metric_definitions: Record<string, string>;
  policies: Record<"status_quo" | "naive_rebalancing" | "agentflow", PolicyMetrics>;
  agentflow_vs_status_quo: {
    shortage_events_reduction_pct: number;
    unmet_demand_reduction_pct: number;
    unmet_demand_avoided_bdt: number;
    service_availability_gain_pp: number;
  };
  daily: Record<string, number | string>[];
  groups: Record<string, Record<string, Record<string, { unmet_cash_demand_bdt: number; shortage_events: number }>>>;
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
