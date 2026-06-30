export type Methodology = "workout" | "market" | "implied_market";

export type OpenDefaultMethod = "elbe" | "probability_weighted";

export type WeightingMethod = "ead_weighted" | "number_weighted";

export type CureLgdMethod = "fixed" | "calculated";

export type Segment = string;

export type CollateralType =
  | "none"
  | "residential_real_estate"
  | "commercial_real_estate"
  | "financial_collateral"
  | "other_physical";

export type DefaultStatus = "resolved" | "written_off" | "open" | "cured";

export interface LgdAssumptions {
  methodology: Methodology;
  open_default_method: OpenDefaultMethod;
  weighting_method: WeightingMethod;
  discount_rate: number;
  downturn_enabled: boolean;
  downturn_multiplier: number;
  haircut_rre: number;
  haircut_cre: number;
  haircut_financial: number;
  haircut_other_physical: number;
  cure_lgd_method: CureLgdMethod;
  cure_lgd: number;
  expected_remaining_recovery_rate: number;
  expected_additional_years_open: number;
}

export interface Loan {
  loan_id: string;
  segment: Segment;
  default_status: DefaultStatus;
  collateral_type: CollateralType;
  collateral_value: number;
  exposure_at_default: number;
  collateral_recovered: number;
  non_collateral_recovered: number;
  recovery_costs: number;
  time_in_default_years: number;
  default_year: number;
  market_price_at_default: number;
  credit_spread_bps: number;
  pre_default_pd: number;
}

export interface ProcessedLoan extends Loan {
  haircut_applied: number;
  net_collateral_value: number;
  lgd_workout: number;
  lgd_market: number;
  lgd_implied_market: number;
  lgd_selected: number;
  lgd_post_cure: number;
  lgd_final: number;
  observed_lgd_to_date: number;
  partial_net_recovery: number;
  estimated_future_recovery: number;
  gross_recovery: number;
  net_recovery: number;
  expected_loss: number;
}

export interface OutcomeProbabilities {
  p_resolved: number;
  p_written_off: number;
  p_cured: number;
  lgd_given_resolved: number;
  lgd_given_written_off: number;
  lgd_given_cured: number;
  completed_count: number;
}

export interface VintageStats {
  year: number;
  loan_count: number;
  total_exposure: number;
  weighted_avg_lgd: number;
  resolved_count: number;
  written_off_count: number;
  open_count: number;
  cured_count: number;
  completed_count: number;
  predicted_lgd_market: number;
  predicted_lgd_implied_market: number;
  realized_lgd_workout: number;
  avg_time_to_resolution: number;
  avg_time_to_writeoff: number;
  avg_time_to_cure: number;
}

export interface VintageAnalysis {
  vintages: VintageStats[];
  outcome_probabilities: Record<Segment, OutcomeProbabilities>;
}

export interface MethodologyComparison {
  workout_lgd: number;
  market_lgd: number;
  implied_market_lgd: number;
}

export interface SegmentSummary {
  loan_count: number;
  resolved_count: number;
  written_off_count: number;
  open_count: number;
  cured_count: number;
  cure_rate: number;
  written_off_rate: number;
  total_exposure: number;
  weighted_avg_lgd: number;
  weighted_avg_lgd_final: number;
  total_expected_loss: number;
  total_collateral_recovered: number;
  total_non_collateral_recovered: number;
  total_recovery_costs: number;
  total_net_recovery: number;
  methodology_comparison: MethodologyComparison;
}

export interface PortfolioSummary {
  loan_count: number;
  total_exposure: number;
  resolved_count: number;
  written_off_count: number;
  open_count: number;
  cured_count: number;
  cure_rate: number;
  written_off_rate: number;
  weighted_avg_lgd: number;
  weighted_avg_lgd_final: number;
  total_expected_loss: number;
  by_segment: Record<Segment, SegmentSummary>;
  methodology_comparison: MethodologyComparison;
}

export interface PortfolioResponse {
  loans: ProcessedLoan[];
  summary: PortfolioSummary;
  vintage_analysis: VintageAnalysis;
}

export interface PanelUploadResponse {
  data_id: string;
  row_count: number;
  loan_count: number;
  month_min: string;
  month_max: string;
  columns: string[];
}

export interface DefaultEpisode {
  loan_id: string;
  raw_loan_id: string;
  segment: Segment;
  default_status: DefaultStatus;
  start_month: string;
  end_month: string;
  row_count: number;
  exposure_at_default: number;
}

export interface ConstructDefaultsResponse {
  data_id: string;
  raw_loan_count: number;
  episode_count: number;
  episodes: DefaultEpisode[];
  status_counts: Record<string, number>;
}

export interface DownturnCalibrationResponse {
  stress_avg_lgd: number;
  benign_avg_lgd: number;
  derived_multiplier: number;
}

export interface DownturnAudit {
  enabled: boolean;
  source: "derived" | "manual";
  stressYears: number[];
  benignYears: number[];
  derivedStressLgd: number | null;
  derivedBenignLgd: number | null;
}

export const DEFAULT_ASSUMPTIONS: LgdAssumptions = {
  methodology: "workout",
  open_default_method: "elbe",
  weighting_method: "number_weighted",
  discount_rate: 0.05,
  downturn_enabled: false,
  downturn_multiplier: 1.25,
  haircut_rre: 0.20,
  haircut_cre: 0.40,
  haircut_financial: 0.15,
  haircut_other_physical: 0.50,
  cure_lgd_method: "fixed",
  cure_lgd: 0.05,
  expected_remaining_recovery_rate: 0.75,
  expected_additional_years_open: 1.5,
};

const KNOWN_SEGMENT_LABELS: Record<string, string> = {
  retail_mortgage: "Retail Mortgage",
  retail_unsecured: "Retail Unsecured",
  corporate: "Corporate",
  sme: "SME",
};

export function segmentLabel(segment: string): string {
  if (KNOWN_SEGMENT_LABELS[segment]) return KNOWN_SEGMENT_LABELS[segment];
  return segment
    .split(/[_\s]+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export const METHODOLOGY_LABELS: Record<Methodology, string> = {
  workout: "Workout",
  market: "Market",
  implied_market: "Implied Market",
};

export const OPEN_DEFAULT_METHOD_LABELS: Record<OpenDefaultMethod, string> = {
  elbe: "ELBE",
  probability_weighted: "Probability-Weighted",
};

export const WEIGHTING_METHOD_LABELS: Record<WeightingMethod, string> = {
  ead_weighted: "EAD-Weighted",
  number_weighted: "Number-Weighted",
};

export const CURE_LGD_METHOD_LABELS: Record<CureLgdMethod, string> = {
  fixed: "Fixed",
  calculated: "Calculated",
};

export const STATUS_LABELS: Record<DefaultStatus, string> = {
  resolved: "Resolved",
  written_off: "Written Off",
  open: "Open",
  cured: "Cured",
};

export const COLLATERAL_LABELS: Record<CollateralType, string> = {
  none: "None",
  residential_real_estate: "RRE",
  commercial_real_estate: "CRE",
  financial_collateral: "Financial",
  other_physical: "Other Physical",
};

export function pct(v: number): string {
  return (v * 100).toFixed(1) + "%";
}

export function currency(v: number): string {
  if (Math.abs(v) >= 1_000_000) return "£" + (v / 1_000_000).toFixed(1) + "M";
  if (Math.abs(v) >= 1_000) return "£" + (v / 1_000).toFixed(0) + "k";
  return "£" + v.toFixed(0);
}
