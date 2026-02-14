# Data Issues & Consistency Report

This document captures data issues and inconsistencies found during ContextCore development, derived from lessons learned and debugging sessions.

---

## Critical Issues

### 1. Persona Query Mismatch (P1)

**Problem**: Documentation shows TraceQL queries like `{ value.persona = "developer" }` but this only matches capabilities where developer is the PRIMARY persona, not all capabilities targeting developers.

**Affected Files**:
- `docs/skill-semantic-conventions.md` (line 745)
- `grafana/provisioning/dashboards/json/value-capabilities.json` (persona filter panels)

**Data Model**:
```
value.persona  = "designer"                    # Primary persona only
value.personas = "designer,developer,creator"  # All target personas
```

**Incorrect Query**:
```traceql
{ value.persona = "developer" }  # Only matches if developer is PRIMARY
```

**Correct Query**:
```traceql
{ value.personas =~ ".*developer.*" }  # Matches any capability targeting developers
```

**Fix Required**:
1. Update `docs/skill-semantic-conventions.md` example queries
2. Dashboard panels already fixed to use regex on `value.personas`
3. Add clarifying documentation about primary vs all personas

---

### 2. Tempo Instance Confusion (P1)

**Problem**: Multiple Tempo instances exist (Docker Compose vs Kubernetes), and data emitted to one is not visible from the other.

**Symptoms**:
- `contextcore value emit` sends to localhost:4317 (Docker Tempo)
- Grafana in K8s queries tempo.observability.svc.cluster.local:3200 (K8s Tempo)
- Dashboard shows "no data" despite successful emission

**Environment**:
| Instance | OTLP Endpoint | Query Endpoint |
|----------|---------------|----------------|
| Docker Tempo | localhost:4317 | localhost:3200 |
| K8s Tempo | localhost:4318 (port-forward) | localhost:3201 (port-forward) |

**Fix Required**:
1. Document which Tempo instance to use for each environment
2. Add `--endpoint` flag documentation to CLI help
3. Consider adding endpoint auto-detection based on environment

---

### 3. Dashboard Datasource UID Hardcoding (P2)

**Problem**: All dashboard JSON files have hardcoded Tempo datasource UID `P214B5B846CF3925F`. This breaks in environments with different datasource UIDs.

**Affected Files**:
- `grafana/provisioning/dashboards/json/value-capabilities.json`
- `grafana/provisioning/dashboards/json/skills-browser.json`
- All other dashboard JSON files

**Current State**:
```json
"datasource": {"type": "tempo", "uid": "P214B5B846CF3925F"}
```

**Fix Options**:
1. Use datasource name instead of UID: `"datasource": {"type": "tempo", "name": "Tempo"}`
2. Use variable: `"datasource": "${DS_TEMPO}"`
3. Document required datasource UID in provisioning setup

---

## Medium Issues

### 4. Grafana Stat Panel Bug with TraceQL (P2)

**Problem**: Grafana's Tempo datasource has a nil pointer dereference bug when using stat panels with TraceQL queries, causing "Loading plugin panel..." to hang forever.

**Error from Grafana logs**:
```
level=error msg="Request error" error="runtime error: invalid memory address or nil pointer dereference"
stack="github.com/grafana/grafana/pkg/tsdb/tempo/search.go:102..."
```

**Workaround**: Use table panels with `footer.countRows: true` instead of stat panels with `reduceOptions.calcs: ["count"]`.

**Affected**: Grafana 12.3.0 with Tempo datasource

---

### 5. Enum Handling in Emitters (P3 - FIXED)

**Problem**: Pydantic models with `use_enum_values=True` already convert enums to strings, but emitter code was calling `.value` on the result, causing `'str' object has no attribute 'value'`.

**Fix Applied**:
```python
# Before (broken):
audience = capability.get_audience()
span.set_attribute("capability.audience", audience.value)

# After (fixed):
audience = capability.get_audience()
audience_value = audience if isinstance(audience, str) else audience.value
span.set_attribute("capability.audience", audience_value)
```

**Files Fixed**:
- `src/contextcore/knowledge/emitter.py`
- `src/contextcore/value/emitter.py`

---

## Documentation Inconsistencies

### 6. Channel Query Examples

**Problem**: Similar to persona, `value.channel` vs `value.channels` confusion.

**Correct Usage**:
- `value.channel` = primary channel only
- `value.channels` = comma-separated list of all channels
- Use `value.channels =~ ".*slack.*"` for "any capability supporting Slack"

The documentation at line 766 correctly uses regex, but should be more explicit about when to use singular vs plural.

---

### 7. Skill Variable Options Not Dynamic

**Problem**: Dashboard skill filter variables have hardcoded options instead of dynamic discovery.

**Current State**:
```json
"options": [
  {"text": "All", "value": ".*"},
  {"text": "capability-value-promoter", "value": "capability-value-promoter"},
  {"text": "dev-tour-guide", "value": "dev-tour-guide"}
]
```

**Desired State**: Query available skills dynamically from Tempo.

**Challenge**: Grafana's Tempo datasource doesn't support label_values() queries like Prometheus.

---

## Data Model Recommendations

### Singular vs Plural Attribute Convention

For list-valued attributes, ContextCore uses both:
- **Singular** (`.persona`, `.channel`): Primary/default value
- **Plural** (`.personas`, `.channels`): Comma-separated full list

**Recommendation**: Document this pattern clearly and ensure all queries that need "any match" use the plural form with regex.

### TraceQL Query Patterns

| Use Case | Query Pattern |
|----------|---------------|
| Exact primary match | `{ .value.persona = "developer" }` |
| Any in list | `{ .value.personas =~ ".*developer.*" }` |
| Multiple conditions | `{ .value.type = "direct" && .value.personas =~ ".*developer.*" }` |

---

## Action Items

- [ ] Update `docs/skill-semantic-conventions.md` with correct persona query examples
- [ ] Document Tempo instance selection for different environments
- [ ] Consider datasource variable approach for dashboard portability
- [ ] File Grafana bug report for stat panel nil pointer with Tempo
- [ ] Add dynamic skill variable query when Grafana supports it

---

## Session Lessons (2026-01-24)

### Data Emission Target Awareness

**Lesson**: Always verify which backend you're emitting to before debugging "no data" issues.

**Pattern**:
```bash
# Check where data is going
echo $OTEL_EXPORTER_OTLP_ENDPOINT

# Check where Grafana is querying
curl -s http://localhost:3000/api/datasources -u admin:admin | jq '.[] | select(.type=="tempo") | .url'
```

### TraceQL Attribute Syntax

**Lesson**: TraceQL requires dot prefix for span attributes in filter clauses.

**Correct**: `{ name =~ "value_capability:.*" && .value.type = "direct" }`
**Wrong**: `{ name =~ "value_capability:.*" && value.type = "direct" }` (no dot)

### Dashboard Panel Type Selection

**Lesson**: When TraceQL queries cause Grafana plugin errors, switch from stat panels to table panels with footer row counts as a reliable alternative.

---

*Last Updated: 2026-01-24*
