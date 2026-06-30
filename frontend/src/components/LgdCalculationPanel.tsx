import { useEffect, useState } from "react";
import { calculateLgd } from "../api/client";
import { CollateralHaircutsPanel } from "./CollateralHaircutsPanel";
import { LgdBySegmentChart } from "./LgdBySegmentChart";
import { LgdDistributionChart } from "./LgdDistributionChart";
import { LoanTable } from "./LoanTable";
import { MethodologyComparisonChart } from "./MethodologyComparisonChart";
import { MethodologySelector, WeightingMethodSelector } from "./MethodologyControls";
import { RecoveryBreakdownChart } from "./RecoveryBreakdownChart";
import { SegmentSummaryTable } from "./SegmentSummaryTable";
import { SummaryCards } from "./SummaryCards";
import { WeightingAssumptionsPanel } from "./WeightingAssumptionsPanel";
import type { LgdAssumptions, PortfolioResponse } from "../types/portfolio";
import { DEFAULT_ASSUMPTIONS } from "../types/portfolio";

interface Props {
  dataId: string;
  onContinue: (result: PortfolioResponse, assumptions: LgdAssumptions) => void;
}

export function LgdCalculationPanel({ dataId, onContinue }: Props) {
  const [assumptions, setAssumptions] = useState<LgdAssumptions>(DEFAULT_ASSUMPTIONS);
  const [result, setResult] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runCalculation(a: LgdAssumptions) {
    setLoading(true);
    setError(null);
    try {
      const data = await calculateLgd(dataId, a);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "LGD calculation failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setResult(null);
    runCalculation(assumptions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataId]);

  function applyAssumptions(next: LgdAssumptions) {
    setAssumptions(next);
    runCalculation(next);
  }

  function updateAssumption<K extends keyof LgdAssumptions>(key: K, value: LgdAssumptions[K]) {
    applyAssumptions({ ...assumptions, [key]: value });
  }

  return (
    <div className="calculate-lgd-panel">
      <div className="staging-controls">
        <MethodologySelector
          value={assumptions.methodology}
          onChange={(m) => updateAssumption("methodology", m)}
        />
        <WeightingMethodSelector
          value={assumptions.weighting_method}
          onChange={(w) => updateAssumption("weighting_method", w)}
        />
      </div>

      <WeightingAssumptionsPanel assumptions={assumptions} onApply={applyAssumptions} />
      <CollateralHaircutsPanel assumptions={assumptions} onApply={applyAssumptions} />

      {loading && <div className="status-message">Calculating LGD...</div>}
      {error && (
        <div className="status-message error">
          {error}{" "}
          <button className="toggle-btn" onClick={() => runCalculation(assumptions)}>
            Retry
          </button>
        </div>
      )}

      {result && !loading && (
        <>
          <SummaryCards summary={result.summary} assumptions={assumptions} />
          <LgdDistributionChart loans={result.loans} />
          <LgdBySegmentChart
            summary={result.summary}
            downturnEnabled={assumptions.downturn_enabled}
            weightingMethod={assumptions.weighting_method}
          />
          <RecoveryBreakdownChart summary={result.summary} weightingMethod={assumptions.weighting_method} />
          <MethodologyComparisonChart summary={result.summary} />
          <SegmentSummaryTable summary={result.summary} />
          <LoanTable loans={result.loans} />

          <button className="primary-button" onClick={() => onContinue(result, assumptions)}>
            Continue to Vintage &amp; Stability
          </button>
        </>
      )}
    </div>
  );
}
