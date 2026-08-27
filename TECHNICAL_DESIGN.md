# Autonomous Operations Agent — Technical Design

## 1. Problem statement

Customer operations teams investigate potential customer issues by gathering facts from several systems: customer profiles, transaction history, support tickets, and internal knowledge. This work is manual, inconsistent, and time-consuming. An investigator must determine which sources are relevant, interpret incomplete or conflicting results, decide whether more evidence is needed, and produce an actionable recommendation.

This prototype demonstrates a bounded autonomous agent that accepts a high-level investigation objective—for example, “Investigate customer 104 and determine why they may be at risk of churn”—then plans and performs a read-only investigation before returning an evidence-based recommendation for human review.

## 2. Solution statement

Build a Python service around a LangGraph state machine. The graph converts an objective into a scoped investigation, chooses from a small set of read-only domain tools, records observations as evidence, evaluates whether the evidence is sufficient, and produces a structured recommendation.

The first version uses deterministic mock or adapter-backed tools and a hosted LLM for planning, interpretation, and synthesis. It makes no external changes and does not contact customers. Recommendations identify actions that a human may approve and execute elsewhere.

## 3. Functional requirements

1. Accept a natural-language investigation objective and an optional request identifier.
2. Extract or confirm the target customer identifier and the investigation goal.
3. Build a focused investigation plan from the available read-only tools.
4. Query customer profile, transactions, support tickets, and internal knowledge when relevant.
5. Capture each tool invocation, normalized result, timestamp, and source as traceable evidence.
6. Assess whether more evidence is needed after each observation.
7. Handle unavailable, empty, malformed, or conflicting tool results without fabricating facts.
8. Stop when evidence is sufficient, an investigation limit is reached, or no safe next step exists.
9. Return a structured final recommendation containing:
   - customer and objective;
   - risk level and confidence;
   - evidence and source references;
   - likely churn drivers;
   - recommended next actions;
   - assumptions, missing information, and escalation needs;
   - explicit human-approval requirement for consequential actions.
10. Persist or expose an execution trace suitable for debugging and audit in the prototype.

## 4. Non-functional requirements

- **Safety:** All tools are read-only. The agent must not change customer data, issue refunds, alter subscriptions, create tickets, send messages, or contact customers.
- **Bounded execution:** Enforce a maximum graph step count, tool-call count, retry count, and time budget per investigation.
- **Traceability:** Every conclusion must be linked to observed tool output or be marked as an inference or assumption.
- **Structured contracts:** Use Pydantic models for objectives, tool inputs/outputs, state, evidence, and recommendations.
- **Reliability:** Validate tool outputs, handle expected failures explicitly, and produce a partial result when safe rather than failing silently.
- **Security and privacy:** Minimize data supplied to the model; redact sensitive fields from logs; authenticate future API callers; and avoid storing unnecessary customer data.
- **Testability:** Keep graph nodes and tool adapters independently testable with deterministic fixtures.
- **Observability:** Emit structured logs and correlation IDs. Record graph transitions, tool calls, errors, and stop reasons.
- **Maintainability:** Prefer small modules, explicit interfaces, and configuration over extra infrastructure or premature abstractions.

## 5. Agent responsibilities

The agent is responsible for reasoning over the objective and the evidence, not for directly owning external systems.

- Interpret the objective and identify the customer and investigation intent.
- Select the next appropriate read-only tool from the permitted tool registry.
- Form valid tool inputs within the scope of the objective.
- Convert tool observations into concise evidence items.
- Identify gaps, contradictions, and uncertainty.
- Decide whether to continue, stop, or escalate based on the investigation policy.
- Synthesize a structured, evidence-based recommendation.
- Clearly distinguish observed facts from model inferences.
- Respect every autonomy and execution bound supplied in configuration.

## 6. Tool responsibilities

Tools provide controlled access to specific information sources. They do not decide strategy or produce final business recommendations.

| Tool | Responsibility | Example input | Example output |
| --- | --- | --- | --- |
| `get_customer_profile` | Retrieve customer identity, segment, plan, tenure, account status, and permitted profile attributes. | `customer_id` | Normalized customer profile or not-found result. |
| `get_transaction_history` | Retrieve a bounded recent transaction/subscription-payment history. | `customer_id`, date range | Transactions, payment failures, refunds, and aggregate summary. |
| `search_support_tickets` | Retrieve recent support issues for the target customer. | `customer_id`, limit | Ticket summaries, status, severity, and timestamps. |
| `search_knowledge_base` | Retrieve approved internal guidance relevant to discovered issues. | Search query, limit | Article excerpts, identifiers, and relevance metadata. |

Each tool must:

- use a Pydantic input and output model;
- validate and normalize source data;
- return a typed error or empty result instead of an ambiguous failure;
- apply source-specific authorization and data minimization;
- enforce pagination and result limits;
- be idempotent and read-only; and
- include source metadata sufficient to cite an evidence item.

Early development should implement these as fixture-backed adapters. Replacing fixtures with real system clients must preserve the same tool contracts.

## 7. Autonomy boundaries

The agent is allowed to investigate within the stated objective and make recommendations. It is not allowed to take consequential action.

### Allowed

- Read customer data available through approved tools.
- Search internal knowledge related to evidence already discovered.
- Perform bounded follow-up queries needed to resolve an evidence gap.
- Calculate or summarize risk signals from retrieved data.
- Recommend reversible or consequential actions for human review.

### Prohibited

- Writing to any system of record.
- Sending email, chat, SMS, or other outbound communications.
- Issuing refunds, credits, discounts, plan changes, or account-status changes.
- Creating, updating, assigning, or closing support tickets.
- Querying customers outside the objective’s authorized scope.
- Claiming facts not supported by observations.
- Continuing past configured execution limits.

### Human approval gate

The final output may contain `proposed_actions`, but every action is advisory. Any future action-capable tool must sit outside the investigation graph and require an explicit human approval event with the reviewed recommendation, action parameters, approver identity, and audit record.

## 8. Proposed architecture

```text
Objective
   |
   v
Objective validation and scope
   |
   v
LangGraph investigation workflow
   |-- plan next inquiry ----> read-only tool registry
   |                               |-- customer profile adapter
   |                               |-- transaction adapter
   |                               |-- support-ticket adapter
   |                               `-- knowledge-base adapter
   |                                      |
   `----------- observation/evidence <---'
   |
   v
Sufficiency and policy check -- continue / stop / escalate
   |
   v
Structured recommendation (Pydantic model)
```

### LangGraph workflow nodes

1. **`validate_objective`** — parse the objective, validate target scope, and initialize state.
2. **`plan_next_step`** — use the available evidence and policy to choose the next permitted inquiry or stop.
3. **`execute_tool`** — invoke exactly one validated read-only tool through the registry.
4. **`record_observation`** — normalize the result into evidence and update the trace.
5. **`evaluate_sufficiency`** — determine whether the evidence supports a recommendation, requires a follow-up, or requires escalation.
6. **`compose_recommendation`** — generate the final structured output from evidence only.
7. **`finalize`** — attach stop reason, limits consumed, and approval notice.

Conditional edges route from `evaluate_sufficiency` to `plan_next_step`, `compose_recommendation`, or `finalize` for an unable-to-proceed result. A separate policy guard runs before tool execution and blocks unknown, write-capable, out-of-scope, or over-limit calls.

The LLM may propose the next tool and synthesize findings, but deterministic validators enforce tool schemas, allowed-tool policy, scope, and limits. Keep prompts focused on the current state and compact evidence summaries rather than raw source dumps whenever possible.

## 9. Agent state design

Use a typed LangGraph state backed by Pydantic-compatible models. Keep raw source payloads out of prompts unless needed and retain only approved, bounded data in state.

```text
InvestigationState
├── request_id: str
├── objective: InvestigationObjective
├── customer_id: int | None
├── status: pending | investigating | complete | escalated | blocked
├── plan: list[PlannedStep]
├── current_step: PlannedStep | None
├── observations: list[ToolObservation]
├── evidence: list[EvidenceItem]
├── open_questions: list[str]
├── tool_calls: list[ToolCallRecord]
├── limits: ExecutionLimits
├── stop_reason: str | None
├── errors: list[InvestigationError]
└── recommendation: InvestigationRecommendation | None
```

### Key model expectations

- `InvestigationObjective`: original text, target customer ID, authorized scope, and desired outcome.
- `PlannedStep`: selected tool, rationale, validated input, and the question it is intended to answer.
- `ToolObservation`: tool name, status, normalized output, source reference, and retrieval time.
- `EvidenceItem`: factual statement, source references, relevance to churn risk, and confidence. Inferences must be labelled as such.
- `ExecutionLimits`: maximum steps, tool calls, retries, and elapsed time.
- `InvestigationRecommendation`: risk assessment, drivers, evidence, proposed actions, missing information, approval requirement, and final confidence.

State updates should be additive for observations, evidence, tool calls, and errors. Nodes should not mutate external systems or overwrite past evidence. A reducer or explicit merge function should preserve the chronological trace.

## 10. Proposed project structure

```text
.
├── README.md
├── TECHNICAL_DESIGN.md
├── pyproject.toml
├── src/
│   └── operations_agent/
│       ├── __init__.py
│       ├── config.py
│       ├── models/
│       │   ├── objective.py
│       │   ├── evidence.py
│       │   ├── recommendation.py
│       │   ├── state.py
│       │   └── tools.py
│       ├── graph/
│       │   ├── workflow.py
│       │   ├── nodes.py
│       │   └── policy.py
│       ├── tools/
│       │   ├── registry.py
│       │   ├── customer_profile.py
│       │   ├── transactions.py
│       │   ├── support_tickets.py
│       │   └── knowledge_base.py
│       ├── services/
│       │   ├── planning.py
│       │   ├── evidence.py
│       │   └── recommendation.py
│       └── observability.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── docs/
    └── decisions/
```

Do not create the FastAPI or Next.js layers yet. Add an API module only after the core graph and tool contracts have stable tests. Add a frontend only after the API has an agreed request/result contract.

## 11. Milestone plan

### Milestone 1 — Domain contracts and fixture data

- Define Pydantic models for objectives, tool contracts, evidence, state, limits, and recommendations.
- Create representative fixture data for at least one at-risk and one low-risk customer.
- Write unit tests for validation and normalization.

**Exit criterion:** typed data contracts and fixtures are stable and tested without an LLM.

### Milestone 2 — Read-only tool adapters

- Implement fixture-backed versions of the four tools.
- Add a tool registry that permits only declared read-only tools.
- Test success, no-result, malformed result, and source-failure paths.

**Exit criterion:** tools return predictable typed results and cannot perform writes.

### Milestone 3 — Bounded investigation graph

- Implement the LangGraph nodes, transitions, policy guard, limits, and trace collection.
- Use a simple deterministic planner first; then introduce the hosted LLM behind a narrow planning/synthesis interface.
- Test normal, incomplete-data, conflicting-data, and over-limit investigations.

**Exit criterion:** the graph completes safely and deterministically under configured bounds.

### Milestone 4 — Evidence-based recommendations

- Implement structured recommendation generation and evidence citation checks.
- Ensure consequential recommendations include the approval requirement.
- Add scenario-based tests for churn-risk explanations and unsupported-claim prevention.

**Exit criterion:** outputs are structured, traceable, and safe for human review.

### Milestone 5 — Operational hardening

- Add structured logs, redaction, configuration, retries, and evaluation fixtures.
- Define a small quality rubric: tool-selection accuracy, evidence grounding, appropriate stopping, and policy compliance.
- Run repeatable evaluation cases against the hosted model.

**Exit criterion:** prototype behavior is observable, measurable, and suitable for a demo.

### Milestone 6 — API and user interface (later)

- Add a minimal FastAPI endpoint to submit objectives and retrieve results/traces.
- Add a minimal Next.js review interface that displays evidence, confidence, and proposed actions.
- Keep approval as a human workflow; do not connect action execution until a separate design is approved.

**Exit criterion:** users can initiate and review investigations without expanding the agent’s autonomy.
