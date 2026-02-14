# Documentation Gap Analysis

**Generated**: 2026-02-14
**Source commands**: `contextcore docs audit`, `contextcore docs curate --gaps-only`

---

## Curate Gaps (persona-specific, 10 total — all HIGH priority)

| Persona | Gap | Capabilities lacking docs |
|---------|-----|--------------------------|
| **AI Agent** | Persistent memory undocumented | `contextcore.agent.persistent_memory` |
| **AI Agent** | A2A protocol undocumented | `a2a.server`, `a2a.client`, `a2a.task_adapter`, `a2a.content_model`, `handoff.input_request`, `api.unified` |
| **Compliance** | Audit trail undocumented | `audit.full_trail`, `audit.time_queries`, `audit.evidence_linking` |
| **Developer** | Auto-derived status undocumented | `status.auto_derive` |
| **Developer** | Governance gates undocumented (for developer) | `pipeline.check_pipeline`, `pipeline.diagnose` |
| **Eng Leader** | Portfolio dashboards undocumented | `dashboard.portfolio`, `dashboard.project_drilldown` |
| **Operator** | Incident context undocumented | `alert.enrichment`, `incident.context` |
| **PM** | Deliverable validation undocumented | `tracker.deliverable_validation` |
| **PM** | Unified source of truth undocumented | `manifest.load`, `manifest.distill_crd`, `manifest.validate` |
| **PM** | Contract-first planning undocumented | `manifest.export_provenance` |

---

## Audit Gaps (capability-centric, 28 cluster gaps across 33 capabilities)

### High priority (2 clusters)

- `contextcore.insight.*` — missing **adr** and **design** (importance 0.61)

### Medium priority (21 clusters) — top themes

| Cluster | Missing types | Key rationale |
|---------|---------------|---------------|
| `docs.*` (4 caps) | adr, design, operational, reference | CLI commands without operational guide; no benefit linkage |
| `manifest.*` (7 caps) | requirements, design, adr, operational, reference | `manifest.load` has no requirements doc; anti-patterns not captured |
| `pipeline.*` (2-4 caps) | adr, design, reference | Anti-patterns and critical personas not documented |
| `handoff.*` (1-3 caps) | adr, design | Risk flags; beta maturity with complex inputs |
| `a2a.*` (1 cap) | adr, design, operational | Beta maturity; critical personas |
| `insight.*` (2 caps) | reference, requirements | 8 input properties without requirements doc |
| `code_generation.*` | adr, design | Anti-patterns not captured in decision records |

### Low priority (5 clusters)

- `audit.*`, `dashboard.*`, `api.*`, `aos.*`, `guidance.*` — mostly missing reference docs

---

## Overall missing doc type breakdown

| Doc type | Capabilities needing one |
|----------|--------------------------|
| **reference** | 21 |
| **design** | 17 |
| **adr** | 16 |
| **operational** | 10 |
| **requirements** | 7 |

---

## Cross-command overlap: highest-impact documents to write

Documents that close gaps in **both** curate and audit simultaneously:

| Suggested document | Curate gaps closed | Audit clusters closed |
|--------------------|--------------------|-----------------------|
| A2A design/reference doc | AI Agent persona (6 capabilities) | `a2a.*` adr, design, operational |
| Insight design + ADR | — | `insight.*` adr, design (highest priority cluster) |
| Manifest operational guide | PM persona (3 gaps) | `manifest.*` operational, reference |
| Pipeline reference doc | Developer persona (governance gates) | `pipeline.*` reference |
| Dashboard reference doc | Eng Leader persona (portfolio) | `dashboard.*` reference |
| Audit trail reference doc | Compliance persona (3 capabilities) | `audit.*` reference |

---

## Regenerate this analysis

```bash
# Curate gaps
contextcore docs curate --gaps-only

# Audit gaps
contextcore docs audit

# Machine-readable for automation
contextcore docs curate --gaps-only --format json > curate-gaps.json
contextcore docs audit --format json > audit-gaps.json
```
