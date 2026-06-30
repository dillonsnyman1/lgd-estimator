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
  downturnEnabled: boolean;
  weightingMethod: WeightingMethod;
}

export function LgdBySegmentChart({ summary, downturnEnabled, weightingMethod }: Props) {
  const data = Object.keys(summary.by_segment)
    .map((seg) => {
      const ss = summary.by_segment[seg];
      return {
        segment: segmentLabel(seg),
        "LGD (selected)": +(ss.weighted_avg_lgd * 100).toFixed(1),
        ...(downturnEnabled ? { "Downturn LGD": +(ss.weighted_avg_lgd_final * 100).toFixed(1) } : {}),
      };
    });

  const weightingNote = weightingMethod === "ead_weighted" ? "EAD-weighted" : "Number-weighted (IRB)";

  return (
    <div className="chart-card">
      <h3>LGD by Segment</h3>
      <p className="chart-note">{weightingNote} average LGD per segment.</p>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="segment" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => v + "%"}
            domain={[0, 100]}
          />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(v) => [(v as number).toFixed(1) + "%"]}
          />
          {downturnEnabled && <Legend wrapperStyle={{ fontSize: 12 }} />}
          <Bar dataKey="LGD (selected)" fill="var(--accent)" radius={[2, 2, 0, 0]} />
          {downturnEnabled && (
            <Bar dataKey="Downturn LGD" fill="var(--negative)" radius={[2, 2, 0, 0]} />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
