// Typed client for the FastAPI service. All numbers shown in the UI come from these endpoints.

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Static mode (GitHub Pages): read a snapshot exported from the API by scripts/export_static.py instead of calling it.
export const STATIC = import.meta.env.VITE_STATIC_DATA === "true";
export const REPO_URL = "https://github.com/TK87tech/Risk-scenario-explorer";
const DATA_URL = `${import.meta.env.BASE_URL}data`;

async function staticJson<T>(file: string): Promise<T> {
  const res = await fetch(`${DATA_URL}/${file}`);
  if (!res.ok) throw new ApiError(res.status, `Could not load ${file}`);
  return res.json() as Promise<T>;
}

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
  scenarios: () => (STATIC ? staticJson<Scenario[]>("scenarios.json") : request<Scenario[]>("/api/scenarios")),
  provinces: () =>
    STATIC ? staticJson<GeoJSON.FeatureCollection>("provinces.json") : request<GeoJSON.FeatureCollection>("/api/provinces"),
  results: (id: string) =>
    STATIC ? staticJson<Results>(`results_${id}.json`) : request<Results>(`/api/scenarios/${encodeURIComponent(id)}/results`),
  compare: (base: string, target: string) =>
    STATIC
      ? staticJson<Comparison>(`compare_${base}__${target}.json`)
      : request<Comparison>(`/api/compare?base=${encodeURIComponent(base)}&target=${encodeURIComponent(target)}`),
  /** Static mode only: the deterministic explanation exported for this scenario (and comparison). */
  staticExplanation: async (scenarioId: string, compareTo?: string) => {
    const all = await staticJson<Record<string, string>>("explanations.json");
    return all[compareTo ? `${scenarioId}|${compareTo}` : scenarioId];
  },
  explain: (token: string, body: { scenario_id: string; compare_to?: string; question: string }) =>
    request<Explanation>("/api/explain", { method: "POST", body: JSON.stringify(body) }, token),
  async download(token: string, id: string, format: "csv" | "geojson"): Promise<void> {
    const res = await fetch(`${API_URL}/api/scenarios/${encodeURIComponent(id)}/download?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new ApiError(res.status, res.status === 403 ? "Downloads need the analyst role." : res.statusText);
    saveFile(await res.blob(), `${id}_results.${format}`);
  },
  /** Static mode only: build the same CSV/GeoJSON the API's download endpoint returns, in the browser. */
  staticDownload(results: Results, provinces: GeoJSON.FeatureCollection, format: "csv" | "geojson"): void {
    const id = results.scenario.id;
    if (format === "csv") {
      const cols = ["province", "population", "exposed_population", "exposed_share_pct", "risk_class"] as const;
      const lines = [cols.join(","), ...results.provinces.map((p) => cols.map((c) => p[c]).join(","))];
      saveFile(new Blob([lines.join("\n") + "\n"], { type: "text/csv" }), `${id}_results.csv`);
      return;
    }
    const byName = Object.fromEntries(results.provinces.map((p) => [p.province, p]));
    const merged = {
      ...provinces,
      features: provinces.features.map((f) => ({ ...f, properties: { ...f.properties, ...byName[f.properties?.province] } })),
    };
    saveFile(new Blob([JSON.stringify(merged)], { type: "application/geo+json" }), `${id}_results.geojson`);
  },
};

function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement("a"), { href: url, download: filename }).click();
  URL.revokeObjectURL(url);
}
