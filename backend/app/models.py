from enum import Enum

from pydantic import BaseModel, Field


class Methodology(str, Enum):
    workout = "workout"
    market = "market"
    implied_market = "implied_market"


class OpenDefaultMethod(str, Enum):
    elbe = "elbe"                           # partial net recovery + estimated future collateral recovery
    probability_weighted = "probability_weighted"  # P(WO)*LGD|WO + P(cure)*LGD|cure + P(res)*LGD|res, calibrated from same-segment completed loans


class CureLgdMethod(str, Enum):
    fixed = "fixed"           # use the cure_lgd assumption flat rate
    calculated = "calculated" # derive from actual recovery cash flows (same DCF formula as resolved loans)


class WeightingMethod(str, Enum):
    ead_weighted = "ead_weighted"       # EAD-weighted average LGD (IFRS 9 / portfolio EL context)
    number_weighted = "number_weighted" # simple average across defaults (IRB CRR Art. 181 default-weighted)


class SampleSegment(str, Enum):
    """Fixed taxonomy used only for synthetic sample-data generation.

    Real (uploaded) portfolios use a free-text `Loan.segment` instead.
    """
    retail_mortgage = "retail_mortgage"
    retail_unsecured = "retail_unsecured"
    corporate = "corporate"
    sme = "sme"


class CollateralType(str, Enum):
    none = "none"
    residential_real_estate = "residential_real_estate"
    commercial_real_estate = "commercial_real_estate"
    financial_collateral = "financial_collateral"
    other_physical = "other_physical"


class DefaultStatus(str, Enum):
    resolved = "resolved"       # workout complete - all recoveries received, LGD finalised
    written_off = "written_off" # balance written off the books; recovery fields = final amounts received before/at write-off
    open = "open"               # still in workout; LGD estimated via ELBE or probability-weighted cohort approach
    cured = "cured"             # returned to performing - minimal LGD (residual costs only)


class LgdAssumptions(BaseModel):
    methodology: Methodology = Methodology.workout
    open_default_method: OpenDefaultMethod = Field(
        default=OpenDefaultMethod.elbe,
        description="method for estimating LGD on open (in-workout) defaults",
    )
    weighting_method: WeightingMethod = Field(
        default=WeightingMethod.number_weighted,
        description="EAD-weighted (IFRS 9 / portfolio EL) or number-weighted / default-weighted (IRB CRR Art. 181)",
    )
    discount_rate: float = Field(default=0.05, ge=0, le=1, description="annual rate used to discount workout cash flows to the date of default")
    downturn_enabled: bool = Field(default=False, description="apply downturn LGD multiplier for IRB stress scenario")
    downturn_multiplier: float = Field(default=1.25, ge=1.0, le=3.0, description="multiplicative uplift applied to LGD when downturn is enabled")
    haircut_rre: float = Field(default=0.20, ge=0, le=1, description="haircut on residential real estate collateral")
    haircut_cre: float = Field(default=0.40, ge=0, le=1, description="haircut on commercial real estate collateral")
    haircut_financial: float = Field(default=0.15, ge=0, le=1, description="haircut on financial collateral")
    haircut_other_physical: float = Field(default=0.50, ge=0, le=1, description="haircut on other physical collateral")
    cure_lgd_method: CureLgdMethod = Field(
        default=CureLgdMethod.fixed,
        description="fixed: use cure_lgd assumption; calculated: derive from actual recovery cash flows",
    )
    cure_lgd: float = Field(default=0.05, ge=0, le=1, description="LGD assigned to cured exposures when cure_lgd_method=fixed")
    # ELBE parameters - used when open_default_method == elbe
    expected_remaining_recovery_rate: float = Field(
        default=0.75, ge=0, le=1,
        description="(ELBE) fraction of remaining net collateral expected to be recovered from open defaults",
    )
    expected_additional_years_open: float = Field(
        default=1.5, ge=0.25, le=5.0,
        description="(ELBE) additional years until resolution assumed for open (in-workout) defaults",
    )


class Loan(BaseModel):
    loan_id: str
    segment: str = Field(min_length=1, description="loan segment - free text, e.g. 'retail_mortgage' or any custom label from uploaded data")
    default_status: DefaultStatus = Field(description="resolved: workout complete; open: still in workout; cured: returned to performing")
    collateral_type: CollateralType
    collateral_value: float = Field(ge=0, description="gross market value of collateral at time of default")
    exposure_at_default: float = Field(gt=0, description="outstanding exposure at the point of default (EAD)")

    # Recovery cash flows:
    #   resolved - final actual amounts
    #   open     - partial amounts received or incurred to date
    #   cured    - small amounts (costs only, typically)
    collateral_recovered: float = Field(ge=0, description="gross cash received from collateral liquidation (actual for resolved; partial to-date for open)")
    non_collateral_recovered: float = Field(ge=0, description="gross cash from non-collateral sources - debtor payments, guarantees, debt sales (actual or partial)")
    recovery_costs: float = Field(ge=0, description="direct recovery costs - legal, enforcement, administration (actual or partial to-date)")
    time_in_default_years: float = Field(gt=0, description="for resolved: actual time from default to resolution; for open: elapsed time in default so far; for cured: time to cure")

    # Year of default for vintage analysis (cohort label)
    default_year: int = Field(default=0, ge=0, description="calendar year the loan entered default (e.g. 2022); 0 = derive from time_in_default_years")

    # Market approach input
    market_price_at_default: float = Field(ge=0, le=1, description="secondary market price as fraction of face value, 30-90 days post-default")

    # Implied-market approach inputs
    credit_spread_bps: float = Field(ge=0, description="credit spread over risk-free rate in basis points, observed pre-default")
    pre_default_pd: float = Field(gt=0, le=1, description="market-implied PD used with the credit spread to back out LGD")


class ProcessedLoan(Loan):
    haircut_applied: float
    net_collateral_value: float

    lgd_workout: float          # resolved/WO/cured: DCF; open: ELBE or probability-weighted (per selected method)
    lgd_market: float           # 1 - market price at default
    lgd_implied_market: float
    lgd_selected: float         # chosen methodology (pre-downturn); open always uses workout estimate
    lgd_post_cure: float        # retained for compatibility (equals lgd_selected)
    lgd_final: float            # after downturn adjustment
    observed_lgd_to_date: float # actual cash-flow LGD from recoveries received so far, independent of cure/open-default method; final for resolved/written-off, partial/incomplete for open

    # ELBE breakdown (populated for open loans when open_default_method == elbe; 0.0 otherwise)
    partial_net_recovery: float
    estimated_future_recovery: float

    gross_recovery: float       # collateral_recovered + non_collateral_recovered (partial for open)
    net_recovery: float         # net of costs and discounting
    expected_loss: float


class OutcomeProbabilities(BaseModel):
    """Per-segment outcome probabilities and conditional LGDs, calibrated from completed loans."""
    p_resolved: float
    p_written_off: float
    p_cured: float
    lgd_given_resolved: float    # avg LGD of resolved loans in the calibration set
    lgd_given_written_off: float # avg LGD of written_off loans in the calibration set
    lgd_given_cured: float = 0.05  # avg LGD of cured loans in the calibration set
    completed_count: int         # number of completed loans used for calibration


class VintageStats(BaseModel):
    year: int
    loan_count: int
    total_exposure: float
    weighted_avg_lgd: float
    resolved_count: int
    written_off_count: int
    open_count: int
    cured_count: int
    completed_count: int                  # resolved + written_off - the basis for the predicted-vs-realized comparison below
    predicted_lgd_market: float            # ex-ante: avg lgd_market across this vintage's completed loans, known at default
    predicted_lgd_implied_market: float    # ex-ante: avg lgd_implied_market across this vintage's completed loans
    realized_lgd_workout: float            # ex-post: avg lgd_workout (actual cash-flow LGD) across this vintage's completed loans
    avg_time_to_resolution: float          # avg time_in_default_years for this vintage's resolved loans (0 if none)
    avg_time_to_writeoff: float            # avg time_in_default_years for this vintage's written_off loans (0 if none)
    avg_time_to_cure: float                # avg time_in_default_years for this vintage's cured loans (0 if none)


class VintageAnalysis(BaseModel):
    vintages: list[VintageStats]
    outcome_probabilities: dict[str, OutcomeProbabilities]


class MethodologyComparison(BaseModel):
    workout_lgd: float
    market_lgd: float
    implied_market_lgd: float


class SegmentSummary(BaseModel):
    loan_count: int
    resolved_count: int
    written_off_count: int
    open_count: int
    cured_count: int
    cure_rate: float
    written_off_rate: float
    total_exposure: float
    weighted_avg_lgd: float
    weighted_avg_lgd_final: float
    total_expected_loss: float
    total_collateral_recovered: float
    total_non_collateral_recovered: float
    total_recovery_costs: float
    total_net_recovery: float
    methodology_comparison: MethodologyComparison


class PortfolioSummary(BaseModel):
    loan_count: int
    total_exposure: float
    resolved_count: int
    written_off_count: int
    open_count: int
    cured_count: int
    cure_rate: float
    written_off_rate: float
    weighted_avg_lgd: float
    weighted_avg_lgd_final: float
    total_expected_loss: float
    by_segment: dict[str, SegmentSummary]
    methodology_comparison: MethodologyComparison


class PortfolioResponse(BaseModel):
    loans: list[ProcessedLoan]
    summary: PortfolioSummary
    vintage_analysis: VintageAnalysis


class PanelUploadResponse(BaseModel):
    data_id: str
    row_count: int
    loan_count: int
    month_min: str
    month_max: str
    columns: list[str]


class ConstructDefaultsRequest(BaseModel):
    data_id: str


class DefaultEpisode(BaseModel):
    loan_id: str = Field(description="synthesized id used downstream by the LGD engine, e.g. 'L00042-2' for a re-default episode")
    raw_loan_id: str = Field(description="original loan_id from the uploaded panel")
    segment: str
    default_status: DefaultStatus
    start_month: str
    end_month: str
    row_count: int
    exposure_at_default: float


class ConstructDefaultsResponse(BaseModel):
    data_id: str
    raw_loan_count: int
    episode_count: int
    episodes: list[DefaultEpisode]
    status_counts: dict[str, int]


class LgdCalculateRequest(BaseModel):
    data_id: str
    assumptions: LgdAssumptions


class DownturnCalibrationRequest(BaseModel):
    data_id: str
    assumptions: LgdAssumptions
    stress_years: list[int] = Field(default_factory=list)
    benign_years: list[int] = Field(default_factory=list)


class DownturnCalibrationResponse(BaseModel):
    stress_avg_lgd: float
    benign_avg_lgd: float
    derived_multiplier: float
