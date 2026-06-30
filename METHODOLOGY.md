# LGD Estimator - Methodology Reference

This document describes the full methodology implemented in this tool: how defaulted
loans are classified, how LGD is estimated under each method, how open (in-workout)
defaults are handled via two alternative approaches, and how the vintage analysis and
outcome probability calibration work. Worked numerical examples and diagrams are
included throughout to illustrate each concept. Regulatory and academic references
follow each section.

---

## 1. Background: What is LGD?

Loss Given Default (LGD) is the fraction of the Exposure at Default (EAD) that a
lender ultimately loses when an obligor defaults. It is often expressed alongside its
complement, the Recovery Rate (RR = 1 - LGD).

Together with Probability of Default (PD) and EAD, LGD is one of the three core
credit risk parameters:

```
Expected Loss (EL) = PD x LGD x EAD
```

Under the Basel Internal Ratings-Based (IRB) approach, LGD also feeds directly into
the Vasicek capital formula that computes Risk-Weighted Assets (RWA) and Pillar 1
capital requirements.

### LGD in context

```
                Performing          Default           Resolution
                   loans              event
                    |                  |
  ==================|==================|================================
                    |                  |
  Loan outstanding  |     EAD          |
  ==================|==================|
                    |                  |
  Cash received:    |                  |-->  Collateral proceeds
                    |                  |-->  Debtor payments
                    |                  |-->  Guarantees called
                    |                  |-->  Debt sale proceeds
                    |                  |
  Costs incurred:   |                  |--> Legal fees
                    |                  |--> Administration
                    |                  |--> Valuation/enforcement
                    |                  |
  Net recovery      |                  |= PV(cash received - costs)
  LGD               |                  |= 1 - net_recovery / EAD
```

### Why LGD distributions are bimodal

Empirical LGD distributions are typically bimodal - concentrated near 0% (near-full
recovery) and near 100% (near-total loss), with relatively few cases in the middle.
This reflects the binary nature of collateral: either it covers the exposure or it
does not. For secured loans, most cases cluster near 0-30%; for unsecured loans,
near 60-100%.

```
  Frequency
      |
   ** |                                           ***
  *   |                                          *   *
 *    |                                         *     *
*     |                                        *       *
------+---------------------------------------------- LGD
      0%                                             100%

      (typical bimodal shape: well-secured portfolio)
```

This bimodality means mean LGD alone is an incomplete summary statistic; the full
distribution matters for stress testing and tail risk assessment.

**Key references:**
- Schuermann, T. (2004). "What Do We Know About Loss Given Default?" Wharton
  Financial Institutions Center Working Paper 04-01.
- Altman, E.I., Resti, A., and Sironi, A. (2004). "Default Recovery Rates in Credit
  Risk Modelling: A Review of the Literature and Empirical Evidence." Economic Notes,
  33(2): 183-208.
- EBA (2017). "Guidelines on PD estimation, LGD estimation and the treatment of
  defaulted exposures." EBA/GL/2017/16.

---

## 2. Default Episode Construction and Status Classification

The tool ingests a raw **monthly loan-panel** - one row per loan per month -
rather than a pre-summarised default record. Before any LGD calculation runs,
each loan's panel rows are scanned to detect default episodes and classify
their outcome. This section describes that construction step; Sections 3
onwards describe the LGD calculation that runs on its output.

### Episode detection algorithm

Two columns in the panel drive the entire process and are treated as fully
authoritative - the tool does not infer or smooth either one:

- `default_flag` - whether the loan is in default that month
- `write_off_flag` - whether the bank wrote the loan off that month

For each loan, rows are scanned in chronological order. An episode **starts**
at the first row where `default_flag` is `True`. From there, the loan's
subsequent rows are checked, in priority order, for the first row that
matches one of:

1. `write_off_flag = True` → outcome `written_off`, episode ends at this row
2. `outstanding_balance <= 0` → outcome `resolved`, episode ends at this row
3. `default_flag` reverts to `False` → outcome `cured`, episode ends at the
   *previous* row (the last one with `default_flag = True`)

If none of these trigger before the panel's last observed row for that loan,
the episode is still `open` at that row.

```
  default_flag:   F  F  T  T  T  T  T  F  F   <- cured: ends at the 5th T
  default_flag:   F  F  T  T  T  T  T  T  T   <- still open at panel end
  write_off_flag:                      T      <- written_off (checked first)
  balance:        ...  120  60  0             <- resolved (balance hits 0)
```

There is no DPD threshold and no cure-confirmation window: whatever
definition-of-default logic (DPD triggers, unlikeliness-to-pay, etc.)
produced the `default_flag` column is assumed to already be correct and
final upstream. `dpd` is still carried through the pipeline, but purely as
trajectory/charting data - it never triggers or confirms an episode boundary.

### Re-default and synthetic loan IDs

A loan can cure and default again later. Each non-overlapping episode for a
given raw `loan_id` becomes its own `Loan` record passed to the LGD engine.
If a loan has more than one episode, its episodes are given synthesized IDs
- `L00042-1`, `L00042-2`, ... - so `loan_id` stays unique downstream; a
loan with exactly one episode keeps its original ID unchanged. The Default
Construction step in the wizard reports both the raw loan count and the
resulting episode count (e.g. "200 raw loans → 187 default episodes") so
this cardinality change is never silent.

### Recovery cash flow reconstruction

Once an episode's row range is known, its `Loan` fields are built by
aggregating across that range:

| `Loan` field | Derivation |
|---|---|
| `exposure_at_default` | `outstanding_balance` on the episode's first row |
| `default_year` | Calendar year of `observation_month` on the episode's first row |
| `collateral_recovered` | Sum of `cash_received_collateral` across the episode's rows |
| `non_collateral_recovered` | Sum of `cash_received_other` across the episode's rows |
| `recovery_costs` | Sum of `recovery_cost_incurred` across the episode's rows |
| `time_in_default_years` | `max(1, end_row - start_row) / 12`, floored at one month so same-month cures still satisfy the engine's `time_in_default_years > 0` constraint |
| `collateral_type`, `collateral_value` | Taken from the episode's first row |
| `market_price_at_default`, `credit_spread_bps`, `pre_default_pd` | Taken from the row immediately *before* the episode starts (the loan's last performing observation) |

Loans whose `default_flag` is `False` for their entire panel history never
enter this process at all - only rows belonging to a detected episode feed
into the LGD engine; performing-only exposures are excluded by construction.

### Status summary

| Status | Description | Recovery fields | LGD method |
|---|---|---|---|
| `resolved` | Workout complete - all cash flows received and case closed | Final actual totals | Selected methodology |
| `written_off` | Balance removed from the balance sheet | Final amounts received at or before write-off | Selected methodology |
| `open` | Still in workout - partial data only | Partial amounts to date | ELBE or probability-weighted (user choice) |
| `cured` | Returned to performing status | Minimal (mainly costs) | Cure LGD parameter |

### Default lifecycle

```
                 +-----------+
                 |  Default  |
                 |   event   |
                 +-----+-----+
                       |
         +-------------+-------------+
         |             |             |
         v             v             v
    +---------+   +---------+   +---------+
    |  Open   |   |  Cured  |   | Direct  |
    | workout |   | (perf.) |   |  W/O    |
    +----+----+   +---------+   +----+----+
         |        LGD = cure_lgd      |
         |                            |
    +----+----+                       |
    | Still   |                       |
    | open?   |                       |
    +----+----+                       |
         |                            |
    +----+-------------------+        |
    |    v                   |        |
    | Resolved         Written Off    |
    | (workout           (limited     |
    |  complete)          recovery)   |
    +--------+        +-------+-------+
             |                |
             +--------+-------+
                      |
              LGD via selected
               methodology
```

This classification is consistent with EBA/GL/2017/16 Section 6, which distinguishes
cure, resolution through workout, and write-off as distinct endpoints. Tracking
all four outcomes is essential for the probability-weighted method (Section 7.2).

---

## 3. Collateral Haircuts

Gross collateral value (the market value at default) is reduced by a type-specific
haircut before being used in any recovery calculation:

```
net_collateral_value = collateral_value x (1 - haircut)
```

### Default haircuts

| Collateral type | Default haircut | Rationale |
|---|---|---|
| Residential real estate (RRE) | 20% | Relatively liquid; strong legal enforceability |
| Commercial real estate (CRE) | 40% | Less liquid; forced-sale discounts significant; longer enforcement |
| Financial collateral | 15% | Mark-to-market assets; subject to market risk during enforcement |
| Other physical | 50% | Specialist assets; difficult to value and sell in distress |
| None | 100% | No collateral; full haircut (no collateral recovery) |

These are based on typical supervisory haircut ranges in CRR Article 224 and IRB
collateral eligibility rules (CRR Article 181).

### Example

```
  Loan:      EAD = £500,000
  Collateral: CRE property, gross value = £400,000
  CRE haircut: 40%

  Net collateral = £400,000 x (1 - 0.40) = £240,000
  Net collateral coverage = £240,000 / £500,000 = 48% of EAD

  -> Maximum possible collateral-based recovery: 48% of EAD
  -> Minimum LGD if full collateral recovered: 52% (non-collateral sources
     or over-recovery could reduce this further)
```

---

## 4. Workout LGD (Resolved and Written-Off Loans)

The workout methodology is the primary approach for IRB LGD estimation. It is grounded
in the discounted cash flow principle: the lender's loss is the difference between
EAD and the present value of all net recoveries.

### Formula

```
discount_factor = 1 / (1 + r)^t
gross_recovery  = collateral_recovered + non_collateral_recovered
net_recovery    = max(0, (gross_recovery - recovery_costs) x discount_factor)
lgd_workout     = max(0, min(1, 1 - net_recovery / EAD))
```

where `r` = discount rate, `t` = `time_in_default_years`.

### Timeline diagram

```
  t = 0 (default date)                    t = T (resolution)
  |                                              |
  |--------------workout period-----------------|
  |                                              |
  |                                     +--------+--------+
  |                                     | Cash flows      |
  |                                     | received at T:  |
  |                                     |                 |
  |                                     | Collateral: £X  |
  |                                     | Non-coll:   £Y  |
  |                                     | Costs:     -£Z  |
  |                                     |                 |
  |         PV = (X+Y-Z) / (1+r)^T <--- |                 |
  |                                                       |
  LGD = 1 - PV(net recovery) / EAD
```

### Worked example

```
  Loan:     EAD = £200,000, RRE collateral, 20% haircut
            time_in_default = 2.0 years, discount rate = 5%

  Recoveries:
    Collateral recovered:     £140,000  (property sold)
    Non-collateral recovered: £  8,000  (debtor payments)
    Recovery costs:           £  6,000  (legal, enforcement)

  Calculation:
    discount_factor = 1 / 1.05^2 = 0.9070
    gross = £140,000 + £8,000 = £148,000
    net_recovery = max(0, (£148,000 - £6,000) x 0.9070)
                 = £142,000 x 0.9070
                 = £128,794

    lgd_workout = 1 - £128,794 / £200,000 = 35.6%
```

### Why discounting matters

Cash received two years after default is worth less than immediate cash. At 5%:

```
  Year 0: £100 received -> PV = £100.00
  Year 1: £100 received -> PV = £ 95.24
  Year 2: £100 received -> PV = £ 90.70
  Year 3: £100 received -> PV = £ 86.38

  For a long workout (4 years), a £140k recovery is worth:
    PV = £140,000 / 1.05^4 = £115,152 (vs £140,000 at zero rate)
    -> Discount drag alone adds ~12% to LGD for a heavily recovered loan
```

EBA GL/2017/16 Section 7.2.3 requires discounting all cash flows to the default date.

### Cost deduction order

Costs are deducted before discounting - `(gross - costs) x discount_factor` - not
after. The alternative `gross x discount_factor - costs` would fail to discount the
costs themselves, understating the true loss from delayed enforcement.

### Written-off loans

Treated identically to resolved: recovery fields represent final actual amounts at
write-off date. Written-off loans typically produce high LGDs (70%+) because write-off
occurs after prolonged workout with minimal recovery, or when collateral is insufficient.

**References:**
- BCBS (2006). "Basel II: International Convergence of Capital Measurement and Capital
  Standards." Annex 5, paragraphs 468-473.
- EBA (2017). EBA/GL/2017/16, Section 7.2 ("Estimation of LGD").
- Altman, E.I. and Kalotay, E.A. (2014). "Ultimate Recovery Mixtures." Journal of
  Banking and Finance, 40: 116-129.

---

## 5. Market-Based LGD

The market-based approach uses the secondary market price of a defaulted loan or bond,
observed shortly after default (typically 30-90 days), as a market consensus estimate
of ultimate recovery value:

```
lgd_market = max(0, min(1, 1 - market_price_at_default))
```

### Why this works

Secondary market prices for defaulted debt embed:
1. The market's collective estimate of ultimate recovery amounts
2. Implicit discounting over the expected workout horizon
3. A risk premium for uncertainty about timing and outcome

The market-based approach is therefore forward-looking and risk-adjusted, rather than
a retrospective cash flow calculation.

### Example

```
  Corporate bond, EAD = £5,000,000
  Secondary market price 60 days after default: £0.58 per £1 face

  lgd_market = 1 - 0.58 = 0.42 = 42%

  Interpretation: market participants collectively expect to recover 58%
  of face value through the workout process, implying a 42% loss rate.
```

### Market price vs realised LGD

```
  Market price (60 days post-default)  vs  Realised workout LGD (at resolution)
  --------------------------------------------------------------------------------------
  Market embeds: - Expected recovery
                 - Time discount (implicit)   These are often close but not equal:
                 - Uncertainty premium        - Market price may be too high (optimism)
                                              - Or too low (distress sellers, illiquidity)
                                              - Workout LGD uses actual r and actual t
```

### Limitations

- Illiquid or unavailable for private loans (retail mortgages, SME bilateral facilities)
- Volatile in the weeks immediately after default
- Market prices include a risk premium, so market-implied LGD may exceed realised workout LGD

**References:**
- Altman, E.I. (1989). "Measuring Corporate Bond Mortality and Performance." Journal
  of Finance, 44(4): 909-922.
- Altman, E.I., Brady, B., Resti, A., and Sironi, A. (2005). "The Link between
  Default and Recovery Rates." Journal of Business, 78(6): 2203-2228.
- Gupton, G.M. (2005). "Advancing Loss Given Default Prediction Models." Economic
  Notes, 34(2): 185-230.

---

## 6. Implied-Market LGD

The implied-market approach extracts an LGD estimate from a bond's credit spread and
a market-implied PD, using the "credit triangle" relationship:

```
lgd_implied_market = max(0, min(1, credit_spread_bps / 10,000 / pre_default_pd))
```

### The credit triangle

Under simplified credit pricing models (Jarrow-Turnbull, Duffie-Singleton), a risky
bond spread over the risk-free rate compensates investors for expected credit loss:

```
      Credit spread
           |
           |   Spread = PD x LGD     (simplified, risk-neutral, continuous)
           |
           +--------> PD (probability of default)
           |
           +--------> LGD (loss given default)

  Rearranging:    LGD = Spread / PD
```

The formula converts the spread from basis points to a fraction:

```
  LGD = (credit_spread_bps / 10,000) / pre_default_pd
```

### Example

```
  Pre-default credit spread: 350 bps
  Market-implied PD:         5.0% (0.05)

  lgd_implied = (350 / 10,000) / 0.05
              = 0.035 / 0.05
              = 0.70 = 70%

  Interpretation: the market prices in a 70% loss rate given default, at a
  5% PD. If PD were 7%, implied LGD would be: 0.035/0.07 = 50%.
```

### Sensitivity to inputs

```
  Spread = 300 bps, varying PD:

  PD = 3%  ->  LGD = 0.03/0.03 = 100%  (implausibly high at low PD)
  PD = 5%  ->  LGD = 0.03/0.05 =  60%
  PD = 8%  ->  LGD = 0.03/0.08 = 37.5%
  PD = 12% ->  LGD = 0.03/0.12 =  25%

  Key insight: implied LGD is very sensitive to the PD input,
  especially at low PD levels.
```

### Limitations

- The approximation `spread = PD x LGD` holds only under specific model assumptions;
  in practice, spreads also include a liquidity premium, convexity adjustment, and
  risk premium
- Risk-neutral PDs are systematically higher than real-world (physical) PDs, which
  biases implied LGD downwards
- Pre-default inputs; applying them post-default introduces a look-ahead inconsistency

The implied-market method is best used as a cross-check against workout and market
approaches, not as a standalone estimate.

**References:**
- Duffie, D. and Singleton, K.J. (1999). "Modeling Term Structures of Defaultable
  Bonds." Review of Financial Studies, 12(4): 687-720.
- Jarrow, R. and Turnbull, S. (1995). "Pricing Derivatives on Financial Securities
  Subject to Credit Risk." Journal of Finance, 50(1): 53-85.
- O'Kane, D. (2008). "Modelling Single-Name and Multi-Name Credit Derivatives."
  Wiley Finance, Chapter 3.

---

## 7. Open (In-Workout) Default Estimation

Loans classified as `open` are still in the workout process: the final recovery
outcome is unknown. Two methods are available to forecast the final LGD. The selected
workout methodology (workout / market / implied-market) does not apply to open loans -
market and implied-market values are still computed from pre-default inputs and shown
in the methodology comparison chart as a cross-check, but `lgd_selected` always
uses the workout estimate.

---

### 7.1 ELBE (Expected Loss Best Estimate)

ELBE is the EBA's term for the best estimate of expected loss on a defaulted exposure
still in workout (EBA GL/2017/16, Section 7.3.2). It combines actual partial recoveries
to date with a forward-looking estimate of future collateral recovery.

#### Timeline

```
  t = 0 (default)       t = current        t = T (expected resolution)
  |                          |                       |
  |-------- elapsed -------->|                       |
  |                          |---expected future --->|
  |                          |
  |    Cash received so far: |     Remaining collateral to be realised:
  |    - Collateral: £C_1    |     - Remaining net coll x recovery_rate
  |    - Non-coll:   £N_1    |     -> discounted from T back to t=0
  |    - Costs:     -£K_1    |
  |                          |
  |    Discounted to t=0     |
  |    using elapsed time    |
```

#### Step 1 - Partial net recovery to date

```
  d_partial    = 1 / (1 + r)^t_current
  gross_to_date = collateral_recovered + non_collateral_recovered
  partial_net   = max(0, (gross_to_date - recovery_costs) x d_partial)
```

#### Step 2 - Estimated future collateral recovery

```
  remaining_net_coll          = max(0, net_collateral - collateral_recovered)
  estimated_future_gross      = remaining_net_coll x expected_remaining_recovery_rate
  total_horizon               = t_current + expected_additional_years_open
  d_future                    = 1 / (1 + r)^total_horizon
  estimated_future_discounted = estimated_future_gross x d_future
```

#### Step 3 - ELBE

```
  total_net = partial_net + estimated_future_discounted
  ELBE      = max(0, min(1, 1 - total_net / EAD))
```

#### Worked example

```
  Loan:     EAD = £300,000, RRE collateral, 20% haircut
            Gross collateral = £250,000 -> net collateral = £200,000
            t_current = 1.0 year, discount rate = 5%
            Assumptions: expected_recovery_rate = 75%, additional_years = 1.5

  Actual cash received to date:
    Collateral recovered:     £ 60,000
    Non-collateral recovered: £  5,000
    Recovery costs to date:   £  4,000

  Step 1 - Partial net recovery:
    d_partial = 1 / 1.05^1.0 = 0.9524
    partial_net = max(0, (60,000 + 5,000 - 4,000) x 0.9524)
               = 61,000 x 0.9524 = £58,096

  Step 2 - Estimated future collateral recovery:
    remaining_net_coll = max(0, 200,000 - 60,000) = £140,000
    estimated_future_gross = £140,000 x 0.75 = £105,000
    total_horizon = 1.0 + 1.5 = 2.5 years
    d_future = 1 / 1.05^2.5 = 0.8858
    estimated_future_discounted = £105,000 x 0.8858 = £93,009

  Step 3 - ELBE:
    total_net = £58,096 + £93,009 = £151,105
    ELBE = 1 - £151,105 / £300,000 = 49.6%

  Compare to partial-only estimate:
    lgd_partial_only = 1 - £58,096 / £300,000 = 80.6%
    -> ELBE is significantly lower, capturing the expected future recovery
       from the remaining £140k of net collateral.
```

#### Role of ELBE in IFRS 9 Stage 3

Under IFRS 9, the ECL for a credit-impaired (Stage 3) exposure equals the lifetime
expected credit loss. For a defaulted loan, this resolves to the expected loss on the
remaining exposure - which ELBE estimates. ELBE is the regulatory concept used by
IRB banks in their IFRS 9 Stage 3 impairment calculations.

**References:**
- EBA (2017). EBA/GL/2017/16, Section 7.3.2 ("ELBE and LGD in-default").
- IASB (2014). "IFRS 9 Financial Instruments." International Accounting Standards Board.
- Bellini, T. (2019). "IFRS 9 and CECL Credit Risk Modelling and Validation."
  Academic Press, Chapter 8.

---

### 7.2 Probability-Weighted Outcome Method

This method estimates the expected final LGD of an open default by weighting the
conditional LGD of each possible outcome by the historical probability of that outcome,
calibrated from completed defaults in the same segment.

#### Formula

```
  LGD_open = P(resolved)     x LGD|resolved
           + P(written_off)  x LGD|written_off
           + P(cured)        x cure_lgd
```

where:
- P(resolved), P(written_off), P(cured) are empirical outcome frequencies from
  completed loans in the same segment (portfolio-wide fallback if <5 completed loans)
- LGD|resolved = EAD-weighted average workout LGD of resolved loans in segment
- LGD|written_off = EAD-weighted average workout LGD of written-off loans in segment
- cure_lgd = configurable assumption (same parameter used for cured loans)

Note: P(resolved) + P(written_off) + P(cured) = 1, since these exhaust all outcomes.

#### Theoretical basis - law of total expectation

```
  E[LGD] = sum over outcomes k:  P(outcome = k) x E[LGD | outcome = k]

  This is the law of total expectation applied to the default resolution
  outcome space {resolved, written_off, cured}. The three outcomes are
  mutually exclusive and exhaustive (for non-open loans), so the weights
  sum to 1.
```

#### Worked example

```
  Segment: Corporate
  Completed loan history in segment (n = 40 loans):
    Resolved:     24 loans, EAD-weighted avg LGD = 42%
    Written_off:   8 loans, EAD-weighted avg LGD = 81%
    Cured:         8 loans
    -----------------------------------------------
    P(resolved)    = 24/40 = 60.0%
    P(written_off) = 8/40  = 20.0%
    P(cured)       = 8/40  = 20.0%

  Open loan (still in workout):
    cure_lgd = 5%

  LGD_open = 0.60 x 0.42 + 0.20 x 0.81 + 0.20 x 0.05
           = 0.252 + 0.162 + 0.010
           = 42.4%

  Interpretation: given the historical resolution mix for corporate loans in
  this portfolio, the expected final LGD for any currently open corporate
  loan is 42.4%.
```

#### For completed loans, this formula reproduces actuals

For a resolved loan: P(resolved) = 1, P(WO) = 0, P(cured) = 0
  -> LGD = 1 x LGD|resolved = actual LGD. Trivially equal to workout LGD.

This confirms the method is consistent: the formula gives the expected outcome
for uncertain cases and the actual outcome for completed cases.

#### Comparison with ELBE

| Aspect | ELBE | Probability-Weighted |
|---|---|---|
| Data source | Loan-level partial cash flows + assumptions | Segment-level historical outcome mix + conditional LGDs |
| Key assumptions | `expected_remaining_recovery_rate`, `expected_additional_years_open` | None (calibrated from data) |
| Sensitive to | Remaining collateral, workout duration | Segment outcome mix, data completeness |
| Accounts for partial recovery | Yes (Step 1) | No (gives segment-average estimate) |
| Best suited for | Good loan-level data, strong collateral position | Portfolio with many completed defaults per segment |

In practice, IRB banks often combine both: the cohort-based probabilities provide the
structural estimate, while ELBE adjustments incorporate loan-specific information.
A natural extension would be to use a regression model to predict outcome probabilities
from loan features (segment, seasoning, collateral coverage) rather than flat empirical
frequencies - see `Expansion.md` for details.

**References:**
- Schuermann, T. (2004). "What Do We Know About Loss Given Default?" Section 3
  ("The Workout Approach").
- EBA (2017). EBA/GL/2017/16, Section 7.3.3 ("In-default LGD models").
- Bellini, T. (2019). "IFRS 9 and CECL Credit Risk Modelling and Validation."
  Academic Press, Chapter 8.

---

## 8. Cure LGD

Loans that return to performing status are assigned a flat, configurable LGD (default
5%). This captures the residual loss from the default episode: foregone interest during
default, any write-downs taken before cure, and the cost of the resolution process.

```
  lgd_cured = cure_lgd   (default 5%)
```

A positive cure LGD (rather than zero) reflects that even a successful cure is not
costless for the lender. The cure LGD parameter is also used as the conditional LGD
for the cured outcome in the probability-weighted method.

Under EBA GL/2017/16 Section 7.2.5, cured exposures require careful treatment to
avoid double-counting: the default episode ends at cure, and subsequent re-defaults
are tracked separately.

---

## 9. Downturn LGD Adjustment (IRB)

Empirical research consistently shows that LGD and default rates are positively
correlated across the credit cycle: when default rates rise (downturns), collateral
values fall and recovery rates worsen simultaneously. This "wrong-way" relationship
means that using a through-the-cycle average LGD in the IRB capital formula would
understate risk.

Basel II/III and CRR Article 181(1)(b) therefore require that IRB LGD estimates
reflect conditions during an economic downturn. When enabled:

```
  lgd_final = min(1, lgd_selected x downturn_multiplier)
```

### Multiplier rationale

```
  Typical observed downturn vs. average LGD differences by segment:

  Retail mortgage (RRE):     1.1x - 1.3x  (property values fall 15-30%)
  Retail unsecured:          1.0x - 1.2x  (limited collateral; less cyclical)
  Corporate (secured):       1.2x - 1.5x  (CRE and equipment values cyclical)
  Corporate (unsecured):     1.1x - 1.3x  (balance sheet deterioration)

  Default multiplier here: 1.25x (+25%), approximating a moderate stress
  for a mixed portfolio.
```

### Example

```
  Resolved loan, workout LGD = 38%
  Downturn multiplier = 1.25

  lgd_downturn = min(1, 0.38 x 1.25) = min(1, 0.475) = 47.5%

  The downturn-adjusted LGD is 9.5 percentage points higher, representing
  the additional capital buffer required for adverse conditions.

  If LGD were already 90%:
  lgd_downturn = min(1, 0.90 x 1.25) = min(1, 1.125) = 100%  (capped)
```

**References:**
- BCBS (2006). "Basel II." Annex 5, paragraphs 468-473.
- CRR Article 181(1)(b): LGD estimates must reflect economic downturn conditions.
- BCBS (2023). "Targeted Revisions to the Credit Risk Framework" (Basel IV).
- Altman, E.I. and Kalotay, E.A. (2014). "Ultimate Recovery Mixtures." Journal of
  Banking and Finance, 40: 116-129.
- Frye, J. (2000). "Depressing Recoveries." Risk, November: 108-111.

---

## 9b. Deriving the Downturn Multiplier from Vintages

Rather than entering `downturn_multiplier` as a flat manual assumption, the
tool can derive it empirically from the portfolio's own vintage data: pick
one or more default-year vintages that represent stressed conditions and one
or more that represent benign conditions, and let their realized LGD ratio
set the multiplier.

### Formula

```
stress_avg_lgd  = weighted_avg_lgd(vintages in stress_years)
benign_avg_lgd  = weighted_avg_lgd(vintages in benign_years)
derived_multiplier = clamp(stress_avg_lgd / benign_avg_lgd, 1.0, 3.0)
```

`weighted_avg_lgd` here uses whichever portfolio weighting convention is
currently selected (EAD-weighted or number-weighted, Section 11) - each
selected vintage year's `weighted_avg_lgd` (from `VintageStats`) is combined
across years using that same convention, weighting by exposure or loan count
per year. The ratio is clamped to `[1.0, 3.0]` because that's the valid range
of `LgdAssumptions.downturn_multiplier`; a benign LGD that happens to exceed
the stress LGD would otherwise imply a multiplier below 1.0, which is not a
meaningful downturn adjustment.

This calibration always runs against the **pre-downturn** view of the
portfolio - the LGD engine is re-run with `downturn_enabled=False` before
computing the vintage averages - regardless of whether a multiplier is
already applied in the assumptions being edited. Calibrating against an
already-stressed LGD would compound the adjustment into itself.

### Worked example

```
  Stress vintages selected: 2020, 2021 -> stress_avg_lgd  = 48.5%
  Benign vintages selected: 2018, 2019 -> benign_avg_lgd  = 43.2%

  derived_multiplier = clamp(0.485 / 0.432, 1.0, 3.0)
                      = clamp(1.123, 1.0, 3.0)
                      = 1.12x
```

A multiplier derived this way is grounded in the portfolio's own observed
cyclicality rather than an external benchmark range (contrast with the
illustrative 1.1x-1.5x ranges in Section 9) - appropriate when enough
vintages with a mix of cyclical conditions have already worked through to
completion. With too few completed vintages, or vintages that don't actually
span a stress/benign contrast, a manually entered multiplier may be more
defensible.

---

## 10. Vintage Analysis

Vintage analysis groups defaulted loans by their year of default (cohort) and tracks
outcomes and loss rates across cohorts over time.

### Why vintage analysis matters

```
  Default year ->  2018    2019    2020    2021    2022    2023    2024
                 -----------------------------------------------
  Resolved        ||||||||||||||||||||||||||||||||||||||||  |       |
  Written_off           ||||||  ||  |||||  ||||           |       |
  Cured           |||  ||||  ||||||  |||  ||||            ||      ||
  Open            .                 .         .           ||||  |||||||

  LGD:             55%    48%    72%    51%    53%    61%    64%

  Observations:
  - 2020 cohort shows elevated LGD (likely stress-year vintage)
  - Recent vintages (2023-2024) have high open counts (not yet resolved)
  - 2018-2021: near-complete resolution, stable loss rates visible
```

Vintage analysis reveals:
1. **Economic cycle effects**: downturn vintages (e.g. 2020) show higher LGDs
2. **Portfolio maturity**: old vintages should have few open loans
3. **Workout pace**: if old vintages still have many open cases, workout is slow
4. **Model stability**: IRB validation requires stable LGD estimates across vintages

### In this tool

- **Bars**: loan count by default year and status (resolved/WO/cured/open)
- **Line**: EAD-weighted average final LGD per vintage year

`default_year` is derived during default-episode construction (Section 2) as the
calendar year of `observation_month` on the episode's first row - i.e. the month
`default_flag` first turned `True` for that episode. It is not user-supplied and
is not inferred from `time_in_default_years`.

**References:**
- Schuermann, T. (2004). "What Do We Know About Loss Given Default?" Section 2.
- EBA (2017). EBA/GL/2017/16, Section 10 ("Backtesting and model validation").
- McNulty, M. and Assef, A. (2011). "A Framework for Estimating Credit Portfolio Loss."
  Moody's Analytics.

---

## 11. Portfolio Aggregation and Weighting

### LGD averaging: EAD-weighted vs Number-weighted

The tool supports two averaging conventions, which produce materially different
portfolio LGD figures and are prescribed by different regulatory frameworks:

#### EAD-Weighted (IFRS 9 / portfolio EL)

```
  avg_lgd = sum(lgd_i x EAD_i) / sum(EAD_i)
```

Larger exposures contribute proportionally more to the average. This is appropriate
when the quantity of interest is the loss rate on the total outstanding balance - for
example, in an IFRS 9 expected credit loss calculation where EL = LGD x EAD is
aggregated across the portfolio.

#### Number-Weighted / Default-Weighted (IRB - CRR Art. 181)

```
  avg_lgd = sum(lgd_i) / n
```

Each defaulted obligor contributes equally regardless of exposure size. CRR Article
181(1)(a) requires that IRB LGD estimates be computed on a "default-weighted" basis:

> "Estimates of LGD shall be based on historical recovery rates and, where applicable,
> shall not solely rely on the market value of the collateral."
> "LGD estimates shall be calculated on a default-weighted basis."

This means a £5,000 defaulted credit card and a £5,000,000 defaulted corporate loan
each count as one default in the average. The rationale is that IRB LGD is a
parameter of the rating grade or obligor segment, not of the exposure amount - it
estimates the expected loss fraction for any obligor in that segment who defaults,
independent of how large their exposure happens to be.

#### Numerical illustration

```
  Portfolio of 4 defaulted loans:

  Loan   EAD        LGD     EAD x LGD
  -----  ---------  ------  ----------
  L1     £  50,000   20%    £ 10,000
  L2     £  80,000   35%    £ 28,000
  L3     £ 500,000   55%    £275,000
  L4     £1,000,000  70%    £700,000
  -----  ---------          ----------
  Total  £1,630,000         £1,013,000

  EAD-weighted LGD  = £1,013,000 / £1,630,000 = 62.1%
  Number-weighted LGD = (20 + 35 + 55 + 70) / 4 = 45.0%

  Key insight: L3 and L4 are large and high-LGD, so EAD-weighting pulls
  the portfolio average up significantly. Number-weighting treats all four
  defaults as equal contributors, giving a lower average that better
  reflects the typical loss rate per obligor in this segment.
```

#### When the difference is largest

The two measures diverge most when LGD is correlated with exposure size - which is
common in practice. Large corporate exposures tend to be better secured (lower LGD),
while small retail exposures tend to be unsecured (higher LGD). In that case:
- EAD-weighting is pulled down by large well-secured exposures
- Number-weighting gives equal weight to the many small unsecured defaults

Conversely, if large exposures have high LGD (e.g. large write-offs), EAD-weighting
will exceed number-weighting.

#### This tool's implementation

Switching the weighting method affects:
- Portfolio and segment average LGDs (`weighted_avg_lgd`, `weighted_avg_lgd_final`)
- Methodology comparison chart (workout / market / implied-market averages)
- Vintage analysis per-year LGD values
- Conditional LGDs in the probability-weighted open-default method (LGD|resolved,
  LGD|written_off used to calibrate open loan estimates)

It does NOT affect expected loss (EL = LGD x EAD is inherently EAD-weighted) or
individual loan LGDs.

**References:**
- CRR Article 181(1)(a): "LGD estimates shall be calculated on a default-weighted basis."
- EBA (2017). EBA/GL/2017/16, Section 7.2.1: "LGD estimates shall be default-weighted."
- BCBS (2006). "Basel II." Paragraph 468: LGD is computed as a default-weighted average.
- Schuermann, T. (2004). "What Do We Know About Loss Given Default?" Section 4.1
  ("Weighting Schemes").

### Expected loss (in-default)

```
  EL_i = lgd_final_i x EAD_i
```

Since all loans have already defaulted, PD = 100% and EL reduces to LGD x EAD.
This is the in-default expected loss: the estimated credit loss for the default
portfolio, conditional on default having already occurred. Expected loss is always
summed as an EAD-weighted amount regardless of the selected LGD averaging method,
since EL is a monetary quantity (£) not a rate.

### Methodology comparison

The methodology comparison chart shows the portfolio average LGD under all three
methodologies simultaneously - workout, market, and implied-market - using the
selected weighting method. For open loans, workout uses the selected open-default
method; market and implied-market always use their respective pre-default inputs.

---

## 12. Data Fields Reference

### 12.1 Monthly panel CSV (user-uploaded input)

One row per loan per month - the raw data this tool ingests. `segment` is
free text (not restricted to a fixed taxonomy); `collateral_type` must match
the enum below. See Section 2 for how `default_flag` and `write_off_flag`
drive episode detection.

| Field | Unit | Description |
|---|---|---|
| `loan_id` | - | Join key across a loan's monthly rows |
| `segment` | - | Free-text segment label |
| `observation_month` | `YYYY-MM` | Panel time axis |
| `outstanding_balance` | currency | Balance that month; drives EAD and episode-end (resolved) detection |
| `dpd` | days | Days past due that month - trajectory/charting only, not used to detect default |
| `collateral_type` | - | `none`, `residential_real_estate`, `commercial_real_estate`, `financial_collateral`, `other_physical` |
| `collateral_value` | currency | Snapshot collateral value that month |
| `cash_received_collateral` | currency | Incremental collateral-liquidation cash that month |
| `cash_received_other` | currency | Incremental non-collateral recovery cash that month |
| `recovery_cost_incurred` | currency | Incremental legal/admin/enforcement cost that month |
| `default_flag` | bool | Authoritative signal the loan is in default that month |
| `write_off_flag` | bool | Authoritative signal the loan was written off that month |
| `market_price` | 0-1 | Secondary market price, read from the loan's last pre-default row |
| `credit_spread_bps` | basis points | Credit spread, read from the loan's last pre-default row |
| `pre_default_pd` | 0-1 | Market-implied PD, read from the loan's last pre-default row |

### 12.2 `Loan` fields (derived output of default-episode construction)

These fields are not part of the upload schema - they are computed per
default episode by `loans_from_panel()` (Section 2) and are what the LGD
engine actually consumes. They're listed here because they're the fields
referenced throughout Sections 3-11.

| Field | Unit | Description |
|---|---|---|
| `loan_id` | - | Original `loan_id`, or `{loan_id}-{episode_number}` for a re-defaulted loan's later episodes |
| `segment` | - | Carried over from the episode's first panel row |
| `default_status` | - | `resolved`, `written_off`, `open`, `cured` - the episode's detected outcome |
| `collateral_type` | - | `none`, `residential_real_estate`, `commercial_real_estate`, `financial_collateral`, `other_physical` |
| `collateral_value` | currency | Gross collateral value, from the episode's first row |
| `exposure_at_default` | currency | `outstanding_balance` on the episode's first row (EAD) |
| `collateral_recovered` | currency | Sum of `cash_received_collateral` across the episode's rows |
| `non_collateral_recovered` | currency | Sum of `cash_received_other` across the episode's rows |
| `recovery_costs` | currency | Sum of `recovery_cost_incurred` across the episode's rows |
| `time_in_default_years` | years | Months spanned by the episode / 12, floored at one month |
| `default_year` | year | Calendar year of `observation_month` on the episode's first row |
| `market_price_at_default` | 0-1 | `market_price` from the row immediately before the episode starts |
| `credit_spread_bps` | basis points | `credit_spread_bps` from the row immediately before the episode starts |
| `pre_default_pd` | 0-1 | `pre_default_pd` from the row immediately before the episode starts |

---

*All data in this tool is synthetic and generated for illustration purposes only.
Nothing here reflects actual client data, production model output, or employer
methodology. This is a portfolio demonstration project only.*
