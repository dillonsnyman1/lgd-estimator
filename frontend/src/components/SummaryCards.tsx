import type { LgdAssumptions, PortfolioSummary, SegmentSummary } from "../types/portfolio";
import { OPEN_DEFAULT_METHOD_LABELS, currency, pct } from "../types/portfolio";

interface Props {
  summary: PortfolioSummary | SegmentSummary;
  assumptions: LgdAssumptions;
}

interface CardProps {
  label: string;
  value: string;
  sub?: string;
}

function Card({ label, value, sub }: CardProps) {
  return (
    <div className="summary-card">
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-value">{value}</div>
      {sub && <div className="summary-card-sub">{sub}</div>}
    </div>
  );
}

export function SummaryCards({ summary: s, assumptions }: Props) {
  const downturnDiff = s.weighted_avg_lgd_final - s.weighted_avg_lgd;
  const downturnLabel = downturnDiff > 0.0001
    ? `Downturn: ${pct(s.weighted_avg_lgd_final)} (+${pct(downturnDiff)})`
    : undefined;

  const weightingLabel = assumptions.weighting_method === "ead_weighted"
    ? "EAD-weighted"
    : "Number-weighted (IRB)";

  const openMethodLabel = OPEN_DEFAULT_METHOD_LABELS[assumptions.open_default_method];

  return (
    <div className="summary-cards">
      <Card
        label="Portfolio LGD"
        value={pct(s.weighted_avg_lgd)}
        sub={downturnLabel ?? weightingLabel}
      />
      <Card
        label="Total Exposure"
        value={currency(s.total_exposure)}
        sub={`${s.loan_count} defaults`}
      />
      <Card
        label="Expected Loss"
        value={currency(s.total_expected_loss)}
        sub={`EL rate: ${pct(s.total_expected_loss / s.total_exposure)}`}
      />
      <Card
        label="Cure Rate"
        value={pct(s.cure_rate)}
        sub={`${s.cured_count} of ${s.loan_count} cured`}
      />
      <Card
        label="Open (In-Workout)"
        value={String(s.open_count)}
        sub={openMethodLabel}
      />
      <Card
        label="Written Off"
        value={String(s.written_off_count)}
        sub={`${pct(s.written_off_rate)} of portfolio`}
      />
    </div>
  );
}
