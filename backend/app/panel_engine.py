"""Construct default episodes and LGD-engine-ready Loan records from a raw monthly panel.

Pure function, no FastAPI dependency - independently unit-testable.

A loan's `default_flag` is the authoritative signal for "in default this month"
(see app/panel_generator.py and the panel CSV schema); this module never infers
default status from `dpd`. For each loan, one or more non-overlapping default
episodes are detected by scanning its rows in chronological order:

  - An episode starts at the first row where `default_flag` turns `True`.
  - It ends, in priority order, at the first row where:
      1. `write_off_flag` is `True`              -> outcome = written_off
      2. `outstanding_balance` reaches 0          -> outcome = resolved
      3. `default_flag` turns back to `False`     -> outcome = cured
         (episode end is the prior row, the last one with `default_flag=True`)
  - If none of these trigger before the panel's last observed row, the
    episode is still `open`.

  `default_flag` is treated as fully authoritative for both entry and exit -
  no confirmation window is applied to cures. A loan tape's default flag is
  assumed to already reflect whatever definition-of-default logic (DPD
  triggers, unlikeliness-to-pay, etc.) the institution uses upstream; this
  module's job is only to turn that flag into episodes, not to second-guess it.

A loan can cure and default again later (re-default): each non-overlapping
episode becomes its own `Loan` record, with synthesized ids (`L00042-1`,
`L00042-2`, ...) when a loan has more than one episode, so `loan_id` stays
unique for the LGD engine and loan table.
"""

import pandas as pd

from app.models import CollateralType, DefaultEpisode, DefaultStatus, Loan

_OUTCOME_TO_STATUS = {
    "written_off": DefaultStatus.written_off,
    "resolved": DefaultStatus.resolved,
    "cured": DefaultStatus.cured,
    "open": DefaultStatus.open,
}


def _detect_episodes(rows: list[dict]) -> list[tuple[int, int, str]]:
    """Returns a list of (start_idx, end_idx, outcome) into `rows`, in order."""
    episodes: list[tuple[int, int, str]] = []
    n = len(rows)
    i = 0
    while i < n:
        if not rows[i]["default_flag"]:
            i += 1
            continue

        start = i
        end = n - 1
        outcome = "open"
        j = i
        while j < n:
            row = rows[j]
            if row["write_off_flag"]:
                end, outcome = j, "written_off"
                break
            if row["outstanding_balance"] <= 0:
                end, outcome = j, "resolved"
                break
            if not row["default_flag"]:
                end, outcome = j - 1, "cured"
                break
            j += 1
        else:
            # Reached the end of the panel without a trigger - still open.
            outcome = "open"

        episodes.append((start, end, outcome))
        i = end + 1

    return episodes


def loans_from_panel(df: pd.DataFrame) -> tuple[list[Loan], list[DefaultEpisode]]:
    df = df.sort_values(["loan_id", "observation_month"]).reset_index(drop=True)

    loans: list[Loan] = []
    episodes_out: list[DefaultEpisode] = []

    for raw_loan_id, group in df.groupby("loan_id", sort=False):
        rows = group.to_dict("records")
        episodes = _detect_episodes(rows)
        multi = len(episodes) > 1

        for ep_num, (start, end, outcome) in enumerate(episodes, start=1):
            episode_rows = rows[start:end + 1]
            start_row, end_row = rows[start], rows[end]
            pre_row = rows[max(start - 1, 0)]

            months_elapsed = max(1, end - start)
            collateral_recovered = round(sum(r["cash_received_collateral"] for r in episode_rows), 2)
            non_collateral_recovered = round(sum(r["cash_received_other"] for r in episode_rows), 2)
            recovery_costs = round(sum(r["recovery_cost_incurred"] for r in episode_rows), 2)

            synthetic_id = f"{raw_loan_id}-{ep_num}" if multi else str(raw_loan_id)

            loan = Loan(
                loan_id=synthetic_id,
                segment=str(start_row["segment"]),
                default_status=_OUTCOME_TO_STATUS[outcome],
                collateral_type=CollateralType(start_row["collateral_type"]),
                collateral_value=round(float(start_row["collateral_value"]), 2),
                exposure_at_default=max(0.01, round(float(start_row["outstanding_balance"]), 2)),
                collateral_recovered=collateral_recovered,
                non_collateral_recovered=non_collateral_recovered,
                recovery_costs=recovery_costs,
                time_in_default_years=round(months_elapsed / 12.0, 4),
                default_year=int(str(start_row["observation_month"])[:4]),
                market_price_at_default=float(pre_row["market_price"]),
                credit_spread_bps=float(pre_row["credit_spread_bps"]),
                pre_default_pd=float(pre_row["pre_default_pd"]),
            )
            loans.append(loan)

            episodes_out.append(DefaultEpisode(
                loan_id=synthetic_id,
                raw_loan_id=str(raw_loan_id),
                segment=str(start_row["segment"]),
                default_status=_OUTCOME_TO_STATUS[outcome],
                start_month=str(start_row["observation_month"]),
                end_month=str(end_row["observation_month"]),
                row_count=len(episode_rows),
                exposure_at_default=loan.exposure_at_default,
            ))

    return loans, episodes_out
