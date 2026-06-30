import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MethodologyComparison } from "../types/portfolio";

interface Props {
  summary: { methodology_comparison: MethodologyComparison };
}

const METHOD_COLORS = ["var(--accent)", "#8b5cf6", "#06b6d4"];

export function MethodologyComparisonChart({ summary }: Props) {
  const mc = summary.methodology_comparison;
  const data = [
    { label: "Workout", value: +(mc.workout_lgd * 100).toFixed(1) },
    { label: "Market", value: +(mc.market_lgd * 100).toFixed(1) },
    { label: "Implied market", value: +(mc.implied_market_lgd * 100).toFixed(1) },
  ];

  return (
    <div className="chart-card">
      <h3>Methodology Comparison</h3>
      <p className="chart-note">Portfolio LGD across the three estimation approaches.</p>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => v + "%"}
            domain={[0, 100]}
          />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(v) => [(v as number).toFixed(1) + "%", "Portfolio LGD"]}
          />
          <Bar dataKey="value" radius={[2, 2, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={METHOD_COLORS[i]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
