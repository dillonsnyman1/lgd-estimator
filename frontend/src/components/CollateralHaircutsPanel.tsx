import { useEffect, useState } from "react";
import type { LgdAssumptions } from "../types/portfolio";

interface Props {
  assumptions: LgdAssumptions;
  onApply: (a: LgdAssumptions) => void;
}

const HAIRCUTS: { key: keyof LgdAssumptions; label: string }[] = [
  { key: "haircut_rre", label: "RRE" },
  { key: "haircut_cre", label: "CRE" },
  { key: "haircut_financial", label: "Financial" },
  { key: "haircut_other_physical", label: "Other physical" },
];

export function CollateralHaircutsPanel({ assumptions, onApply }: Props) {
  const [local, setLocal] = useState(assumptions);

  useEffect(() => {
    setLocal(assumptions);
  }, [assumptions]);

  function set(key: keyof LgdAssumptions, value: number) {
    setLocal((prev) => ({ ...prev, [key]: value }));
  }

  const dirty = JSON.stringify(local) !== JSON.stringify(assumptions);

  return (
    <div className="assumptions-panel">
      <div className="staging-controls">
        {HAIRCUTS.map(({ key, label }) => (
          <div key={key} className="staging-field">
            <label>{label} haircut</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={local[key] as number}
              onChange={(e) => set(key, Number(e.target.value))}
            />
            <span className="field-hint">
              {((local[key] as number) * 100).toFixed(0)}% →&nbsp;
              {((1 - (local[key] as number)) * 100).toFixed(0)}% net recovery
            </span>
          </div>
        ))}
      </div>

      <button
        className="apply-button"
        onClick={() => onApply(local)}
        disabled={!dirty}
      >
        Apply
      </button>
    </div>
  );
}
