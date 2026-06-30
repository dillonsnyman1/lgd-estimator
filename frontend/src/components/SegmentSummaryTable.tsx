import type { PortfolioSummary } from "../types/portfolio";
import { currency, pct, segmentLabel } from "../types/portfolio";

interface Props {
  summary: PortfolioSummary;
}

export function SegmentSummaryTable({ summary }: Props) {
  const segments = Object.keys(summary.by_segment);

  return (
    <div className="chart-card">
      <h3>Segment Summary</h3>
      <div className="chart-table-wrapper">
        <table className="loan-table" style={{ fontSize: "12px" }}>
          <thead>
            <tr>
              <th>Segment</th>
              <th>Loans</th>
              <th>Total exposure</th>
              <th>Wtd avg LGD</th>
              <th>Wtd avg LGD (final)</th>
              <th>Cure rate</th>
              <th>Written-off rate</th>
              <th>Expected loss</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((seg) => {
              const s = summary.by_segment[seg];
              return (
                <tr key={seg}>
                  <td>{segmentLabel(seg)}</td>
                  <td className="num">{s.loan_count}</td>
                  <td className="num">{currency(s.total_exposure)}</td>
                  <td className="num">{pct(s.weighted_avg_lgd)}</td>
                  <td className="num bold">{pct(s.weighted_avg_lgd_final)}</td>
                  <td className="num">{pct(s.cure_rate)}</td>
                  <td className="num">{pct(s.written_off_rate)}</td>
                  <td className="num">{currency(s.total_expected_loss)}</td>
                </tr>
              );
            })}
            <tr>
              <td className="bold">Portfolio</td>
              <td className="num bold">{summary.loan_count}</td>
              <td className="num bold">{currency(summary.total_exposure)}</td>
              <td className="num bold">{pct(summary.weighted_avg_lgd)}</td>
              <td className="num bold">{pct(summary.weighted_avg_lgd_final)}</td>
              <td className="num bold">{pct(summary.cure_rate)}</td>
              <td className="num bold">{pct(summary.written_off_rate)}</td>
              <td className="num bold">{currency(summary.total_expected_loss)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
