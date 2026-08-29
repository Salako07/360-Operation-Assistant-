# Stakeholder demonstration: Customer 104 churn investigation

## Purpose

Demonstrate a bounded autonomous investigation that selects read-only tools, gathers evidence, produces a recommendation, and stops before any consequential customer action.

**This is a prototype and is not production-ready.**

## Demonstration objective

Enter this objective in the web interface:

> Investigate customer 104 and determine why they may be at risk of churn. Provide an evidence-based recommendation.

## What stakeholders should observe

1. The interface accepts one high-level objective rather than a fixed sequence of source-system queries.
2. The execution trace records `OBJECTIVE_RECEIVED`, followed by visible agent and plan events.
3. The agent independently selects relevant approved tools. A typical run queries the customer profile, transactions, and support tickets; it may then search the knowledge base for approved guidance.
4. Each tool execution is shown by a `TOOL_STARTED` and `TOOL_COMPLETED` event. The timeline reports tool names and result categories—not private reasoning or raw source data.
5. The plan is created and revised as the investigation progresses. Completed steps are retained in state for inspection.
6. Customer 104 evidence normally includes a past-due account, a declined renewal payment, a service-credit refund, and an unresolved high-priority reporting-reliability ticket (`SUP-4821`).
7. The final result separates findings, evidence, likely cause, recommendation, and uncertainty.
8. The UI shows the hypothetical action “Send a retention outreach to customer 104” as **Not executed** and **Awaiting human approval**.

## Demonstration flow

1. Start the FastAPI backend with the configured hosted-model environment variables.
2. Start the Next.js frontend after setting its `NEXT_PUBLIC_API_BASE_URL` to the backend URL.
3. Open the frontend in a browser and submit the demonstration objective.
4. Review the visible timeline and completed-tool chips while the request runs.
5. Review the final evidence and recommendation.
6. Point out that the recommendation may suggest outreach, billing review, or engineering escalation, but the agent cannot send outreach, issue credits, alter an account, or contact a customer.
7. Use the proposed-action card to explain the separate LangGraph approval workflow. A human decision is required before any future action-execution service can run.

## Script-only alternative

The same live investigation can be run by executing [examples/demo_customer_104.py](../examples/demo_customer_104.py) after supplying the hosted-model environment variables. It prints the visible plan, safe execution trace, final recommendation, and unexecuted proposed action.

## Architecture walkthrough

```text
Next.js dashboard
  -> FastAPI POST /agent/run
    -> application service
      -> LangGraph customer-investigation workflow
        -> configured hosted chat model
        -> allowlisted read-only tools
      -> explicit state, result, and safe execution trace
    -> typed HTTP response
  -> dashboard timeline and recommendation view
```

## Known limitations and failure cases

| Area | Current prototype behavior | Needed for a production system |
| --- | --- | --- |
| Frontend updates | Shows lightweight local progress until the synchronous API response arrives, then shows the recorded trace. | Server-sent events or WebSockets with durable progress events. |
| Data sources | Uses deterministic local in-memory fixtures. | Authorized integrations with CRM, billing, support, product analytics, and knowledge systems. |
| Approval | Uses an in-memory LangGraph checkpoint and no action executor. | Durable approval queues, policy enforcement, RBAC, immutable audit records, and an idempotent action service. |
| LLM output | Requires prompt-defined labelled sections. | Evaluation gates, schema-constrained output, model monitoring, and human sampling. |
| Errors | Uses bounded retries, timeouts, and graceful terminal states. | Provider circuit breakers, distributed rate limiting, alerting, dead-letter handling, and SLOs. |
| Timeouts | Stops waiting for blocking calls. | Provider- and client-level cancellation support; a thread cannot safely terminate a blocked third-party call. |

## Security considerations

- Do not commit `.env` files, API keys, customer records, or production connection strings.
- The public API response exposes only safe execution-trace metadata, not chain-of-thought or raw tool results.
- The current prototype has no authentication, tenant isolation, authorization, or persistent audit storage.
- Production deployment needs least-privilege source-system credentials, secret management, encryption, PII classification and redaction policy, API authentication, request authorization, and security monitoring.

## Scalability considerations

- The FastAPI endpoint is synchronous and invokes an LLM inline; it is suitable only for low-volume demonstrations.
- Production deployments need asynchronous job handling, horizontal workers, durable graph checkpoints, request queues, backpressure, caching where permitted, and per-tenant concurrency limits.
- Tool adapters need pagination, batching, rate-limit handling, and source-specific retry/circuit-breaker policies.
- Audit and execution-trace events should be sent to scalable, access-controlled observability storage.

## Moving from hosted LLM to self-hosted vLLM

The application depends on the LangChain chat-model abstraction. vLLM can use the same model factory when it exposes an OpenAI-compatible endpoint:

- set `LLM_PROVIDER=openai_compatible`;
- set `LLM_BASE_URL` to the vLLM `/v1` endpoint;
- set `LLM_MODEL` to the served model name;
- configure `LLM_API_KEY` if the vLLM deployment requires one.

Before switching, validate tool-call compatibility, context-window behavior, JSON/schema adherence, latency and timeout settings, capacity planning, model safety behavior, and the evaluation scenarios. The integration is replaceable, but quality and operational characteristics are model-specific.
