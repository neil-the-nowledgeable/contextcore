# Pipeline-Innate Requirements: Observability

**Scope:** These requirements apply to ALL projects processed through the ContextCore Capability Delivery Pipeline. They are inherited automatically and satisfied by artifact generation, not by plan features.

**Label:** `pipeline-innate` (appears in `requirements_hints[].labels` in `onboarding-metadata.json`)

---

## REQ-CDP-OBS-001: Service Level Objectives

**Priority:** P1
**Artifact:** `slo_definition`

**Acceptance criteria:**
- Project defines an availability target (e.g., `99.9%`)
- Project defines an error budget derived from the availability target
- SLO definition artifact is generated with availability and error budget thresholds
- Manifest `spec.requirements.availability` and `spec.requirements.errorBudget` are populated

**Acceptance anchors:**
- `spec.requirements.availability`
- `spec.requirements.errorBudget`

---

## REQ-CDP-OBS-002: Service Dashboard

**Priority:** P1
**Artifact:** `dashboard`

**Acceptance criteria:**
- A Grafana service dashboard is generated for each deployment target
- Dashboard includes panels derived from `spec.requirements` (availability, latency, throughput)
- Dashboard datasources include the project's telemetry backends (Tempo, Loki, Mimir as applicable)
- Dashboard placement follows `spec.observability.dashboardPlacement`

**Acceptance anchors:**
- `spec.requirements.availability`
- `spec.requirements.latencyP99`
- `spec.requirements.throughput`

---

## REQ-CDP-OBS-003: Alerting Rules

**Priority:** P1
**Artifact:** `prometheus_rule`

**Acceptance criteria:**
- Prometheus alerting rules are generated with severity derived from `spec.business.criticality`
- Alert thresholds are derived from `spec.requirements.availability` and `spec.requirements.latencyP99`
- Rules depend on a service monitor for metric collection

**Acceptance anchors:**
- `spec.requirements.availability`
- `spec.requirements.latencyP99`
- `spec.business.criticality`

---

## REQ-CDP-OBS-004: Service Monitor

**Priority:** P1
**Artifact:** `service_monitor`

**Acceptance criteria:**
- A ServiceMonitor (or equivalent metric scrape config) is generated for each deployment target
- Scrape interval is derived from `spec.observability.metricsInterval`
- Target namespace matches `spec.targets[].namespace`

**Acceptance anchors:**
- `spec.observability.metricsInterval`
- `spec.targets[].namespace`

---

## REQ-CDP-OBS-005: Notification Policy

**Priority:** P1
**Artifact:** `notification_policy`

**Acceptance criteria:**
- Alert notification routing is generated with channels from `spec.observability.alertChannels`
- Owner contact information is derived from `metadata.owners`
- Notification policy depends on alerting rules being defined

**Acceptance anchors:**
- `spec.observability.alertChannels`
- `metadata.owners`

---

## REQ-CDP-OBS-006: Log Recording Rules

**Priority:** P2
**Artifact:** `loki_rule`

**Acceptance criteria:**
- Loki log recording rules are generated for error rate and request rate
- Log selectors are derived from `spec.targets[].name`
- Log format aligns with `spec.observability.logLevel` and OTel conventions

**Acceptance anchors:**
- `spec.targets[].name`
- `spec.observability.logLevel`

---

## REQ-CDP-OBS-007: Incident Runbook

**Priority:** P3
**Artifact:** `runbook`

**Acceptance criteria:**
- An incident runbook is generated addressing documented risks from `spec.risks[]`
- Escalation contacts are derived from `metadata.owners`
- Runbook depends on alerting rules and notification policy being defined

**Acceptance anchors:**
- `spec.risks[]`
- `metadata.owners`

---

## Traceability

| Requirement | Manifest Field | Artifact Type | Pipeline Stage |
|------------|---------------|---------------|----------------|
| REQ-CDP-OBS-001 | `spec.requirements.availability`, `spec.requirements.errorBudget` | `slo_definition` | EXPORT |
| REQ-CDP-OBS-002 | `spec.requirements.*`, `spec.targets[]` | `dashboard` | EXPORT |
| REQ-CDP-OBS-003 | `spec.requirements.availability`, `spec.business.criticality` | `prometheus_rule` | EXPORT |
| REQ-CDP-OBS-004 | `spec.observability.metricsInterval`, `spec.targets[]` | `service_monitor` | EXPORT |
| REQ-CDP-OBS-005 | `spec.observability.alertChannels`, `metadata.owners` | `notification_policy` | EXPORT |
| REQ-CDP-OBS-006 | `spec.targets[].name`, `spec.observability.logLevel` | `loki_rule` | EXPORT |
| REQ-CDP-OBS-007 | `spec.risks[]`, `metadata.owners` | `runbook` | EXPORT |

## Implementation

These requirements are defined in `src/contextcore/utils/pipeline_requirements.py` and injected into `onboarding-metadata.json` by `src/contextcore/utils/onboarding.py`. The plan-ingestion consumer (`startd8-sdk`) auto-satisfies them based on the `pipeline-innate` label.
