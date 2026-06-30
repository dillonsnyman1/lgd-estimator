import { useEffect, useState } from "react";
import { constructDefaults } from "../api/client";
import type { ConstructDefaultsResponse, DefaultStatus } from "../types/portfolio";
import { STATUS_LABELS, segmentLabel } from "../types/portfolio";
import { Pagination } from "./Pagination";

interface Props {
  dataId: string;
  onContinue: (result: ConstructDefaultsResponse) => void;
}

const STATUS_CLASS: Record<string, string> = {
  resolved: "status-resolved",
  written_off: "status-written-off",
  open: "status-open",
  cured: "status-cured",
};

const ALL_STATUSES: DefaultStatus[] = ["resolved", "written_off", "open", "cured"];

const PAGE_SIZE = 25;

export function DefaultConstructionPanel({ dataId, onContinue }: Props) {
  const [result, setResult] = useState<ConstructDefaultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  async function runConstruction() {
    setLoading(true);
    setError(null);
    try {
      const data = await constructDefaults(dataId);
      setResult(data);
      setPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Default construction failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setResult(null);
    runConstruction();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataId]);

  return (
    <div className="construct-defaults-panel">
      <p className="step-intro">
        Default episodes are identified directly from the panel's <code>default_flag</code> column
        - no inference or cure-confirmation buffer. The flag is treated as authoritative for both
        entry and exit.
      </p>

      {loading && <div className="status-message">Constructing default episodes...</div>}
      {error && (
        <div className="status-message error">
          {error}{" "}
          <button className="toggle-btn" onClick={runConstruction}>
            Retry
          </button>
        </div>
      )}

      {result && !loading && (() => {
        const defaultedLoanIds = new Set(result.episodes.map((ep) => ep.raw_loan_id));
        const neverDefaultedCount = result.raw_loan_count - defaultedLoanIds.size;
        const redefaultExtra = result.episode_count - defaultedLoanIds.size;
        const pageCount = Math.max(1, Math.ceil(result.episodes.length / PAGE_SIZE));
        const safePage = Math.min(page, pageCount);
        const pagedEpisodes = result.episodes.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
        return (
        <>
          <div className="status-message">
            {result.raw_loan_count.toLocaleString()} raw loans → {result.episode_count.toLocaleString()} default
            episodes.
            {neverDefaultedCount > 0 &&
              ` ${neverDefaultedCount.toLocaleString()} loan${neverDefaultedCount === 1 ? "" : "s"} never defaulted and ${neverDefaultedCount === 1 ? "was" : "were"} excluded.`}
            {redefaultExtra > 0 &&
              ` ${redefaultExtra.toLocaleString()} loan${redefaultExtra === 1 ? "" : "s"} cured and re-defaulted, producing more than one episode.`}
          </div>

          <div className="summary-cards">
            {ALL_STATUSES.map((status) => (
              <div className="summary-card" key={status}>
                <div className="summary-card-label">{STATUS_LABELS[status]}</div>
                <div className="summary-card-value">{(result.status_counts[status] ?? 0).toLocaleString()}</div>
              </div>
            ))}
          </div>

          <div className="table-wrapper">
            <table className="loan-table">
              <thead>
                <tr>
                  <th>Episode ID</th>
                  <th>Raw loan ID</th>
                  <th>Segment</th>
                  <th>Status</th>
                  <th>Start month</th>
                  <th>End / as-of month</th>
                  <th>Rows</th>
                  <th>EAD</th>
                </tr>
              </thead>
              <tbody>
                {pagedEpisodes.map((ep) => (
                  <tr key={ep.loan_id}>
                    <td className="mono">{ep.loan_id}</td>
                    <td className="mono">{ep.raw_loan_id}</td>
                    <td>{segmentLabel(ep.segment)}</td>
                    <td>
                      <span className={`status-badge ${STATUS_CLASS[ep.default_status]}`}>
                        {STATUS_LABELS[ep.default_status]}
                      </span>
                    </td>
                    <td>{ep.start_month}</td>
                    <td>{ep.default_status === "open" ? `ongoing (as of ${ep.end_month})` : ep.end_month}</td>
                    <td className="num">{ep.row_count}</td>
                    <td className="num">{ep.exposure_at_default.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination
              page={safePage}
              pageCount={pageCount}
              onPageChange={setPage}
              totalItems={result.episodes.length}
              pageSize={PAGE_SIZE}
            />
          </div>

          <button className="primary-button" onClick={() => onContinue(result)}>
            Continue to LGD Calculation
          </button>
        </>
        );
      })()}
    </div>
  );
}
