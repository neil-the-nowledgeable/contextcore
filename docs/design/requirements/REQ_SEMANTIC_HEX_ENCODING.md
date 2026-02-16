# Requirements: Semantic Hex Encoding for Trace and Span Identifiers

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (high value, low complexity)
**Companion doc:** [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
**Related:** [SpanState v2 Schema](../../../src/contextcore/state.py), [Offline Task Store](../../../README.md)
**Estimated implementation:** ~150 lines + tests

---

## Problem Statement

OpenTelemetry trace IDs (32-char hex, 128 bits) and span IDs (16-char hex, 64 bits)
are opaque random values. When inspecting a trace in Tempo, a log line in Loki, or a
metric label in Mimir, the identifier `a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5` tells you
nothing about what project, feature set, or task it belongs to. You must look up the
trace, find its attributes, and read them to understand context.

This creates three problems:

1. **Cross-signal correlation requires lookups.** A Loki log line with
   `trace_id=a7f3b2c1...` cannot be associated with a project without querying
   Tempo to read the trace's `project.id` attribute. In high-volume environments,
   this round-trip is expensive and sometimes impossible (trace may have expired
   from Tempo while log persists in Loki).

2. **Offline task stores lose correlation.** ContextCore's offline task store
   format (`~/.persOS/context-core/`) serializes spans to JSON files for
   cross-session persistence. Random trace IDs in these files have no inherent
   meaning -- they are arbitrary identifiers that only gain context when loaded
   into an observability backend with their attributes intact.

3. **Human debugging is slower.** When a developer sees `trace_id=636f6e7465...`
   in a log, they cannot immediately tell which project generated it. With
   semantic encoding, `636f6e74657874636f72652f63637800` decodes to
   `"contextcore/ccx"` -- instantly identifying the project and feature set
   without any lookup.

**The key insight:** OTel IDs are constrained to be pure hex strings of fixed
length, but they are NOT constrained to be random. Any 32-char hex string is a
valid trace ID, and any 16-char hex string is a valid span ID. ASCII text
encoded as hex produces pure hex strings -- so we can encode project context
directly into the identifiers.

**The encoding scheme:**
- **trace_id** (32 hex = 16 bytes): UTF-8 encode `"{project_id}/{feature_set}"`,
  null-pad to 16 bytes, hex encode. Example: `"contextcore/ccx"` becomes
  `636f6e74657874636f72652f63637800`.
- **span_id** (16 hex = 8 bytes): UTF-8 encode `"{PREFIX}-{NNNN}"` (exactly 8
  chars), hex encode. Example: `"CCX-0001"` becomes `4343582d30303031`.

All encoded IDs are:
- **Pure hex** -- pass `[0-9a-f]{32}` and `[0-9a-f]{16}` validation.
- **OTel-valid** -- non-zero, correct length, accepted by any OTLP backend.
- **Deterministic** -- same input always produces the same ID.
- **Round-trip decodable** -- `bytes.fromhex(hex).decode('utf-8').rstrip('\x00')`
  recovers the original string.

**Why current code misses this:** `state.py` lines 598-616 define
`format_trace_id(trace_id: int) -> str` and `format_span_id(span_id: int) -> str`
which format random integers as hex. The OTel SDK's `RandomIdGenerator` produces
128-bit and 64-bit random integers. There is no facility for semantic encoding.

**The CS parallel:** This is **self-describing identifiers** from distributed
systems theory (similar to content-addressable storage where the hash IS the
content identifier). The identifier carries its own metadata, eliminating the
need for external lookups. Compare: URNs (`urn:isbn:0451450523`) encode the
namespace and resource in the identifier itself.

---

## Requirements

### REQ-SHE-001: SemanticTraceId encoder function

**Priority:** P1
**Description:** Define an `encode_trace_id(project_id: str, feature_set: str) -> str`
function that encodes a project identifier and feature set into a valid 32-character
hex trace ID. The function concatenates `"{project_id}/{feature_set}"`, UTF-8 encodes
the string, null-pads to exactly 16 bytes, and hex encodes the result.

**Acceptance criteria:**
- Returns a 32-character lowercase hex string.
- Passes `re.fullmatch(r'[0-9a-f]{32}', result)` validation.
- Result is non-zero (not `"0" * 32`).
- `"contextcore/ccx"` encodes to `636f6e74657874636f72652f63637800`.
- `"contextcore/ne"` encodes to `636f6e74657874636f72652f6e650000`.
- `"cc-startd8/otel"` encodes to `63632d737461727464382f6f74656c00`.
- Raises `ValueError` if the combined string exceeds 16 bytes after UTF-8 encoding.
- Raises `ValueError` if `project_id` is empty.

**Affected files:**
- `src/contextcore/identifiers.py` (new module)

---

### REQ-SHE-002: SemanticTraceId decoder function

**Priority:** P1
**Description:** Define a `decode_trace_id(hex_str: str) -> tuple[str, str]` function
that decodes a 32-character hex trace ID back into a `(project_id, feature_set)`
tuple. The function hex-decodes to bytes, UTF-8 decodes, strips null padding, and
splits on the first `/` separator.

**Acceptance criteria:**
- `decode_trace_id("636f6e74657874636f72652f63637800")` returns `("contextcore", "ccx")`.
- `decode_trace_id("636f6e74657874636f72652f6e650000")` returns `("contextcore", "ne")`.
- `decode_trace_id("63632d737461727464382f6f74656c00")` returns `("cc-startd8", "otel")`.
- Returns `("", "")` (empty tuple) for non-decodable hex (random IDs that are not
  valid UTF-8). This is graceful degradation, not an error.
- Raises `ValueError` if `hex_str` is not exactly 32 characters.
- Raises `ValueError` if `hex_str` contains non-hex characters.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-003: SemanticSpanId encoder function

**Priority:** P1
**Description:** Define an `encode_span_id(task_id: str) -> str` function that
encodes a task identifier into a valid 16-character hex span ID. The function UTF-8
encodes the task ID string, null-pads to exactly 8 bytes, and hex encodes the result.

**Acceptance criteria:**
- Returns a 16-character lowercase hex string.
- Passes `re.fullmatch(r'[0-9a-f]{16}', result)` validation.
- Result is non-zero (not `"0" * 16`).
- `"CCX-0001"` encodes to `4343582d30303031`.
- `"CCX-0010"` encodes to `4343582d30303130`.
- `"NE-00001"` encodes to `4e452d3030303031`.
- Raises `ValueError` if the task ID exceeds 8 bytes after UTF-8 encoding.
- Raises `ValueError` if `task_id` is empty.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-004: SemanticSpanId decoder function

**Priority:** P1
**Description:** Define a `decode_span_id(hex_str: str) -> str` function that
decodes a 16-character hex span ID back into a task identifier string. The function
hex-decodes to bytes, UTF-8 decodes, and strips null padding.

**Acceptance criteria:**
- `decode_span_id("4343582d30303031")` returns `"CCX-0001"`.
- `decode_span_id("4343582d30303130")` returns `"CCX-0010"`.
- `decode_span_id("4e452d3030303031")` returns `"NE-00001"`.
- Returns `""` (empty string) for non-decodable hex (random span IDs that are not
  valid UTF-8). Graceful degradation, not an error.
- Raises `ValueError` if `hex_str` is not exactly 16 characters.
- Raises `ValueError` if `hex_str` contains non-hex characters.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-005: is_semantic helper functions

**Priority:** P1
**Description:** Define `is_semantic_trace_id(hex_str: str) -> bool` and
`is_semantic_span_id(hex_str: str) -> bool` functions that detect whether a given
hex ID was produced by semantic encoding (as opposed to random generation). Detection
uses UTF-8 decodability: if the hex decodes to valid UTF-8 containing printable
ASCII characters, it is likely semantic.

**Acceptance criteria:**
- `is_semantic_trace_id("636f6e74657874636f72652f63637800")` returns `True`.
- `is_semantic_trace_id("a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5")` returns `False`
  (random hex is very unlikely to be valid printable ASCII).
- `is_semantic_span_id("4343582d30303031")` returns `True`.
- `is_semantic_span_id("a7f3b2c1d4e5f6a7")` returns `False`.
- Functions never raise exceptions -- they return `False` for any invalid input.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-006: Integration with format/parse functions in state.py

**Priority:** P1
**Description:** The existing `format_trace_id()`, `format_span_id()`,
`parse_trace_id()`, and `parse_span_id()` functions in `state.py` (lines 598-616)
must remain unchanged. The new semantic encoding functions are a separate API that
coexists with the existing integer-based format/parse functions. Code that generates
random IDs via OTel's `RandomIdGenerator` continues to work. Semantic IDs are opt-in.

**Acceptance criteria:**
- No changes to `state.py` lines 598-616.
- `format_trace_id(int)` and `format_span_id(int)` continue to accept integers.
- `parse_trace_id(str)` and `parse_span_id(str)` continue to return integers.
- Semantic IDs produced by `encode_trace_id()` are valid inputs to `parse_trace_id()`
  (they parse to an integer, though the integer is not meaningful).
- Random IDs produced by `format_trace_id(random_int)` are valid inputs to
  `decode_trace_id()` (they return empty strings, not errors).

**Affected files:**
- `src/contextcore/state.py` (no modifications -- compatibility verified by tests)
- `src/contextcore/identifiers.py`

---

### REQ-SHE-007: Prefix registry for span ID namespaces

**Priority:** P2
**Description:** Define a `SpanIdPrefix` registry that maps feature sets to their
span ID prefix conventions. This ensures span IDs within a trace use consistent,
non-colliding prefixes. The registry is a simple dict, not a database -- it lives
in `identifiers.py` and can be extended by users.

**Acceptance criteria:**
- Default registry includes at least:
  - `"ccx"` -> prefix `"CCX"` (Context Correctness Extensions)
  - `"ne"` -> prefix `"NE"` (general tasks)
  - `"wcp"` -> prefix `"WCP"` (Weaver Cross-repo Protocol)
- `build_span_id(prefix: str, sequence: int) -> str` creates a task ID string
  in the format `"{PREFIX}-{NNNN}"` and encodes it.
  - Example: `build_span_id("CCX", 1)` returns the hex encoding of `"CCX-0001"`.
  - Sequence number is zero-padded to fill remaining bytes (8 - len(prefix) - 1
  for the dash).
- `build_span_id()` raises `ValueError` if prefix + dash + sequence exceeds 8 bytes.
- Registry is informational -- `encode_span_id()` works with any string, not just
  registered prefixes.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-008: Integration with offline task store

**Priority:** P1
**Description:** The offline task store format (JSON files in `~/.persOS/context-core/`)
must support semantic hex IDs. When generating offline task store files, the
`encode_trace_id()` and `encode_span_id()` functions should be used to produce
correlated IDs. When importing offline task stores, `decode_trace_id()` and
`decode_span_id()` can be used to extract project context without reading attributes.

**Acceptance criteria:**
- Offline task store JSON files with semantic hex IDs pass SpanState v2 validation.
- `trace_id` values in offline stores are valid 32-char hex (pure hex, no prefix).
- `span_id` values in offline stores are valid 16-char hex.
- The `project.id` attribute in span attributes matches the decoded `project_id`
  from the trace ID (consistency check).
- Import code can detect semantic vs random IDs via `is_semantic_trace_id()` and
  handle both transparently.

**Affected files:**
- `src/contextcore/identifiers.py`
- Offline task store generator scripts (consumer, not modified)

---

### REQ-SHE-009: Cross-signal correlation documentation

**Priority:** P2
**Description:** Document how semantic hex IDs enable cross-signal correlation
across Tempo (traces), Loki (logs), and Mimir (metrics) without requiring attribute
lookups. Include example queries in TraceQL, LogQL, and PromQL that leverage the
decodable trace ID.

**Acceptance criteria:**
- Documentation includes:
  - TraceQL example: `{ trace:id = "636f6e74657874636f72652f63637800" }` to find
    all spans in the `contextcore/ccx` trace.
  - LogQL example: `{service_name="contextcore"} | json | trace_id="636f6e74657874636f72652f63637800"`
    to find correlated logs.
  - PromQL example: using trace ID as a label value for metric correlation.
  - Decoding workflow: copy hex from any signal, decode to project context.
- Documentation explains that semantic IDs are deterministic -- the same
  `(project_id, feature_set)` always produces the same trace ID, enabling
  "find all traces for this project/feature" queries.
- Documentation is added to `docs/semantic-conventions.md` under a new
  "Semantic Hex Identifiers" section.

**Affected files:**
- `docs/semantic-conventions.md` (new section)

---

### REQ-SHE-010: Input validation and safety

**Priority:** P1
**Description:** All encoding functions must validate inputs strictly. Invalid
inputs must produce clear error messages, not silent corruption or ambiguous hex.

**Acceptance criteria:**
- `encode_trace_id("", "")` raises `ValueError` with message mentioning project_id.
- `encode_trace_id("a-very-long-project-name", "feature")` raises `ValueError`
  with message mentioning the 16-byte limit and the actual byte count.
- `encode_span_id("")` raises `ValueError`.
- `encode_span_id("TOOLONG-01")` raises `ValueError` mentioning the 8-byte limit.
- Non-ASCII characters that are multi-byte in UTF-8 (e.g., emoji) are rejected
  if they would exceed the byte limit.
- The `/` separator in trace IDs is reserved -- `project_id` must not contain `/`.
  `encode_trace_id("proj/ect", "feat")` raises `ValueError`.
- Null bytes (`\x00`) in input strings are rejected (they would be confused with
  padding). `encode_span_id("CC\x00-0001")` raises `ValueError`.

**Affected files:**
- `src/contextcore/identifiers.py`

---

### REQ-SHE-011: Uniqueness guarantees and collision analysis

**Priority:** P2
**Description:** Document the uniqueness properties of semantic hex IDs and the
scenarios where collisions can occur. Semantic IDs are intentionally NOT unique
across traces -- the same `(project_id, feature_set)` always produces the same
trace ID. This is by design for correlation, but users must understand the tradeoff.

**Acceptance criteria:**
- Documentation explicitly states:
  - Semantic trace IDs are **deterministic, not unique**. All spans in the same
    `(project_id, feature_set)` share the same trace ID by design.
  - Semantic span IDs are unique within a trace if task IDs are unique within
    the feature set.
  - For use cases requiring globally unique IDs (live distributed tracing), use
    the existing `RandomIdGenerator`. Semantic encoding is for offline task
    stores, project tracking, and batch imports -- not live request tracing.
  - The 16-byte (trace) and 8-byte (span) limits restrict the namespace. Projects
    with IDs longer than ~12 characters (leaving room for `/{feature}`) should
    use abbreviated project IDs.
- A collision table documents the namespace capacity:
  - trace_id: 16 printable ASCII bytes = up to 16 characters of context.
  - span_id: 8 printable ASCII bytes = up to 8 characters of context.

**Affected files:**
- `docs/semantic-conventions.md` (within the Semantic Hex Identifiers section)

---

### REQ-SHE-012: OTel compliance validation

**Priority:** P1
**Description:** All semantic hex IDs must pass OTel validity checks. The
OpenTelemetry specification requires trace IDs to be non-zero 128-bit values
(32 hex chars) and span IDs to be non-zero 64-bit values (16 hex chars). The
encoding functions must guarantee these constraints.

**Acceptance criteria:**
- `encode_trace_id("a", "b")` produces a non-zero trace ID (the ASCII encoding
  of any non-empty string is always non-zero).
- `encode_span_id("A")` produces a non-zero span ID.
- All encoded IDs pass `int(hex_str, 16) != 0` (OTel INVALID_TRACE_ID / INVALID_SPAN_ID check).
- Encoded trace IDs are accepted by `opentelemetry.trace.TraceId` validation
  when available (guarded by `_HAS_OTEL`).
- Encoded span IDs are accepted by `opentelemetry.trace.SpanId` validation
  when available.

**Affected files:**
- `src/contextcore/identifiers.py` (validation within encode functions)

---

### REQ-SHE-013: Backward compatibility guarantee

**Priority:** P1
**Description:** All changes for semantic hex encoding must be fully backward
compatible. Existing code that uses random trace/span IDs must continue to work
without modification. Semantic encoding is opt-in, never forced.

**Acceptance criteria:**
- No existing tests in `tests/` break.
- `TaskTracker`, `StateManager`, and all existing consumers of trace/span IDs
  accept both random and semantic IDs without code changes.
- SpanState v2 validation accepts semantic IDs (they are valid hex strings).
- The `identifiers.py` module has no required dependencies on OTel -- it works
  with pure string operations.
- `format_trace_id()` and `parse_trace_id()` in `state.py` are NOT modified.

**Affected files:**
- All files -- verified by existing test suite

---

## Contract Schema

Semantic hex encoding does not introduce a new YAML contract type. It is a
utility that produces OTel-compliant identifiers with embedded project context.

### Encoding Functions (Python)

```python
def encode_trace_id(project_id: str, feature_set: str) -> str:
    """Encode project context into a 32-char hex trace ID.

    Args:
        project_id: Project identifier (no '/' or null bytes, ASCII).
        feature_set: Feature set identifier (no null bytes, ASCII).

    Returns:
        32-character lowercase hex string.

    Raises:
        ValueError: If inputs are empty, contain forbidden chars,
            or exceed 16 bytes when combined as "{project_id}/{feature_set}".
    """
    if not project_id:
        raise ValueError("project_id must not be empty")
    if "/" in project_id:
        raise ValueError("project_id must not contain '/'")
    if "\x00" in project_id or "\x00" in feature_set:
        raise ValueError("inputs must not contain null bytes")

    raw = f"{project_id}/{feature_set}"
    encoded = raw.encode("utf-8")
    if len(encoded) > 16:
        raise ValueError(
            f"Combined '{raw}' is {len(encoded)} bytes, max 16"
        )
    padded = encoded.ljust(16, b"\x00")
    return padded.hex()


def decode_trace_id(hex_str: str) -> tuple[str, str]:
    """Decode a semantic trace ID to (project_id, feature_set).

    Returns ("", "") if the hex is not a valid semantic encoding
    (e.g., random IDs). Never raises for valid 32-char hex input.
    """
    if len(hex_str) != 32:
        raise ValueError(f"trace_id must be 32 hex chars, got {len(hex_str)}")
    try:
        decoded = bytes.fromhex(hex_str).decode("utf-8").rstrip("\x00")
    except (ValueError, UnicodeDecodeError):
        return ("", "")

    if "/" not in decoded:
        return ("", "")

    parts = decoded.split("/", 1)
    if not all(c.isprintable() for c in decoded):
        return ("", "")

    return (parts[0], parts[1])


def encode_span_id(task_id: str) -> str:
    """Encode a task identifier into a 16-char hex span ID.

    Args:
        task_id: Task identifier (no null bytes, ASCII, max 8 bytes).

    Returns:
        16-character lowercase hex string.
    """
    if not task_id:
        raise ValueError("task_id must not be empty")
    if "\x00" in task_id:
        raise ValueError("task_id must not contain null bytes")

    encoded = task_id.encode("utf-8")
    if len(encoded) > 8:
        raise ValueError(
            f"task_id '{task_id}' is {len(encoded)} bytes, max 8"
        )
    padded = encoded.ljust(8, b"\x00")
    return padded.hex()


def decode_span_id(hex_str: str) -> str:
    """Decode a semantic span ID to a task identifier.

    Returns "" if the hex is not a valid semantic encoding.
    """
    if len(hex_str) != 16:
        raise ValueError(f"span_id must be 16 hex chars, got {len(hex_str)}")
    try:
        decoded = bytes.fromhex(hex_str).decode("utf-8").rstrip("\x00")
    except (ValueError, UnicodeDecodeError):
        return ""

    if not all(c.isprintable() for c in decoded):
        return ""

    return decoded
```

### Build Helper

```python
def build_span_id(prefix: str, sequence: int) -> str:
    """Build and encode a span ID from a prefix and sequence number.

    Example: build_span_id("CCX", 1) -> hex encoding of "CCX-0001"

    The prefix and dash consume len(prefix)+1 bytes. The remaining
    bytes (8 - len(prefix) - 1) are used for zero-padded sequence.
    """
    dash_and_prefix = len(prefix.encode("utf-8")) + 1  # +1 for dash
    remaining = 8 - dash_and_prefix
    if remaining < 1:
        raise ValueError(f"Prefix '{prefix}' too long, leaves no room for sequence")

    task_id = f"{prefix}-{sequence:0{remaining}d}"
    return encode_span_id(task_id)
```

### Encoding Examples

```
# Trace IDs (32 hex chars = 16 bytes)
"contextcore/ccx"  -> 636f6e74657874636f72652f63637800
"contextcore/ne"   -> 636f6e74657874636f72652f6e650000
"cc-startd8/otel"  -> 63632d737461727464382f6f74656c00
"beaver/cost"      -> 6265617665722f636f737400000000000

# Span IDs (16 hex chars = 8 bytes)
"CCX-0001"         -> 4343582d30303031
"CCX-0010"         -> 4343582d30303130
"NE-00001"         -> 4e452d3030303031
"WCP-0001"         -> 5743502d30303031

# Round-trip verification
bytes.fromhex("636f6e74657874636f72652f63637800").decode().rstrip('\x00')
# -> "contextcore/ccx"

bytes.fromhex("4343582d30303031").decode().rstrip('\x00')
# -> "CCX-0001"
```

---

## Integration Points

Semantic hex encoding is a cross-cutting utility. It integrates with the
existing ContextCore stack without modifying any interfaces.

### State Persistence (state.py)

Semantic IDs are valid hex strings. `StateManager.save_span()` stores trace_id
and span_id as strings -- semantic IDs pass through unchanged. No modifications
to `state.py` are required.

**Composition:** "Semantic IDs are transparent to state persistence."

### Task Tracker (tracker.py)

`TaskTracker.start_task()` currently receives trace IDs from the OTel SDK. For
offline/batch scenarios, callers can pass semantic IDs directly. The tracker
does not validate ID format beyond non-null checks.

**Composition:** "Tracker accepts semantic IDs as-is."

### Offline Task Store (persOS/context-core)

The offline task store JSON format stores trace_id and span_id as hex strings.
Semantic IDs are drop-in compatible. The store format gains implicit project
context in every ID without schema changes.

**Composition:** "Offline stores are self-describing via their IDs."

### Demo Exporter (demo/exporter.py)

`DualTelemetryExporter` formats trace_id and span_id with `format(ctx.trace_id, "032x")`.
Semantic IDs can be pre-computed and stored as integers via `int(hex_str, 16)`,
then formatted back to hex by the existing code path.

**Composition:** "Demo data can use semantic IDs for reproducible traces."

### Cross-Signal Queries

Semantic IDs enable direct correlation queries:

```
# Tempo (TraceQL): Find all spans for contextcore/ccx
{ trace:id = "636f6e74657874636f72652f63637800" }

# Loki (LogQL): Find correlated logs
{service_name="contextcore"} | json | trace_id="636f6e74657874636f72652f63637800"

# Mimir (PromQL): Metric labels with trace context
contextcore_task_percent_complete{trace_id="636f6e74657874636f72652f63637800"}

# Human workflow: Decode any ID from any signal
$ python3 -c "print(bytes.fromhex('636f6e74657874636f72652f63637800').decode().rstrip('\x00'))"
contextcore/ccx
```

**Composition:** "Any signal can identify the project without attribute lookups."

### Defense-in-Depth Layers

Semantic hex encoding does not interact with contract validation layers (1-7).
Contract validators check field presence, schema compatibility, quality
thresholds, etc. -- they do not inspect trace/span ID values. Semantic IDs
pass through all layers transparently.

**Composition:** "Orthogonal to contract validation."

---

## Test Requirements

### Unit Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_encode_trace_id_basic` | `"contextcore/ccx"` produces expected hex | P1 |
| `test_encode_trace_id_short` | `"a/b"` produces valid 32-char hex | P1 |
| `test_encode_trace_id_max_length` | 16-byte input produces valid hex without padding | P1 |
| `test_encode_trace_id_too_long` | 17+ bytes raises `ValueError` | P1 |
| `test_encode_trace_id_empty_project` | Empty project_id raises `ValueError` | P1 |
| `test_encode_trace_id_slash_in_project` | `/` in project_id raises `ValueError` | P1 |
| `test_encode_trace_id_null_in_input` | Null byte in input raises `ValueError` | P1 |
| `test_encode_trace_id_non_zero` | Result is never all zeros | P1 |
| `test_decode_trace_id_basic` | Decodes known hex to `("contextcore", "ccx")` | P1 |
| `test_decode_trace_id_random_hex` | Random hex returns `("", "")` | P1 |
| `test_decode_trace_id_no_slash` | Valid UTF-8 without `/` returns `("", "")` | P1 |
| `test_decode_trace_id_wrong_length` | Non-32-char input raises `ValueError` | P1 |
| `test_decode_trace_id_non_hex` | Non-hex characters raise `ValueError` | P1 |
| `test_encode_span_id_basic` | `"CCX-0001"` produces expected hex | P1 |
| `test_encode_span_id_short` | `"A"` produces valid 16-char hex | P1 |
| `test_encode_span_id_max_length` | 8-byte input produces valid hex without padding | P1 |
| `test_encode_span_id_too_long` | 9+ bytes raises `ValueError` | P1 |
| `test_encode_span_id_empty` | Empty string raises `ValueError` | P1 |
| `test_encode_span_id_null_in_input` | Null byte raises `ValueError` | P1 |
| `test_encode_span_id_non_zero` | Result is never all zeros | P1 |
| `test_decode_span_id_basic` | Decodes known hex to `"CCX-0001"` | P1 |
| `test_decode_span_id_random_hex` | Random hex returns `""` | P1 |
| `test_decode_span_id_wrong_length` | Non-16-char input raises `ValueError` | P1 |
| `test_is_semantic_trace_id_true` | Detects semantic trace ID | P1 |
| `test_is_semantic_trace_id_false` | Rejects random trace ID | P1 |
| `test_is_semantic_span_id_true` | Detects semantic span ID | P1 |
| `test_is_semantic_span_id_false` | Rejects random span ID | P1 |
| `test_build_span_id_basic` | `build_span_id("CCX", 1)` produces correct hex | P1 |
| `test_build_span_id_sequence_padding` | Sequence is zero-padded correctly | P1 |
| `test_build_span_id_prefix_too_long` | Long prefix raises `ValueError` | P1 |
| `test_round_trip_trace_id` | encode then decode returns original values | P1 |
| `test_round_trip_span_id` | encode then decode returns original value | P1 |

### Integration Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_semantic_id_with_state_manager` | SpanState with semantic IDs saves/loads correctly | P2 |
| `test_semantic_id_format_parse_compat` | `parse_trace_id(encode_trace_id(...))` returns valid int | P2 |
| `test_semantic_id_in_offline_store` | Offline store JSON with semantic IDs passes validation | P2 |
| `test_otel_trace_id_validity` | Semantic trace ID accepted by OTel TraceId validation | P2 |
| `test_otel_span_id_validity` | Semantic span ID accepted by OTel SpanId validation | P2 |
| `test_decode_graceful_with_random_ids` | Decode functions handle random IDs from existing data | P2 |

### Property-Based Tests (optional, P3)

| Test | Validates |
|------|-----------|
| `test_encode_decode_round_trip_trace` | For all valid `(project_id, feature_set)`, decode(encode(x)) == x |
| `test_encode_decode_round_trip_span` | For all valid task_id, decode(encode(x)) == x |
| `test_encoded_always_valid_hex` | All encoded outputs match `[0-9a-f]{N}` |
| `test_encoded_always_non_zero` | No encoded output equals all-zero ID |
| `test_deterministic` | Same input always produces same output |

---

## Non-Requirements

The following are explicitly out of scope for semantic hex encoding:

1. **Replacing random ID generation.** Semantic encoding is an alternative to
   random generation, not a replacement. The OTel SDK's `RandomIdGenerator`
   remains the default for live distributed tracing. Semantic encoding is for
   offline task stores, project tracking, and batch imports.

2. **Collision prevention.** Semantic IDs are deterministic -- the same
   `(project_id, feature_set)` always produces the same trace ID. This is by
   design for correlation. Callers requiring unique IDs per trace instance
   should use random generation.

3. **Encryption or obfuscation.** Semantic IDs are intentionally decodable.
   They carry project context in cleartext (encoded as hex). Do not use
   semantic IDs for sensitive project names or confidential identifiers.

4. **Unicode project names.** The encoding supports UTF-8, but the 16-byte
   (trace) and 8-byte (span) limits are tight. Multi-byte UTF-8 characters
   (accented letters, CJK, emoji) consume 2-4 bytes each, severely limiting
   the usable namespace. Use ASCII project identifiers for maximum capacity.

5. **Dynamic span ID assignment.** `build_span_id()` assigns sequential IDs
   from a prefix. It does NOT auto-increment or guarantee uniqueness across
   concurrent sessions. Sequence management is the caller's responsibility.

6. **Modifying OTel SDK ID generation.** Semantic encoding does NOT replace
   or monkey-patch the OTel SDK's `RandomIdGenerator`. It is a standalone
   utility that produces hex strings consumable by any code that accepts
   trace/span IDs as strings.

7. **Binary encoding schemes.** The encoding uses null-padded UTF-8, not a
   custom binary format. This keeps the implementation simple and the round-trip
   decodable with standard Python (`bytes.fromhex().decode()`). A more compact
   binary encoding could fit more context but at the cost of simplicity.

8. **Cross-project span ID uniqueness.** Span IDs are unique within a trace
   (same trace_id) but NOT across traces. `"CCX-0001"` in project A and
   `"CCX-0001"` in project B produce the same span ID hex. They are
   distinguished by their different trace IDs.
