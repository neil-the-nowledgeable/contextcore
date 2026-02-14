# A2A v1 Governance Policy

Effective as of the conclusion of the 7-day A2A governance rollout.

---

## 1. Schema versioning

- All contracts are pinned to `schema_version = "v1"`.
- `v1` is frozen for this sprint. No new fields are allowed.
- Additive schema evolution uses a new version (`v2`), never widening `v1`.
- `additionalProperties: false` is enforced at the top level of all contracts.

## 2. New-field approval rule

Before adding a field to any contract schema:

1. **Identify the query or policy** that depends on the new field.
2. **Document the query** in `docs/` with the field name, expected values, and dashboard panel.
3. **Get platform lead approval** before merging.
4. **Bump to the next schema version** (`v2`, `v3`, etc.). Do not modify `v1`.

Fields added without a concrete query/alert justification will be rejected.

## 3. Boundary validation requirements

- **100% of outbound handoffs** must be schema-validated before sending.
- **100% of inbound handoffs** must be schema-validated before acceptance.
- Invalid payloads are rejected deterministically with a structured error envelope.
- Rejection events must be emitted for observability (logged and/or recorded as span events).

## 4. Phase gate requirements

- **100% of enforced phase transitions** must emit a `GateResult`.
- Blocking gates must prevent downstream phase execution when `result = "fail"` and `blocking = true`.
- Gate results must include:
  - `reason` (what went wrong)
  - `next_action` (what to do about it)
  - `evidence` (supporting data for the decision)

## 5. Required gates for PI-101-002 (and future pilot features)

| Gate | Phase | Blocking | Checks |
|------|-------|----------|--------|
| Checksum chain integrity | `CONTRACT_INTEGRITY` | Yes | `source_checksum`, `artifact_manifest_checksum`, `project_context_checksum` |
| Mapping completeness | `CONTRACT_INTEGRITY` | Yes | All artifact IDs have task mapping entries |
| Gap parity | `INGEST_PARSE_ASSESS` | Yes | Every gap has a corresponding feature; no orphans |

Additional gates may be added in future sprints following the new-field approval rule.

## 6. Required observability for rollout

Every feature that uses A2A contracts must be queryable via the governance dashboard:

| Query | Datasource | Must answer |
|-------|------------|-------------|
| Blocked span hotspot | Tempo | Which phases block most? |
| Gate failures | Tempo | Which gates fail and how severe? |
| Handoff validation failures | Loki | Which contracts are rejected at boundaries? |
| Dropped artifacts | Loki | Which artifacts were lost in parse/transform? |
| Finalize failure trend | Loki | Is the failure rate improving? |

## 7. Ownership boundaries

| Domain | Owner |
|--------|-------|
| Runtime orchestration (task routing, delegation, scheduling) | LangChain |
| Governance and observability (contracts, gates, validation, dashboards) | ContextCore |

No runtime duplication work enters the ContextCore scope. ContextCore consumes runtime events but does not implement runtime logic.

## 8. Contract types and their purpose

| Contract | Purpose | When to use |
|----------|---------|-------------|
| `TaskSpanContract` | Task/subtask span lifecycle | Opening, updating, or closing phase spans |
| `HandoffContract` | Agent-to-agent delegation | Every capability delegation between agents |
| `ArtifactIntent` | Artifact requirement declaration | Before generating an artifact; promotes to task when policy criteria met |
| `GateResult` | Phase boundary check outcome | Every enforced phase transition |

## 9. What goes in a contract vs a span event

**Use a contract** when data:
- Crosses a module/process/agent boundary
- Is validated at a boundary
- Is used for routing or blocking decisions
- Must be audited later

**Use a span event** when data:
- Is local diagnostic detail
- Is non-routing commentary
- Is ephemeral debug context

## 10. Rollout process for new features

1. Map the feature to the span model (parent trace + phase spans).
2. Add contract payloads for each boundary crossing.
3. Add gate checks at each phase transition.
4. Run the pilot with `contextcore contract a2a-pilot`.
5. Verify evidence in the governance dashboard.
6. Once baseline is stable, tighten thresholds and automate blocking rules.

---

## Compliance checklist

Before declaring a feature "A2A compliant":

- [ ] All handoffs are schema-validated on send and receive
- [ ] All enforced phase transitions emit `GateResult`
- [ ] At least one full pilot trace completed with gate evidence
- [ ] Time-to-root-cause is reduced vs prior baseline
- [ ] No uncontrolled schema expansion during the sprint
- [ ] New contributor can execute the pilot workflow without tribal knowledge
