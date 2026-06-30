import { useEffect, useState } from "react";
import { calculateLgd, computeDownturnCalibration } from "../api/client";
import { SummaryCards } from "./SummaryCards";
import type {
  DownturnAudit,
  DownturnCalibrationResponse,
  LgdAssumptions,
  PortfolioResponse,
  VintageAnalysis,
} from "../types/portfolio";
import { pct } from "../types/portfolio";

interface Props {
  dataId: string;
  assumptions: LgdAssumptions;
  vintageAnalysis: VintageAnalysis;
  onContinue: (result: PortfolioResponse, assumptions: LgdAssumptions, audit: DownturnAudit) => void;
}

type YearRole = "stress" | "benign" | null;
type MultiplierSource = "derived" | "manual";

const MULTIPLIER_SOURCE_LABELS: Record<MultiplierSource, string> = {
  derived: "Derived from Vintages",
  manual: "Manual Override",
};

export function DownturnCalibrationPanel({ dataId, assumptions, vintageAnalysis, onContinue }: Props) {
  const years = vintageAnalysis.vintages.map((v) => v.year).sort((a, b) => a - b);

  const [multiplierSource, setMultiplierSource] = useState<MultiplierSource>("derived");
  const [roles, setRoles] = useState<Record<number, YearRole>>({});
  const [calibration, setCalibration] = useState<DownturnCalibrationResponse | null>(null);
  const [calibrating, setCalibrating] = useState(false);
  const [multiplier, setMultiplier] = useState(assumptions.downturn_multiplier);
  const [downturnEnabled, setDownturnEnabled] = useState(assumptions.downturn_enabled);
  const [result, setResult] = useState<PortfolioResponse | null>(null);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stressYears = years.filter((y) => roles[y] === "stress");
  const benignYears = years.filter((y) => roles[y] === "benign");
  const stressKey = stressYears.join(",");
  const benignKey = benignYears.join(",");

  function cycleRole(year: number) {
    setRoles((prev) => {
      const current = prev[year] ?? null;
      const next: YearRole = current === null ? "stress" : current === "stress" ? "benign" : null;
      return { ...prev, [year]: next };
    });
    setResult(null);
  }

  useEffect(() => {
    if (multiplierSource !== "derived" || !stressKey || !benignKey) {
      setCalibration(null);
      return;
    }
    let cancelled = false;
    setCalibrating(true);
    setError(null);
    computeDownturnCalibration(dataId, assumptions, stressYears, benignYears)
      .then((data) => {
        if (cancelled) return;
        setCalibration(data);
        setMultiplier(data.derived_multiplier);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Calibration failed.");
      })
      .finally(() => {
        if (!cancelled) setCalibrating(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataId, stressKey, benignKey, multiplierSource]);

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      const next = { ...assumptions, downturn_enabled: downturnEnabled, downturn_multiplier: multiplier };
      const data = await calculateLgd(dataId, next);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "LGD calculation failed.");
    } finally {
      setApplying(false);
    }
  }

  const appliedAssumptions: LgdAssumptions = {
    ...assumptions,
    downturn_enabled: downturnEnabled,
    downturn_multiplier: multiplier,
  };

  const audit: DownturnAudit = {
    enabled: downturnEnabled,
    source: multiplierSource,
    stressYears: downturnEnabled && multiplierSource === "derived" ? stressYears : [],
    benignYears: downturnEnabled && multiplierSource === "derived" ? benignYears : [],
    derivedStressLgd: downturnEnabled && multiplierSource === "derived" ? calibration?.stress_avg_lgd ?? null : null,
    derivedBenignLgd: downturnEnabled && multiplierSource === "derived" ? calibration?.benign_avg_lgd ?? null : null,
  };

  return (
    <div className="downturn-calibration-panel">
      <p>
        Derive a downturn LGD multiplier from stress (higher-LGD) vs benign (lower-LGD) default
        vintages, or enter one manually.
      </p>

      <label className="toggle-label">
        <input
          type="checkbox"
          checked={downturnEnabled}
          onChange={(e) => setDownturnEnabled(e.target.checked)}
        />
        Apply downturn adjustment
      </label>

      {downturnEnabled && (
        <>
          <div className="staging-field">
            <label>Multiplier source</label>
            <div className="toggle-group">
              {(Object.keys(MULTIPLIER_SOURCE_LABELS) as MultiplierSource[]).map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className={`toggle-btn${multiplierSource === opt ? " active" : ""}`}
                  onClick={() => setMultiplierSource(opt)}
                >
                  {MULTIPLIER_SOURCE_LABELS[opt]}
                </button>
              ))}
            </div>
          </div>

          {multiplierSource === "derived" && (
            <>
              <p className="field-hint">
                Click a year to cycle: unselected → stress → benign → unselected.
              </p>

              <div className="year-selector">
                {years.map((y) => {
                  const role = roles[y] ?? null;
                  return (
                    <button
                      key={y}
                      type="button"
                      className={`year-chip${role ? ` ${role}` : ""}`}
                      onClick={() => cycleRole(y)}
                    >
                      {y}
                    </button>
                  );
                })}
              </div>
              <div className="year-legend">
                <span className="year-legend-swatch stress" /> Stress vintage
                <span className="year-legend-swatch benign" /> Benign vintage
              </div>

              {calibrating && <div className="status-message">Calibrating...</div>}

              {calibration && !calibrating && stressYears.length > 0 && benignYears.length > 0 && (
                <div className="summary-cards">
                  <div className="summary-card">
                    <div className="summary-card-label">Stress Avg LGD</div>
                    <div className="summary-card-value">{pct(calibration.stress_avg_lgd)}</div>
                    <div className="summary-card-sub">{stressYears.join(", ")}</div>
                  </div>
                  <div className="summary-card">
                    <div className="summary-card-label">Benign Avg LGD</div>
                    <div className="summary-card-value">{pct(calibration.benign_avg_lgd)}</div>
                    <div className="summary-card-sub">{benignYears.join(", ")}</div>
                  </div>
                  <div className="summary-card">
                    <div className="summary-card-label">Derived Multiplier</div>
                    <div className="summary-card-value">{calibration.derived_multiplier.toFixed(2)}x</div>
                    <div className="summary-card-sub">Stress ÷ Benign, clamped to [1.0, 3.0]</div>
                  </div>
                </div>
              )}
            </>
          )}

          <div className="downturn-row">
            {multiplierSource === "manual" ? (
              <div className="staging-field">
                <label>Downturn multiplier</label>
                <input
                  type="number"
                  min={1}
                  max={3}
                  step={0.01}
                  value={multiplier}
                  onChange={(e) => setMultiplier(Number(e.target.value))}
                />
                <span className="field-hint">Enter a value between 1.0x and 3.0x</span>
              </div>
            ) : (
              <div className="staging-field">
                <label>Downturn multiplier</label>
                <input
                  type="text"
                  value={calibration ? `${calibration.derived_multiplier.toFixed(2)}x` : "—"}
                  disabled
                />
                <span className="field-hint">
                  {calibration ? "Derived from selected vintages" : "Select stress & benign years above"}
                </span>
              </div>
            )}
          </div>
        </>
      )}

      <div className="downturn-row">
        <button
          className="apply-button"
          onClick={handleApply}
          disabled={applying || (downturnEnabled && multiplierSource === "derived" && !calibration)}
        >
          {applying ? "Applying..." : downturnEnabled ? "Apply & Recalculate" : "Continue without Downturn Adjustment"}
        </button>
      </div>

      {error && <div className="status-message error">{error}</div>}

      {result && !applying && (
        <>
          <SummaryCards summary={result.summary} assumptions={appliedAssumptions} />
          <button className="primary-button" onClick={() => onContinue(result, appliedAssumptions, audit)}>
            Continue to Report
          </button>
        </>
      )}
    </div>
  );
}
