# DSPy vs ContextCore

## Strengths and weaknesses (both)

### DSPy strengths (its realm: programmatic prompt/model optimization)
- Strong signature-driven approach for structured LLM programs.
- Good optimization/tuning workflows for output quality.
- Useful for repeatable prompt/program improvement loops.

### DSPy weaknesses (relative to governance)
- Not a full multi-agent governance/control-plane system.
- Cross-stage provenance and boundary policies are not first-class.
- Operational task/subtask lifecycle visibility requires extra instrumentation.

### ContextCore strengths (its realm: governance + observability)
- Strong lifecycle tracking and boundary decision semantics.
- Better fit for operational execution accountability.
- Contracts make cross-agent coordination explicit and auditable.

### ContextCore weaknesses (relative to optimization ergonomics)
- No native equivalent to DSPy-style optimization abstractions.
- Less direct support for experiment-oriented prompt optimization loops.

## What to model in ContextCore (without duplicating DSPy)
- Optimization governance attributes: `optimization.run_id`, `optimization.metric`, `prompt.version`.
- Gate semantics for promotion decisions (when optimized outputs are deployable).
- Evidence typing for optimization reports (`evidence.type=optimization_report`).

## Quick wins (1-2 weeks)
- Add DSPy integration pattern note with contract mappings.
- Add optional optimization attributes in semantic conventions.
- Add gate template for optimization pass/fail thresholds.

## All-upside / low-downside actions (do now)
- Add optimization evidence conventions without changing runtime.
- Keep DSPy optimization loops external; gate deployment with ContextCore policy.
- Add query for failed optimization promotions by phase.

