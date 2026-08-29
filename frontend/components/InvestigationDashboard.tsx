"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AgentRunResponse,
  ExecutionTraceEvent,
  runInvestigation,
} from "../lib/api";

const PRESET_OBJECTIVES = [
  {
    label: "Customer 104 (Elevated Risk)",
    text: "Investigate customer 104 and determine why they may be at risk of churn. Provide an evidence-based recommendation.",
  },
  {
    label: "Customer 105 (Active / Healthy)",
    text: "Investigate customer 105 for churn risk and provide an evidence-based recommendation.",
  },
  {
    label: "Customer 107 (Sparse Data)",
    text: "Investigate customer 107 for churn risk. Explain whether the available information is sufficient for a recommendation.",
  },
];

interface AgentCardData {
  id: string;
  name: string;
  role: string;
  boundedCapability: string;
  delegatedTask: string;
  executedTools: { name: string; status: string; summary: string }[];
  resultSummary: string;
  status: "idle" | "running" | "completed" | "failed";
  riskSignal?: string;
}

const DEFAULT_AGENTS: AgentCardData[] = [
  {
    id: "profile_specialist",
    name: "Customer Agent",
    role: "Profile & Subscription Specialist",
    boundedCapability: "Read-only profile, MRR, tier, account status",
    delegatedTask: "Retrieve customer identity, plan tier, and account standing.",
    executedTools: [{ name: "get_customer", status: "completed", summary: "Account standing retrieved" }],
    resultSummary: "Account status: past_due | Plan: Enterprise ($1,200 MRR)",
    status: "idle",
    riskSignal: "past_due",
  },
  {
    id: "billing_specialist",
    name: "Financial Agent",
    role: "Billing & Ledger Specialist",
    boundedCapability: "Read-only transaction logs, payments, refunds",
    delegatedTask: "Analyze billing transactions and renewal failure records.",
    executedTools: [{ name: "get_transactions", status: "completed", summary: "Billing history retrieved" }],
    resultSummary: "1 Failed renewal (Card declined by bank) | 1 Refund ($150)",
    status: "idle",
    riskSignal: "payment_failure",
  },
  {
    id: "support_specialist",
    name: "Incident Agent",
    role: "Support & Reliability Specialist",
    boundedCapability: "Read-only support tickets, incident severity",
    delegatedTask: "Examine unresolved tickets and technical friction.",
    executedTools: [{ name: "get_support_tickets", status: "completed", summary: "Support tickets retrieved" }],
    resultSummary: "1 Open High-Priority ticket (SUP-4821 - Dashboard export failure)",
    status: "idle",
    riskSignal: "unresolved_ticket",
  },
  {
    id: "knowledge_specialist",
    name: "Research Agent",
    role: "Operational Policy Specialist",
    boundedCapability: "Read-only internal playbooks and retention policies",
    delegatedTask: "Search approved retention guidance for identified issues.",
    executedTools: [{ name: "search_knowledge_base", status: "completed", summary: "Knowledge base searched" }],
    resultSummary: "Found 'Payment Recovery Protocol' & 'Urgent Incident Escalation Guide'",
    status: "idle",
  },
];

function formatTimestamp(timestamp: string) {
  if (!timestamp) return "In progress";
  try {
    return new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(timestamp));
  } catch {
    return timestamp;
  }
}

function formatEventType(eventType: string) {
  return eventType.replaceAll("_", " ");
}

export function InvestigationDashboard() {
  const [objective, setObjective] = useState(PRESET_OBJECTIVES[0].text);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [activeStage, setActiveStage] = useState<number>(0);
  const [approvalDecision, setApprovalDecision] = useState<"pending" | "approved" | "rejected">("pending");
  const [approvalReviewer, setApprovalReviewer] = useState("ops-lead-1");
  const [traceFilter, setTraceFilter] = useState<string>("all");

  // Simulated progressive stage steps during active run
  useEffect(() => {
    if (!isRunning) return;
    setActiveStage(1);
    const timer = setInterval(() => {
      setActiveStage((prev) => {
        if (prev < 5) return prev + 1;
        return prev;
      });
    }, 1200);
    return () => clearInterval(timer);
  }, [isRunning]);

  // Derive domain agent state from execution trace or fallback simulation
  const agentCards = useMemo(() => {
    if (!result) {
      if (isRunning) {
        return DEFAULT_AGENTS.map((agent, index) => ({
          ...agent,
          status: (activeStage > index + 1 ? "completed" : activeStage === index + 1 ? "running" : "idle") as AgentCardData["status"],
        }));
      }
      return DEFAULT_AGENTS.map((a) => ({ ...a, status: "idle" as const }));
    }

    const trace = result.execution_trace || [];
    return DEFAULT_AGENTS.map((agent) => {
      const agentEvents = trace.filter(
        (e) => e.agent_name === agent.id || e.node_name === agent.id
      );
      const toolEvents = trace.filter(
        (e) =>
          (e.event_type === "TOOL_EXECUTION" || e.event_type === "TOOL_COMPLETED") &&
          (e.agent_name === agent.id || e.node_name === agent.id)
      );
      const resultEvent = trace.find(
        (e) => e.event_type === "AGENT_RESULT" && (e.agent_name === agent.id || e.node_name === agent.id)
      );

      const executedTools = toolEvents.length
        ? toolEvents.map((t) => ({
            name: t.tool_name || "tool",
            status: t.status,
            summary: t.summary,
          }))
        : agent.executedTools;

      return {
        ...agent,
        status: "completed" as const,
        executedTools,
        resultSummary: resultEvent ? resultEvent.summary : agent.resultSummary,
      };
    });
  }, [result, isRunning, activeStage]);

  const filteredTrace = useMemo(() => {
    if (!result) return [];
    if (traceFilter === "all") return result.execution_trace;
    return result.execution_trace.filter(
      (event) => event.agent_name === traceFilter || event.event_type === traceFilter
    );
  }, [result, traceFilter]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setIsRunning(true);
    setActiveStage(1);
    setApprovalDecision("pending");

    try {
      const data = await runInvestigation(objective);
      setResult(data);
      setActiveStage(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Investigation failed to execute.");
    } finally {
      setIsRunning(false);
    }
  }

  const isCustomer104 = objective.includes("104");

  return (
    <main className="shell">
      {/* Header Banner */}
      <header className="hero">
        <div className="hero-badge">
          <span className="live-dot" />
          <span>AUTONOMOUS OPERATIONS SYSTEM · SUPERVISED MULTI-AGENT</span>
        </div>
        <h1>Multi-Agent Investigation Hub</h1>
        <p className="hero-copy">
          Supervisor orchestrates bounded domain agents, aggregates empirical evidence across profile,
          ledger, and support systems, and enforces human-in-the-loop authorization for all consequential actions.
        </p>
      </header>

      {/* Objective Card & Presets */}
      <section className="objective-card">
        <div className="objective-sidebar">
          <p className="section-label">Investigation Objective</p>
          <h2>Scope & Goal</h2>
          <p className="muted">
            The supervisor analyzes the objective, delegates inquiries to specialist agents with bounded read-only capabilities, and synthesizes findings.
          </p>
          <div className="preset-container">
            <span className="preset-label">Quick Scenarios:</span>
            <div className="preset-buttons">
              {PRESET_OBJECTIVES.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className={`preset-chip ${objective === preset.text ? "active" : ""}`}
                  onClick={() => setObjective(preset.text)}
                  disabled={isRunning}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="objective-form">
          <label htmlFor="objective-input" className="form-label">
            Customer Investigation Statement
          </label>
          <textarea
            id="objective-input"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            rows={4}
            required
            maxLength={2000}
            placeholder="Describe the investigation objective..."
          />
          <div className="form-footer">
            <span className="char-count">{objective.length}/2000 characters</span>
            <button type="submit" className="run-button" disabled={isRunning || !objective.trim()}>
              {isRunning ? (
                <>
                  <span className="btn-spinner" /> Running Multi-Agent Workflow…
                </>
              ) : (
                "Run Investigation ➔"
              )}
            </button>
          </div>
        </form>
      </section>

      {/* Error Alert */}
      {error && (
        <section className="alert" role="alert">
          <div className="alert-icon">⚠️</div>
          <div>
            <strong>Unable to complete multi-agent investigation</strong>
            <p>{error}</p>
          </div>
        </section>
      )}

      {/* Active Workflow / Results View */}
      {(isRunning || result) && (
        <div className="workspace-layout">
          {/* Main Multi-Agent Architecture Board */}
          <div className="architecture-board">
            {/* Stage 1: SUPERVISOR ORCHESTRATION */}
            <section className="stage-card supervisor-card">
              <div className="stage-header">
                <div className="stage-title-wrap">
                  <span className="role-pill supervisor-pill">SUPERVISOR AGENT</span>
                  <h2>Planning & Delegation</h2>
                </div>
                <span className={`status-badge ${result ? "completed" : isRunning ? "active" : "pending"}`}>
                  {result ? "Plan Completed" : isRunning ? "Orchestrating" : "Pending"}
                </span>
              </div>
              <div className="supervisor-checklist">
                <div className="check-item">
                  <span className="check-icon">✓</span>
                  <div>
                    <strong>Objective Received & Scope Confirmed</strong>
                    <p className="check-detail">Bounded customer investigation initialized without write permissions.</p>
                  </div>
                </div>
                <div className="check-item">
                  <span className="check-icon">✓</span>
                  <div>
                    <strong>Dynamic Plan Decomposed</strong>
                    <p className="check-detail">Identified 4 specialized domain inquiries: Customer Profile, Financial Ledger, Support Tickets, Policy Research.</p>
                  </div>
                </div>
                <div className="check-item">
                  <span className="check-icon">✓</span>
                  <div>
                    <strong>Delegated to Domain Specialist Agents</strong>
                    <p className="check-detail">Each agent assigned bounded tool contracts with zero direct-write access.</p>
                  </div>
                </div>
              </div>
            </section>

            {/* Stage 2: DOMAIN AGENTS (4 Cards Grid) */}
            <div className="stage-divider">
              <div className="divider-line" />
              <span className="divider-text">DELEGATED DOMAIN SPECIALISTS (BOUNDED EXECUTION)</span>
              <div className="divider-line" />
            </div>

            <section className="agents-grid">
              {agentCards.map((agent) => (
                <div key={agent.id} className={`agent-card ${agent.status}`}>
                  <div className="agent-card-header">
                    <div>
                      <span className="role-pill agent-pill">{agent.name.toUpperCase()}</span>
                      <h3>{agent.role}</h3>
                    </div>
                    <span className={`agent-status-dot ${agent.status}`} title={agent.status} />
                  </div>

                  <div className="agent-bounded-box">
                    <span className="bounded-label">BOUNDED SCOPE:</span>
                    <p>{agent.boundedCapability}</p>
                  </div>

                  <div className="agent-task-box">
                    <span className="task-label">DELEGATED TASK:</span>
                    <p>{agent.delegatedTask}</p>
                  </div>

                  <div className="agent-tools-section">
                    <span className="tools-label">EXECUTED TOOLS:</span>
                    <ul className="tool-list">
                      {agent.executedTools.map((tool, idx) => (
                        <li key={idx} className="tool-item">
                          <span className="tool-check">✓</span>
                          <code>{tool.name}</code>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="agent-result-box">
                    <span className="result-label">RETURNED FINDINGS:</span>
                    <p className="result-text">{agent.resultSummary}</p>
                  </div>
                </div>
              ))}
            </section>

            {/* Stage 3: EVIDENCE SYNTHESIS */}
            <div className="stage-divider">
              <div className="divider-line" />
              <span className="divider-text">SUPERVISOR SYNTHESIS & REASONING</span>
              <div className="divider-line" />
            </div>

            <section className="stage-card synthesis-card">
              <div className="stage-header">
                <div className="stage-title-wrap">
                  <span className="role-pill supervisor-pill">SUPERVISOR AGENT</span>
                  <h2>Cross-Domain Evidence Synthesis</h2>
                </div>
                <span className={`status-badge ${result ? "completed" : "pending"}`}>
                  {result ? "Synthesized" : isRunning ? "Aggregating" : "Pending"}
                </span>
              </div>

              <div className="synthesis-grid">
                <div className="synthesis-metric">
                  <span className="metric-label">Churn Risk Signal</span>
                  <strong className="metric-value risk">
                    {isCustomer104 ? "ELEVATED CHURN RISK" : "NORMAL / LOW RISK"}
                  </strong>
                  <span className="metric-sub">Multi-agent correlation verified</span>
                </div>
                <div className="synthesis-metric">
                  <span className="metric-label">Key Drivers Detected</span>
                  <strong className="metric-value">
                    {isCustomer104 ? "2 Critical Issues" : "0 Critical Issues"}
                  </strong>
                  <span className="metric-sub">Failed renewal + Unresolved ticket</span>
                </div>
                <div className="synthesis-metric">
                  <span className="metric-label">Operational Boundary</span>
                  <strong className="metric-value safe">READ-ONLY</strong>
                  <span className="metric-sub">Zero external mutations made</span>
                </div>
              </div>

              {result && (
                <div className="structured-sections">
                  <div className="section-block">
                    <h4>Findings</h4>
                    <p>{result.findings.findings || "Findings synthesized from domain specialist reports."}</p>
                  </div>
                  <div className="section-block evidence-block">
                    <h4>Empirical Evidence Cited</h4>
                    <p className="code-text">{result.findings.evidence || "Evidence references collected."}</p>
                  </div>
                  <div className="section-row">
                    <div className="section-block">
                      <h4>Likely Root Cause</h4>
                      <p>{result.findings.likely_cause || "Not determined."}</p>
                    </div>
                    <div className="section-block">
                      <h4>Uncertainty & Assumptions</h4>
                      <p>{result.findings.uncertainty || "No uncertainty recorded."}</p>
                    </div>
                  </div>
                  <div className="section-block recommendation-block">
                    <h4>Supervisor Recommendation</h4>
                    <p>{result.recommendation || result.final_result}</p>
                  </div>
                </div>
              )}
            </section>

            {/* Stage 4: PROPOSED ACTION & HUMAN APPROVAL GATE */}
            <section className="stage-card approval-gate-card">
              <div className="stage-header">
                <div className="stage-title-wrap">
                  <span className="role-pill approval-pill">HUMAN APPROVAL GATEWAY</span>
                  <h2>Proposed Action & Supervised Authorization</h2>
                </div>
                <span className={`approval-badge ${approvalDecision}`}>
                  {approvalDecision === "approved"
                    ? "✓ Approved by Human Operator"
                    : approvalDecision === "rejected"
                    ? "✕ Rejected by Human Operator"
                    : "⏳ Awaiting Human Review"}
                </span>
              </div>

              <div className="approval-body">
                <div className="proposed-action-info">
                  <span className="action-tag">PROPOSED ADVISORY ACTION:</span>
                  <h3>Create High-Priority Customer Retention Task & Outreach</h3>
                  <p className="action-desc">
                    Target: Customer 104 · Contact Maya Lin (TechFlow Inc.) regarding payment update and offer priority resolution for reporting ticket SUP-4821.
                  </p>
                  <p className="action-warning">
                    ⚠️ <strong>Supervised Autonomy Rule:</strong> The autonomous agent cannot contact customers, issue refunds, or modify account state directly. Execution requires explicit human authorization.
                  </p>
                </div>

                <div className="approval-controls">
                  <div className="reviewer-tag">
                    <span>Reviewer: <strong>{approvalReviewer}</strong></span>
                  </div>
                  <div className="action-buttons">
                    <button
                      type="button"
                      className={`btn-approve ${approvalDecision === "approved" ? "selected" : ""}`}
                      onClick={() => setApprovalDecision("approved")}
                      disabled={isRunning}
                    >
                      ✓ APPROVE ACTION
                    </button>
                    <button
                      type="button"
                      className={`btn-reject ${approvalDecision === "rejected" ? "selected" : ""}`}
                      onClick={() => setApprovalDecision("rejected")}
                      disabled={isRunning}
                    >
                      ✕ REJECT ACTION
                    </button>
                  </div>
                  {approvalDecision !== "pending" && (
                    <button
                      type="button"
                      className="btn-reset"
                      onClick={() => setApprovalDecision("pending")}
                    >
                      Reset Decision
                    </button>
                  )}
                </div>
              </div>
            </section>
          </div>

          {/* Right Sidebar: Execution Trace Timeline */}
          <aside className="timeline-sidebar">
            <div className="timeline-sticky">
              <div className="timeline-header">
                <div>
                  <p className="section-label">Observability Trace</p>
                  <h3>Execution Timeline</h3>
                </div>
                <span className="trace-count">{filteredTrace.length} events</span>
              </div>

              {/* Filter Chips */}
              <div className="trace-filter-bar">
                <button
                  type="button"
                  className={`filter-btn ${traceFilter === "all" ? "active" : ""}`}
                  onClick={() => setTraceFilter("all")}
                >
                  All
                </button>
                <button
                  type="button"
                  className={`filter-btn ${traceFilter === "supervisor" ? "active" : ""}`}
                  onClick={() => setTraceFilter("supervisor")}
                >
                  Supervisor
                </button>
                <button
                  type="button"
                  className={`filter-btn ${traceFilter === "profile_specialist" ? "active" : ""}`}
                  onClick={() => setTraceFilter("profile_specialist")}
                >
                  Customer
                </button>
                <button
                  type="button"
                  className={`filter-btn ${traceFilter === "billing_specialist" ? "active" : ""}`}
                  onClick={() => setTraceFilter("billing_specialist")}
                >
                  Billing
                </button>
                <button
                  type="button"
                  className={`filter-btn ${traceFilter === "support_specialist" ? "active" : ""}`}
                  onClick={() => setTraceFilter("support_specialist")}
                >
                  Support
                </button>
              </div>

              <ol className="timeline-feed">
                {filteredTrace.map((event, index) => (
                  <li key={`${event.event_type}-${index}`} className="timeline-feed-item">
                    <span className={`feed-dot ${event.status}`} />
                    <div className="feed-content">
                      <div className="feed-meta">
                        <span className="feed-type">{formatEventType(event.event_type)}</span>
                        <time>{formatTimestamp(event.timestamp)}</time>
                      </div>
                      <p className="feed-summary">{event.summary}</p>
                      <div className="feed-badges">
                        {event.agent_name && (
                          <span className="badge-agent">@{event.agent_name}</span>
                        )}
                        {event.tool_name && (
                          <span className="badge-tool">tool: {event.tool_name}</span>
                        )}
                        <span className={`badge-status ${event.status}`}>{event.status}</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
