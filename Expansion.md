# Expansion Roadmap

Potential extensions to the LGD Estimator, grouped by theme. Each section
describes what the feature would add and what it would require technically.

---

## 1. Vintage analysis - IMPLEMENTED

Vintage analysis is now live: the dashboard shows a ComposedChart with stacked
status bars (resolved/WO/cured/open) by default year and a LGD line overlay.
The outcome probability table shows per-segment P(resolved), P(WO), P(cured)
and conditional LGDs calibrated from completed loans.

---

## 2. Backtesting and calibration

Compare model-estimated LGD against observed realised LGD for the resolved
subset. For workout LGD this is straightforward - the estimated figure equals
the realised figure by construction, but backtesting becomes meaningful once
a predictive LGD model (e.g. a regression on collateral coverage, segment and
seasoning) is introduced and its out-of-sample predictions need to be tested
against actuals.

**What it adds:** Calibration plots (predicted vs. realised LGD by decile),
mean absolute error, and a Brier-score-style decomposition into calibration
and refinement components. These are the standard metrics used in IRB model
validation (EBA GL/2017/16).

**What it requires:** A predictive LGD estimate separate from the workout
calculation - for example, a linear regression or gradient boosted model
trained on resolved defaults and applied to open ones.

---

## 2b. Regression-based outcome probability prediction

The current probability-weighted open-default method uses flat historical frequencies
(P(WO) = count(WO) / count(completed) per segment). A natural extension is to use a
statistical model to predict the probability of each outcome from loan-level features:

**Model inputs:** seasoning (time_in_default_years), collateral coverage (net collateral
/ EAD), segment, collateral type, EAD, partial recovery rate to date (cash received /
EAD so far).

**Model form:** multinomial logistic regression or gradient boosted classifier, with
three outcome classes: {resolved, written_off, cured}. Estimated coefficients would
replace the flat frequency weights used in the current implementation.

**What it adds:** LGD estimates for open defaults that are sensitive to the individual
loan's characteristics - a heavily collateralised loan with 40% partial recovery in
year 1 would get a higher P(resolved) and lower P(WO) than a fully unsecured loan
with near-zero recovery in year 3. The current tool treats all open loans in the same
segment identically regardless of their partial recovery progress.

**What it requires:** Sufficient historical data to train the model (at minimum
~200-300 resolved defaults per segment); scikit-learn or statsmodels in the backend;
a new panel in the frontend to show which features are driving the outcome probabilities
for each open loan.

---

## 3. LGD model validation metrics

Extend the methodology comparison to include formal validation statistics
beyond the EAD-weighted average:

- **Mean absolute error** against observed LGD (for resolved loans)
- **Brier score** (mean squared error between predicted and realised LGD)
- **Spearman rank correlation** between predicted and realised LGD by decile
- **t-test / Wilcoxon test** for bias (whether the model systematically over-
  or under-estimates)
- **Concentration ratio** - does the model correctly rank order loans by
  loss severity?

**What it adds:** A validation panel showing these statistics for whichever
methodology is selected, calculated on the resolved subset of the portfolio.
Useful for illustrating how IRB banks validate LGD models under EBA guidelines.

**What it requires:** Only backend changes - these are all computed from the
existing fields (`lgd_final` vs. a realised LGD field, or comparing workout
LGD against market LGD as a proxy for an independent estimate).

---

## 4. Multi-period / lifetime LGD for IFRS 9

Under IFRS 9, the ECL for a Stage 3 (credit-impaired) exposure uses the
lifetime LGD rather than a point-in-time 12-month figure. Lifetime LGD
accounts for the time value of money over the expected remaining workout
duration and can vary significantly from the current-period workout LGD,
particularly for long-duration exposures (mortgages, infrastructure loans).

**What it adds:** A lifetime LGD field computed as the present value of all
future expected cash flows over the full remaining workout horizon, compared
against the current-period workout LGD. The difference between the two
illustrates the IFRS 9 vs. IRB LGD gap that banks need to reconcile in their
regulatory reporting.

**What it requires:** A probability-of-resolution schedule (i.e. the expected
cash flow timing over the workout horizon) rather than a single discount
point. The ELBE framework already does a two-step version of this; extending
it to a multi-period schedule is a natural progression.

---

## 5. Regulatory floor comparison (CRR Art. 181)

Under the Capital Requirements Regulation, IRB LGD estimates are subject to
regulatory floors:

| Exposure type | LGD floor (secured) | LGD floor (unsecured) |
|---|---|---|
| Retail mortgage | 10% (RRE), 15% (CRE) | 30% |
| Retail other | - | 30% |
| Corporate / SME | - | 45% |

**What it adds:** A floored LGD column alongside the model LGD, showing how
many loans are constrained by the regulatory floor and by how much. A summary
panel showing the portfolio RWA impact of applying the floors vs. using raw
model estimates.

**What it requires:** Floor logic in the engine (trivial) and a new column in
the loan table and summary cards. The segment mapping to exposure class is
already present.

---

## 6. Concentration analysis

The current tool reports EAD-weighted average LGD per segment but does not
show how concentrated the loss exposure is - i.e. whether the portfolio LGD
is driven by a small number of large exposures with extreme LGDs.

**What it adds:**

- A Lorenz curve of expected loss (ranked by LGD, cumulative EL vs. cumulative
  EAD) showing how skewed the loss distribution is
- A top-N concentration table (largest N expected losses as a fraction of
  total EL)
- Herfindahl-Hirschman Index (HHI) for expected loss concentration by segment

**What it requires:** Sorting and cumulative aggregation on the loan list;
a new chart component. No changes to the engine.

---

## 7. Collateral coverage segmentation

Replace the current flat collateral-type breakdown with a two-dimensional
view: collateral type crossed with net collateral coverage (net collateral /
EAD). LGD is almost always better predicted by how much collateral there is
relative to the exposure than by the type alone.

**What it adds:** A heat map of average LGD by coverage bucket (e.g.
0-25%, 25-50%, 50-75%, 75-100%, >100%) crossed with collateral type. This
is the standard segmentation used when constructing LGD models for IRB
applications.

**What it requires:** A coverage computation (already in `net_collateral_value
/ exposure_at_default`) and a bucketing step in the backend summary. The
coverage field is already available on `ProcessedLoan`.

---

## 8. Scenario / sensitivity analysis

Allow users to define a stress scenario (e.g. "collateral values fall 30%,
workout durations extend by 2 years, recovery costs rise 10%") and see the
instantaneous LGD impact across the portfolio without having to manually
adjust each assumption individually.

**What it adds:** A scenario panel with pre-defined scenarios (base, mild
stress, severe stress) and a custom scenario builder. Results shown as a
comparison table: base LGD vs. stressed LGD vs. downturn LGD, by segment.

**What it requires:** A scenario object that maps to a set of assumption
overrides; the engine is already parameterised so no calculation changes are
needed. The frontend would need a new panel and a side-by-side comparison view.

---

## 9. Recovery timing decomposition

The current workout LGD applies a single discount factor at the workout
completion date. In practice, recoveries arrive over time - partial payments
during the workout, followed by a large collateral realisation near the end.
Discounting a lump sum at the resolution date slightly overstates the present
value of early recoveries.

**What it adds:** A chart showing cumulative discounted recovery over time
for a selected loan, illustrating how the discount drag builds up over long
workouts, plus a per-loan LGD figure computed by discounting each month's
recovery individually rather than the episode's gross total.

**What it requires:** Less than originally scoped here - the monthly panel
ingestion (see METHODOLOGY.md Section 2) already provides exactly this as
row-per-month incremental cash flows (`cash_received_collateral`,
`cash_received_other`, `recovery_cost_incurred` per month); `loans_from_panel()`
currently sums these to a single episode total before they reach the engine.
The remaining work is in the engine, not the data model: `_lgd_workout_resolved`
would need the per-month rows (not just the summed `Loan` fields) to discount
each month's net cash flow back to the default date individually and sum the
discounted amounts, rather than discounting one lump sum at `time_in_default_years`.

---

## 10. Batch portfolio comparison

Allow two portfolios to be uploaded side by side (e.g. two different
origination vintages, or the same portfolio before and after a policy change)
and compare their LGD distributions, segment breakdowns and resolution rates.

**What it adds:** A diff view showing delta LGD by segment, a chart of the
two LGD distributions overlaid, and a summary table of count/EAD/EL differences.
Useful for illustrating how portfolio composition changes affect aggregate LGD.

**What it requires:** A second upload endpoint (or a multi-file upload flow),
state management for two portfolios in the frontend, and a set of comparison
components. The engine processes each independently; the comparison logic is
purely in the aggregation layer.
