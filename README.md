# LGD Estimator

[![CI/CD](https://github.com/dillonsnyman1/lgd-estimator/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/dillonsnyman1/lgd-estimator/actions/workflows/ci-cd.yml)

A full-stack demo that walks through an LGD model-development pipeline as a
six-step wizard: upload a raw monthly loan-panel, construct default episodes
and recovery cash flows from it, calculate Loss Given Default under three
complementary approaches (workout / market / implied-market), review vintage
and stability diagnostics, calibrate a downturn multiplier, and export the
final scored loan book with a full audit trail.

| Step | Page | What it does |
|---|---|---|
| 1 | Upload | Upload a monthly loan-panel CSV, or load the bundled sample panel |
| 2 | Default Construction | Detect default episodes and reconstruct recovery cash flows from the panel |
| 3 | LGD Calculation | Set methodology, weighting, discount rate, open-default method, haircuts; view results |
| 4 | Vintage & Stability | Default-cohort trends, outcome-probability calibration, predicted-vs-realized LGD |
| 5 | Downturn Calibration | Derive (or manually set) the IRB downturn multiplier from stress vs benign vintages |
| 6 | Report | Final assumptions, summary, full audit trail, CSV export of scored loans |

Open defaults - those still in the workout process - can be handled via two
selectable methods: ELBE (Expected Loss Best Estimate), which combines partial
recoveries to date with a model estimate of future collateral recovery, or a
probability-weighted outcome method that calibrates P(write-off), P(cure) and
P(resolution) from completed same-segment loans and computes a forecasted LGD
via the law of total expectation.

Portfolio and segment LGDs can be aggregated as either EAD-weighted averages
(appropriate for IFRS 9 expected credit loss) or simple number-weighted averages
(required for IRB under CRR Article 181). Vintage analysis tracks LGD and default
status mix by cohort year, and the outcome probability panel shows the per-segment
calibration used by the probability-weighted method.

- **Backend**: Python + FastAPI - monthly-panel ingestion, default-episode
  construction, the LGD engine (open-default methods, vintage analysis,
  downturn calibration, two-pass portfolio processing), and an in-memory
  session store between wizard steps
- **Frontend**: React + Vite + TypeScript wizard (panel upload, default
  construction summary, LGD calculation dashboard with summary cards/charts/
  loan table, vintage & stability panel, downturn calibration panel, final
  report with audit trail and CSV export)

> **Disclaimer**: This is a simplified, illustrative implementation built for
> portfolio purposes. It is **not** a production-grade credit risk model and
> should not be used for regulatory reporting or capital allocation. All data
> is synthetic.

---

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the full methodology reference,
including all formulas and data field definitions. The key concepts are
summarised below.

### Default status

Each loan is classified into one of four statuses that determine how its LGD
is computed:

| Status | Description |
|---|---|
| `resolved` | Workout is complete; final actual cash flows are used |
| `written_off` | Removed from books; actual pre-write-off recoveries are used |
| `open` | Still in workout; ELBE or probability-weighted method is applied (see below) |
| `cured` | Returned to performing; assigned the cure LGD assumption |

### Collateral haircuts

Gross collateral value is reduced by a type-specific haircut before being used
in the workout calculation. Haircuts are configurable and default to:

| Collateral type | Default haircut |
|---|---|
| Residential real estate (RRE) | 20% |
| Commercial real estate (CRE) | 40% |
| Financial collateral | 15% |
| Other physical | 50% |

Net collateral value = `collateral_value * (1 - haircut)`.

### Workout LGD (resolved and written-off)

For loans with a completed workout, LGD is computed from the actual cash flows:

```
discount_factor = 1 / (1 + r)^t
net_recovery    = max(0, (gross_recovered - recovery_costs) * discount_factor)
lgd_workout     = max(0, min(1, 1 - net_recovery / EAD))
```

where `r` is the discount rate and `t` is `time_in_default_years`.

### Open defaults: method selector

Two methods are available for open (in-workout) defaults. Both can be selected
interactively. Market and implied-market figures are always computed for comparison
regardless of which method is selected.

#### ELBE (Expected Loss Best Estimate)

Open defaults have an incomplete cash flow history, so a two-step ELBE is
used when this method is selected:

**Step 1 - partial net recovery to date:**

```
d_partial      = 1 / (1 + r)^t_current
gross_to_date  = collateral_recovered + non_collateral_recovered
partial_net    = max(0, (gross_to_date - recovery_costs) * d_partial)
```

**Step 2 - estimated future collateral recovery:**

```
remaining_net_coll         = max(0, net_collateral_value - collateral_recovered)
estimated_future_gross     = remaining_net_coll * expected_remaining_recovery_rate
total_horizon              = t_current + expected_additional_years_open
d_future                   = 1 / (1 + r)^total_horizon
estimated_future_discounted = estimated_future_gross * d_future
```

**ELBE:**

```
total_net = partial_net + estimated_future_discounted
elbe      = max(0, min(1, 1 - total_net / EAD))
```

`expected_remaining_recovery_rate` and `expected_additional_years_open` are
configurable assumptions (defaults: 75% and 1.5 years).

#### Probability-Weighted Outcome Method

Calibrates three outcome probabilities from completed loans in the same segment
(resolved, written-off, cured) and applies the law of total expectation:

```
LGD = P(resolved) x LGD|resolved
    + P(written_off) x LGD|written_off
    + P(cured) x cure_lgd
```

The conditional LGDs (LGD given each outcome) are also measured from the same
completed-loan cohort. If fewer than five completed loans exist for a segment, the
engine falls back to portfolio-wide probabilities. This method produces a
"forecasted completed LGD" - identical to the actual observed LGD for resolved and
written-off loans, and an estimated figure for open loans still in workout.

The outcome probability panel in the dashboard shows the per-segment calibration
(P(res), P(WO), P(cure), LGD|res, LGD|WO and n) used in the calculation.

### Market-based LGD

Uses the secondary market price observed at the time of default:

```
lgd_market = max(0, min(1, 1 - market_price_at_default))
```

### Implied-market LGD

Extracts LGD from the credit spread and a market-implied PD:

```
lgd_implied_market = max(0, min(1, credit_spread_bps / 10000 / pre_default_pd))
```

### Cure LGD

Cured loans (those that returned to performing) are assigned a single
configurable LGD (default 5%). This reflects the residual loss from the
default episode rather than a full workout figure.

### Downturn adjustment (IRB)

When enabled, a multiplier is applied to the selected LGD to produce a
downturn LGD suitable for IRB capital calculations:

```
lgd_final = min(1, lgd_selected * downturn_multiplier)
```

The multiplier is configurable (default 1.25; range 1.0-3.0).

### Vintage analysis

Defaults are grouped by cohort year (`default_year`, derived from the month a
default episode started). The vintage chart shows the default count by status
(resolved, written-off, cured, open) alongside the cohort average LGD for each
year. This is a standard IRB model validation diagnostic for identifying LGD
drift or seasoning effects across origination cohorts.

### Downturn multiplier calibration

The downturn multiplier can be derived directly from the vintage data instead
of entered manually: pick one or more "stress" (higher-LGD) vintage years and
one or more "benign" (lower-LGD) vintage years, and the multiplier is computed
as the ratio of their weighted-average LGDs, clamped to [1.0, 3.0]:

```
derived_multiplier = clamp(avg_lgd(stress_years) / avg_lgd(benign_years), 1.0, 3.0)
```

Calibration always runs against the pre-downturn LGD view, regardless of
whether a downturn multiplier is already applied in the current assumptions,
so an already-stressed figure can't distort the stress-vs-benign comparison.

### Portfolio aggregation and weighting

Two averaging conventions are supported, selectable in the UI:

| Method | Formula | Use case |
|---|---|---|
| EAD-weighted | `sum(lgd_i * EAD_i) / sum(EAD_i)` | IFRS 9 ECL / portfolio EL |
| Number-weighted | `sum(lgd_i) / n` | IRB - CRR Art. 181 default-weighted |

CRR Article 181(1)(a) requires IRB LGD to be "default-weighted" (each defaulted
obligor counted equally, regardless of exposure size). EAD-weighting is appropriate
when the quantity of interest is the loss rate on the total outstanding balance.

The weighting selection affects portfolio and segment average LGDs, vintage LGDs,
and the conditional LGDs calibrated by the probability-weighted open-default method.
Expected loss (`lgd_final * EAD`) is always a monetary sum and is unaffected.

---

## Project Structure

```
lgd-estimator/
├── backend/          # FastAPI app: panel ingestion, default-episode construction,
│                     # the LGD engine (ELBE, probability-weighted, downturn
│                     # calibration), synthetic panel generator, tests
├── frontend/         # React + Vite + TypeScript wizard
├── infra/            # Terraform: Lambda, API Gateway, CloudFront, S3
└── METHODOLOGY.md    # Full methodology reference
```

---

## Running Locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

Run the test suite:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:5173` and expects the backend API at
`http://localhost:8000`.

---

## API Endpoints

All endpoints take and return JSON (the upload endpoint is multipart/form-data).
Each step's `data_id` is passed forward to the next step's request body.

| Method | Path | Request body | Description |
|---|---|---|---|
| `POST` | `/api/panel/upload` | multipart CSV file | Uploads a monthly loan-panel CSV; validates required columns, stores it, returns a profile |
| `POST` | `/api/panel/load-sample` | - | Loads the bundled sample monthly panel; same response shape as upload |
| `POST` | `/api/panel/construct-defaults` | `{ data_id }` | Detects default episodes from the panel, reconstructs recovery cash flows, returns episode list + status counts |
| `POST` | `/api/lgd/calculate` | `{ data_id, assumptions }` | Runs the LGD engine over the constructed loans for the given assumptions, returns the full portfolio result |
| `POST` | `/api/lgd/downturn-calibration` | `{ data_id, assumptions, stress_years, benign_years }` | Derives a downturn multiplier from the LGD of the selected stress vs benign default vintages |

`assumptions` is the same `LgdAssumptions` object across `/api/lgd/calculate`
and `/api/lgd/downturn-calibration`:

| Field | Default | Description |
|---|---|---|
| `methodology` | `workout` | Primary LGD estimation approach (`workout`, `market`, `implied_market`) |
| `open_default_method` | `elbe` | Method for open (in-workout) defaults (`elbe`, `probability_weighted`) |
| `weighting_method` | `number_weighted` | LGD averaging convention (`ead_weighted`, `number_weighted`) |
| `discount_rate` | `0.05` | Discount rate applied to cash flows in the workout calculation |
| `downturn_enabled` | `false` | Whether to apply the downturn LGD multiplier |
| `downturn_multiplier` | `1.25` | Multiplier applied to LGD when downturn is enabled (1.0-3.0) |
| `haircut_rre` | `0.20` | Haircut applied to residential real estate collateral |
| `haircut_cre` | `0.40` | Haircut applied to commercial real estate collateral |
| `haircut_financial` | `0.15` | Haircut applied to financial collateral |
| `haircut_other_physical` | `0.50` | Haircut applied to other physical collateral |
| `cure_lgd_method` | `fixed` | `fixed`: use `cure_lgd`; `calculated`: derive from actual recovery cash flows |
| `cure_lgd` | `0.05` | LGD assigned to cured exposures when `cure_lgd_method=fixed` |
| `expected_remaining_recovery_rate` | `0.75` | Fraction of remaining net collateral expected to be recovered (ELBE only) |
| `expected_additional_years_open` | `1.5` | Expected further workout duration for open defaults (ELBE only) |

Data uploaded via `/api/panel/upload` or `/api/panel/construct-defaults` is
held in an in-memory session store, keyed by `data_id` (see
[Deployment](#deployment) below) - it is not persisted to a database or disk.

### CSV Format

The panel CSV is a raw loan-month tape: **one row per loan per month**, not
one row per default. Required columns:

```
loan_id, segment, observation_month, outstanding_balance, dpd,
collateral_type, collateral_value, cash_received_collateral,
cash_received_other, recovery_cost_incurred, default_flag, write_off_flag
```

Three further columns are read for every loan's pre-default snapshot
(the row immediately before its default episode starts) but are not enforced
at upload time, so a malformed or missing value only surfaces as an error
once you run default construction:

```
market_price, credit_spread_bps, pre_default_pd
```

| Column | Type | Notes |
|---|---|---|
| `loan_id` | string | Join key across months |
| `segment` | string | Free text - any label, not restricted to a fixed taxonomy |
| `observation_month` | `YYYY-MM` | Panel time axis |
| `outstanding_balance` | float ≥0 | Drives `exposure_at_default` and episode-end detection |
| `dpd` | int ≥0 | Days past due - informational/trajectory only, not used to detect default |
| `collateral_type` | enum | `none`, `residential_real_estate`, `commercial_real_estate`, `financial_collateral`, `other_physical` |
| `collateral_value` | float ≥0 | Snapshot collateral value for that month |
| `cash_received_collateral` | float ≥0 | Incremental collateral-liquidation cash that month |
| `cash_received_other` | float ≥0 | Incremental non-collateral recovery cash that month |
| `recovery_cost_incurred` | float ≥0 | Incremental legal/admin/enforcement cost that month |
| `default_flag` | bool | Authoritative default-episode signal - the sole trigger for episode entry and cure |
| `write_off_flag` | bool | Authoritative write-off signal - the sole trigger for write-off |
| `market_price` | 0-1 | Pre-default secondary market price (for `market` methodology) |
| `credit_spread_bps` | float ≥0 | Pre-default credit spread (for `implied_market` methodology) |
| `pre_default_pd` | (0,1] | Pre-default market-implied PD (for `implied_market` methodology) |

`default_flag` and `write_off_flag` are treated as fully authoritative - there
is no DPD-threshold inference and no cure-confirmation window. See
[METHODOLOGY.md](METHODOLOGY.md) Section 2 for exactly how episodes are
detected from these two flags. The bundled sample panel
(`backend/app/sample_data/sample_monthly_panel.csv`, loadable from the
dashboard's Upload step) is a working format reference.

---

## Deployment

The app deploys to AWS with no custom domain - CloudFront serves the frontend,
and the FastAPI backend runs on Lambda (as an arm64 container image, for pandas
compatibility) behind an API Gateway HTTP API. Everything is defined in
Terraform under [`infra/`](infra/), and a GitHub Actions workflow
([`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)) runs the backend
tests and frontend build on every push/PR, then - if those pass - builds the
backend image, applies the Terraform config, and publishes the frontend to
S3/CloudFront. The deploy job runs automatically on every push to `main`, or on
demand via the Actions tab.

> **Live demo**: [link] - try uploading your own monthly loan-panel CSV or
> adjusting the LGD assumptions and collateral haircuts.
>
> The backend keeps an in-memory session store between wizard steps: each
> uploaded panel and its constructed loans are held server-side, keyed by a
> generated `data_id`, for up to one hour of inactivity before being evicted.
> Nothing is written to a database or to disk, and each `data_id` is only ever
> returned to the request that created it, so concurrent users' data does not
> overlap - but on a multi-instance Lambda deployment, a `data_id` issued by
> one warm instance won't resolve on another, so don't expect a session to
> survive indefinitely under real concurrent load.
