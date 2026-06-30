from app.panel_generator import generate_monthly_panel

REQUIRED_COLUMNS = {
    "loan_id",
    "segment",
    "observation_month",
    "outstanding_balance",
    "dpd",
    "collateral_type",
    "collateral_value",
    "cash_received_collateral",
    "cash_received_other",
    "recovery_cost_incurred",
    "default_flag",
    "write_off_flag",
    "market_price",
    "credit_spread_bps",
    "pre_default_pd",
}


def test_schema_columns():
    df = generate_monthly_panel(loans_per_segment=5)
    assert set(df.columns) == REQUIRED_COLUMNS


def test_no_nans_in_required_columns():
    df = generate_monthly_panel(loans_per_segment=5)
    assert df[list(REQUIRED_COLUMNS)].isna().sum().sum() == 0


def test_dtypes():
    df = generate_monthly_panel(loans_per_segment=5)
    assert df["dpd"].dtype.kind in "iu"
    assert df["default_flag"].dtype == bool
    assert df["write_off_flag"].dtype == bool
    for col in ("outstanding_balance", "collateral_value", "cash_received_collateral",
                "cash_received_other", "recovery_cost_incurred", "market_price",
                "credit_spread_bps", "pre_default_pd"):
        assert df[col].dtype.kind == "f"


def test_non_negative_balances_and_cashflows():
    df = generate_monthly_panel(loans_per_segment=10)
    assert (df["outstanding_balance"] >= 0).all()
    assert (df["dpd"] >= 0).all()
    assert (df["collateral_value"] >= 0).all()
    assert (df["cash_received_collateral"] >= 0).all()
    assert (df["cash_received_other"] >= 0).all()
    assert (df["recovery_cost_incurred"] >= 0).all()


def test_determinism_same_seed():
    df1 = generate_monthly_panel(loans_per_segment=10, seed=7)
    df2 = generate_monthly_panel(loans_per_segment=10, seed=7)
    assert df1.equals(df2)


def test_different_seed_differs():
    df1 = generate_monthly_panel(loans_per_segment=10, seed=1)
    df2 = generate_monthly_panel(loans_per_segment=10, seed=2)
    assert not df1.equals(df2)


def test_loan_count_matches_request():
    df = generate_monthly_panel(loans_per_segment=5)
    assert df["loan_id"].nunique() == 5 * 4  # 4 sample segments


def test_some_loans_written_off():
    df = generate_monthly_panel(loans_per_segment=50)
    written_off_loans = df.loc[df["write_off_flag"], "loan_id"].nunique()
    assert written_off_loans > 0


def test_write_off_flag_only_set_once_per_loan():
    df = generate_monthly_panel(loans_per_segment=50)
    flags_per_loan = df.groupby("loan_id")["write_off_flag"].sum()
    assert (flags_per_loan <= 1).all()


def test_most_loans_default_but_some_never_do():
    df = generate_monthly_panel(loans_per_segment=50)
    default_rows_per_loan = df.groupby("loan_id")["default_flag"].sum()
    never_defaulted = (default_rows_per_loan == 0).sum()
    # NEVER_DEFAULT_PROB ~8% - assert some, but not most, loans never default.
    assert 0 < never_defaulted < len(default_rows_per_loan) * 0.25


def test_write_off_implies_default_flag():
    df = generate_monthly_panel(loans_per_segment=50)
    write_off_rows = df.loc[df["write_off_flag"]]
    assert write_off_rows["default_flag"].all()
