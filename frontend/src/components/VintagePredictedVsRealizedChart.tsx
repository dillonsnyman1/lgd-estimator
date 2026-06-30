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
import type { VintageAnalysis } from "../types/portfolio";

interface Props {
  vintageAnalysis: VintageAnalysis;
}

export function VintagePredictedVsRealizedChart({ vintageAnalysis }: Props) {
  const data = vintageAnalysis.vintages
    .filter((v) => v.completed_count > 0)
    .map((v) => ({
      year: v.year,
      "Predicted (Market)": +(v.predicted_lgd_market * 100).toFixed(1),
      "Predicted (Implied Market)": +(v.predicted_lgd_implied_market * 100).toFixed(1),
      "Realized (Workout)": +(v.realized_lgd_workout * 100).toFixed(1),
      n: v.completed_count,
    }));

  return (
    <div className="chart-card">
      <h3>Predicted vs Realized LGD by Vintage</h3>
      <p className="chart-note">
        Ex-ante market-implied LGD (known at the moment of default) vs ex-post realized LGD from
        actual recovery cash flows, across each vintage's completed (resolved/written-off) loans.
        Vintages with no completed loans yet are excluded.
      </p>
      {data.length === 0 ? (
        <p className="chart-note">No completed loans yet to compare.</p>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v: number) => v + "%"}
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(v) => (v as number).toFixed(1) + "%"}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="Predicted (Market)" fill="#8b5cf6" radius={[2, 2, 0, 0]} />
            <Bar dataKey="Predicted (Implied Market)" fill="#06b6d4" radius={[2, 2, 0, 0]} />
            <Bar dataKey="Realized (Workout)" fill="var(--accent)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
