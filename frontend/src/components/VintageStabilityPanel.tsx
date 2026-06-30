import { OutcomeProbabilityPanel } from "./OutcomeProbabilityPanel";
import { TimeToOutcomeChart } from "./TimeToOutcomeChart";
import { VintageChart } from "./VintageChart";
import { VintagePredictedVsRealizedChart } from "./VintagePredictedVsRealizedChart";
import type { VintageAnalysis, WeightingMethod } from "../types/portfolio";

interface Props {
  vintageAnalysis: VintageAnalysis;
  weightingMethod: WeightingMethod;
  onContinue: () => void;
}

export function VintageStabilityPanel({ vintageAnalysis, weightingMethod, onContinue }: Props) {
  return (
    <div className="vintage-stability-panel">
      <p>
        How default outcomes and LGD have trended by vintage (year of default), and how reliably
        the ex-ante methodologies have predicted realized loss once a default actually resolves.
      </p>

      <div className="charts-flex-row">
        <VintageChart vintageAnalysis={vintageAnalysis} weightingMethod={weightingMethod} />
        <OutcomeProbabilityPanel vintageAnalysis={vintageAnalysis} />
      </div>

      <VintagePredictedVsRealizedChart vintageAnalysis={vintageAnalysis} />
      <TimeToOutcomeChart vintageAnalysis={vintageAnalysis} />

      <button className="primary-button" onClick={onContinue}>
        Continue to Downturn Calibration
      </button>
    </div>
  );
}
