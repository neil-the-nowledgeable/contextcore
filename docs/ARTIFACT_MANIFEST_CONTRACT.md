# Artifact Manifest Contract

> **The bridge between ContextCore (knows WHAT) and Wayfinder (knows HOW)**

## Overview

The **Artifact Manifest** (`artifact-manifest.yaml`) is the contract between:

| Layer | Responsibility | Example |
|-------|---------------|---------|
| **ContextCore** | Determines WHAT observability artifacts are needed based on business context | "checkoutservice needs a P2-severity alert rule because criticality=high" |
| **Wayfinder** | Generates HOW those artifacts should be created | Creates the actual PrometheusRule YAML with appropriate thresholds |

This separation enables:
1. **Programmatic observability** - Artifacts are derived, not manually configured
2. **Gap tracking** - Know what exists vs what's missing
3. **Audit trail** - Understand WHY each config exists (derivation rules)
4. **Portability** - Any ContextCore-compliant implementation can consume the contract

## File Structure

### Generating the Artifact Manifest

```bash
# From a Context Manifest
contextcore manifest export -p .contextcore.yaml -o ./output

# This produces:
#   output/my-project-projectcontext.yaml      # K8s CRD (not applied)
#   output/my-project-artifact-manifest.yaml   # Artifact contract

# For programmatic onboarding (plan ingestion, artisan seed enrichment):
contextcore manifest export -p .contextcore.yaml -o ./output --emit-onboarding

# Adds:
#   output/onboarding-metadata.json            # Artifact type schemas, output conventions,
#                                              # coverage gaps, semantic conventions
```

### Schema

```yaml
apiVersion: contextcore.io/v1
kind: ArtifactManifest
metadata:
  generatedAt: "2026-02-05T12:00:00Z"
  generatedFrom: ".contextcore.yaml"
  contextcoreVersion: "2.0.0"
  projectId: "online-boutique"

artifacts:
  - id: checkoutservice-prometheus-rules
    type: prometheus_rule
    name: "checkoutservice Alerting Rules"
    target: checkoutservice
    priority: required
    status: needed
    derivedFrom:
      - property: severity
        sourceField: spec.business.criticality
        transformation: "high → P2"
        rationale: "Alert severity is derived from business criticality"
    parameters:
      alertSeverity: P2
      availabilityThreshold: "99.9"
      latencyThreshold: "200ms"
    existingPath: null  # Populated when scanning existing artifacts
    validationErrors: []

coverage:
  totalRequired: 40
  totalExisting: 0
  totalOutdated: 0
  overallCoverage: 0.0
  byTarget:
    - target: checkoutservice
      requiredCount: 4
      existingCount: 0
      coveragePercent: 0.0
      gaps:
        - checkoutservice-dashboard
        - checkoutservice-prometheus-rules
  byType:
    dashboard: 10
    prometheus_rule: 10
    slo_definition: 10
    service_monitor: 10

crdReference: "my-project-projectcontext.yaml"
```

## Artifact Types

| Type | Description | Priority Logic | Schema URL (validation) |
|------|-------------|----------------|-------------------------|
| `dashboard` | Grafana dashboard | Required for all | [Grafana JSON model](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/) |
| `prometheus_rule` | Alerting rules | Required for critical/high | [PrometheusRule CRD](https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.PrometheusRule) |
| `slo_definition` | Sloth SLO | Required for critical | [OpenSLO](https://openslo.com/) |
| `service_monitor` | Prometheus scrape config | Required for all | [ServiceMonitor CRD](https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.ServiceMonitor) |
| `loki_rule` | Log recording rules | Recommended | [Loki rules](https://grafana.com/docs/loki/latest/rules/) |
| `notification_policy` | Alert routing | Required for critical/high | [Alertmanager config](https://prometheus.io/docs/alerting/latest/configuration/) |
| `runbook` | Incident response doc | Required for critical | Markdown (structure varies) |
| `alert_template` | Alert message template | Optional | [Alertmanager config](https://prometheus.io/docs/alerting/latest/configuration/) |

The `onboarding-metadata.json` includes `schema_url` per artifact type for post-generation validation.

## Derivation Rules

Each artifact includes `derivedFrom` entries explaining how configuration is derived:

```yaml
derivedFrom:
  - property: severity      # The artifact property being set
    sourceField: spec.business.criticality  # Source in CRD/manifest
    transformation: "high → P2"  # How value is transformed
    rationale: "Alert severity is derived from business criticality"
```

### Standard Derivations

| Source Field | Derived Property | Transformation |
|--------------|-----------------|----------------|
| `spec.business.criticality` | Alert severity | critical→P1, high→P2, medium→P3, low→P4 |
| `spec.requirements.availability` | SLO objective | Direct mapping |
| `spec.requirements.latencyP99` | Latency threshold | Direct mapping |
| `spec.observability.alertChannels` | Notification routes | Direct mapping |
| `spec.risks[]` | Runbook sections | One section per risk |

## Coverage Tracking

### Marking Existing Artifacts

```bash
# Scan a directory for existing artifacts
contextcore manifest export -p .contextcore.yaml -o ./output \
    --scan-existing /path/to/observability/

# Or specify individual artifacts
contextcore manifest export -p .contextcore.yaml -o ./output \
    --existing "checkoutservice-dashboard:/observability/dashboards/checkout.json" \
    --existing "checkoutservice-prometheus-rules:/observability/rules/checkout.yaml"
```

### Coverage States

| Status | Meaning |
|--------|---------|
| `needed` | Artifact should exist but doesn't |
| `exists` | Artifact exists and is current |
| `outdated` | Artifact exists but needs update |
| `skipped` | Explicitly skipped (with reason) |

### Outdated Detection Rules

An artifact is **outdated** when it exists but the source contract has changed. Implementers should use one or more of these mechanisms:

| Mechanism | When to Use | How |
|-----------|-------------|-----|
| **Checksum** | Recommended for files | Compare SHA-256 of existing artifact content against a canonical checksum (e.g., from `onboarding-metadata.json` or provenance). If different, mark outdated. |
| **Source checksum** | Best for regeneration | If `source_checksum` in provenance or onboarding differs from current `.contextcore.yaml` checksum, all artifacts may need regeneration. |
| **Timestamp** | Heuristic only | Compare `generatedAt` in manifest vs artifact file mtime. Use only as a fallback; timestamps can be misleading. |
| **Version** | Schema evolution | If `schemaVersion` in manifest is newer than the version used when the artifact was generated, mark outdated. |

**Algorithm:** When scanning existing artifacts, compute each file's checksum. If the manifest's `derivedFrom` or parameters would produce different output, or if `source_checksum` has changed, set status to `outdated`. Otherwise set to `exists`.

## Implementation Guide for Wayfinder

### Parameter Source: Manifest vs CRD

Implementers must know when to use manifest parameters vs loading the CRD for additional context. The artifact manifest `parameters` are pre-derived from the CRD at export time — use them directly for generation. Load the CRD only when you need richer context not present in `parameters`.

| Artifact Type | Parameters | Source | When to Load CRD |
|---------------|------------|--------|------------------|
| `dashboard` | criticality, dashboardPlacement, datasources, risks | Manifest (pre-derived from CRD) | For full risk descriptions, governance styling preferences |
| `prometheus_rule` | alertSeverity, availabilityThreshold, latencyThreshold | Manifest | For SLO refinement details beyond thresholds |
| `slo_definition` | availability, latencyP99, errorBudget, throughput | Manifest | Usually not needed — parameters are complete |
| `service_monitor` | metricsInterval, namespace | Manifest | For target discovery from spec.targets |
| `loki_rule` | logSelectors, recordingRules, labelExtractors | Manifest | For log format hints from spec.observability |
| `notification_policy` | alertChannels, owner, owners | Manifest | For full owner contact details (email, slack, oncall) |
| `runbook` | risks, escalationContacts | Manifest | For full risk descriptions, escalation playbooks |
| `alert_template` | alertSeverity, summaryTemplate, descriptionTemplate | Manifest | For governance messaging preferences |

**Rule of thumb:** Start with manifest parameters. Load the CRD only when the generator needs fields not included in `parameters` (e.g., `spec.risks[].description`, `spec.observability.ownerContacts`, governance focus areas).

### 1. Load the Contract

```python
import yaml
from pathlib import Path

# Load artifact manifest (parameters are ready to use)
manifest = yaml.safe_load(Path("artifact-manifest.yaml").read_text())

# Load CRD only when additional context is needed (see table above)
crd = yaml.safe_load(Path("projectcontext.yaml").read_text()) if need_crd_context else None
```

### 2. Iterate Over Artifacts

```python
for artifact in manifest["artifacts"]:
    if artifact["status"] != "needed":
        continue  # Skip existing/skipped
    
    artifact_type = artifact["type"]
    target = artifact["target"]
    params = artifact["parameters"]
    
    if artifact_type == "dashboard":
        generate_dashboard(target, params)
    elif artifact_type == "prometheus_rule":
        generate_prometheus_rules(target, params)
    # ... etc
```

### 3. Use Derivation Rules

```python
# Access derivation rules for audit/logging
for rule in artifact.get("derivedFrom", []):
    print(f"Setting {rule['property']} from {rule['sourceField']}")
    print(f"  Transform: {rule['transformation']}")
    print(f"  Rationale: {rule.get('rationale', 'N/A')}")
```

### 4. Report Coverage Back

After generating artifacts, re-run export to update coverage:

```bash
# Re-scan to update coverage
contextcore manifest export -p .contextcore.yaml -o ./output \
    --scan-existing ./generated-artifacts/
```

## Pipeline Integration

### CI/CD Pipeline

```yaml
# .github/workflows/observability.yml
jobs:
  generate-observability:
    steps:
      - name: Export artifact manifest
        run: contextcore manifest export -p .contextcore.yaml -o ./output
      
      - name: Generate artifacts with Wayfinder
        run: wayfinder generate --manifest ./output/artifact-manifest.yaml
      
      - name: Validate coverage
        run: |
          contextcore manifest export -p .contextcore.yaml -o ./output \
              --scan-existing ./generated/
          # Fail if coverage < 80%
          python scripts/check_coverage.py ./output/artifact-manifest.yaml
```

### GitOps Integration

```
repo/
├── .contextcore.yaml              # Master Source of Truth
├── output/
│   ├── projectcontext.yaml        # Generated CRD
│   └── artifact-manifest.yaml     # Generated contract
└── observability/
    ├── dashboards/                # Generated by Wayfinder
    ├── prometheus-rules/
    ├── slo-definitions/
    └── runbooks/
```

## Related Documentation

- [Context Manifest v2.0](./CONTEXT_MANIFEST_VALUE_PROPOSITION.md)
- [Semantic Conventions](./semantic-conventions.md)
- [Prime Contractor Workflow](./PRIME_CONTRACTOR_WORKFLOW.md)

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-05 | Initial artifact manifest contract |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Clarify parameter source when CRD is needed | claude-4 (claude-opus-4-20250514) | Critical for implementers to know when to load CRD vs using manifest parameters - prevents confusion and incorrect implementations | 2026-02-11 22:02:31 UTC |
| R1-F2 | Specify behavior for outdated artifact detection | claude-4 (claude-opus-4-20250514) | Essential for coverage tracking functionality - without this, the 'outdated' status cannot be properly implemented | 2026-02-11 22:02:31 UTC |
| R1-F3 | Define schema URLs for artifact validation | claude-4 (claude-opus-4-20250514) | Necessary for proper validation implementation - generators need concrete schemas to validate against | 2026-02-11 22:02:31 UTC |
| R1-F5 | Specify error handling for invalid derivation rules | claude-4 (claude-opus-4-20250514) | Important for robustness - derivedFrom references could be invalid and need proper error handling requirements | 2026-02-11 22:02:31 UTC |
| R2-F1 | Add alert_template artifact type specification | claude-3-5-sonnet-20241022 | Contract lists 8 types but only defines 7 - missing specification causes implementation confusion | 2026-02-11 22:02:31 UTC |
| R2-F2 | Define 'outdated' detection algorithm | claude-3-5-sonnet-20241022 | Critical gap - contract has outdated status but no algorithm, making implementation ambiguous | 2026-02-11 22:02:31 UTC |
| R2-F3 | Specify CRD schema subset needed | claude-3-5-sonnet-20241022 | Contract mentions CRD loading but doesn't specify which fields - implementers need concrete guidance | 2026-02-11 22:02:31 UTC |
| R2-F4 | Add validation schema for derivedFrom | claude-3-5-sonnet-20241022 | derivedFrom structure needs formal schema to prevent invalid transformation rules | 2026-02-11 22:02:31 UTC |
| R2-F6 | Add conflict resolution for existing artifacts | claude-3-5-sonnet-20241022 | Contract gap - behavior when generated conflicts with manual artifacts needs specification | 2026-02-11 22:02:31 UTC |
| R1-F1 | Clarify parameter source when CRD is needed | claude-4 (claude-opus-4-20250514) | Critical gap - implementation cannot proceed without knowing which parameters come from CRD vs manifest | 2026-02-11 22:06:10 UTC |
| R1-F2 | Specify behavior for outdated artifact detection | claude-4 (claude-opus-4-20250514) | Essential for Step 22's coverage-aware generation to determine when regeneration is needed | 2026-02-11 22:06:10 UTC |
| R1-F3 | Define schema URLs for artifact validation | claude-4 (claude-opus-4-20250514) | Needed for Step 12's validation to ensure generated artifacts conform to expected schemas | 2026-02-11 22:06:10 UTC |
| R1-F5 | Specify error handling for invalid derivation rules | claude-4 (claude-opus-4-20250514) | Prevents runtime failures when derivedFrom references non-existent fields | 2026-02-11 22:06:10 UTC |
| R2-F1 | Add alert_template artifact type specification | claude-3-5-sonnet-20241022 | Critical missing type - plan references 7 types but contract only defines 6, blocking complete implementation | 2026-02-11 22:06:10 UTC |
| R2-F2 | Define 'outdated' detection algorithm | claude-3-5-sonnet-20241022 | Essential for implementing coverage-aware generation in Step 22 | 2026-02-11 22:06:10 UTC |
| R2-F3 | Specify CRD schema subset needed | claude-3-5-sonnet-20241022 | Step 9 needs to extract alertSeverity from CRD but lacks specification of required fields | 2026-02-11 22:06:10 UTC |
| R2-F4 | Add validation schema for derivedFrom | claude-3-5-sonnet-20241022 | Prevents malformed derivation rules that could cause runtime errors | 2026-02-11 22:06:10 UTC |
| R2-F6 | Add conflict resolution for existing artifacts | claude-3-5-sonnet-20241022 | Step 22 checks existence but doesn't specify merge vs overwrite behavior for manual artifacts | 2026-02-11 22:06:10 UTC |
| R3-F1 | Clarify CRD requirement scope | claude-3.5-sonnet | Implementation blocker - generators cannot proceed without knowing which types need CRD data | 2026-02-11 22:06:10 UTC |
| R3-F2 | Define parameter override precedence | claude-3.5-sonnet | Ambiguous behavior when both manifest parameters and derivedFrom rules exist | 2026-02-11 22:06:10 UTC |
| R3-F3 | Add artifact output examples | claude-3.5-sonnet | Implementers guessing output format leads to inconsistent artifacts | 2026-02-11 22:06:10 UTC |
| R3-F4 | Specify partial generation recovery | claude-3.5-sonnet | Undefined behavior for partial success could leave manifest in inconsistent state | 2026-02-11 22:06:10 UTC |
| R3-F5 | Define sensitive parameter handling | claude-3.5-sonnet | Security concern - escalationContacts may contain PII requiring special handling | 2026-02-11 22:06:10 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F1 | Clarify parameter source when CRD is needed | claude-4 (claude-opus-4-20250514) | Feature document change not applicable to implementation plan review | 2026-02-11 21:56:56 UTC |
| R1-F2 | Specify behavior for outdated artifact detection | claude-4 (claude-opus-4-20250514) | Feature document change not applicable to implementation plan review | 2026-02-11 21:56:56 UTC |
| R1-F3 | Define schema URLs for artifact validation | claude-4 (claude-opus-4-20250514) | Feature document change not applicable to implementation plan review | 2026-02-11 21:56:56 UTC |
| R1-F4 | Clarify if generators can modify the manifest | claude-4 (claude-opus-4-20250514) | Feature document change not applicable to implementation plan review | 2026-02-11 21:56:56 UTC |
| R1-F5 | Specify error handling for invalid derivation rules | claude-4 (claude-opus-4-20250514) | Feature document change not applicable to implementation plan review | 2026-02-11 21:56:56 UTC |
| R1-F4 | Clarify if generators can modify the manifest | claude-4 (claude-opus-4-20250514) | The plan already addresses this in Step 23 with the --update-manifest flag, making the contract modification unnecessary | 2026-02-11 22:02:31 UTC |
| R2-F5 | Clarify manifest mutation permissions | claude-3-5-sonnet-20241022 | Implementation concern not contract concern - the plan already defines this with --update-manifest flag | 2026-02-11 22:02:31 UTC |
| R1-F4 | Clarify if generators can modify the manifest | claude-4 (claude-opus-4-20250514) | Step 23 already implements manifest updates with --update-manifest flag | 2026-02-11 22:06:10 UTC |
| R2-F5 | Clarify manifest mutation permissions | claude-3-5-sonnet-20241022 | Step 23 already defines manifest update behavior with --update-manifest flag | 2026-02-11 22:06:10 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-20250514)
- **Date**: 2026-02-11 21:56:22 UTC
- **Scope**: Requirements traceability and architecture review — manifest generation plan vs contract spec

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Clarify parameter source when CRD is needed | Contract says "Load CRD for additional context" but doesn't specify when generators need CRD data vs manifest parameters | Implementation Guide section | Cross-reference which parameters come from manifest vs CRD |
| R1-F2 | Interfaces | medium | Specify behavior for outdated artifact detection | Contract defines "outdated" status but not how to detect when existing artifacts need updates | Coverage States section | Define version/checksum comparison mechanism |
| R1-F3 | Validation | medium | Define schema URLs for artifact validation | Contract mentions artifacts must be valid but doesn't provide schema references for validation | Artifact Types table | Add schema URL column for each type |
| R1-F4 | Architecture | low | Clarify if generators can modify the manifest | Contract shows manifest updates but doesn't specify if generators can add new fields | Schema section | Document which fields are generator-writable |
| R1-F5 | Risks | medium | Specify error handling for invalid derivation rules | derivedFrom could reference non-existent source fields | Derivation Rules section | Add error handling requirements |

#### Review Round R2

- **Reviewer**: claude-4 (claude-opus-4-20250514)
- **Date**: 2026-02-11 22:01:41 UTC
- **Scope**: Requirements traceability and architecture review — manifest generation plan vs contract spec

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | Add alert_template artifact type specification | Contract lists 8 types but only defines 7 - alert_template is missing | Artifact Types table | Add example parameters and purpose |
| R2-F2 | Interfaces | critical | Define "outdated" detection algorithm | Contract has outdated status but no algorithm for detecting when regeneration needed | Coverage States section | Specify version/checksum comparison |
| R2-F3 | Data | high | Specify CRD schema subset needed | Contract says "load CRD for context" but doesn't specify which fields generators need | Implementation Guide section | List required CRD paths per artifact type |
| R2-F4 | Validation | medium | Add validation schema for derivedFrom | derivedFrom structure needs schema to prevent invalid transformations | Derivation Rules section | Add JSON schema for rule validation |
| R2-F5 | Architecture | medium | Clarify manifest mutation permissions | Contract shows updates but doesn't specify which systems can modify | Schema section | Define read-only vs mutable fields |
| R2-F6 | Risks | high | Add conflict resolution for existing artifacts | Contract doesn't specify behavior when generated conflicts with manual | Coverage Tracking section | Define merge vs overwrite strategy |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-20250514)
- **Date**: 2026-02-11 22:05:24 UTC
- **Scope**: Requirements traceability and architecture review — manifest generation plan vs contract spec

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | critical | Clarify CRD requirement scope | Contract says "Load CRD for additional context" but doesn't enumerate which artifact types need CRD data | Implementation Guide | List which types need CRD |
| R3-F2 | Interfaces | high | Define parameter override precedence | When both manifest parameters AND derivedFrom exist, which wins? | Derivation Rules section | Add precedence rules |
| R3-F3 | Validation | medium | Add artifact output examples | Contract defines inputs but not expected outputs - implementers guess format | Artifact Types table | Add "Example Output" column |
| R3-F4 | Risks | high | Specify partial generation recovery | If 50/77 succeed then fail, should status be partially updated? | Coverage Tracking | Define partial update semantics |
| R3-F5 | Security | medium | Define sensitive parameter handling | Some parameters (escalationContacts) may be sensitive | Schema section | Mark sensitive fields |

