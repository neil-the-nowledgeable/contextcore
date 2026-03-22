# Requirements: Security Contract Verification in Installation System

> **Status:** Implemented (REQ-SCV-001–004, 24 tests)
> **Date:** 2026-03-21
> **Author:** Observability Team
> **Priority Tier:** P3 (enhancement to existing verification system)
> **Scope:** ContextCore `install verify` — add SECURITY category to validate security contract completeness
> **Depends on:** REQ-ICD-105 (graph-derived database detection, implemented), REQ-ICD-106 (security contract schema, implemented)
> **Implementation files:**
> - `src/contextcore/install/requirements.py` — new category + check functions
> - `src/contextcore/install/verifier.py` — no changes (category-agnostic)
> - `grafana/provisioning/dashboards/core/installation.json` — new panel row

---

## 1. Problem Statement

ContextCore's installation verification system covers 5 categories (configuration, infrastructure, tooling, observability, documentation) with 28 checks. None address security contract completeness.

The security contract system (REQ-ICD-105/106) introduced two tiers of security metadata:

| Tier | Source | Fidelity |
|------|--------|----------|
| **2** | Communication graph imports → `detected_databases` | Medium — auto-detected, zero config |
| **1** | `spec.security.data_stores` in manifest | Full — client_library, sensitivity, credential_source, access_policy |

When Tier 2 detects databases but Tier 1 declarations are absent, the security contract is **incomplete** — startd8-sdk falls back to auto-detection instead of using explicit manifest declarations. This gap is invisible unless someone manually compares `instrumentation_hints.detected_databases` against `security_contract.databases`.

The installation verification system is the right place to surface this: it already checks for configuration completeness, emits telemetry, and displays results in the Installation dashboard.

---

## 2. Requirements

### REQ-SCV-001: SECURITY requirement category

**Priority:** P1 (prerequisite)

Add `SECURITY = "security"` to `RequirementCategory` enum. The verifier, dashboard, and telemetry system are category-agnostic — no changes needed beyond the enum value.

**Acceptance:**
- `RequirementCategory.SECURITY` exists
- `contextcore install verify --category security` filters to security checks only
- `contextcore install list-requirements` shows security category

### REQ-SCV-002: Manifest security declaration check

**Priority:** P1

When `.contextcore.yaml` exists and the communication graph contains services with `detected_databases` (Tier 2), verify that `spec.security.data_stores` (Tier 1) is declared for those services.

**Check logic:**
1. Load `.contextcore.yaml` from project root
2. If no `spec.security` section → check whether any `detected_databases` exist in the most recent export's `onboarding-metadata.json`
3. If detected databases exist but no `spec.security` → FAILED ("Databases detected in communication graph but no spec.security declared")
4. If no detected databases and no `spec.security` → PASSED (not applicable)
5. If `spec.security.data_stores` exists → PASSED

**Critical:** No — this is a quality signal, not a blocking requirement. Missing Tier 1 declarations don't break the pipeline; they reduce fidelity.

**Depends on:** `cli_installed` (needs contextcore to find project root)

### REQ-SCV-003: High-sensitivity audit policy check

**Priority:** P2

When `spec.security.data_stores` contains entries with `sensitivity: high`, verify that `access_policy.audit_access: true` is set.

**Check logic:**
1. Load `.contextcore.yaml`
2. For each data store with `sensitivity: high`:
   - Check `access_policy.audit_access` is `true`
3. If any high-sensitivity store lacks `audit_access: true` → FAILED
4. If no high-sensitivity stores → PASSED (not applicable)
5. If all high-sensitivity stores have `audit_access: true` → PASSED

**Critical:** No — advisory. The generated code will still work without audit logging, but it won't meet security best practices.

**Depends on:** `security_manifest_declaration` (REQ-SCV-002 must pass first)

### REQ-SCV-004: Credential source validation check

**Priority:** P3

When `spec.security.data_stores` declares `credential_source`, verify the value is one of the known mechanisms: `env_var`, `environment_variable`, `secrets_manager`, `workload_identity`.

**Check logic:**
1. Load `.contextcore.yaml`
2. For each data store with a non-empty `credential_source`:
   - Validate against known values
3. Unknown values → FAILED with specific store ID and value
4. All known or empty → PASSED

**Critical:** No — unknown credential sources still pass through to startd8-sdk; this catches typos.

---

## 3. Dashboard Integration

### REQ-SCV-010: Installation dashboard security row

**Priority:** P2

Add a panel row to the Installation Status dashboard showing security contract completeness. Uses the same metrics the verifier already emits (`contextcore_install_requirement_status_ratio` with `category="security"` label).

**Panels:**
- **Security Contract Status** (Stat) — shows PASSED/FAILED count for security category
- Existing **Completeness by Category** bar chart automatically includes `security` (no change needed — it queries all categories)
- Existing **Requirement Status** table automatically includes security requirements (no change needed)

Only 1 new panel needed; the existing panels are category-agnostic.

---

## 4. Non-Requirements

- **Runtime credential validation** — verifying that `workload_identity` is actually configured in the cluster is out of scope. The check validates the *declaration*, not the *infrastructure*.
- **Network security checks** — TLS, mTLS, network policies are infrastructure concerns, not security contract concerns.
- **RBAC enforcement validation** — the RBAC system (`src/contextcore/rbac/`) has its own enforcement path. The install check validates that `DATA_STORE` resources are *declared*, not that access policies are *enforced*.

---

## 5. Implementation Estimate

~60 lines production code (3 check functions + category enum), ~40 lines tests, 1 dashboard panel JSON update.

No changes to `verifier.py` — the verification engine is category-agnostic.

---

## 6. Verification

```bash
# Run security checks only
contextcore install verify --category security

# Full verification (includes new security category)
contextcore install verify

# List security requirements
contextcore install list-requirements | grep security
```

---

## 7. Cross-References

| Document | Relationship |
|----------|-------------|
| [REQ_INSTRUMENTATION_CONTRACT_DERIVATION.md](REQ_INSTRUMENTATION_CONTRACT_DERIVATION.md) | REQ-ICD-105/106 — security contract schema and detection that this validates |
| [INSTALLATION_TRACKING_PLAN.md](../../plans/INSTALLATION_TRACKING_PLAN.md) | Installation system architecture |
| `src/contextcore/install/requirements.py` | Where check functions are added |
| `src/contextcore/models/core.py` | `SecuritySpec`, `DataStoreSpec`, `AccessPolicySpec` models |
