import type {
  ConstructDefaultsResponse,
  DownturnCalibrationResponse,
  LgdAssumptions,
  PanelUploadResponse,
  PortfolioResponse,
} from "../types/portfolio";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // ignore parse error
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadPanel(file: File): Promise<PanelUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/api/panel/upload`, { method: "POST", body: form });
  return parseResponse<PanelUploadResponse>(res);
}

export async function loadSamplePanel(): Promise<PanelUploadResponse> {
  const res = await fetch(`${BASE_URL}/api/panel/load-sample`, { method: "POST" });
  return parseResponse<PanelUploadResponse>(res);
}

export async function constructDefaults(dataId: string): Promise<ConstructDefaultsResponse> {
  const res = await fetch(`${BASE_URL}/api/panel/construct-defaults`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_id: dataId }),
  });
  return parseResponse<ConstructDefaultsResponse>(res);
}

export async function calculateLgd(dataId: string, assumptions: LgdAssumptions): Promise<PortfolioResponse> {
  const res = await fetch(`${BASE_URL}/api/lgd/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_id: dataId, assumptions }),
  });
  return parseResponse<PortfolioResponse>(res);
}

export async function computeDownturnCalibration(
  dataId: string,
  assumptions: LgdAssumptions,
  stressYears: number[],
  benignYears: number[],
): Promise<DownturnCalibrationResponse> {
  const res = await fetch(`${BASE_URL}/api/lgd/downturn-calibration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data_id: dataId,
      assumptions,
      stress_years: stressYears,
      benign_years: benignYears,
    }),
  });
  return parseResponse<DownturnCalibrationResponse>(res);
}
