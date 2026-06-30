import { useCallback, useState } from "react";

import "./App.css";
import { DefaultConstructionPanel } from "./components/DefaultConstructionPanel";
import { DownturnCalibrationPanel } from "./components/DownturnCalibrationPanel";
import { LgdCalculationPanel } from "./components/LgdCalculationPanel";
import { PanelUploadPanel } from "./components/PanelUploadPanel";
import { ReportPanel } from "./components/ReportPanel";
import { VintageStabilityPanel } from "./components/VintageStabilityPanel";
import type {
  ConstructDefaultsResponse,
  DownturnAudit,
  LgdAssumptions,
  PanelUploadResponse,
  PortfolioResponse,
} from "./types/portfolio";
import { STEP_LABELS, STEP_ORDER, type Step } from "./types/wizard";

function App() {
  const [step, setStepRaw] = useState<Step>("upload");
  const setStep = useCallback((s: Step) => {
    setStepRaw(s);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const [dataId, setDataId] = useState<string | null>(null);
  const [panelProfile, setPanelProfile] = useState<PanelUploadResponse | null>(null);
  const [defaultsResult, setDefaultsResult] = useState<ConstructDefaultsResponse | null>(null);
  const [lgdResult, setLgdResult] = useState<PortfolioResponse | null>(null);
  const [assumptions, setAssumptions] = useState<LgdAssumptions | null>(null);
  const [finalResult, setFinalResult] = useState<PortfolioResponse | null>(null);
  const [finalAssumptions, setFinalAssumptions] = useState<LgdAssumptions | null>(null);
  const [downturnAudit, setDownturnAudit] = useState<DownturnAudit | null>(null);

  function handlePanelLoaded(id: string, profile: PanelUploadResponse) {
    setDataId(id);
    setPanelProfile(profile);
    setStep("construct_defaults");
  }

  function handleDefaultsConstructed(result: ConstructDefaultsResponse) {
    setDefaultsResult(result);
    setStep("calculate_lgd");
  }

  function handleLgdCalculated(result: PortfolioResponse, a: LgdAssumptions) {
    setLgdResult(result);
    setAssumptions(a);
    setStep("vintage_stability");
  }

  function handleVintageStabilityContinue() {
    setStep("downturn_calibration");
  }

  function handleDownturnCalibrationContinue(result: PortfolioResponse, a: LgdAssumptions, audit: DownturnAudit) {
    setFinalResult(result);
    setFinalAssumptions(a);
    setDownturnAudit(audit);
    setStep("report");
  }

  const currentStepIndex = STEP_ORDER.indexOf(step);

  return (
    <>
      <header className="app-header">
        <h1>LGD Estimator</h1>
        <p>
          A staged LGD model-development pipeline: ingest a raw monthly loan-panel, identify
          default episodes and reconstruct recovery cash flows, then calculate Loss Given Default
          using workout (discounted cash flow), market-based and implied-market approaches, with
          segment weighting, vintage stability analysis and downturn calibration.
        </p>
      </header>

      <nav className="step-nav">
        {STEP_ORDER.map((s, i) => {
          const canNavigate = i < currentStepIndex;
          return (
            <div
              key={s}
              className={`step-indicator ${s === step ? "active" : ""} ${canNavigate ? "completed clickable" : ""}`}
              onClick={canNavigate ? () => setStep(s) : undefined}
            >
              <span className="step-number">{i + 1}</span>
              <span className="step-label">{STEP_LABELS[s]}</span>
            </div>
          );
        })}
      </nav>

      {step === "upload" && <PanelUploadPanel onContinue={handlePanelLoaded} />}

      {step === "construct_defaults" && dataId && (
        <DefaultConstructionPanel dataId={dataId} onContinue={handleDefaultsConstructed} />
      )}

      {step === "calculate_lgd" && dataId && (
        <LgdCalculationPanel dataId={dataId} onContinue={handleLgdCalculated} />
      )}

      {step === "vintage_stability" && lgdResult && assumptions && (
        <VintageStabilityPanel
          vintageAnalysis={lgdResult.vintage_analysis}
          weightingMethod={assumptions.weighting_method}
          onContinue={handleVintageStabilityContinue}
        />
      )}

      {step === "downturn_calibration" && dataId && lgdResult && assumptions && (
        <DownturnCalibrationPanel
          dataId={dataId}
          assumptions={assumptions}
          vintageAnalysis={lgdResult.vintage_analysis}
          onContinue={handleDownturnCalibrationContinue}
        />
      )}

      {step === "report" && panelProfile && defaultsResult && finalResult && finalAssumptions && downturnAudit && (
        <ReportPanel
          panelProfile={panelProfile}
          defaultsResult={defaultsResult}
          finalResult={finalResult}
          finalAssumptions={finalAssumptions}
          downturnAudit={downturnAudit}
        />
      )}
    </>
  );
}

export default App;
