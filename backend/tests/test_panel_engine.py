import pandas as pd

from app.models import DefaultStatus
from app.panel_engine import loans_from_panel

_MONTHS = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05", "2022-06"]


def _row(loan_id="L00001", month_idx=0, **overrides):
    defaults = dict(
        loan_id=loan_id,
        segment="retail_mortgage",
        observation_month=_MONTHS[month_idx],
        outstanding_balance=50_000.0,
        dpd=0,
        collateral_type="residential_real_estate",
        collateral_value=60_000.0,
        cash_received_collateral=0.0,
        cash_received_other=0.0,
        recovery_cost_incurred=0.0,
        default_flag=False,
        write_off_flag=False,
        market_price=0.8,
        credit_spread_bps=200.0,
        pre_default_pd=0.02,
    )
    defaults.update(overrides)
    return defaults


def _panel(*rows):
    return pd.DataFrame(rows)


def test_default_start_month_and_open_outcome():
    df = _panel(
        _row(month_idx=0, default_flag=False),
        _row(month_idx=1, default_flag=True),
        _row(month_idx=2, default_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert len(loans) == 1
    assert episodes[0].start_month == "2022-02"
    assert episodes[0].end_month == "2022-03"
    assert episodes[0].default_status == DefaultStatus.open


def test_cure_is_immediate_on_first_false_row():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=True),
        _row(month_idx=2, default_flag=False),
    )
    loans, episodes = loans_from_panel(df)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.default_status == DefaultStatus.cured
    assert ep.start_month == "2022-01"
    assert ep.end_month == "2022-02"
    assert ep.row_count == 2


def test_write_off_takes_priority_over_zero_balance():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=True, outstanding_balance=0.0, write_off_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert episodes[0].default_status == DefaultStatus.written_off
    assert episodes[0].end_month == "2022-02"


def test_resolved_when_balance_reaches_zero_without_write_off():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=True, outstanding_balance=0.0),
    )
    loans, episodes = loans_from_panel(df)
    assert episodes[0].default_status == DefaultStatus.resolved
    assert episodes[0].end_month == "2022-02"


def test_open_when_panel_ends_mid_default():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=True),
        _row(month_idx=2, default_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert episodes[0].default_status == DefaultStatus.open
    assert episodes[0].end_month == "2022-03"


def test_redefault_produces_two_synthesized_loan_ids():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=False),
        _row(month_idx=2, default_flag=False),
        _row(month_idx=3, default_flag=True),
        _row(month_idx=4, default_flag=True),
        _row(month_idx=5, default_flag=True, write_off_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert len(episodes) == 2
    assert [ep.loan_id for ep in episodes] == ["L00001-1", "L00001-2"]
    assert episodes[0].default_status == DefaultStatus.cured
    assert episodes[0].start_month == "2022-01"
    assert episodes[0].end_month == "2022-01"
    assert episodes[1].default_status == DefaultStatus.written_off
    assert episodes[1].start_month == "2022-04"
    assert episodes[1].end_month == "2022-06"


def test_single_episode_loan_keeps_original_loan_id():
    df = _panel(
        _row(month_idx=0, default_flag=True),
        _row(month_idx=1, default_flag=True, outstanding_balance=0.0, write_off_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert loans[0].loan_id == "L00001"
    assert episodes[0].loan_id == "L00001"


def test_same_month_resolution_floors_time_in_default():
    df = _panel(
        _row(month_idx=0, default_flag=True, outstanding_balance=0.0, write_off_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert len(loans) == 1
    assert loans[0].time_in_default_years == round(1 / 12, 4)


def test_cash_flow_sums_are_exact_across_episode_rows():
    df = _panel(
        _row(month_idx=0, default_flag=True, cash_received_collateral=100.0, cash_received_other=10.0, recovery_cost_incurred=1.0),
        _row(month_idx=1, default_flag=True, cash_received_collateral=200.0, cash_received_other=20.0, recovery_cost_incurred=2.0),
        _row(month_idx=2, default_flag=True, cash_received_collateral=300.0, cash_received_other=5.0, recovery_cost_incurred=3.0, outstanding_balance=0.0),
    )
    loans, episodes = loans_from_panel(df)
    assert len(loans) == 1
    loan = loans[0]
    assert loan.collateral_recovered == 600.0
    assert loan.non_collateral_recovered == 35.0
    assert loan.recovery_costs == 6.0


def test_pre_default_row_used_for_market_fields():
    df = _panel(
        _row(month_idx=0, default_flag=False, market_price=0.91, credit_spread_bps=150.0, pre_default_pd=0.01),
        _row(month_idx=1, default_flag=True, outstanding_balance=0.0, write_off_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert loans[0].market_price_at_default == 0.91
    assert loans[0].credit_spread_bps == 150.0
    assert loans[0].pre_default_pd == 0.01


def test_multiple_loans_processed_independently():
    df = _panel(
        _row(loan_id="L00001", month_idx=0, default_flag=True, outstanding_balance=0.0, write_off_flag=True),
        _row(loan_id="L00002", month_idx=0, default_flag=True),
        _row(loan_id="L00002", month_idx=1, default_flag=True),
    )
    loans, episodes = loans_from_panel(df)
    assert {loan.loan_id for loan in loans} == {"L00001", "L00002"}
    assert len(episodes) == 2
