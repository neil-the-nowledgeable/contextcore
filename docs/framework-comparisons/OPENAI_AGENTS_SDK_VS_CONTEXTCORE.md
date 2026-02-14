# OpenAI Agents SDK vs ContextCore

## Strengths and weaknesses (both)

### OpenAI Agents SDK strengths (its realm: platform-native agent runtime)
- Fast path for building tool-using agents on OpenAI stack.
- Strong platform integration and good developer velocity.
- Built-in runtime features can reduce boilerplate.

### OpenAI Agents SDK weaknesses (relative to governance)
- Vendor-centric runtime can reduce portability across ecosystems.
- Governance boundaries and policy semantics need external discipline.
- Cross-system provenance model is not the core abstraction.

### ContextCore strengths (its realm: governance + observability)
- Runtime-agnostic governance contracts and phase gates.
- Strong traceability for handoffs and execution state transitions.
- Better fit for multi-tool, multi-stack control-plane consistency.

### ContextCore weaknesses (relative to platform runtime convenience)
- Less turnkey runtime features than platform-native SDKs.
- Requires integration overlays for vendor-specific events.

## What to model in ContextCore (without duplicating OpenAI runtime)
- Mapping conventions from tool calls to `handoff.capability_id`.
- Conversation lineage normalization (`gen_ai.conversation.id` -> task/handoff context).
- Evaluation evidence semantics (`evidence.type=eval_grade`, policy-driven gate impact).

## Quick wins (1-2 weeks)
- Add OpenAI Agents SDK integration pattern doc.
- Add conversation-id and eval evidence conventions.
- Add one validation middleware example for outbound/inbound handoffs.

## All-upside / low-downside actions (do now)
- Standardize vendor event normalization into existing contracts.
- Keep execution within OpenAI SDK; use ContextCore only for governance evidence.
- Add portability guardrails in docs (avoid vendor-specific fields in core contracts).

