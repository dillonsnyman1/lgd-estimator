"""LGD estimation engine.

Three workout methodologies are supported for completed (resolved/written_off) loans:

  workout        Discounted cash flow recovery.
  market         1 - secondary market price at default.
  implied_market Credit spread divided by market-implied PD.

Two methods are available for open (in-workout) defaults. Both produce a complete
forecast of the final LGD; the selected methodology does not affect open loans
(market/implied-market inputs are pre-default observations, not current values).

  elbe                 Expected Loss Best Estimate (ELBE).
                       Step 1: discount partial cash flows received to date.
                       Step 2: estimate future collateral recovery from remaining
                               net collateral, discounted at the full expected horizon.
                       LGD = 1 - (partial_net + estimated_future) / EAD.

  probability_weighted Cohort-based outcome weighting.
                       Calibrated from completed loans in the same segment:
                         P(res), P(WO), P(cure) = outcome frequencies
                         LGD|res, LGD|WO        = EAD-weighted segment averages
                       LGD = P(res)*LGD|res + P(WO)*LGD|WO + P(cure)*cure_lgd.
                       Falls back to portfolio-wide probabilities for segments
                       with fewer than 5 completed loans.

Default status affects the calculation path:

  resolved / written_off
      All three methodologies computed from final actual recovery figures.

  open
      Both open methods always applied; selected via open_default_method assumption.
      Market and implied-market are also computed from pre-default inputs and
      included in the methodology comparison chart.

  cured
      fixed:      all methodologies return cure_lgd assumption regardless of recovery amounts.
      calculated: same DCF formula as resolved loans; lgd_selected follows selected methodology.
"""

from app.models import (
    CollateralType,
    CureLgdMethod,
    DefaultStatus,
    LgdAssumptions,
    Loan,
    Methodology,
    MethodologyComparison,
    OpenDefaultMethod,
    OutcomeProbabilities,
    PortfolioResponse,
    PortfolioSummary,
    ProcessedLoan,
    SegmentSummary,
    VintageAnalysis,
    VintageStats,
    WeightingMethod,
)

_CURRENT_YEAR = 2026


def _effective_haircut(collateral_type: CollateralType, assumptions: LgdAssumptions) -> float:
    match collateral_type:
        case CollateralType.none:
            return 1.0
        case CollateralType.residential_real_estate:
            return assumptions.haircut_rre
        case CollateralType.commercial_real_estate:
            return assumptions.haircut_cre
        case CollateralType.financial_collateral:
            return assumptions.haircut_financial
        case CollateralType.other_physical:
            return assumptions.haircut_other_physical


def _discount(rate: float, years: float) -> float:
    return 1.0 / (1.0 + rate) ** years


def _effective_year(loan: Loan) -> int:
    if loan.default_year and loan.default_year > 0:
        return loan.default_year
    return max(2000, _CURRENT_YEAR - round(loan.time_in_default_years))


# ---------------------------------------------------------------------------
# Completed-loan LGD formulas
# ---------------------------------------------------------------------------

def _lgd_workout_resolved(loan: Loan, assumptions: LgdAssumptions) -> tuple[float, float, float, float, float]:
    """Returns (lgd, gross_recovery, net_recovery, partial_net, estimated_future).

    For resolved/written_off loans all recovery figures are final actuals.
    partial_net = net_recovery; estimated_future = 0.
    """
    d = _discount(assumptions.discount_rate, loan.time_in_default_years)
    gross = loan.collateral_recovered + loan.non_collateral_recovered
    net = max(0.0, (gross - loan.recovery_costs) * d)
    lgd = max(0.0, min(1.0, 1.0 - net / loan.exposure_at_default))
    return lgd, gross, net, net, 0.0


def _lgd_market(loan: Loan) -> float:
    return max(0.0, min(1.0, 1.0 - loan.market_price_at_default))


def _lgd_implied_market(loan: Loan) -> float:
    spread = loan.credit_spread_bps / 10_000.0
    return max(0.0, min(1.0, spread / loan.pre_default_pd))


def _apply_downturn(lgd: float, assumptions: LgdAssumptions) -> float:
    if assumptions.downturn_enabled:
        return min(1.0, lgd * assumptions.downturn_multiplier)
    return lgd


# ---------------------------------------------------------------------------
# Open-default LGD methods
# ---------------------------------------------------------------------------

def _lgd_workout_open(
    loan: Loan,
    net_collateral_value: float,
    assumptions: LgdAssumptions,
) -> tuple[float, float, float, float, float]:
    """ELBE for open (in-workout) defaults.

    Returns (elbe, gross_to_date, total_net_recovery, partial_net, estimated_future).

    Step 1 - Partial net recovery to date:
        Discount cash received so far (collateral + non-collateral, net of costs)
        from the average receipt date back to the default date. We conservatively
        assume all partial flows arrived at time_in_default_years (end of elapsed
        period), discounting by that horizon.

    Step 2 - Estimated future collateral recovery:
        remaining_net_coll = net_collateral_value - collateral_recovered_to_date
        estimated_future = remaining_net_coll * expected_remaining_recovery_rate
        This is discounted from (time_in_default_years + expected_additional_years)
        back to the default date.

    Step 3 - ELBE:
        ELBE = max(0, 1 - (partial_net + estimated_future_discounted) / EAD)
    """
    d_partial = _discount(assumptions.discount_rate, loan.time_in_default_years)
    gross_to_date = loan.collateral_recovered + loan.non_collateral_recovered
    partial_net = max(0.0, (gross_to_date - loan.recovery_costs) * d_partial)

    remaining_net_coll = max(0.0, net_collateral_value - loan.collateral_recovered)
    estimated_future_gross = remaining_net_coll * assumptions.expected_remaining_recovery_rate

    total_horizon = loan.time_in_default_years + assumptions.expected_additional_years_open
    d_future = _discount(assumptions.discount_rate, total_horizon)
    estimated_future_discounted = estimated_future_gross * d_future

    total_net = partial_net + estimated_future_discounted
    elbe = max(0.0, min(1.0, 1.0 - total_net / loan.exposure_at_default))

    return elbe, gross_to_date, total_net, partial_net, estimated_future_discounted


def _lgd_open_probability_weighted(
    loan: Loan,
    outcome_probs: "dict[str, OutcomeProbabilities]",
    assumptions: LgdAssumptions,
) -> float:
    """Probability-weighted outcome LGD for open defaults.

    LGD = P(res)*LGD|res + P(WO)*LGD|WO + P(cure)*cure_lgd

    Probabilities and conditional LGDs are calibrated from completed loans in the
    same segment. Falls back to portfolio-wide probs for segments with <5 completed
    loans, or to 0.5 if no completed loans exist at all.
    """
    probs = outcome_probs.get(loan.segment)
    if probs is None:
        return 0.5
    cure_lgd = (
        probs.lgd_given_cured
        if assumptions.cure_lgd_method == CureLgdMethod.calculated
        else assumptions.cure_lgd
    )
    lgd = (
        probs.p_resolved * probs.lgd_given_resolved
        + probs.p_written_off * probs.lgd_given_written_off
        + probs.p_cured * cure_lgd
    )
    return max(0.0, min(1.0, lgd))


# ---------------------------------------------------------------------------
# Outcome probability calibration
# ---------------------------------------------------------------------------

def _outcome_probs_from_pairs(
    pairs: list[tuple[Loan, ProcessedLoan]],
    weighting: WeightingMethod,
) -> OutcomeProbabilities:
    resolved = [(l, p) for l, p in pairs if l.default_status == DefaultStatus.resolved]
    written_off = [(l, p) for l, p in pairs if l.default_status == DefaultStatus.written_off]
    cured = [(l, p) for l, p in pairs if l.default_status == DefaultStatus.cured]

    total = len(resolved) + len(written_off) + len(cured)
    if total == 0:
        return OutcomeProbabilities(
            p_resolved=1/3, p_written_off=1/3, p_cured=1/3,
            lgd_given_resolved=0.45, lgd_given_written_off=0.80,
            completed_count=0,
        )

    def conditional_lgd(sub: list[tuple[Loan, ProcessedLoan]], fallback: float) -> float:
        if not sub:
            return fallback
        if weighting == WeightingMethod.number_weighted:
            return sum(p.lgd_selected for _, p in sub) / len(sub)
        total_ead = sum(p.exposure_at_default for _, p in sub)
        if total_ead == 0:
            return fallback
        return sum(p.lgd_selected * p.exposure_at_default for _, p in sub) / total_ead

    return OutcomeProbabilities(
        p_resolved=round(len(resolved) / total, 4),
        p_written_off=round(len(written_off) / total, 4),
        p_cured=round(len(cured) / total, 4),
        lgd_given_resolved=round(conditional_lgd(resolved, 0.45), 4),
        lgd_given_written_off=round(conditional_lgd(written_off, 0.80), 4),
        lgd_given_cured=round(conditional_lgd(cured, 0.05), 4),
        completed_count=total,
    )


def _compute_outcome_probabilities(
    non_open_loans: list[Loan],
    non_open_processed: list[ProcessedLoan],
    all_segments: set[str],
    weighting: WeightingMethod,
) -> dict[str, OutcomeProbabilities]:
    """Per-segment outcome probabilities from completed (non-open) loans.

    `all_segments` is the set of segment values present anywhere in the
    portfolio (including open loans), so a segment that only has open loans
    still gets a (portfolio-wide fallback) entry. Falls back to portfolio-wide
    probabilities for segments with fewer than 5 completed loans.
    """
    all_pairs = list(zip(non_open_loans, non_open_processed))
    portfolio_probs = _outcome_probs_from_pairs(all_pairs, weighting)

    seg_pairs: dict[str, list[tuple[Loan, ProcessedLoan]]] = {}
    for loan, proc in all_pairs:
        seg_pairs.setdefault(loan.segment, []).append((loan, proc))

    result: dict[str, OutcomeProbabilities] = {}
    for seg in all_segments:
        pairs = seg_pairs.get(seg, [])
        if len(pairs) < 5:
            result[seg] = portfolio_probs
        else:
            result[seg] = _outcome_probs_from_pairs(pairs, weighting)

    return result


# ---------------------------------------------------------------------------
# Per-loan processing
# ---------------------------------------------------------------------------

def _process_non_open_loan(loan: Loan, assumptions: LgdAssumptions) -> ProcessedLoan:
    """Process resolved, written_off, or cured loans (no outcome_probs needed)."""
    haircut = _effective_haircut(loan.collateral_type, assumptions)
    net_collateral_value = loan.collateral_value * (1.0 - haircut)

    lgd_m = _lgd_market(loan)
    lgd_i = _lgd_implied_market(loan)
    observed_lgd_to_date = _lgd_workout_resolved(loan, assumptions)[0]

    if loan.default_status == DefaultStatus.cured:
        if assumptions.cure_lgd_method == CureLgdMethod.calculated:
            lgd_w, gross_recovery, net_recovery, partial_net, estimated_future = _lgd_workout_resolved(
                loan, assumptions
            )
            lgd_selected = {
                Methodology.workout: lgd_w,
                Methodology.market: lgd_m,
                Methodology.implied_market: lgd_i,
            }[assumptions.methodology]
        else:  # fixed
            lgd_w = assumptions.cure_lgd
            gross_recovery = loan.collateral_recovered + loan.non_collateral_recovered
            d = _discount(assumptions.discount_rate, loan.time_in_default_years)
            net_recovery = max(0.0, (gross_recovery - loan.recovery_costs) * d)
            partial_net = net_recovery
            estimated_future = 0.0
            lgd_selected = assumptions.cure_lgd
    else:
        # resolved or written_off
        lgd_w, gross_recovery, net_recovery, partial_net, estimated_future = _lgd_workout_resolved(
            loan, assumptions
        )
        lgd_selected = {
            Methodology.workout: lgd_w,
            Methodology.market: lgd_m,
            Methodology.implied_market: lgd_i,
        }[assumptions.methodology]

    lgd_final = _apply_downturn(lgd_selected, assumptions)

    return ProcessedLoan(
        **loan.model_dump(),
        haircut_applied=round(haircut, 4),
        net_collateral_value=round(net_collateral_value, 2),
        lgd_workout=round(lgd_w, 4),
        lgd_market=round(lgd_m, 4),
        lgd_implied_market=round(lgd_i, 4),
        lgd_selected=round(lgd_selected, 4),
        lgd_post_cure=round(lgd_selected, 4),
        lgd_final=round(lgd_final, 4),
        observed_lgd_to_date=round(observed_lgd_to_date, 4),
        partial_net_recovery=round(partial_net, 2),
        estimated_future_recovery=round(estimated_future, 2),
        gross_recovery=round(gross_recovery, 2),
        net_recovery=round(net_recovery, 2),
        expected_loss=round(lgd_final * loan.exposure_at_default, 2),
    )


def _process_open_loan(
    loan: Loan,
    assumptions: LgdAssumptions,
    outcome_probs: dict[str, OutcomeProbabilities],
) -> ProcessedLoan:
    """Process an open (in-workout) loan using the selected open_default_method."""
    haircut = _effective_haircut(loan.collateral_type, assumptions)
    net_collateral_value = loan.collateral_value * (1.0 - haircut)

    lgd_m = _lgd_market(loan)
    lgd_i = _lgd_implied_market(loan)
    observed_lgd_to_date = _lgd_workout_resolved(loan, assumptions)[0]

    if assumptions.open_default_method == OpenDefaultMethod.elbe:
        lgd_w, gross_recovery, net_recovery, partial_net, estimated_future = _lgd_workout_open(
            loan, net_collateral_value, assumptions
        )
    else:
        lgd_w = _lgd_open_probability_weighted(loan, outcome_probs, assumptions)
        gross_recovery = loan.collateral_recovered + loan.non_collateral_recovered
        net_recovery = round(loan.exposure_at_default * (1.0 - lgd_w), 2)
        partial_net = 0.0
        estimated_future = 0.0

    lgd_selected = lgd_w  # open loans always use workout estimate
    lgd_final = _apply_downturn(lgd_selected, assumptions)

    return ProcessedLoan(
        **loan.model_dump(),
        haircut_applied=round(haircut, 4),
        net_collateral_value=round(net_collateral_value, 2),
        lgd_workout=round(lgd_w, 4),
        lgd_market=round(lgd_m, 4),
        lgd_implied_market=round(lgd_i, 4),
        lgd_selected=round(lgd_selected, 4),
        lgd_post_cure=round(lgd_selected, 4),
        lgd_final=round(lgd_final, 4),
        observed_lgd_to_date=round(observed_lgd_to_date, 4),
        partial_net_recovery=round(partial_net, 2),
        estimated_future_recovery=round(estimated_future, 2),
        gross_recovery=round(gross_recovery, 2),
        net_recovery=round(net_recovery, 2),
        expected_loss=round(lgd_final * loan.exposure_at_default, 2),
    )


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _avg_lgd(loans: list[ProcessedLoan], attr: str, weighting: WeightingMethod) -> float:
    """Weighted average of any numeric ProcessedLoan attribute, not just LGD fields -
    also reused for time_in_default_years (time-to-outcome) below."""
    if not loans:
        return 0.0
    if weighting == WeightingMethod.number_weighted:
        return sum(getattr(l, attr) for l in loans) / len(loans)
    total_ead = sum(l.exposure_at_default for l in loans)
    if total_ead == 0:
        return 0.0
    return sum(getattr(l, attr) * l.exposure_at_default for l in loans) / total_ead


def _status_rate(loans: list[ProcessedLoan], status: DefaultStatus, weighting: WeightingMethod) -> float:
    """Share of the portfolio in a given status - by loan count or by EAD, per weighting."""
    if not loans:
        return 0.0
    if weighting == WeightingMethod.number_weighted:
        return sum(1 for l in loans if l.default_status == status) / len(loans)
    total_ead = sum(l.exposure_at_default for l in loans)
    if total_ead == 0:
        return 0.0
    return sum(l.exposure_at_default for l in loans if l.default_status == status) / total_ead


def _segment_summary(loans: list[ProcessedLoan], weighting: WeightingMethod) -> SegmentSummary:
    total_ead = sum(l.exposure_at_default for l in loans)
    return SegmentSummary(
        loan_count=len(loans),
        resolved_count=sum(1 for l in loans if l.default_status == DefaultStatus.resolved),
        written_off_count=sum(1 for l in loans if l.default_status == DefaultStatus.written_off),
        open_count=sum(1 for l in loans if l.default_status == DefaultStatus.open),
        cured_count=sum(1 for l in loans if l.default_status == DefaultStatus.cured),
        cure_rate=round(_status_rate(loans, DefaultStatus.cured, weighting), 4),
        written_off_rate=round(_status_rate(loans, DefaultStatus.written_off, weighting), 4),
        total_exposure=round(total_ead, 2),
        weighted_avg_lgd=round(_avg_lgd(loans, "lgd_selected", weighting), 4),
        weighted_avg_lgd_final=round(_avg_lgd(loans, "lgd_final", weighting), 4),
        total_expected_loss=round(sum(l.expected_loss for l in loans), 2),
        total_collateral_recovered=round(sum(l.collateral_recovered for l in loans), 2),
        total_non_collateral_recovered=round(sum(l.non_collateral_recovered for l in loans), 2),
        total_recovery_costs=round(sum(l.recovery_costs for l in loans), 2),
        total_net_recovery=round(sum(l.net_recovery for l in loans), 2),
        methodology_comparison=MethodologyComparison(
            workout_lgd=round(_avg_lgd(loans, "lgd_workout", weighting), 4),
            market_lgd=round(_avg_lgd(loans, "lgd_market", weighting), 4),
            implied_market_lgd=round(_avg_lgd(loans, "lgd_implied_market", weighting), 4),
        ),
    )


def _compute_vintage_analysis(
    processed: list[ProcessedLoan],
    outcome_probs: dict[str, OutcomeProbabilities],
    weighting: WeightingMethod,
) -> VintageAnalysis:
    by_year: dict[int, list[ProcessedLoan]] = {}
    for loan in processed:
        year = _effective_year(loan)
        by_year.setdefault(year, []).append(loan)

    vintages = []
    for year in sorted(by_year):
        loans = by_year[year]
        total_ead = sum(l.exposure_at_default for l in loans)
        avg_lgd = _avg_lgd(loans, "lgd_final", weighting) if loans else 0.0
        completed = [
            l for l in loans
            if l.default_status in (DefaultStatus.resolved, DefaultStatus.written_off)
        ]
        resolved_loans = [l for l in loans if l.default_status == DefaultStatus.resolved]
        written_off_loans = [l for l in loans if l.default_status == DefaultStatus.written_off]
        cured_loans = [l for l in loans if l.default_status == DefaultStatus.cured]
        vintages.append(VintageStats(
            year=year,
            loan_count=len(loans),
            total_exposure=round(total_ead, 2),
            weighted_avg_lgd=round(avg_lgd, 4),
            resolved_count=len(resolved_loans),
            written_off_count=len(written_off_loans),
            open_count=sum(1 for l in loans if l.default_status == DefaultStatus.open),
            cured_count=len(cured_loans),
            completed_count=len(completed),
            predicted_lgd_market=round(_avg_lgd(completed, "lgd_market", weighting), 4),
            predicted_lgd_implied_market=round(_avg_lgd(completed, "lgd_implied_market", weighting), 4),
            realized_lgd_workout=round(_avg_lgd(completed, "lgd_workout", weighting), 4),
            avg_time_to_resolution=round(_avg_lgd(resolved_loans, "time_in_default_years", weighting), 3),
            avg_time_to_writeoff=round(_avg_lgd(written_off_loans, "time_in_default_years", weighting), 3),
            avg_time_to_cure=round(_avg_lgd(cured_loans, "time_in_default_years", weighting), 3),
        ))

    return VintageAnalysis(vintages=vintages, outcome_probabilities=outcome_probs)


# ---------------------------------------------------------------------------
# Downturn calibration
# ---------------------------------------------------------------------------

def _weighted_avg_lgd_for_years(vintages: list[VintageStats], years: list[int], weighting: WeightingMethod) -> float:
    selected = [v for v in vintages if v.year in years]
    if not selected:
        return 0.0
    if weighting == WeightingMethod.number_weighted:
        total = sum(v.loan_count for v in selected)
        if total == 0:
            return 0.0
        return sum(v.weighted_avg_lgd * v.loan_count for v in selected) / total
    total_ead = sum(v.total_exposure for v in selected)
    if total_ead == 0:
        return 0.0
    return sum(v.weighted_avg_lgd * v.total_exposure for v in selected) / total_ead


def compute_downturn_calibration(
    vintage_analysis: VintageAnalysis,
    stress_years: list[int],
    benign_years: list[int],
    weighting: WeightingMethod,
) -> tuple[float, float, float]:
    """Derives a downturn multiplier from stress vs benign default vintages.

    Returns (stress_avg_lgd, benign_avg_lgd, derived_multiplier). The multiplier
    is stress_avg_lgd / benign_avg_lgd, clamped to [1.0, 3.0] to satisfy
    LgdAssumptions.downturn_multiplier's bounds. Callers should pass a
    vintage_analysis computed with downturn_enabled=False, otherwise an
    already-applied multiplier distorts the comparison.
    """
    stress_lgd = _weighted_avg_lgd_for_years(vintage_analysis.vintages, stress_years, weighting)
    benign_lgd = _weighted_avg_lgd_for_years(vintage_analysis.vintages, benign_years, weighting)
    if benign_lgd <= 0:
        return stress_lgd, benign_lgd, 1.0
    multiplier = max(1.0, min(3.0, stress_lgd / benign_lgd))
    return stress_lgd, benign_lgd, multiplier


# ---------------------------------------------------------------------------
# Portfolio entry point
# ---------------------------------------------------------------------------

def process_portfolio(loans: list[Loan], assumptions: LgdAssumptions) -> PortfolioResponse:
    # Pass 1: process completed loans (no outcome_probs needed)
    non_open = [l for l in loans if l.default_status != DefaultStatus.open]
    open_loans = [l for l in loans if l.default_status == DefaultStatus.open]

    non_open_processed = [_process_non_open_loan(l, assumptions) for l in non_open]

    # Outcome probabilities are always computed (needed for vintage_analysis and
    # optionally for the probability-weighted open-loan method)
    all_segments = {l.segment for l in loans}
    outcome_probs = _compute_outcome_probabilities(
        non_open, non_open_processed, all_segments, assumptions.weighting_method
    )

    # Pass 2: process open loans with outcome_probs available
    open_processed = [_process_open_loan(l, assumptions, outcome_probs) for l in open_loans]

    # Reconstruct in original order
    processed_map: dict[str, ProcessedLoan] = {}
    for l in non_open_processed:
        processed_map[l.loan_id] = l
    for l in open_processed:
        processed_map[l.loan_id] = l
    processed = [processed_map[l.loan_id] for l in loans]

    w = assumptions.weighting_method
    total_ead = sum(l.exposure_at_default for l in processed)

    method_comparison = MethodologyComparison(
        workout_lgd=round(_avg_lgd(processed, "lgd_workout", w), 4),
        market_lgd=round(_avg_lgd(processed, "lgd_market", w), 4),
        implied_market_lgd=round(_avg_lgd(processed, "lgd_implied_market", w), 4),
    )

    segments: dict[str, list[ProcessedLoan]] = {}
    for loan in processed:
        segments.setdefault(loan.segment, []).append(loan)

    summary = PortfolioSummary(
        loan_count=len(processed),
        total_exposure=round(total_ead, 2),
        resolved_count=sum(1 for l in processed if l.default_status == DefaultStatus.resolved),
        written_off_count=sum(1 for l in processed if l.default_status == DefaultStatus.written_off),
        open_count=sum(1 for l in processed if l.default_status == DefaultStatus.open),
        cured_count=sum(1 for l in processed if l.default_status == DefaultStatus.cured),
        cure_rate=round(_status_rate(processed, DefaultStatus.cured, w), 4),
        written_off_rate=round(_status_rate(processed, DefaultStatus.written_off, w), 4),
        weighted_avg_lgd=round(_avg_lgd(processed, "lgd_selected", w), 4),
        weighted_avg_lgd_final=round(_avg_lgd(processed, "lgd_final", w), 4),
        total_expected_loss=round(sum(l.expected_loss for l in processed), 2),
        by_segment={seg: _segment_summary(seg_loans, w) for seg, seg_loans in segments.items()},
        methodology_comparison=method_comparison,
    )

    vintage_analysis = _compute_vintage_analysis(processed, outcome_probs, w)

    return PortfolioResponse(loans=processed, summary=summary, vintage_analysis=vintage_analysis)
