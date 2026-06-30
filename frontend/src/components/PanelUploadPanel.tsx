import { useState } from "react";
import { loadSamplePanel, uploadPanel } from "../api/client";
import type { PanelUploadResponse } from "../types/portfolio";

interface Props {
  onContinue: (dataId: string, profile: PanelUploadResponse) => void;
}

export function PanelUploadPanel({ onContinue }: Props) {
  const [profile, setProfile] = useState<PanelUploadResponse | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setFileName(file.name);
    setLoading(true);
    setError(null);
    try {
      const data = await uploadPanel(file);
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadSample() {
    setFileName("sample_monthly_panel.csv");
    setLoading(true);
    setError(null);
    try {
      const data = await loadSamplePanel();
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sample panel.");
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="upload-panel">
      <div className="upload-section">
        <h3>Upload Monthly Loan Panel</h3>
        <p>
          Upload a CSV with one row per loan per month (balance, days-past-due, collateral and
          recovery cash flows). The tool will identify default episodes and reconstruct recovery
          cash flows from this raw history in the next step.
        </p>

        <div className="upload-actions">
          <label className="upload-button">
            Choose CSV File
            <input type="file" accept=".csv" onChange={handleFile} hidden />
          </label>
          <button className="primary-button" disabled={loading} onClick={handleLoadSample}>
            Load Sample Panel
          </button>
        </div>

        {fileName && <p className="file-name">File: {fileName}</p>}
        {loading && <div className="status-message">Uploading and profiling panel...</div>}
        {error && <div className="status-message error">{error}</div>}
      </div>

      {profile && !loading && (
        <>
          <div className="summary-cards">
            <div className="summary-card">
              <div className="summary-card-label">Rows</div>
              <div className="summary-card-value">{profile.row_count.toLocaleString()}</div>
            </div>
            <div className="summary-card">
              <div className="summary-card-label">Loans</div>
              <div className="summary-card-value">{profile.loan_count.toLocaleString()}</div>
            </div>
            <div className="summary-card">
              <div className="summary-card-label">Month Range</div>
              <div className="summary-card-value" style={{ fontSize: 18 }}>
                {profile.month_min} – {profile.month_max}
              </div>
            </div>
            <div className="summary-card">
              <div className="summary-card-label">Columns</div>
              <div className="summary-card-value">{profile.columns.length}</div>
            </div>
          </div>

          <button
            className="primary-button"
            onClick={() => onContinue(profile.data_id, profile)}
          >
            Continue to Default Construction
          </button>
        </>
      )}
    </div>
  );
}
