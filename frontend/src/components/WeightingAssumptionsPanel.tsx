import { useEffect, useState } from "react";
import type { CureLgdMethod, LgdAssumptions, OpenDefaultMethod } from "../types/portfolio";
import { CURE_LGD_METHOD_LABELS, OPEN_DEFAULT_METHOD_LABELS } from "../types/portfolio";

interface Props {
  assumptions: LgdAssumptions;
  onApply: (a: LgdAssumptions) => void;
}

interface ToggleFieldProps<T extends string> {
  label: string;
  value: T;
  labels: Record<T, string>;
  hint?: string;
  onChange: (v: T) => void;
}

function ToggleField<T extends string>({ label, value, labels, hint, onChange }: ToggleFieldProps<T>) {
  return (
    <div className="staging-field">
      <label>{label}</label>
      <div className="toggle-group">
        {(Object.keys(labels) as T[]).map((opt) => (
          <button
            key={opt}
            type="button"
            className={`toggle-btn${value === opt ? " active" : ""}`}
            onClick={() => onChange(opt)}
          >
            {labels[opt]}
          </button>
        ))}
      </div>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

export function WeightingAssumptionsPanel({ assumptions, onApply }: Props) {
  const [local, setLocal] = useState(assumptions);

  useEffect(() => {
    setLocal(assumptions);
  }, [assumptions]);

  function set<K extends keyof LgdAssumptions>(key: K, value: LgdAssumptions[K]) {
    setLocal((prev) => ({ ...prev, [key]: value }));
  }

  function handleApply() {
    onApply(local);
  }

  const dirty = JSON.stringify(local) !== JSON.stringify(assumptions);
  const isElbe = local.open_default_method === "elbe";
  const isFixedCureLgd = local.cure_lgd_method === "fixed";

  return (
    <div className="assumptions-panel">
      <div className="staging-controls">
        <div className="staging-field">
          <label>Discount rate</label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.005}
            value={local.discount_rate}
            onChange={(e) => set("discount_rate", Number(e.target.value))}
          />
          <span className="field-hint">{(local.discount_rate * 100).toFixed(1)}%</span>
        </div>

        <ToggleField<OpenDefaultMethod>
          label="Open defaults: method"
          value={local.open_default_method}
          labels={OPEN_DEFAULT_METHOD_LABELS}
          onChange={(v) => set("open_default_method", v)}
          hint={
            isElbe
              ? "Partial recovery to date + estimated future collateral"
              : "P(WO)×LGD|WO + P(cure)×cure LGD + P(res)×LGD|res, calibrated from same-segment completed loans"
          }
        />

        {isElbe && (
          <>
            <div className="staging-field">
              <label>ELBE: expected remaining recovery</label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={local.expected_remaining_recovery_rate}
                onChange={(e) => set("expected_remaining_recovery_rate", Number(e.target.value))}
              />
              <span className="field-hint">{(local.expected_remaining_recovery_rate * 100).toFixed(0)}% of remaining net collateral</span>
            </div>

            <div className="staging-field">
              <label>ELBE: additional years to resolution</label>
              <input
                type="number"
                min={0.25}
                max={5}
                step={0.25}
                value={local.expected_additional_years_open}
                onChange={(e) => set("expected_additional_years_open", Number(e.target.value))}
              />
              <span className="field-hint">{local.expected_additional_years_open} yrs</span>
            </div>
          </>
        )}

        <ToggleField<CureLgdMethod>
          label="Cure LGD: method"
          value={local.cure_lgd_method}
          labels={CURE_LGD_METHOD_LABELS}
          onChange={(v) => set("cure_lgd_method", v)}
          hint={
            isFixedCureLgd
              ? "Flat assumption applied to all cured loans"
              : "Derived from actual recovery cash flows (DCF), per selected methodology"
          }
        />

        {isFixedCureLgd && (
          <div className="staging-field">
            <label>Cure LGD</label>
            <input
              type="number"
              min={0}
              max={0.5}
              step={0.005}
              value={local.cure_lgd}
              onChange={(e) => set("cure_lgd", Number(e.target.value))}
            />
            <span className="field-hint">{(local.cure_lgd * 100).toFixed(1)}%</span>
          </div>
        )}
      </div>

      <button
        className="apply-button"
        onClick={handleApply}
        disabled={!dirty}
      >
        Apply
      </button>
    </div>
  );
}
