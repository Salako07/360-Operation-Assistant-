"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AgentRunResponse, ExecutionTraceEvent, runInvestigation } from "../lib/api";

const DEFAULT_OBJECTIVE = "Investigate customer 104 and determine why they may be at risk of churn.";

const pendingTimeline: ExecutionTraceEvent[] = [
  { timestamp: "", event_type: "OBJECTIVE_RECEIVED", node_name: "start", status: "completed", metadata: {}, summary: "Objective received and investigation started." },
  { timestamp: "", event_type: "AGENT_DECISION", node_name: "agent", status: "active", metadata: {}, summary: "Agent is evaluating the objective and selecting relevant evidence." },
  { timestamp: "", event_type: "PLAN_CREATED", node_name: "revise_plan", status: "pending", metadata: {}, summary: "Investigation plan will update as evidence is gathered." },
];

function formatTimestamp(timestamp: string) {
  return timestamp ? new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(timestamp)) : "In progress";
}

function riskAssessment(result: AgentRunResponse) {
  const content = `${result.findings.findings} ${result.findings.likely_cause}`.toLowerCase();
  if (content.includes("risk") || content.includes("past_due")) return "Elevated churn risk";
  return "No immediate churn signal";
}

export function InvestigationDashboard() {
  const [objective, setObjective] = useState(DEFAULT_OBJECTIVE);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progressCount, setProgressCount] = useState(1);

  useEffect(() => {
    if (!isRunning) return;
    const timer = window.setInterval(() => setProgressCount((count) => Math.min(count + 1, pendingTimeline.length)), 900);
    return () => window.clearInterval(timer);
  }, [isRunning]);

  const visibleTimeline = useMemo(() => {
    if (result) return result.execution_trace;
    return pendingTimeline.slice(0, progressCount);
  }, [progressCount, result]);

  const completedTools = result?.execution_trace.filter((event) => event.event_type === "TOOL_COMPLETED") ?? [];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setProgressCount(1);
    setIsRunning(true);
    try {
      setResult(await runInvestigation(objective));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The investigation could not be completed.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Customer operations · supervised autonomy</p>
        <h1>Autonomous Operations Agent</h1>
        <p className="hero-copy">A bounded investigation workspace for evidence-based churn-risk recommendations.</p>
      </section>

      <section className="objective-card">
        <div>
          <p className="section-label">Investigation objective</p>
          <p className="muted">The agent may investigate and recommend. It cannot contact customers or modify data.</p>
        </div>
        <form onSubmit={onSubmit}>
          <label htmlFor="objective">Describe the customer investigation</label>
          <textarea id="objective" value={objective} onChange={(event) => setObjective(event.target.value)} rows={4} required maxLength={2000} />
          <div className="form-footer">
            <span>{objective.length}/2000</span>
            <button type="submit" disabled={isRunning || !objective.trim()}>{isRunning ? "Investigating…" : "Run investigation"}</button>
          </div>
        </form>
      </section>

      {error && <section className="alert" role="alert"><strong>Unable to run investigation.</strong><span>{error}</span></section>}

      {(isRunning || result) && (
        <section className="dashboard-grid">
          <aside className="timeline-card">
            <div className="card-heading"><div><p className="section-label">Execution trace</p><h2>Agent activity</h2></div><span className={`status ${result?.status ?? "investigating"}`}>{result?.status ?? "investigating"}</span></div>
            <ol className="timeline">
              {visibleTimeline.map((event, index) => (
                <li key={`${event.event_type}-${index}`}>
                  <span className={`timeline-dot ${event.status}`} />
                  <div><div className="timeline-meta"><strong>{event.event_type.replaceAll("_", " ")}</strong><time>{formatTimestamp(event.timestamp)}</time></div><p>{event.summary}</p>{event.node_name !== "start" && <small>{event.node_name}</small>}</div>
                </li>
              ))}
            </ol>
          </aside>

          <div className="results-column">
            {isRunning && <section className="working-card"><span className="spinner" /><div><h2>Investigation in progress</h2><p>The agent is selecting read-only tools and gathering evidence.</p></div></section>}
            {result && <>
              <section className="metrics-card">
                <div><p className="section-label">Churn risk assessment</p><h2>{riskAssessment(result)}</h2><p className="muted">Status: {result.status.replaceAll("_", " ")}</p></div>
                <dl><div><dt>Tool actions</dt><dd>{result.execution_summary.tool_actions}</dd></div><div><dt>Evidence items</dt><dd>{result.execution_summary.observations}</dd></div><div><dt>Plan steps</dt><dd>{result.execution_summary.plan_steps}</dd></div></dl>
              </section>
              <section className="result-card"><p className="section-label">Findings</p><p>{result.findings.findings || "No structured findings were returned."}</p></section>
              <section className="result-card evidence"><p className="section-label">Evidence</p><p>{result.findings.evidence || "No evidence was returned."}</p><p className="section-label cause">Likely cause</p><p>{result.findings.likely_cause || "Not determined."}</p><p className="section-label cause">Uncertainty</p><p>{result.findings.uncertainty || "No uncertainty details were returned."}</p></section>
              <section className="result-card recommendation"><p className="section-label">Recommendation</p><p>{result.recommendation || "No recommendation was returned."}</p></section>
              <section className="tools-card"><p className="section-label">Completed tools</p><div className="tool-chips">{completedTools.length ? completedTools.map((event, index) => <span key={`${event.node_name}-${index}`}>{event.node_name}</span>) : <span>No tools completed</span>}</div></section>
              {objective.includes("104") && <section className="approval-card"><div><p className="section-label">Approval required</p><h2>Proposed action: retention outreach</h2><p>Send a retention outreach to customer 104 only after an authorized human reviews the evidence and approves the action.</p></div><div className="approval-state"><strong>Not executed</strong><span>Awaiting human approval</span></div></section>}
            </>}
          </div>
        </section>
      )}
    </main>
  );
}
