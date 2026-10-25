import type { User } from "oidc-client-ts";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Comparison, type Explanation, type Results, type RiskClass, type Scenario } from "./api";
import { initAuth, rolesOf, userManager } from "./auth";
import { fmt, RISK_COLORS, RISK_ORDER, signed } from "./format";
import { MapView } from "./MapView";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("rp100");
  const [compareTo, setCompareTo] = useState<string>("");
  const [provinces, setProvinces] = useState<GeoJSON.FeatureCollection | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const roles = rolesOf(user);
  const isAnalyst = roles.includes("analyst");

  useEffect(() => {
    initAuth().then(setUser).catch(() => setUser(null));
    api.scenarios().then(setScenarios).catch((e) => setError(e.message));
    api.provinces().then(setProvinces).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setError(null);
    api.results(scenarioId).then(setResults).catch((e) => setError(e.message));
    if (compareTo) api.compare(compareTo, scenarioId).then(setComparison).catch((e) => setError(e.message));
    else setComparison(null);
  }, [scenarioId, compareTo]);

  const classes = useMemo(
    () => Object.fromEntries((results?.provinces ?? []).map((p) => [p.province, p.risk_class])) as Record<string, RiskClass>,
    [results],
  );
  const changes = useMemo(() => Object.fromEntries((comparison?.all ?? []).map((c) => [c.province, c])), [comparison]);
  const otherScenarios = scenarios.filter((s) => s.id !== scenarioId);

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Risk Scenario Explorer</h1>
          <p className="subtitle">Flood exposure for Thailand's provinces · illustrative hazard data, real boundaries and population</p>
        </div>
        <div className="account">
          {user ? (
            <>
              <span>
                Signed in as <strong>{user.profile.preferred_username}</strong> ({roles.filter((r) => r === "viewer" || r === "analyst").join(", ")})
              </span>
              <button onClick={() => userManager.signoutRedirect()}>Sign out</button>
            </>
          ) : (
            <button className="primary" onClick={() => userManager.signinRedirect()}>Sign in</button>
          )}
        </div>
      </header>

      {error && <p role="alert" className="error">{error}</p>}

      <main className="layout">
        <aside className="panel" aria-label="Scenario controls and summary">
          <section>
            <label htmlFor="scenario">Scenario</label>
            <select id="scenario" value={scenarioId} onChange={(e) => { setScenarioId(e.target.value); if (e.target.value === compareTo) setCompareTo(""); }}>
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {results && <p className="hint">{results.scenario.description}</p>}

            <label htmlFor="compare">Compare with</label>
            <select id="compare" value={compareTo} onChange={(e) => setCompareTo(e.target.value)}>
              <option value="">No comparison</option>
              {otherScenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </section>

          {results && <SummaryCards results={results} comparison={comparison} />}

          <Legend counts={results?.summary.provinces_by_risk_class} />

          <ExplainBox user={user} scenarioId={scenarioId} compareTo={compareTo || undefined} />

          <section aria-labelledby="downloads">
            <h2 id="downloads">Downloads</h2>
            {!user && <p className="hint">Sign in with an analyst account to download results.</p>}
            {user && !isAnalyst && <p className="hint">Your account can view and ask questions; downloads need the analyst role.</p>}
            <div className="row">
              {(["csv", "geojson"] as const).map((f) => (
                <button key={f} disabled={!isAnalyst}
                  onClick={() => api.download(user!.access_token, scenarioId, f).catch((e: ApiError) => setError(e.message))}>
                  Download {f.toUpperCase()}
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section className="content" aria-label="Map and results table">
          <MapView provinces={provinces} classes={classes} selected={selected} onSelect={setSelected} />
          <ResultsTable results={results} changes={changes} selected={selected} onSelect={setSelected} comparing={!!comparison} />
        </section>
      </main>
    </div>
  );
}

function SummaryCards({ results, comparison }: { results: Results; comparison: Comparison | null }) {
  const s = results.summary;
  return (
    <section aria-labelledby="summary" className="cards">
      <h2 id="summary">Summary</h2>
      <div className="card">
        <span className="label">People in flood-prone areas</span>
        <span className="value" data-testid="exposed-total">{fmt.format(s.exposed_population)}</span>
        <span className="hint">{s.exposed_share_pct.toFixed(1)}% of {fmt.format(s.total_population)}</span>
      </div>
      {comparison && (
        <div className="card">
          <span className="label">Change vs {comparison.base.name}</span>
          <span className="value" data-testid="change-total">{signed(comparison.change)}</span>
          <span className="hint">{comparison.change_pct.toFixed(1)}% · {comparison.provinces_changing_class} provinces change risk class</span>
        </div>
      )}
    </section>
  );
}

function Legend({ counts }: { counts?: Record<RiskClass, number> }) {
  return (
    <section aria-labelledby="legend">
      <h2 id="legend">Risk class</h2>
      <p className="hint">Share of a province's population in flood-prone areas.</p>
      <ul className="legend">
        {RISK_ORDER.map((c, i) => (
          <li key={c}>
            <span className="swatch" style={{ background: RISK_COLORS[c] }} aria-hidden="true" />
            <span className="cls">{c}</span>
            <span className="range">{["under 5%", "5–15%", "15–30%", "30% or more"][i]}</span>
            {counts && <span className="count">{counts[c]} provinces</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ExplainBox({ user, scenarioId, compareTo }: { user: User | null; scenarioId: string; compareTo?: string }) {
  const [question, setQuestion] = useState("Which provinces are most exposed, and why does this scenario matter?");
  const [answer, setAnswer] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setBusy(true); setErr(null); setAnswer(null);
    try {
      setAnswer(await api.explain(user.access_token, { scenario_id: scenarioId, compare_to: compareTo, question }));
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="explain">
      <h2 id="explain">Explain these results</h2>
      <form onSubmit={ask}>
        <label htmlFor="question" className="visually-hidden">Your question</label>
        <textarea id="question" rows={3} maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} disabled={!user} />
        <button type="submit" className="primary" disabled={!user || busy}>{busy ? "Explaining…" : "Ask"}</button>
        {!user && <p className="hint">Sign in to ask questions.</p>}
      </form>
      <div aria-live="polite">
        {err && <p role="alert" className="error">{err}</p>}
        {answer && (
          <div className="answer" data-testid="answer">
            <p>{answer.answer}</p>
            <p className="hint">
              {answer.mode === "llm" ? `AI explanation using ${answer.tools_used.join(", ")}` : "Generated from the calculated results"}
              {!answer.guard.passed && ` · AI answer replaced: it contained numbers not in the results (${answer.guard.unsupported_numbers.join(", ")})`}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function ResultsTable({ results, changes, selected, onSelect, comparing }: {
  results: Results | null; changes: Record<string, { change: number }>; selected: string | null;
  onSelect: (p: string) => void; comparing: boolean;
}) {
  if (!results) return <p>Loading results…</p>;
  return (
    <div className="table-wrap">
      <table>
        <caption>Provinces by people in flood-prone areas, {results.scenario.name}. Select a row to highlight it on the map.</caption>
        <thead>
          <tr>
            <th scope="col">Province</th>
            <th scope="col" className="num">Exposed</th>
            <th scope="col" className="num">Share</th>
            <th scope="col">Risk class</th>
            {comparing && <th scope="col" className="num">Change</th>}
          </tr>
        </thead>
        <tbody>
          {results.provinces.map((p) => (
            <tr key={p.province} aria-selected={selected === p.province} className={selected === p.province ? "selected" : ""}>
              <th scope="row">
                <button className="link" onClick={() => onSelect(p.province)}>{p.province}</button>
              </th>
              <td className="num">{fmt.format(p.exposed_population)}</td>
              <td className="num">{p.exposed_share_pct.toFixed(1)}%</td>
              <td><span className="swatch" style={{ background: RISK_COLORS[p.risk_class] }} aria-hidden="true" /> {p.risk_class}</td>
              {comparing && <td className="num">{changes[p.province] ? signed(changes[p.province].change) : "–"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
