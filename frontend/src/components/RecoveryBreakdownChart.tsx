import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PortfolioSummary, WeightingMethod } from "../types/portfolio";
import { segmentLabel } from "../types/portfolio";

interface Props {
  summary: PortfolioSummary;
  weightingMethod: WeightingMethod;
}

export function RecoveryBreakdownChart({ summary, weightingMethod }: Props) {
  const data = Object.keys(summary.by_segment)
    .map((seg) => {
      const ss = summary.by_segment[seg];
      const ead = ss.total_exposure;
      const collPct = +(ss.total_collateral_recovered / ead * 100).toFixed(1);
      const nonCollPct = +(ss.total_non_collateral_recovered / ead * 100).toFixed(1);
      const costPct = +(ss.total_recovery_costs / ead * 100).toFixed(1);
      const lossPct = +(ss.weighted_avg_lgd * 100).toFixed(1);
      return {
        segment: segmentLabel(seg),
        "Collateral recovery": collPct,
        "Non-collateral recovery": nonCollPct,
        "Recovery costs": -costPct,
        "Net loss (LGD)": lossPct,
      };
    });

  const weightingNote = weightingMethod === "ead_weighted" ? "EAD-weighted" : "Number-weighted (IRB)";

  return (
    <div className="chart-card">
      <h3>Recovery Breakdown by Segment</h3>
      <p className="chart-note">
        As % of total segment EAD. Costs are pre-discount gross amounts. Net loss (LGD) is the {weightingNote} average.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} stackOffset="sign">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="segment" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => v + "%"}
          />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(v, name) => [
              ((v as number) < 0 ? -(v as number) : (v as number)).toFixed(1) + "%",
              name as string,
            ]}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="Collateral recovery" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
          <Bar dataKey="Non-collateral recovery" stackId="a" fill="#3b82f6" />
          <Bar dataKey="Recovery costs" stackId="a" fill="#f97316" />
          <Bar dataKey="Net loss (LGD)" stackId="a" fill="var(--negative)" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
