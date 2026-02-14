# Wayfinder Phase 1 Propagation Guide

> **Source commit**: `cfafe87` (ContextCore `main`)
> **Date**: 2026-02-03
> **Phase**: Phase 1 -- OTel Conventions Adoption

This document lists all changes needed in the Wayfinder repo (`~/Documents/dev/wayfinder`) to bring it in sync with the Phase 1 OTel conventions work done in ContextCore.

---

## Summary of Phase 1 Changes

| # | Change | ContextCore File(s) |
|---|--------|---------------------|
| 1 | `service.instance.id` resource attribute | `detector.py` |
| 2 | OTLP protocol factory (`OTEL_EXPORTER_OTLP_PROTOCOL`) | `exporter_factory.py` (new), `contracts/timeouts.py` |
| 3 | Exporter factory adoption in core modules | `tracker.py`, `metrics.py` |
| 4 | Conditional `SpanKind.CLIENT` for LLM calls | `agent/insights.py` |

---

## Change 1: `service.instance.id` Resource Attribute

**Wayfinder file**: `src/contextcore/detector.py`

### What to do

1. Add `import uuid` to imports (line 30)
2. Add `_INSTANCE_ID` module-level cache and `_get_instance_id()` function after `_get_contextcore_version()` (after line 52)
3. Add `"service.instance.id": _get_instance_id()` to the dict returned by `get_service_attributes()` (line 85)

### Code to add (after `_get_contextcore_version`):

```python
# Module-level cache so the instance ID is stable for the process lifetime
_INSTANCE_ID: Optional[str] = None


def _get_instance_id() -> str:
    """
    Get a stable service instance identifier.

    Resolution order:
    1. OTEL_SERVICE_INSTANCE_ID env var (explicit override)
    2. HOSTNAME env var if it contains hyphens (likely a K8s pod name)
    3. Generated UUID cached for process lifetime
    """
    global _INSTANCE_ID
    if _INSTANCE_ID is not None:
        return _INSTANCE_ID

    # 1. Explicit override
    explicit = os.environ.get("OTEL_SERVICE_INSTANCE_ID")
    if explicit:
        _INSTANCE_ID = explicit
        return _INSTANCE_ID

    # 2. K8s pod name (contains hyphens like "pod-name-abc12")
    hostname = os.environ.get("HOSTNAME", "")
    if "-" in hostname:
        _INSTANCE_ID = hostname
        return _INSTANCE_ID

    # 3. Generated UUID, stable for process lifetime
    _INSTANCE_ID = str(uuid.uuid4())
    return _INSTANCE_ID
```

---

## Change 2: OTLP Protocol Factory

### 2a. New file: `src/contextcore/exporter_factory.py`

Copy directly from ContextCore. This is a new file with no Wayfinder-specific modifications needed.

```bash
cp ~/Documents/dev/ContextCore/src/contextcore/exporter_factory.py \
   ~/Documents/dev/wayfinder/src/contextcore/exporter_factory.py
```

### 2b. Update: `src/contextcore/contracts/timeouts.py`

Add after `OTEL_DEFAULT_GRPC_PORT = 4317` (line 21):

```python
# Default OTLP HTTP/protobuf port
OTEL_DEFAULT_HTTP_PORT = 4318
```

---

## Change 3: Exporter Factory Adoption

### 3a. Core modules (identical to ContextCore)

These two files have the same change as ContextCore:

**`src/contextcore/tracker.py`** (line 224):
```python
# Before:
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# ...
exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

# After:
from contextcore.exporter_factory import create_span_exporter
# ...
exporter = create_span_exporter(endpoint=endpoint)
```

**`src/contextcore/metrics.py`** (line 181):
```python
# Before:
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
# ...
exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)

# After:
from contextcore.exporter_factory import create_metric_exporter
# ...
exporter = create_metric_exporter(endpoint=endpoint)
```

### 3b. Wayfinder-only files (additional scope beyond ContextCore)

These files exist only in Wayfinder and also hardcode gRPC. They should adopt the exporter factory for consistency:

| File | Line(s) | Exporter | Notes |
|------|---------|----------|-------|
| `operator.py` | 147-149 | `OTLPSpanExporter` | K8s operator setup |
| `demo/exporter.py` | 24 | `OTLPSpanExporter` | Top-level import, used in class constructor |
| `cli/install.py` | 31-32 | `OTLPSpanExporter` + `OTLPMetricExporter` | Both span and metric exporters |
| `cli/knowledge.py` | 86 | `OTLPSpanExporter` | Knowledge emission |
| `cli/terminology.py` | 67 | `OTLPSpanExporter` | Terminology emission |
| `cli/value.py` | 71 | `OTLPSpanExporter` | Value emission |
| `cli/skill.py` | 26 | `OTLPSpanExporter` | Skill emission |
| `cli_legacy.py` | 1679, 2332, 2997 | `OTLPSpanExporter` | 3 separate functions |

**Pattern for each**: Replace:
```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# ...
exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
```

With:
```python
from contextcore.exporter_factory import create_span_exporter
# ...
exporter = create_span_exporter(endpoint=endpoint)
```

And for metric exporters:
```python
from contextcore.exporter_factory import create_metric_exporter
# ...
exporter = create_metric_exporter(endpoint=endpoint)
```

> **Note on `demo/exporter.py`**: This file has a top-level import (not lazy). The factory import is also safe at top-level since it only imports constants, but verify the demo exporter's constructor still receives the endpoint correctly.

> **Note on `cli_legacy.py`**: This file is marked as "being replaced by modular cli/" in Wayfinder's CLAUDE.md. Consider whether to update all 3 occurrences or skip if deprecation is imminent.

---

## Change 4: Conditional SpanKind in InsightEmitter

**Wayfinder file**: `src/contextcore/agent/insights.py` (line 209-211)

```python
# Before:
with self.tracer.start_as_current_span(
    f"insight.{insight_type.value}",
    kind=SpanKind.INTERNAL,
) as span:

# After:
_span_kind = SpanKind.CLIENT if (provider or model) else SpanKind.INTERNAL
with self.tracer.start_as_current_span(
    f"insight.{insight_type.value}",
    kind=_span_kind,
) as span:
```

---

## Verification

After applying all changes in Wayfinder:

```bash
cd ~/Documents/dev/wayfinder

# Syntax check all modified files
python3 -m py_compile src/contextcore/detector.py
python3 -m py_compile src/contextcore/exporter_factory.py
python3 -m py_compile src/contextcore/contracts/timeouts.py
python3 -m py_compile src/contextcore/tracker.py
python3 -m py_compile src/contextcore/metrics.py
python3 -m py_compile src/contextcore/agent/insights.py
python3 -m py_compile src/contextcore/operator.py
python3 -m py_compile src/contextcore/demo/exporter.py
python3 -m py_compile src/contextcore/cli/install.py
python3 -m py_compile src/contextcore/cli/knowledge.py
python3 -m py_compile src/contextcore/cli/terminology.py
python3 -m py_compile src/contextcore/cli/value.py
python3 -m py_compile src/contextcore/cli/skill.py

# Functional checks
PYTHONPATH=src python3 -c "
from contextcore.detector import get_service_attributes
attrs = get_service_attributes()
assert 'service.instance.id' in attrs
print('service.instance.id OK')
"

PYTHONPATH=src python3 -c "
from contextcore.exporter_factory import _get_protocol
assert _get_protocol() == 'grpc'
print('Default protocol: grpc')
"

# Run tests
python3 -m pytest tests/ -x -q

# Verify no remaining hardcoded gRPC imports (expect 0 after full adoption)
grep -r "from opentelemetry.exporter.otlp.proto.grpc" src/contextcore/ --include="*.py"
```

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Default behavior unchanged | Low | Default protocol stays `grpc`, default port stays `4317` |
| `cli_legacy.py` has 3 hardcoded sites | Low | Legacy file being replaced; update all 3 or defer |
| `demo/exporter.py` uses top-level import | Low | Factory import is safe at top-level |
| `service.instance.id` is additive | None | New attribute, no existing queries filter by it |
| SpanKind change has no dashboard impact | None | No dashboards filter by span kind (verified) |
