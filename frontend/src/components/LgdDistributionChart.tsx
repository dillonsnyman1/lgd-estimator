import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProcessedLoan } from "../types/portfolio";

interface Props {
  loans: ProcessedLoan[];
}

const BUCKETS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01];

export function LgdDistributionChart({ loans }: Props) {
  const data = BUCKETS.slice(0, -1).map((lo, i) => {
    const hi = BUCKETS[i + 1];
    const count = loans.filter((l) => l.lgd_final >= lo && l.lgd_final < hi).length;
    return {
      bucket: `${(lo * 100).toFixed(0)}-${(hi === 1.01 ? 100 : hi * 100).toFixed(0)}%`,
      count,
    };
  });

  return (
    <div className="chart-card">
      <h3>LGD Distribution</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(v) => [v as number, "Loans"]}
          />
          <Bar dataKey="count" fill="var(--accent)" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
