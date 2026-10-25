// Typed client for the FastAPI service. All numbers shown in the UI come from these endpoints.

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type RiskClass = "low" | "moderate" | "high" | "very high";

export interface Scenario { id: string; name: string; description: string }

export interface ProvinceResult {
  province: string;
  population: number;
  exposed_population: number;
  exposed_share_pct: number;
  risk_class: RiskClass;
}

export interface Summary {
  provinces: number;
  total_population: number;
  exposed_population: number;
  exposed_share_pct: number;
  provinces_by_risk_class: Record<RiskClass, number>;
  most_exposed: ProvinceResult[];
}

export interface Results { scenario: Scenario; summary: Summary; provinces: ProvinceResult[] }

export interface Change {
  province: string;
  base_exposed: number;
  target_exposed: number;
  change: number;
  base_risk_class: RiskClass;
  target_risk_class: RiskClass;
}

export interface Comparison {
  base: Scenario;
  target: Scenario;
  base_exposed_population: number;
  target_exposed_population: number;
  change: number;
  change_pct: number;
  provinces_changing_class: number;
  largest_increases: Change[];
  all: Change[];
}

export interface Explanation {
  answer: string;
  mode: "llm" | "template";
  tools_used: string[];
  guard: { passed: boolean; unsupported_numbers: string[] };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  scenarios: () => request<Scenario[]>("/api/scenarios"),
  provinces: () => request<GeoJSON.FeatureCollection>("/api/provinces"),
  results: (id: string) => request<Results>(`/api/scenarios/${encodeURIComponent(id)}/results`),
  compare: (base: string, target: string) =>
    request<Comparison>(`/api/compare?base=${encodeURIComponent(base)}&target=${encodeURIComponent(target)}`),
  explain: (token: string, body: { scenario_id: string; compare_to?: string; question: string }) =>
    request<Explanation>("/api/explain", { method: "POST", body: JSON.stringify(body) }, token),
  async download(token: string, id: string, format: "csv" | "geojson"): Promise<void> {
    const res = await fetch(`${API_URL}/api/scenarios/${encodeURIComponent(id)}/download?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new ApiError(res.status, res.status === 403 ? "Downloads need the analyst role." : res.statusText);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `${id}_results.${format}` });
    a.click();
    URL.revokeObjectURL(url);
  },
};
