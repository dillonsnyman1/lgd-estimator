import os
import time
import uuid
from collections import Counter
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.lgd_engine import compute_downturn_calibration, process_portfolio
from app.models import (
    ConstructDefaultsRequest,
    ConstructDefaultsResponse,
    DownturnCalibrationRequest,
    DownturnCalibrationResponse,
    LgdCalculateRequest,
    Loan,
    PanelUploadResponse,
    PortfolioResponse,
)
from app.panel_engine import loans_from_panel
from app.panel_generator import generate_monthly_panel

SAMPLE_PANEL_PATH = Path(__file__).parent / "sample_data" / "sample_monthly_panel.csv"

REQUIRED_PANEL_COLUMNS = {
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
}

DATA_STORE_TTL = 3600
_panel_store: dict[str, tuple[pd.DataFrame, float]] = {}
_loans_store: dict[str, tuple[list[Loan], float]] = {}

app = FastAPI(title="LGD Estimator")

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _evict_expired() -> None:
    now = time.time()
    for store in (_panel_store, _loans_store):
        expired = [k for k, (_, ts) in store.items() if now - ts > DATA_STORE_TTL]
        for k in expired:
            del store[k]


def _get_panel(data_id: str) -> pd.DataFrame:
    _evict_expired()
    entry = _panel_store.get(data_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Panel not found. Please re-upload or reload the sample.")
    return entry[0]


def _get_loans(data_id: str) -> list[Loan]:
    _evict_expired()
    entry = _loans_store.get(data_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Constructed defaults not found. Please redo the default-construction step.")
    return entry[0]


def _panel_response(data_id: str, df: pd.DataFrame) -> PanelUploadResponse:
    return PanelUploadResponse(
        data_id=data_id,
        row_count=len(df),
        loan_count=df["loan_id"].nunique(),
        month_min=str(df["observation_month"].min()),
        month_max=str(df["observation_month"].max()),
        columns=list(df.columns),
    )


@app.post("/api/panel/upload", response_model=PanelUploadResponse)
async def upload_panel(file: UploadFile) -> PanelUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Please upload a CSV file.")

    try:
        df = pd.read_csv(file.file)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read CSV file: {exc}") from exc

    missing = REQUIRED_PANEL_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}",
        )

    data_id = str(uuid.uuid4())
    _panel_store[data_id] = (df, time.time())
    return _panel_response(data_id, df)


@app.post("/api/panel/load-sample", response_model=PanelUploadResponse)
def load_sample_panel() -> PanelUploadResponse:
    df = pd.read_csv(SAMPLE_PANEL_PATH) if SAMPLE_PANEL_PATH.exists() else generate_monthly_panel()
    data_id = str(uuid.uuid4())
    _panel_store[data_id] = (df, time.time())
    return _panel_response(data_id, df)


@app.post("/api/panel/construct-defaults", response_model=ConstructDefaultsResponse)
def construct_defaults(req: ConstructDefaultsRequest) -> ConstructDefaultsResponse:
    df = _get_panel(req.data_id)
    loans, episodes = loans_from_panel(df)
    if not loans:
        raise HTTPException(status_code=422, detail="No default episodes found in this panel (no rows with default_flag=True).")

    _loans_store[req.data_id] = (loans, time.time())

    return ConstructDefaultsResponse(
        data_id=req.data_id,
        raw_loan_count=df["loan_id"].nunique(),
        episode_count=len(episodes),
        episodes=episodes,
        status_counts=dict(Counter(e.default_status.value for e in episodes)),
    )


@app.post("/api/lgd/calculate", response_model=PortfolioResponse)
def calculate_lgd(req: LgdCalculateRequest) -> PortfolioResponse:
    loans = _get_loans(req.data_id)
    return process_portfolio(loans, req.assumptions)


@app.post("/api/lgd/downturn-calibration", response_model=DownturnCalibrationResponse)
def downturn_calibration(req: DownturnCalibrationRequest) -> DownturnCalibrationResponse:
    loans = _get_loans(req.data_id)
    # Calibrate against the pre-downturn view, regardless of the current
    # assumptions' downturn_enabled state, so an already-applied multiplier
    # doesn't distort the stress-vs-benign comparison.
    calibration_assumptions = req.assumptions.model_copy(update={"downturn_enabled": False})
    result = process_portfolio(loans, calibration_assumptions)
    stress_avg_lgd, benign_avg_lgd, derived_multiplier = compute_downturn_calibration(
        result.vintage_analysis, req.stress_years, req.benign_years, req.assumptions.weighting_method
    )
    return DownturnCalibrationResponse(
        stress_avg_lgd=round(stress_avg_lgd, 4),
        benign_avg_lgd=round(benign_avg_lgd, 4),
        derived_multiplier=round(derived_multiplier, 4),
    )


from mangum import Mangum  # noqa: E402

handler = Mangum(app)
