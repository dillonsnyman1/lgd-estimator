import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VintageAnalysis, WeightingMethod } from "../types/portfolio";

interface Props {
  vintageAnalysis: VintageAnalysis;
  weightingMethod: WeightingMethod;
}

export function VintageChart({ vintageAnalysis, weightingMethod }: Props) {
  const data = vintageAnalysis.vintages.map((v) => ({
    year: v.year,
    Resolved: v.resolved_count,
    "Written Off": v.written_off_count,
    Cured: v.cured_count,
    Open: v.open_count,
    lgd_pct: +(v.weighted_avg_lgd * 100).toFixed(1),
  }));

  const weightingNote = weightingMethod === "ead_weighted" ? "EAD-weighted" : "Number-weighted (IRB)";

  return (
    <div className="chart-card" style={{ flex: "2 1 500px" }}>
      <h3>Vintage Analysis</h3>
      <p className="chart-note">Loan count by default year and status (bars, left axis). {weightingNote} LGD (line, right axis).</p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 4, right: 40, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="count"
            tick={{ fontSize: 11 }}
            label={{ value: "Loans", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 11 } }}
          />
          <YAxis
            yAxisId="lgd"
            orientation="right"
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => v + "%"}
            domain={[0, 100]}
            label={{ value: "LGD", angle: 90, position: "insideRight", offset: 10, style: { fontSize: 11 } }}
          />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(v, name) =>
              name === "LGD"
                ? [(v as number).toFixed(1) + "%", name]
                : [v as number, name]
            }
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar yAxisId="count" dataKey="Resolved" stackId="a" fill="#22c55e" />
          <Bar yAxisId="count" dataKey="Written Off" stackId="a" fill="var(--negative)" />
          <Bar yAxisId="count" dataKey="Cured" stackId="a" fill="#3b82f6" />
          <Bar yAxisId="count" dataKey="Open" stackId="a" fill="#f59e0b" radius={[2, 2, 0, 0]} />
          <Line
            yAxisId="lgd"
            dataKey="lgd_pct"
            name="LGD"
            type="monotone"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
