import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VintageAnalysis } from "../types/portfolio";

interface Props {
  vintageAnalysis: VintageAnalysis;
}

export function TimeToOutcomeChart({ vintageAnalysis }: Props) {
  const data = vintageAnalysis.vintages.map((v) => ({
    year: v.year,
    "Time to Resolution": v.resolved_count > 0 ? +v.avg_time_to_resolution.toFixed(2) : null,
    "Time to Write-off": v.written_off_count > 0 ? +v.avg_time_to_writeoff.toFixed(2) : null,
    "Time to Cure": v.cured_count > 0 ? +v.avg_time_to_cure.toFixed(2) : null,
  }));

  const hasAnyData = data.some(
    (d) => d["Time to Resolution"] !== null || d["Time to Write-off"] !== null || d["Time to Cure"] !== null
  );

  return (
    <div className="chart-card">
      <h3>Time to Outcome by Vintage</h3>
      <p className="chart-note">
        Average elapsed time in default before reaching each terminal outcome, by vintage year.
        Open (still in workout) loans are excluded since their elapsed time is still growing.
        A rising trend can signal a slowing workout process - worth checking against haircut and
        ELBE assumptions for open defaults.
      </p>
      {!hasAnyData ? (
        <p className="chart-note">No completed outcomes yet to compare.</p>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v: number) => v + "y"}
              label={{ value: "Years", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 11 } }}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(v) => (v === null ? ["—", ""] : [(v as number).toFixed(2) + " yrs", ""])}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line dataKey="Time to Resolution" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
            <Line dataKey="Time to Write-off" stroke="var(--negative)" strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
            <Line dataKey="Time to Cure" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
