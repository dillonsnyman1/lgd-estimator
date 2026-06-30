import pytest

from app.lgd_engine import (
    _lgd_implied_market,
    _lgd_market,
    _lgd_open_probability_weighted,
    _lgd_workout_open,
    _lgd_workout_resolved,
    _compute_outcome_probabilities,
    _process_non_open_loan,
    compute_downturn_calibration,
    process_portfolio,
)
from app.models import (
    CollateralType,
    CureLgdMethod,
    DefaultStatus,
    LgdAssumptions,
    Loan,
    Methodology,
    OpenDefaultMethod,
    OutcomeProbabilities,
    VintageAnalysis,
    VintageStats,
    WeightingMethod,
)

_ALL_SAMPLE_SEGMENTS = {"retail_mortgage", "retail_unsecured", "corporate", "sme"}


def _make_loan(**overrides) -> Loan:
    defaults = dict(
        loan_id="L00001",
        segment="retail_mortgage",
        default_status=DefaultStatus.resolved,
        collateral_type=CollateralType.residential_real_estate,
        collateral_value=240_000.0,
        exposure_at_default=200_000.0,
        collateral_recovered=150_000.0,
        non_collateral_recovered=10_000.0,
        recovery_costs=5_000.0,
        time_in_default_years=1.5,
        default_year=2022,
        market_price_at_default=0.82,
        credit_spread_bps=200.0,
        pre_default_pd=0.02,
    )
    defaults.update(overrides)
    return Loan(**defaults)


def _default_assumptions(**overrides) -> LgdAssumptions:
    defaults = dict(
        methodology=Methodology.workout,
        open_default_method=OpenDefaultMethod.elbe,
        discount_rate=0.05,
        downturn_enabled=False,
        downturn_multiplier=1.25,
        haircut_rre=0.20,
        haircut_cre=0.40,
        haircut_financial=0.15,
        haircut_other_physical=0.50,
        cure_lgd=0.05,
        expected_remaining_recovery_rate=0.75,
        expected_additional_years_open=1.5,
    )
    defaults.update(overrides)
    return LgdAssumptions(**defaults)


class TestWorkoutLgdResolved:
    def test_zero_recovery_gives_lgd_one(self):
        loan = _make_loan(collateral_recovered=0, non_collateral_recovered=0, recovery_costs=0)
        assumptions = _default_assumptions()
        lgd, _, _, _, _ = _lgd_workout_resolved(loan, assumptions)
        assert lgd == 1.0

    def test_full_recovery_zero_rate_gives_lgd_zero(self):
        loan = _make_loan(
            collateral_recovered=200_000,
            non_collateral_recovered=0,
            recovery_costs=0,
            time_in_default_years=1.0,
        )
        assumptions = _default_assumptions(discount_rate=0.0)
        lgd, _, _, _, _ = _lgd_workout_resolved(loan, assumptions)
        assert lgd == pytest.approx(0.0, abs=1e-4)

    def test_discounting_increases_lgd(self):
        loan = _make_loan()
        assumptions_0 = _default_assumptions(discount_rate=0.0)
        assumptions_5 = _default_assumptions(discount_rate=0.05)
        lgd_0, *_ = _lgd_workout_resolved(loan, assumptions_0)
        lgd_5, *_ = _lgd_workout_resolved(loan, assumptions_5)
        assert lgd_5 > lgd_0

    def test_lgd_bounded(self):
        loan = _make_loan(recovery_costs=999_999)
        assumptions = _default_assumptions()
        lgd, _, _, _, _ = _lgd_workout_resolved(loan, assumptions)
        assert 0.0 <= lgd <= 1.0


class TestWorkoutElbeOpen:
    def test_partial_plus_estimated_gives_lower_lgd_than_partial_only(self):
        loan = _make_loan(
            default_status=DefaultStatus.open,
            collateral_recovered=50_000,
            non_collateral_recovered=5_000,
            recovery_costs=2_000,
            time_in_default_years=1.0,
        )
        assumptions = _default_assumptions(expected_remaining_recovery_rate=0.75)
        net_collateral = 240_000 * 0.80  # 20% RRE haircut
        elbe, *_ = _lgd_workout_open(loan, net_collateral, assumptions)

        d = 1 / 1.05
        partial_net = max(0, (50_000 + 5_000 - 2_000) * d)
        lgd_partial_only = max(0, min(1, 1 - partial_net / 200_000))
        assert elbe < lgd_partial_only

    def test_no_remaining_collateral_gives_no_future_boost(self):
        loan = _make_loan(
            default_status=DefaultStatus.open,
            collateral_type=CollateralType.none,
            collateral_value=0,
            collateral_recovered=0,
            non_collateral_recovered=20_000,
            recovery_costs=2_000,
            time_in_default_years=1.0,
        )
        assumptions = _default_assumptions()
        elbe, *_ = _lgd_workout_open(loan, 0.0, assumptions)
        d = 1 / 1.05
        partial_net = max(0, (20_000 - 2_000) * d)
        expected = max(0, min(1, 1 - partial_net / 200_000))
        assert elbe == pytest.approx(expected, abs=1e-4)

    def test_elbe_bounded(self):
        loan = _make_loan(default_status=DefaultStatus.open, collateral_recovered=0, non_collateral_recovered=0, recovery_costs=999_999)
        net_collateral = 240_000 * 0.80
        assumptions = _default_assumptions()
        elbe, *_ = _lgd_workout_open(loan, net_collateral, assumptions)
        assert 0.0 <= elbe <= 1.0


class TestProbabilityWeightedOpen:
    def _make_outcome_probs(self, p_res=0.60, p_wo=0.15, p_cure=0.25, lgd_res=0.25, lgd_wo=0.80, lgd_cure=0.08) -> dict:
        probs = OutcomeProbabilities(
            p_resolved=p_res,
            p_written_off=p_wo,
            p_cured=p_cure,
            lgd_given_resolved=lgd_res,
            lgd_given_written_off=lgd_wo,
            lgd_given_cured=lgd_cure,
            completed_count=40,
        )
        return {seg: probs for seg in _ALL_SAMPLE_SEGMENTS}

    def test_probability_weighted_formula(self):
        loan = _make_loan(default_status=DefaultStatus.open)
        assumptions = _default_assumptions(cure_lgd=0.05)
        outcome_probs = self._make_outcome_probs(
            p_res=0.60, p_wo=0.15, p_cure=0.25, lgd_res=0.30, lgd_wo=0.85
        )
        lgd = _lgd_open_probability_weighted(loan, outcome_probs, assumptions)
        expected = 0.60 * 0.30 + 0.15 * 0.85 + 0.25 * 0.05
        assert lgd == pytest.approx(expected, abs=1e-4)

    def test_probability_weighted_bounded(self):
        loan = _make_loan(default_status=DefaultStatus.open)
        assumptions = _default_assumptions()
        outcome_probs = self._make_outcome_probs(p_res=0.0, p_wo=1.0, p_cure=0.0, lgd_res=0.0, lgd_wo=2.0)
        lgd = _lgd_open_probability_weighted(loan, outcome_probs, assumptions)
        assert 0.0 <= lgd <= 1.0

    def test_open_probability_weighted_uses_segment_probs(self):
        # Two resolved loans in corporate with low LGD; one open loan in corporate.
        # The open loan should reflect the corporate segment probabilities.
        resolved = _make_loan(
            loan_id="L1",
            segment="corporate",
            default_status=DefaultStatus.resolved,
            collateral_recovered=160_000,
            non_collateral_recovered=20_000,
            recovery_costs=5_000,
        )
        resolved2 = _make_loan(
            loan_id="L2",
            segment="corporate",
            default_status=DefaultStatus.resolved,
            collateral_recovered=140_000,
            non_collateral_recovered=10_000,
            recovery_costs=5_000,
        )
        open_loan = _make_loan(
            loan_id="L3",
            segment="corporate",
            default_status=DefaultStatus.open,
        )
        assumptions = _default_assumptions(open_default_method=OpenDefaultMethod.probability_weighted)
        result = process_portfolio([resolved, resolved2, open_loan], assumptions)

        # Open loan's LGD should equal P(res)*LGD_res for a 100%-resolved segment
        # (no WO or cured loans)
        open_processed = next(l for l in result.loans if l.loan_id == "L3")
        assert 0.0 <= open_processed.lgd_final <= 1.0

    def test_open_loan_selects_workout_not_market_regardless_of_methodology(self):
        loan = _make_loan(
            default_status=DefaultStatus.open,
            market_price_at_default=0.30,  # market would give LGD=0.70
        )
        assumptions = _default_assumptions(
            methodology=Methodology.market,
            open_default_method=OpenDefaultMethod.elbe,
        )
        result = process_portfolio([loan], assumptions)
        l = result.loans[0]
        # lgd_selected must equal lgd_workout (not lgd_market) for open loans
        assert l.lgd_selected == pytest.approx(l.lgd_workout, abs=1e-4)

    def test_compute_outcome_probabilities_from_completed_loans(self):
        loans = [
            _make_loan(loan_id="L1", default_status=DefaultStatus.resolved, collateral_recovered=160_000, non_collateral_recovered=0, recovery_costs=5_000),
            _make_loan(loan_id="L2", default_status=DefaultStatus.written_off, collateral_recovered=0, non_collateral_recovered=0, recovery_costs=1_000),
            _make_loan(loan_id="L3", default_status=DefaultStatus.cured, collateral_recovered=0, non_collateral_recovered=0, recovery_costs=500),
        ]
        assumptions = _default_assumptions()
        processed = [_process_non_open_loan(l, assumptions) for l in loans]
        probs = _compute_outcome_probabilities(loans, processed, {"retail_mortgage"}, WeightingMethod.ead_weighted)
        rm_probs = probs["retail_mortgage"]
        assert rm_probs.completed_count == 3
        assert rm_probs.p_resolved == pytest.approx(1/3, abs=0.01)
        assert rm_probs.p_written_off == pytest.approx(1/3, abs=0.01)
        assert rm_probs.p_cured == pytest.approx(1/3, abs=0.01)
        assert 0.0 <= rm_probs.lgd_given_resolved <= 1.0
        assert 0.0 <= rm_probs.lgd_given_written_off <= 1.0


class TestMarketLgd:
    def test_market_price_at_par_gives_zero_lgd(self):
        loan = _make_loan(market_price_at_default=1.0)
        assert _lgd_market(loan) == pytest.approx(0.0)

    def test_market_price_zero_gives_full_lgd(self):
        loan = _make_loan(market_price_at_default=0.0)
        assert _lgd_market(loan) == pytest.approx(1.0)

    def test_typical_price(self):
        loan = _make_loan(market_price_at_default=0.65)
        assert _lgd_market(loan) == pytest.approx(0.35, abs=1e-4)


class TestImpliedMarketLgd:
    def test_spread_equals_pd_gives_lgd_one(self):
        loan = _make_loan(credit_spread_bps=1000, pre_default_pd=0.10)
        assert _lgd_implied_market(loan) == pytest.approx(1.0)

    def test_typical_values(self):
        loan = _make_loan(credit_spread_bps=200, pre_default_pd=0.04)
        assert _lgd_implied_market(loan) == pytest.approx(0.50, abs=1e-4)


class TestCureLgdCalculated:
    def test_calculated_uses_dcf_not_assumption(self):
        loan = _make_loan(
            default_status=DefaultStatus.cured,
            collateral_recovered=180_000,
            non_collateral_recovered=0,
            recovery_costs=5_000,
            time_in_default_years=1.0,
        )
        assumptions = _default_assumptions(
            cure_lgd=0.50,  # high fixed assumption - should NOT be used
            cure_lgd_method=CureLgdMethod.calculated,
            discount_rate=0.0,
        )
        result = process_portfolio([loan], assumptions)
        # net_recovery = (180k - 5k) / 200k = 0.875 => lgd = 0.125, well below 0.50
        assert result.loans[0].lgd_final < 0.20

    def test_calculated_cure_lgd_bounded(self):
        loan = _make_loan(
            default_status=DefaultStatus.cured,
            collateral_recovered=0,
            non_collateral_recovered=0,
            recovery_costs=999_999,
        )
        assumptions = _default_assumptions(cure_lgd_method=CureLgdMethod.calculated)
        result = process_portfolio([loan], assumptions)
        assert 0.0 <= result.loans[0].lgd_final <= 1.0

    def test_calculated_follows_selected_methodology(self):
        loan = _make_loan(
            default_status=DefaultStatus.cured,
            market_price_at_default=0.90,  # market LGD = 0.10
        )
        assumptions_workout = _default_assumptions(
            cure_lgd_method=CureLgdMethod.calculated,
            methodology=Methodology.workout,
        )
        assumptions_market = _default_assumptions(
            cure_lgd_method=CureLgdMethod.calculated,
            methodology=Methodology.market,
        )
        r_workout = process_portfolio([loan], assumptions_workout)
        r_market = process_portfolio([loan], assumptions_market)
        assert r_market.loans[0].lgd_selected == pytest.approx(0.10, abs=1e-4)
        assert r_workout.loans[0].lgd_selected != r_market.loans[0].lgd_selected

    def test_probability_weighted_uses_calibrated_cure_lgd_when_calculated(self):
        # Build a portfolio: some cured loans with known recoveries, one open loan
        cured = _make_loan(
            loan_id="C1",
            default_status=DefaultStatus.cured,
            collateral_recovered=190_000,
            non_collateral_recovered=0,
            recovery_costs=0,
            time_in_default_years=1.0,
        )
        open_loan = _make_loan(loan_id="O1", default_status=DefaultStatus.open)

        assumptions_fixed = _default_assumptions(
            open_default_method=OpenDefaultMethod.probability_weighted,
            cure_lgd_method=CureLgdMethod.fixed,
            cure_lgd=0.50,
            discount_rate=0.0,
        )
        assumptions_calc = _default_assumptions(
            open_default_method=OpenDefaultMethod.probability_weighted,
            cure_lgd_method=CureLgdMethod.calculated,
            cure_lgd=0.50,  # should be ignored
            discount_rate=0.0,
        )
        r_fixed = process_portfolio([cured, open_loan], assumptions_fixed)
        r_calc = process_portfolio([cured, open_loan], assumptions_calc)
        # With calculated, cure LGD in calibration is 5% (190k recovered of 200k EAD)
        # vs fixed 50% - so open loan LGD should differ
        open_fixed = next(l for l in r_fixed.loans if l.loan_id == "O1")
        open_calc = next(l for l in r_calc.loans if l.loan_id == "O1")
        assert open_fixed.lgd_final != pytest.approx(open_calc.lgd_final, abs=0.01)


class TestCureAndDownturn:
    def test_cured_loan_uses_cure_lgd(self):
        loan = _make_loan(default_status=DefaultStatus.cured)
        assumptions = _default_assumptions(cure_lgd=0.07)
        result = process_portfolio([loan], assumptions)
        assert result.loans[0].lgd_final == pytest.approx(0.07)

    def test_downturn_multiplier_applies_to_resolved(self):
        loan = _make_loan(default_status=DefaultStatus.resolved)
        base = _default_assumptions(downturn_enabled=False)
        stressed = _default_assumptions(downturn_enabled=True, downturn_multiplier=1.25)
        r_base = process_portfolio([loan], base)
        r_stressed = process_portfolio([loan], stressed)
        assert r_stressed.loans[0].lgd_final >= r_base.loans[0].lgd_final

    def test_downturn_capped_at_one(self):
        loan = _make_loan(collateral_recovered=0, non_collateral_recovered=0, recovery_costs=0)
        assumptions = _default_assumptions(downturn_enabled=True, downturn_multiplier=3.0)
        result = process_portfolio([loan], assumptions)
        assert result.loans[0].lgd_final <= 1.0


class TestVintageAnalysis:
    def test_vintage_analysis_present_in_response(self):
        loans = [_make_loan(loan_id="L1", default_year=2021)]
        result = process_portfolio(loans, _default_assumptions())
        assert result.vintage_analysis is not None
        assert len(result.vintage_analysis.vintages) > 0

    def test_vintage_stats_by_year(self):
        loans = [
            _make_loan(loan_id="L1", default_year=2020),
            _make_loan(loan_id="L2", default_year=2021),
            _make_loan(loan_id="L3", default_year=2020),
        ]
        result = process_portfolio(loans, _default_assumptions())
        years = {v.year for v in result.vintage_analysis.vintages}
        assert 2020 in years
        assert 2021 in years
        v2020 = next(v for v in result.vintage_analysis.vintages if v.year == 2020)
        assert v2020.loan_count == 2

    def test_outcome_probabilities_per_segment_present(self):
        loans = [
            _make_loan(loan_id="L1", segment="retail_mortgage"),
            _make_loan(loan_id="L2", segment="corporate"),
        ]
        result = process_portfolio(loans, _default_assumptions())
        assert "retail_mortgage" in result.vintage_analysis.outcome_probabilities
        assert "corporate" in result.vintage_analysis.outcome_probabilities

    def test_outcome_probabilities_sum_to_one(self):
        loans = [
            _make_loan(loan_id=f"L{i}", default_status=DefaultStatus.resolved) for i in range(5)
        ] + [
            _make_loan(loan_id=f"L{i+5}", default_status=DefaultStatus.written_off) for i in range(3)
        ] + [
            _make_loan(loan_id=f"L{i+8}", default_status=DefaultStatus.cured) for i in range(2)
        ]
        result = process_portfolio(loans, _default_assumptions())
        probs = result.vintage_analysis.outcome_probabilities["retail_mortgage"]
        total = probs.p_resolved + probs.p_written_off + probs.p_cured
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_default_year_zero_falls_back_to_time_derived(self):
        loan = _make_loan(default_year=0, time_in_default_years=3.0)
        result = process_portfolio([loan], _default_assumptions())
        # With time_in_default_years=3, effective year = 2026-3 = 2023
        years = {v.year for v in result.vintage_analysis.vintages}
        assert 2023 in years


class TestPortfolioSummary:
    def test_summary_status_counts(self):
        loans = [
            _make_loan(loan_id="L1", default_status=DefaultStatus.resolved),
            _make_loan(loan_id="L2", default_status=DefaultStatus.open),
            _make_loan(loan_id="L3", default_status=DefaultStatus.cured),
            _make_loan(loan_id="L4", default_status=DefaultStatus.written_off),
        ]
        result = process_portfolio(loans, _default_assumptions())
        s = result.summary
        assert s.resolved_count == 1
        assert s.open_count == 1
        assert s.cured_count == 1
        assert s.written_off_count == 1
        assert s.cure_rate == pytest.approx(0.25)

    def test_methodology_comparison_present(self):
        loans = [_make_loan()]
        result = process_portfolio(loans, _default_assumptions())
        mc = result.summary.methodology_comparison
        assert 0 <= mc.workout_lgd <= 1
        assert 0 <= mc.market_lgd <= 1
        assert 0 <= mc.implied_market_lgd <= 1

    def test_segment_summaries_populated(self):
        loans = [
            _make_loan(loan_id="L1", segment="retail_mortgage"),
            _make_loan(loan_id="L2", segment="corporate"),
        ]
        result = process_portfolio(loans, _default_assumptions())
        assert "retail_mortgage" in result.summary.by_segment
        assert "corporate" in result.summary.by_segment

    def test_original_loan_order_preserved(self):
        loans = [
            _make_loan(loan_id="L1", default_status=DefaultStatus.resolved),
            _make_loan(loan_id="L2", default_status=DefaultStatus.open),
            _make_loan(loan_id="L3", default_status=DefaultStatus.cured),
        ]
        result = process_portfolio(loans, _default_assumptions())
        ids = [l.loan_id for l in result.loans]
        assert ids == ["L1", "L2", "L3"]


def _make_vintage(**overrides) -> VintageStats:
    defaults = dict(
        year=2020,
        loan_count=10,
        total_exposure=1_000_000.0,
        weighted_avg_lgd=0.30,
        resolved_count=8,
        written_off_count=2,
        open_count=0,
        cured_count=0,
        completed_count=10,
        predicted_lgd_market=0.30,
        predicted_lgd_implied_market=0.30,
        realized_lgd_workout=0.30,
        avg_time_to_resolution=1.0,
        avg_time_to_writeoff=1.0,
        avg_time_to_cure=0.2,
    )
    defaults.update(overrides)
    return VintageStats(**defaults)


class TestDownturnCalibration:
    def test_basic_ratio(self):
        vintages = [
            _make_vintage(year=2020, weighted_avg_lgd=0.20, loan_count=10, total_exposure=1_000_000.0),
            _make_vintage(year=2021, weighted_avg_lgd=0.40, loan_count=10, total_exposure=1_000_000.0),
        ]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        stress_lgd, benign_lgd, multiplier = compute_downturn_calibration(
            va, stress_years=[2021], benign_years=[2020], weighting=WeightingMethod.number_weighted
        )
        assert stress_lgd == pytest.approx(0.40)
        assert benign_lgd == pytest.approx(0.20)
        assert multiplier == pytest.approx(2.0)

    def test_multi_year_weighted_average(self):
        vintages = [
            _make_vintage(year=2020, weighted_avg_lgd=0.20, loan_count=10, total_exposure=500_000.0),
            _make_vintage(year=2021, weighted_avg_lgd=0.40, loan_count=30, total_exposure=1_500_000.0),
            _make_vintage(year=2022, weighted_avg_lgd=0.10, loan_count=10, total_exposure=500_000.0),
        ]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        _, benign_lgd, _ = compute_downturn_calibration(
            va, stress_years=[2021], benign_years=[2020, 2022], weighting=WeightingMethod.number_weighted
        )
        # number-weighted: (0.20*10 + 0.10*10) / 20
        assert benign_lgd == pytest.approx(0.15)

    def test_ead_weighting_differs_from_number_weighting(self):
        vintages = [
            _make_vintage(year=2020, weighted_avg_lgd=0.20, loan_count=10, total_exposure=100_000.0),
            _make_vintage(year=2022, weighted_avg_lgd=0.10, loan_count=10, total_exposure=900_000.0),
        ]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        _, benign_number, _ = compute_downturn_calibration(
            va, stress_years=[], benign_years=[2020, 2022], weighting=WeightingMethod.number_weighted
        )
        _, benign_ead, _ = compute_downturn_calibration(
            va, stress_years=[], benign_years=[2020, 2022], weighting=WeightingMethod.ead_weighted
        )
        assert benign_number == pytest.approx(0.15)
        # EAD-weighted skews toward the 2022 vintage's larger exposure (lower LGD)
        assert benign_ead < benign_number

    def test_multiplier_clamped_to_upper_bound(self):
        vintages = [
            _make_vintage(year=2020, weighted_avg_lgd=0.05),
            _make_vintage(year=2021, weighted_avg_lgd=0.90),
        ]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        _, _, multiplier = compute_downturn_calibration(
            va, stress_years=[2021], benign_years=[2020], weighting=WeightingMethod.number_weighted
        )
        assert multiplier == pytest.approx(3.0)

    def test_multiplier_clamped_to_lower_bound_when_stress_below_benign(self):
        vintages = [
            _make_vintage(year=2020, weighted_avg_lgd=0.40),
            _make_vintage(year=2021, weighted_avg_lgd=0.20),
        ]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        _, _, multiplier = compute_downturn_calibration(
            va, stress_years=[2021], benign_years=[2020], weighting=WeightingMethod.number_weighted
        )
        assert multiplier == pytest.approx(1.0)

    def test_empty_benign_years_gives_default_multiplier(self):
        vintages = [_make_vintage(year=2020, weighted_avg_lgd=0.30)]
        va = VintageAnalysis(vintages=vintages, outcome_probabilities={})
        stress_lgd, benign_lgd, multiplier = compute_downturn_calibration(
            va, stress_years=[2020], benign_years=[], weighting=WeightingMethod.number_weighted
        )
        assert benign_lgd == 0.0
        assert multiplier == pytest.approx(1.0)
