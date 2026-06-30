import type { VintageAnalysis } from "../types/portfolio";
import { segmentLabel, pct } from "../types/portfolio";

interface Props {
  vintageAnalysis: VintageAnalysis;
}

export function OutcomeProbabilityPanel({ vintageAnalysis }: Props) {
  const probs = vintageAnalysis.outcome_probabilities;

  return (
    <div className="chart-card" style={{ flex: "1 1 280px" }}>
      <h3>Outcome Probabilities</h3>
      <p className="chart-note">
        Calibrated from completed loans per segment. Used when open default method is set to
        Probability-Weighted. LGD|cure is also used as the cure LGD when the Cure LGD method is
        set to Calculated.
      </p>
      <div className="chart-table-wrapper">
        <table className="loan-table" style={{ fontSize: "12px" }}>
          <thead>
            <tr>
              <th>Segment</th>
              <th>P(res)</th>
              <th>P(WO)</th>
              <th>P(cure)</th>
              <th>LGD|res</th>
              <th>LGD|WO</th>
              <th>LGD|cure</th>
              <th>n</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(probs).map((seg) => {
              const p = probs[seg];
              return (
                <tr key={seg}>
                  <td>{segmentLabel(seg)}</td>
                  <td className="num">{pct(p.p_resolved)}</td>
                  <td className="num">{pct(p.p_written_off)}</td>
                  <td className="num">{pct(p.p_cured)}</td>
                  <td className="num">{pct(p.lgd_given_resolved)}</td>
                  <td className="num">{pct(p.lgd_given_written_off)}</td>
                  <td className="num">{pct(p.lgd_given_cured)}</td>
                  <td className="num">{p.completed_count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
