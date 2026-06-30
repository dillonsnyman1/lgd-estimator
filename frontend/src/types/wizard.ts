export type Step =
  | "upload"
  | "construct_defaults"
  | "calculate_lgd"
  | "vintage_stability"
  | "downturn_calibration"
  | "report";

export const STEP_LABELS: Record<Step, string> = {
  upload: "Upload",
  construct_defaults: "Default Construction",
  calculate_lgd: "LGD Calculation",
  vintage_stability: "Vintage & Stability",
  downturn_calibration: "Downturn Calibration",
  report: "Report",
};

export const STEP_ORDER: Step[] = [
  "upload",
  "construct_defaults",
  "calculate_lgd",
  "vintage_stability",
  "downturn_calibration",
  "report",
];
