---
name: incident-triage
description: |
  Investigate a production or dev problem in a Techcoop service from symptom to root cause, using SigNoz (metrics, logs, traces), then source code, then hosts and databases, and report only what was measured. Use when the user says "investigate the root cause", "why is X failing / slow / 500ing", "check the logs for dev", "what's the latency of X", "is anyone using X", "the service is crash-looping", or reports an alert, an error, or a broken page. Use it even when the user only asks for one number (latency, error rate, usage): the gotchas below are about getting that number right.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Monitor
  - ToolSearch
  - AskUserQuestion
---

# incident-triage

Go from the outside in, and let each step narrow the next:
**symptom → signal (SigNoz) → causal error → code/config → host/DB.**
Don't start at the host, and don't theorise from code before you've seen the error.

Load what you need with ToolSearch first: `signoz_*`, and `dokploy-mcp__*` / `jenkins_*` if a deploy is involved. For DB access use `scripts/db-tunnel.sh` from `techcoop-infrastructure` (read-only SELECTs; ask before anything that writes). For hosts use `scripts/remote.sh <host>` from the same repo. Don't say a source is out of reach until you've checked these.

## 1 — Pin the symptom

- Which service, which environment, since when, and for whom. Get one concrete failing request or page.
- Reproduce it if you can: the endpoint with `curl`, or the page in the browser. One authenticated browser pass on `farmhub-dev3` isolated a single 500 from `OrderService/ListOrders` while auth and every other call were fine. That took minutes; reading code would have taken hours.
- If a deploy happened recently, note its time and ref. Before concluding a bug is unfixed, `git fetch` and check `origin/main`: the fix may already have landed.

## 2 — Query SigNoz with a narrow filter

**Discover before you filter.** Field keys and service names differ by signal and workspace:

1. `signoz_list_services` (or `signoz_get_field_values` on `service.name`) gives the exact service name, e.g. `cerify-prod`.
2. `signoz_get_field_keys` for the signal and context you will filter on. Attribute keys are `attribute.<x>` (singular); `attributes.<x>` silently matches nothing.
3. Then query with `service.name` plus a bounded time window.

**Pick the signal that actually carries the data:**

- **Latency** usually lives in **metrics**, not traces. FarmHub chat latency is `chat_turn_duration_seconds` / `chat_agent_duration_seconds`; trace search alone missed it. Use `signoz_list_metrics` to find the metric.
- **Errors and start-up problems** live in logs: `signoz_search_logs` for the service, filtered on severity or a message fragment.
- **One slow or failed request** lives in traces: `signoz_search_traces`, then `signoz_get_trace_details`.

**Metric traps:**

- Use the aggregation that fits the metric type. A `monotonic` counter rejects `timeAggregation: sum`; use `rate` or `increase`.
- A name ending in `.bucket` is a histogram bucket. Ask for a percentile on the histogram itself and check the returned series makes sense before quoting a p95.
- An **empty or invalid query is not evidence of zero activity**. A wrong metric name, field context, time window or aggregation all look like "no data". Before reporting "unused" or "no traffic", cross-check with a second metric or source. Azure APIM's `TotalRequests` read 0 while `Requests` showed 37,740 over 30 days.
- Convert SigNoz timestamps (Unix ms) with a date function, never in your head. Use the `webUrl` values it returns as links, verbatim.

## 3 — Find the causal error

The first error in the log is often a symptom. Follow it back to the one that starts the chain, then read the code or config it points to. Example: FarmGate's `pq: invalid input syntax for type json` traced to a column written as text and read as JSONB. The code plus the live schema proved it; neither did alone.

## 4 — Host and database, only once narrowed

- Containers: status, restart count, recent logs, ports, mounts (Dokploy `docker-*` tools, or `scripts/remote.sh`).
- DB: the table or column the error names, migration version and dirty state. `Dirty database version 42` against a repo whose migrations stop at 34 is its own finding: something else migrated that database. Don't pin it on the latest change.
- Read-only by default. Restarts, migrations, data fixes: propose them, then wait for a yes.

## 5 — Report what was measured

```
incident-triage — <service> / <env>
  symptom:     <what fails, for whom, since when>
  evidence:    <query/log/trace → what it showed>  (one line each, with webUrl)
  root cause:  <stated as measured | "likely": what would confirm it>
  fix:         <proposed change, or the PR/commit if done>
  not checked: <anything you could not reach, and why>
```

Keep "measured" and "inferred" apart. If the user pushes back with live evidence, update the conclusion and say what changed. Don't defend the earlier inference.
