# Architecture Decision Memo

## Decision

I would ship the **single-agent architecture** as the MVP. It gathers the same evidence, applies the same deterministic procurement controls and produced the same quality score as the staged design, with lower latency and fewer model calls.

## Evidence

Both architectures were tested on the same six public cases. Each case was scored on four criteria: correct next action, grounded evidence, policy compliance and correct human escalation.

| Metric | Single agent | Staged / 2-agent |
|---|---:|---:|
| Cases passing all quality criteria | 6/6 | 6/6 |
| Quality checks passed | 24/24 | 24/24 |
| Average latency | 1.53 s | 2.03 s |
| Average LLM calls | 1.0 | 1.7 |
| Average tool calls | 5.0 | 5.0 |
| Policy or grounding failures | 0 | 0 |

The staged version was approximately **33% slower** without improving measured quality. Two reviewer calls were unavailable during evaluation; the deterministic safety layer preserved the correct result, demonstrating graceful degradation but also showing the extra dependency introduced by staging.

## Trade-offs

The reviewer agent can challenge unsupported claims and may become useful for ambiguous, high-risk requests. However, in this bounded workflow it repeated controls already enforced by the policy engine. It adds latency, model usage, another failure point and more traces to inspect. The single agent remains explainable because each recommendation cites tool evidence, while approvals and risk flags are produced by deterministic rules rather than model judgement.

## Risks and limitations

The evaluation uses six synthetic cases and a static data snapshot, not production traffic. Semantic matching for overlapping tools is deliberately lightweight. Before production use, I would test more ambiguous requests, measure provider cost and availability, connect a real approval system, add access controls and monitor human overrides. A specialist reviewer should remain mandatory when evidence is missing, stale, conflicting or sensitive.

## Why this is the right MVP

The client problem is not “use multiple agents”; it is helping procurement reviewers reach a safe, evidence-backed next action faster. One agent plus five visible tools, deterministic policy checks, transparent uncertainty and human approval solves that problem with less operational complexity. I would keep the staged architecture behind an experiment flag and promote it only if broader evaluation shows a measurable quality gain.
