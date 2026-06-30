"""Synthetic monthly loan-panel generator.

Produces a raw loan-month panel (one row per loan per month) with realistic
delinquency/default trajectories, calibrated to the same per-segment LGD
ranges previously used by the one-row-per-default generator:

  retail_mortgage   ~15-30%  (well-secured, high cure rate)
  retail_unsecured  ~72-90%  (no collateral, low recovery)
  corporate         ~35-55%  (partially secured, moderate recovery)
  sme               ~45-65%  (mixed collateral, higher than corporate)

Default status mix (approximate, varies by segment):
  cured        18-28% - default_flag set then cleared after a confirmation window
  resolved     45-55% - default_flag stays set, recovery cash brings balance to 0
  written_off  10-18% - default_flag stays set, write_off_flag set on the last row
  open         12-18% - default_flag stays set through the end of the panel

A small fraction of loans (~8%, see NEVER_DEFAULT_PROB) never default at all -
default_flag stays False for the loan's entire history. They're included so
the sample panel demonstrates that performing-only loans are correctly
excluded from default-episode construction, the way a real portfolio extract
would include both defaulted and performing exposures.

`default_flag` is the authoritative default-episode signal (set explicitly,
not inferred from `dpd`); `dpd` is simulated alongside it for trajectory
realism and cure-confirmation only.

This is a first-cut, simplified simulator: each loan is assigned an eventual
outcome up front and a monthly trajectory is generated to match it, rather
than a month-by-month stochastic hazard-rate state machine. It exists to
exercise the panel ingestion pipeline end-to-end with schema-correct,
plausible data; a full hazard-rate state machine is a later enhancement.
"""

import random
from datetime import date

import pandas as pd

from app.models import CollateralType, DefaultStatus, SampleSegment

LOANS_PER_SEGMENT = 50

PANEL_START_MONTH = date(2015, 1, 1)
PANEL_END_MONTH = date(2025, 12, 1)

CURE_CONFIRM_MONTHS = 3
_RAMP_MONTHS = 2  # months at dpd 30, 60 immediately before crossing the threshold
NEVER_DEFAULT_PROB = 0.08

_DEFAULT_HAIRCUTS = {
    CollateralType.none: 1.0,
    CollateralType.residential_real_estate: 0.20,
    CollateralType.commercial_real_estate: 0.40,
    CollateralType.financial_collateral: 0.15,
    CollateralType.other_physical: 0.50,
}

# Same calibration constants as the retired one-row-per-default generator.
_SEGMENT_CONFIG = {
    SampleSegment.retail_mortgage: {
        "ead_range": (80_000, 400_000),
        "cure_prob": 0.27,
        "written_off_of_non_cured": 0.12,
        "open_of_non_cured": 0.15,
        "time_range_resolved": (0.5, 3.0),
        "cure_months_range": (2, 8),  # forbearance/payment-plan confirmation takes longer
        "collateral_options": [
            (CollateralType.residential_real_estate, 0.92, (0.72, 0.94), (0.88, 1.0)),
            (CollateralType.none, 0.08, None, None),
        ],
        "non_coll_pct": (0.01, 0.07),
        "costs_pct": (0.01, 0.04),
        "written_off_recovery_pct": (0.02, 0.12),
    },
    SampleSegment.retail_unsecured: {
        "ead_range": (1_000, 25_000),
        "cure_prob": 0.18,
        "written_off_of_non_cured": 0.22,
        "open_of_non_cured": 0.15,
        "time_range_resolved": (0.5, 2.0),
        "cure_months_range": (1, 4),  # simple repayment catch-up, resolves quickly
        "collateral_options": [
            (CollateralType.none, 1.0, None, None),
        ],
        "non_coll_pct": (0.10, 0.28),
        "costs_pct": (0.05, 0.13),
        "written_off_recovery_pct": (0.0, 0.08),
    },
    SampleSegment.corporate: {
        "ead_range": (200_000, 5_000_000),
        "cure_prob": 0.14,
        "written_off_of_non_cured": 0.15,
        "open_of_non_cured": 0.17,
        "time_range_resolved": (1.0, 4.5),
        "cure_months_range": (2, 10),  # covenant waivers / restructuring negotiations take longer
        "collateral_options": [
            (CollateralType.commercial_real_estate, 0.30, (0.60, 0.85), (0.80, 0.95)),
            (CollateralType.financial_collateral, 0.20, (0.55, 0.80), (0.90, 1.0)),
            (CollateralType.other_physical, 0.20, (0.20, 0.50), (0.65, 0.85)),
            (CollateralType.none, 0.30, None, None),
        ],
        "non_coll_pct": (0.12, 0.30),
        "costs_pct": (0.03, 0.08),
        "written_off_recovery_pct": (0.0, 0.15),
    },
    SampleSegment.sme: {
        "ead_range": (50_000, 2_000_000),
        "cure_prob": 0.20,
        "written_off_of_non_cured": 0.18,
        "open_of_non_cured": 0.16,
        "time_range_resolved": (0.75, 3.5),
        "cure_months_range": (2, 8),
        "collateral_options": [
            (CollateralType.residential_real_estate, 0.18, (0.60, 0.80), (0.82, 0.96)),
            (CollateralType.commercial_real_estate, 0.18, (0.40, 0.65), (0.72, 0.90)),
            (CollateralType.other_physical, 0.24, (0.15, 0.40), (0.60, 0.82)),
            (CollateralType.none, 0.40, None, None),
        ],
        "non_coll_pct": (0.08, 0.22),
        "costs_pct": (0.03, 0.09),
        "written_off_recovery_pct": (0.0, 0.10),
    },
}


def _month_index(d: date) -> int:
    return (d.year - PANEL_START_MONTH.year) * 12 + (d.month - PANEL_START_MONTH.month)


_TOTAL_MONTHS = _month_index(PANEL_END_MONTH) + 1


def _month_at(idx: int) -> str:
    y = PANEL_START_MONTH.year + idx // 12
    m = PANEL_START_MONTH.month + idx % 12
    if m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


def _pick_collateral(options: list[tuple], rng: random.Random) -> tuple:
    weights = [o[1] for o in options]
    idx = rng.choices(range(len(options)), weights=weights, k=1)[0]
    return options[idx]


def _default_status(cfg: dict, rng: random.Random) -> DefaultStatus:
    if rng.random() < cfg["cure_prob"]:
        return DefaultStatus.cured
    remaining_prob = rng.random()
    if remaining_prob < cfg["written_off_of_non_cured"]:
        return DefaultStatus.written_off
    if remaining_prob < cfg["written_off_of_non_cured"] + cfg["open_of_non_cured"]:
        return DefaultStatus.open
    return DefaultStatus.resolved


def _row(
    loan_id: str, segment: SampleSegment, month_idx: int, balance: float, dpd: float,
    collateral_type: CollateralType, collateral_value: float,
    cash_collateral: float, cash_other: float, recovery_cost: float,
    default_flag: bool, write_off_flag: bool,
    market_price: float, credit_spread_bps: float, pre_default_pd: float,
) -> dict:
    return {
        "loan_id": loan_id,
        "segment": segment.value,
        "observation_month": _month_at(month_idx),
        "outstanding_balance": round(max(0.0, balance), 2),
        "dpd": int(round(dpd)),
        "collateral_type": collateral_type.value,
        "collateral_value": round(collateral_value, 2),
        "cash_received_collateral": round(max(0.0, cash_collateral), 2),
        "cash_received_other": round(max(0.0, cash_other), 2),
        "recovery_cost_incurred": round(max(0.0, recovery_cost), 2),
        "default_flag": bool(default_flag),
        "write_off_flag": bool(write_off_flag),
        "market_price": round(market_price, 4),
        "credit_spread_bps": round(credit_spread_bps, 1),
        "pre_default_pd": round(pre_default_pd, 4),
    }


def _cured_rows(
    loan_id: str, segment: SampleSegment, default_start_idx: int, ead: float,
    collateral_type: CollateralType, collateral_value: float,
    market_price: float, credit_spread_bps: float, pre_default_pd: float,
    cure_decline_months: int, rng: random.Random,
) -> list[dict]:
    # Declining DPD trajectory from a random peak down toward 0, length varies
    # per loan/segment (cure_decline_months) so time-to-cure isn't a constant.
    peak_dpd = rng.choice([60, 90, 120, 150])
    decline_path = [
        max(5, round(peak_dpd * (cure_decline_months - i) / cure_decline_months / 5) * 5)
        for i in range(cure_decline_months)
    ]
    dpd_path = decline_path + [0] * CURE_CONFIRM_MONTHS
    cost_month = rng.randrange(0, cure_decline_months)
    rows = []
    for i, dpd in enumerate(dpd_path):
        cost = round(ead * rng.uniform(0.005, 0.02), 2) if i == cost_month else 0.0
        rows.append(_row(
            loan_id, segment, default_start_idx + i, ead, dpd, collateral_type, collateral_value,
            0.0, 0.0, cost, dpd > 0, False, market_price, credit_spread_bps, pre_default_pd,
        ))
    return rows


def _completed_rows(
    loan_id: str, segment: SampleSegment, default_start_idx: int, post_months: int, ead: float,
    collateral_type: CollateralType, collateral_value: float, net_collateral: float,
    coll_recovery_rate_range: tuple | None, cfg: dict,
    market_price: float, credit_spread_bps: float, pre_default_pd: float,
    rng: random.Random, write_off: bool,
) -> list[dict]:
    if write_off:
        recovery_pct = rng.uniform(*cfg["written_off_recovery_pct"])
        total_recovery = ead * recovery_pct
        collateral_share = min(net_collateral * 0.5, total_recovery * 0.7) if coll_recovery_rate_range else 0.0
        total_collateral_recovered = collateral_share
        total_non_collateral_recovered = max(0.0, total_recovery - collateral_share)
        total_costs = round(ead * rng.uniform(*cfg["costs_pct"]) * 0.8, 2)
    else:
        if coll_recovery_rate_range is not None:
            coll_rate = rng.uniform(*coll_recovery_rate_range)
            total_collateral_recovered = min(net_collateral * coll_rate, ead * 0.99)
        else:
            total_collateral_recovered = 0.0
        total_non_collateral_recovered = ead * rng.uniform(*cfg["non_coll_pct"])
        total_costs = ead * rng.uniform(*cfg["costs_pct"])

    rows = []
    balance = ead
    remaining_collateral = total_collateral_recovered
    remaining_other = total_non_collateral_recovered
    remaining_cost = total_costs
    for i in range(post_months):
        is_last = i == post_months - 1
        dpd = min(90 + 25 * i, 540)
        if is_last:
            cash_collateral, cash_other, cost = remaining_collateral, remaining_other, remaining_cost
        else:
            frac = rng.uniform(0.6, 1.4) / post_months
            cash_collateral = min(remaining_collateral, total_collateral_recovered * frac)
            cash_other = min(remaining_other, total_non_collateral_recovered * frac)
            cost = min(remaining_cost, total_costs * frac)
            remaining_collateral -= cash_collateral
            remaining_other -= cash_other
            remaining_cost -= cost
        balance = max(0.0, balance - cash_collateral - cash_other)
        wo_flag = write_off and is_last
        if is_last:
            # Episode closes here either way: a write-off zeroes the balance by
            # bank decision, a resolved workout zeroes it because any shortfall
            # between recovered cash and EAD is the realized loss, not a
            # residual receivable.
            balance = 0.0
        rows.append(_row(
            loan_id, segment, default_start_idx + i, balance, dpd, collateral_type, collateral_value,
            cash_collateral, cash_other, cost, True, wo_flag, market_price, credit_spread_bps, pre_default_pd,
        ))
    return rows


def _open_rows(
    loan_id: str, segment: SampleSegment, default_start_idx: int, post_months: int, ead: float,
    collateral_type: CollateralType, collateral_value: float, net_collateral: float,
    coll_recovery_rate_range: tuple | None, cfg: dict,
    market_price: float, credit_spread_bps: float, pre_default_pd: float, rng: random.Random,
) -> list[dict]:
    completeness = rng.uniform(0.20, 0.55)
    if coll_recovery_rate_range is not None:
        coll_rate = rng.uniform(*coll_recovery_rate_range)
        full_coll = min(net_collateral * coll_rate, ead * 0.99)
        total_collateral_recovered = full_coll * completeness
    else:
        total_collateral_recovered = 0.0
    total_non_collateral_recovered = ead * rng.uniform(*cfg["non_coll_pct"]) * completeness
    total_costs = ead * rng.uniform(*cfg["costs_pct"]) * rng.uniform(0.5, 1.0)

    rows = []
    balance = ead
    for i in range(post_months):
        dpd = min(90 + 20 * i, 480)
        frac = 1.0 / post_months
        cash_collateral = total_collateral_recovered * frac
        cash_other = total_non_collateral_recovered * frac
        cost = total_costs * frac
        balance = max(0.0, balance - cash_collateral - cash_other)
        rows.append(_row(
            loan_id, segment, default_start_idx + i, balance, dpd, collateral_type, collateral_value,
            cash_collateral, cash_other, cost, True, False, market_price, credit_spread_bps, pre_default_pd,
        ))
    return rows


def _performing_rows(
    loan_id: str, segment: SampleSegment, start_idx: int, end_idx: int, ead: float,
    collateral_type: CollateralType, collateral_value: float,
    market_price: float, credit_spread_bps: float, pre_default_pd: float,
) -> list[dict]:
    return [
        _row(
            loan_id, segment, idx, ead, 0, collateral_type, collateral_value,
            0.0, 0.0, 0.0, False, False, market_price, credit_spread_bps, pre_default_pd,
        )
        for idx in range(start_idx, end_idx + 1)
    ]


def _generate_loan_panel(index: int, segment: SampleSegment, rng: random.Random) -> list[dict]:
    cfg = _SEGMENT_CONFIG[segment]
    loan_id = f"L{index:05d}"

    ead = round(rng.uniform(*cfg["ead_range"]), 2)

    coll_option = _pick_collateral(cfg["collateral_options"], rng)
    collateral_type, _, net_coll_frac_range, coll_recovery_rate_range = coll_option
    haircut = _DEFAULT_HAIRCUTS[collateral_type]
    if net_coll_frac_range is None:
        collateral_value = 0.0
        net_collateral = 0.0
    else:
        net_coll_frac = rng.uniform(*net_coll_frac_range)
        net_collateral = ead * net_coll_frac
        collateral_value = round(net_collateral / (1.0 - haircut), 2)

    market_price = round(max(0.02, min(0.98, rng.uniform(0.30, 0.95))), 4)
    pre_default_pd = round(rng.uniform(0.004, 0.04), 4)
    credit_spread_bps = round(max(5.0, pre_default_pd * rng.uniform(2_000, 6_000)), 1)

    if rng.random() < NEVER_DEFAULT_PROB:
        start_idx = rng.randint(0, max(0, _TOTAL_MONTHS // 4))
        return _performing_rows(
            loan_id, segment, start_idx, _TOTAL_MONTHS - 1, ead, collateral_type, collateral_value,
            market_price, credit_spread_bps, pre_default_pd,
        )

    status = _default_status(cfg, rng)

    pre_months = rng.randint(6, 24)
    lo = pre_months + _RAMP_MONTHS

    if status == DefaultStatus.cured:
        cure_decline_months = rng.randint(*cfg["cure_months_range"])
        fixed_post_months = cure_decline_months + CURE_CONFIRM_MONTHS
        hi = max(lo, _TOTAL_MONTHS - fixed_post_months)
        default_start_idx = rng.randint(lo, hi)
        post_months = fixed_post_months
    elif status == DefaultStatus.open:
        hi = max(lo, _TOTAL_MONTHS - 2)
        default_start_idx = rng.randint(lo, hi)
        post_months = _TOTAL_MONTHS - default_start_idx
    else:
        total_years = rng.uniform(*cfg["time_range_resolved"])
        target_post_months = max(2, round(total_years * 12))
        hi = max(lo, _TOTAL_MONTHS - target_post_months)
        default_start_idx = rng.randint(lo, hi)
        post_months = max(2, min(target_post_months, _TOTAL_MONTHS - default_start_idx))

    rows: list[dict] = []

    performing_start = default_start_idx - pre_months - _RAMP_MONTHS
    for idx in range(performing_start, default_start_idx - _RAMP_MONTHS):
        rows.append(_row(
            loan_id, segment, idx, ead, 0, collateral_type, collateral_value,
            0.0, 0.0, 0.0, False, False, market_price, credit_spread_bps, pre_default_pd,
        ))

    ramp_dpds = [30, 60][:_RAMP_MONTHS]
    for j, dpd in enumerate(ramp_dpds):
        idx = default_start_idx - _RAMP_MONTHS + j
        rows.append(_row(
            loan_id, segment, idx, ead, dpd, collateral_type, collateral_value,
            0.0, 0.0, 0.0, False, False, market_price, credit_spread_bps, pre_default_pd,
        ))

    if status == DefaultStatus.cured:
        rows += _cured_rows(
            loan_id, segment, default_start_idx, ead, collateral_type, collateral_value,
            market_price, credit_spread_bps, pre_default_pd, cure_decline_months, rng,
        )
    elif status == DefaultStatus.open:
        rows += _open_rows(
            loan_id, segment, default_start_idx, post_months, ead, collateral_type, collateral_value,
            net_collateral, coll_recovery_rate_range, cfg, market_price, credit_spread_bps, pre_default_pd, rng,
        )
    else:
        rows += _completed_rows(
            loan_id, segment, default_start_idx, post_months, ead, collateral_type, collateral_value,
            net_collateral, coll_recovery_rate_range, cfg, market_price, credit_spread_bps, pre_default_pd,
            rng, write_off=(status == DefaultStatus.written_off),
        )

    return rows


def generate_monthly_panel(
    loans_per_segment: int = LOANS_PER_SEGMENT,
    seed: int | None = 13,
    segments: list[SampleSegment] | None = None,
) -> pd.DataFrame:
    rng = random.Random(seed)
    target_segments = segments if segments is not None else list(SampleSegment)
    rows: list[dict] = []
    index = 1
    for segment in target_segments:
        for _ in range(loans_per_segment):
            rows.extend(_generate_loan_panel(index, segment, rng))
            index += 1

    df = pd.DataFrame(rows)
    return df.sort_values(["loan_id", "observation_month"]).reset_index(drop=True)
