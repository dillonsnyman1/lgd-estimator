import { useMemo, useState } from "react";
import type { DefaultStatus, ProcessedLoan } from "../types/portfolio";
import {
  COLLATERAL_LABELS,
  STATUS_LABELS,
  currency,
  pct,
  segmentLabel,
} from "../types/portfolio";
import { Pagination } from "./Pagination";

interface Props {
  loans: ProcessedLoan[];
}

const STATUS_CLASS: Record<string, string> = {
  resolved: "status-resolved",
  written_off: "status-written-off",
  open: "status-open",
  cured: "status-cured",
};

const ALL_STATUSES: DefaultStatus[] = ["resolved", "written_off", "open", "cured"];

const PAGE_SIZE = 25;

export function LoanTable({ loans }: Props) {
  const [statusFilter, setStatusFilter] = useState<DefaultStatus | undefined>(undefined);
  const [page, setPage] = useState(1);

  const counts = useMemo(() => {
    const c: Record<DefaultStatus, number> = { resolved: 0, written_off: 0, open: 0, cured: 0 };
    for (const l of loans) c[l.default_status]++;
    return c;
  }, [loans]);

  const filteredLoans = statusFilter ? loans.filter((l) => l.default_status === statusFilter) : loans;
  const pageCount = Math.max(1, Math.ceil(filteredLoans.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pagedLoans = filteredLoans.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function handleStatusFilterChange(status: DefaultStatus | undefined) {
    setStatusFilter(status);
    setPage(1);
  }

  return (
    <div className="table-wrapper">
      <div className="table-filter-bar">
        <div className="toggle-group">
          <button
            type="button"
            className={`toggle-btn${statusFilter === undefined ? " active" : ""}`}
            onClick={() => handleStatusFilterChange(undefined)}
          >
            All ({loans.length})
          </button>
          {ALL_STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              className={`toggle-btn${statusFilter === status ? " active" : ""}`}
              onClick={() => handleStatusFilterChange(status)}
            >
              {STATUS_LABELS[status]} ({counts[status]})
            </button>
          ))}
        </div>
      </div>
      <table className="loan-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Segment</th>
            <th>Status</th>
            <th>Collateral</th>
            <th>EAD</th>
            <th>Net collateral</th>
            <th>Collateral recovered</th>
            <th>Non-collateral recovered</th>
            <th>Recovery costs</th>
            <th>Net recovery</th>
            <th>Time (yrs)</th>
            <th>Default year</th>
            <th>Observed LGD (to date)</th>
            <th>LGD workout</th>
            <th>LGD market</th>
            <th>LGD implied</th>
            <th>LGD selected</th>
            <th>LGD final</th>
            <th>Expected loss</th>
          </tr>
        </thead>
        <tbody>
          {pagedLoans.map((l) => (
            <tr key={l.loan_id}>
              <td className="mono">{l.loan_id}</td>
              <td>{segmentLabel(l.segment)}</td>
              <td>
                <span className={`status-badge ${STATUS_CLASS[l.default_status]}`}>
                  {STATUS_LABELS[l.default_status]}
                </span>
              </td>
              <td>{COLLATERAL_LABELS[l.collateral_type]}</td>
              <td className="num">{currency(l.exposure_at_default)}</td>
              <td className="num">{l.collateral_type !== "none" ? currency(l.net_collateral_value) : "—"}</td>
              <td className="num">{currency(l.collateral_recovered)}</td>
              <td className="num">{currency(l.non_collateral_recovered)}</td>
              <td className="num">{currency(l.recovery_costs)}</td>
              <td className="num">{currency(l.net_recovery)}</td>
              <td className="num">{l.time_in_default_years.toFixed(1)}</td>
              <td className="num">{l.default_year || "—"}</td>
              <td className={`num${l.default_status === "open" ? " cell-partial" : ""}`}>
                {pct(l.observed_lgd_to_date)}
              </td>
              <td className="num">{pct(l.lgd_workout)}</td>
              <td className="num">{pct(l.lgd_market)}</td>
              <td className="num">{pct(l.lgd_implied_market)}</td>
              <td className="num">{pct(l.lgd_selected)}</td>
              <td className="num bold">{pct(l.lgd_final)}</td>
              <td className="num">{currency(l.expected_loss)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        page={safePage}
        pageCount={pageCount}
        onPageChange={setPage}
        totalItems={filteredLoans.length}
        pageSize={PAGE_SIZE}
      />
    </div>
  );
}
