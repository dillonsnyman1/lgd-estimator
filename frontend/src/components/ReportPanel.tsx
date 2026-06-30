import { SummaryCards } from "./SummaryCards";
import type {
  ConstructDefaultsResponse,
  DownturnAudit,
  LgdAssumptions,
  PanelUploadResponse,
  PortfolioResponse,
  ProcessedLoan,
} from "../types/portfolio";
import {
  CURE_LGD_METHOD_LABELS,
  METHODOLOGY_LABELS,
  OPEN_DEFAULT_METHOD_LABELS,
  STATUS_LABELS,
  WEIGHTING_METHOD_LABELS,
  pct,
} from "../types/portfolio";

interface Props {
  panelProfile: PanelUploadResponse;
  defaultsResult: ConstructDefaultsResponse;
  finalResult: PortfolioResponse;
  finalAssumptions: LgdAssumptions;
  downturnAudit: DownturnAudit;
}

function exportLoansCsv(loans: ProcessedLoan[]) {
  if (loans.length === 0) return;
  const headers = Object.keys(loans[0]) as (keyof ProcessedLoan)[];
  const rows = loans.map((loan) => headers.map((h) => String(loan[h])).join(","));
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "lgd_scored_loans.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportPanel({ panelProfile, defaultsResult, finalResult, finalAssumptions, downturnAudit }: Props) {
  const a = finalAssumptions;

  return (
    <div className="report-panel">
      <p>Final assumptions, results and an audit trail of the choices made at each step of this build.</p>

      <SummaryCards summary={finalResult.summary} assumptions={a} />

      <div className="chart-card">
        <h3>Assumptions Used</h3>
        <div className="chart-table-wrapper">
          <table className="loan-table" style={{ fontSize: "12px" }}>
            <tbody>
              <tr>
                <td>Methodology</td>
                <td className="num">{METHODOLOGY_LABELS[a.methodology]}</td>
              </tr>
              <tr>
                <td>Weighting method</td>
                <td className="num">{WEIGHTING_METHOD_LABELS[a.weighting_method]}</td>
              </tr>
              <tr>
                <td>Discount rate</td>
                <td className="num">{pct(a.discount_rate)}</td>
              </tr>
              <tr>
                <td>Open-default method</td>
                <td className="num">{OPEN_DEFAULT_METHOD_LABELS[a.open_default_method]}</td>
              </tr>
              {a.open_default_method === "probability_weighted" && (
                <>
                  <tr>
                    <td>Expected remaining recovery rate</td>
                    <td className="num">{pct(a.expected_remaining_recovery_rate)}</td>
                  </tr>
                  <tr>
                    <td>Expected additional years open</td>
                    <td className="num">{a.expected_additional_years_open.toFixed(2)}</td>
                  </tr>
                </>
              )}
              <tr>
                <td>Cure LGD method</td>
                <td className="num">{CURE_LGD_METHOD_LABELS[a.cure_lgd_method]}</td>
              </tr>
              {a.cure_lgd_method === "fixed" && (
                <tr>
                  <td>Cure LGD</td>
                  <td className="num">{pct(a.cure_lgd)}</td>
                </tr>
              )}
              <tr>
                <td>Haircut - Residential RE</td>
                <td className="num">{pct(a.haircut_rre)}</td>
              </tr>
              <tr>
                <td>Haircut - Commercial RE</td>
                <td className="num">{pct(a.haircut_cre)}</td>
              </tr>
              <tr>
                <td>Haircut - Financial collateral</td>
                <td className="num">{pct(a.haircut_financial)}</td>
              </tr>
              <tr>
                <td>Haircut - Other physical</td>
                <td className="num">{pct(a.haircut_other_physical)}</td>
              </tr>
              <tr>
                <td>Downturn adjustment</td>
                <td className="num">{a.downturn_enabled ? `Applied, ${a.downturn_multiplier.toFixed(2)}x` : "Not applied"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="chart-card">
        <h3>Audit Trail</h3>
        <div className="chart-table-wrapper">
          <table className="loan-table" style={{ fontSize: "12px" }}>
            <tbody>
              <tr>
                <td>Panel ingested</td>
                <td className="num">
                  {panelProfile.loan_count.toLocaleString()} loans, {panelProfile.row_count.toLocaleString()} rows
                  ({panelProfile.month_min} – {panelProfile.month_max})
                </td>
              </tr>
              <tr>
                <td>Default construction</td>
                <td className="num">
                  {defaultsResult.raw_loan_count.toLocaleString()} raw loans →{" "}
                  {defaultsResult.episode_count.toLocaleString()} default episodes
                </td>
              </tr>
              {(Object.keys(STATUS_LABELS) as (keyof typeof STATUS_LABELS)[]).map((status) => (
                <tr key={status}>
                  <td className="mono">&nbsp;&nbsp;{STATUS_LABELS[status]}</td>
                  <td className="num">{(defaultsResult.status_counts[status] ?? 0).toLocaleString()}</td>
                </tr>
              ))}
              <tr>
                <td>Downturn calibration</td>
                <td className="num">
                  {!downturnAudit.enabled && "Not applied"}
                  {downturnAudit.enabled && downturnAudit.source === "manual" && (
                    <>Manual override, {a.downturn_multiplier.toFixed(2)}x</>
                  )}
                  {downturnAudit.enabled && downturnAudit.source === "derived" && (
                    <>
                      Derived from stress vintages [{downturnAudit.stressYears.join(", ")}]
                      {downturnAudit.derivedStressLgd !== null && ` (${pct(downturnAudit.derivedStressLgd)})`} vs benign
                      vintages [{downturnAudit.benignYears.join(", ")}]
                      {downturnAudit.derivedBenignLgd !== null && ` (${pct(downturnAudit.derivedBenignLgd)})`} →{" "}
                      {a.downturn_multiplier.toFixed(2)}x
                    </>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <button className="primary-button" onClick={() => exportLoansCsv(finalResult.loans)}>
        Export Scored Loans (CSV)
      </button>
    </div>
  );
}
