import type { Methodology, WeightingMethod } from "../types/portfolio";
import { METHODOLOGY_LABELS, WEIGHTING_METHOD_LABELS } from "../types/portfolio";

interface MethodologySelectorProps {
  value: Methodology;
  onChange: (m: Methodology) => void;
}

export function MethodologySelector({ value, onChange }: MethodologySelectorProps) {
  return (
    <div className="field-group">
      <label className="field-label">LGD Methodology</label>
      <div className="toggle-group">
        {(Object.keys(METHODOLOGY_LABELS) as Methodology[]).map((m) => (
          <button
            key={m}
            type="button"
            className={`toggle-btn${value === m ? " active" : ""}`}
            onClick={() => onChange(m)}
          >
            {METHODOLOGY_LABELS[m]}
          </button>
        ))}
      </div>
      <span className="field-hint">
        {value === "workout" && "Discounted cash flow; open defaults use ELBE"}
        {value === "market" && "1 - secondary market price at default"}
        {value === "implied_market" && "Credit spread / market-implied PD"}
      </span>
    </div>
  );
}

interface WeightingMethodSelectorProps {
  value: WeightingMethod;
  onChange: (w: WeightingMethod) => void;
}

export function WeightingMethodSelector({ value, onChange }: WeightingMethodSelectorProps) {
  return (
    <div className="field-group">
      <label className="field-label">LGD Averaging</label>
      <div className="toggle-group">
        {(Object.keys(WEIGHTING_METHOD_LABELS) as WeightingMethod[]).map((w) => (
          <button
            key={w}
            type="button"
            className={`toggle-btn${value === w ? " active" : ""}`}
            onClick={() => onChange(w)}
          >
            {WEIGHTING_METHOD_LABELS[w]}
          </button>
        ))}
      </div>
      <span className="field-hint">
        {value === "ead_weighted"
          ? "EAD-weighted average LGD (IFRS 9 / portfolio EL context)"
          : "Simple average across defaults (IRB - CRR Art. 181 default-weighted)"}
      </span>
    </div>
  );
}
