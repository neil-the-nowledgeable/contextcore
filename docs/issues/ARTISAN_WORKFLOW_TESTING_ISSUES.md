# Artisan Workflow Testing Issues

This document captures issues affecting Artisan workflow testing and reliability, split into:

1) what we observed in this session first, and
2) additional issues evidenced in other project sources.

---

## 1) Issues Observed In This Session (First)

- **Pipeline model omitted `init` as a first-class step**  
  The prior version of `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` started at export and did not represent `contextcore install init` in the top-level flow. This made the operational model incomplete for testing/debugging.

- **Gate-0 validation was underrepresented in troubleshooting flow**  
  Without `init` in the main flow, early checks (installation completeness verification, OTLP endpoint correctness, initial telemetry flush) were not explicit, which can delay root-cause analysis when Artisan output is wrong or stale.

- **Documentation/process drift risk (fixed in-session)**  
  We updated the guide to a 4-step flow (`init -> export -> plan ingestion -> artisan`), expanded troubleshooting to include Init checks, and aligned quick commands accordingly. This was a process/documentation issue that directly impacts testing accuracy.

- **No direct Artisan runtime execution in this session**  
  In this session, we did not run the Artisan workflow itself. Findings here are documentation/process correctness issues that influence testing quality rather than a fresh runtime failure reproduction.

---

## 2) Additional Evidence From Other Sources (Separate Listing)

| Issue | Why it matters for Artisan testing | Evidence source(s) | Category |
| --- | --- | --- | --- |
| Seed lacks explicit export linkage | Artisan can run with incomplete context if seed does not carry artifact manifest/CRD references | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Export linkage: 2/5`) | input-quality |
| Missing artifact type -> parameter mapping | Generators may not know exact parameter contracts per artifact type | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Artifact schema: 1/5`) | input-quality |
| Plan/context artifact count mismatch (77 vs 6) | Causes scope confusion and potential over/under-generation | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Coverage gaps: 3/5`) | input-quality |
| Output path conventions missing in seed | Generated files can land in wrong or inconsistent directories | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Gap 5: No Output Path Conventions`) | integration |
| Semantic conventions not propagated to seed | Dashboards/rules may be generated with inconsistent query/label conventions | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Gap 6: Semantic Conventions Not in Seed`) | integration |
| Provenance chain is weak across boundaries | Harder to prove freshness/integrity from export through finalize | `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md` (`Provenance chain: 2/5`) | reliability |
| Stale/mismatched checksums in handoffs | Pipeline can silently operate on outdated data | `docs/MANIFEST_TROUBLESHOOTING.md`, `docs/MANIFEST_EXPORT_TROUBLESHOOTING.md`, `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` | reliability |
| Coverage threshold failures during export | Under-specified artifact contracts block downstream testing unless coverage is corrected | `docs/MANIFEST_EXPORT_TROUBLESHOOTING.md`, `docs/MANIFEST_TROUBLESHOOTING.md` | process |
| Routing/parsing drops artifacts | Missing features in plan lead to missing tasks/artifacts in Artisan | `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` (coverage.gaps vs parsed features checks) | routing |
| Finalize may report partial/failed despite pipeline completion | “Run completed” can hide incomplete artifact generation | `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` (FINALIZE status rollup checks) | observability |
| Prime integration can overwrite uncommitted local changes | Can invalidate test baselines and destroy in-progress validation work | `docs/plans/PRIME_CONTRACTOR_GIT_SAFETY.md` | reliability |
| External SDK integration brittleness (`None` values, missing providers) | Can fail ingestion/orchestration before meaningful Artisan testing begins | `2026-01-22_lessons_learned.md` | reliability |
| Need for explicit troubleshooting playbooks | Recurring issues require standardized runbooks to reduce time-to-diagnose | `docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md` (Suggestion 17) | documentation |

---

## 3) Recurring Patterns

- **Integrity and freshness are the dominant failure mode**: checksum/provenance drift and stale files recur across multiple docs.
- **Context propagation is incomplete**: artifact schema, semantic conventions, and output conventions are not always carried cleanly into seed/handoff.
- **Translation loss between stages**: coverage gaps and route/parse mismatches indicate artifacts can disappear between export and implementation.
- **Operational safety gaps increase test noise**: local overwrite risk and SDK dependency brittleness create false negatives during workflow testing.
