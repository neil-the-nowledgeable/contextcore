"""
Content-level verification gate functions for Gate 3.

Provides post-generation content checks that catch semantic errors in
generated source code — the class of bugs that syntactic linting misses.

Addresses REQ-PCG-022 req 6: Gate 3 has no content-level verification.

Four standalone functions + ``ContentVerifier`` wrapper (mirrors
:class:`GateChecker` pattern from ``gates.py``):

1. **scan_placeholders** — regex scan for leftover placeholder tokens
2. **verify_schema_fields** — cross-check proto field names against source
3. **verify_import_consistency** — imports vs dependency manifest
4. **verify_protocol_coherence** — transport protocol vs file indicators

Usage::

    from contextcore.contracts.a2a.content_verification import ContentVerifier

    verifier = ContentVerifier(trace_id="trace-123")
    verifier.scan_placeholders(source_dir="src/", task_id="T-001")
    verifier.verify_import_consistency(
        source_dir="src/", manifest_path="requirements.in", task_id="T-001",
    )
    if verifier.has_blocking_failure:
        print(verifier.summary())
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from contextcore.contracts.a2a.models import (
    EvidenceItem,
    GateOutcome,
    GateResult,
    GateSeverity,
    Phase,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Placeholder patterns (scan_placeholders)
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bREPLACE_WITH_\w+", re.IGNORECASE),
    re.compile(r"\bTODO:", re.IGNORECASE),
    re.compile(r"\bFIXME:", re.IGNORECASE),
    re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE),
    re.compile(r"\bINSERT_HERE\b", re.IGNORECASE),
    re.compile(r"\bXXX\b"),
]

_SOURCE_EXTENSIONS = {".py", ".go", ".js", ".ts", ".java", ".cs", ".proto"}


def _iter_source_files(source_dir: Path) -> list[Path]:
    """Yield source files from a directory tree."""
    files: list[Path] = []
    if not source_dir.is_dir():
        return files
    for p in source_dir.rglob("*"):
        if p.is_file() and p.suffix in _SOURCE_EXTENSIONS:
            files.append(p)
    return sorted(files)


# ---------------------------------------------------------------------------
# Gate 1: Placeholder scan
# ---------------------------------------------------------------------------


def scan_placeholders(
    *,
    gate_id: str,
    task_id: str,
    source_dir: str | Path,
    phase: Phase | str = Phase.FINALIZE_VERIFY,
    trace_id: str | None = None,
    blocking: bool = True,
    extra_patterns: list[str] | None = None,
) -> GateResult:
    """
    Scan source files for leftover placeholder tokens.

    Args:
        gate_id: Unique gate identifier.
        task_id: Parent task span ID.
        source_dir: Directory tree to scan.
        phase: Execution phase (default ``FINALIZE_VERIFY``).
        trace_id: Optional trace ID.
        blocking: Whether failures block downstream.
        extra_patterns: Additional regex patterns to scan for.

    Returns:
        A :class:`GateResult` with per-match evidence.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    patterns = list(_PLACEHOLDER_PATTERNS)
    for p in (extra_patterns or []):
        patterns.append(re.compile(p, re.IGNORECASE))

    evidence: list[EvidenceItem] = []
    source_path = Path(source_dir)

    for fpath in _iter_source_files(source_path):
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = str(fpath.relative_to(source_path))
        for lineno, line in enumerate(lines, start=1):
            for pat in patterns:
                match = pat.search(line)
                if match:
                    evidence.append(EvidenceItem(
                        type="placeholder_found",
                        ref=f"{rel}:{lineno}",
                        description=f"Pattern '{match.group()}' in {rel} line {lineno}.",
                    ))

    if evidence:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=f"Placeholder scan failed: {len(evidence)} placeholder(s) found in source files.",
            next_action="Replace all placeholder tokens with real values before finalizing.",
            blocking=blocking,
            evidence=evidence[:20],  # Cap evidence to avoid noise
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="Placeholder scan passed: no placeholder tokens found.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[EvidenceItem(
                type="placeholder_clean",
                ref="all",
                description="No placeholder patterns detected in source files.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info("Gate %s [%s]: %s", gate_id, result.result.value, result.reason)
    return result


# ---------------------------------------------------------------------------
# Gate 2: Schema field verification
# ---------------------------------------------------------------------------

# Matches proto message field definitions like:  string product_id = 1;
_PROTO_FIELD_RE = re.compile(
    r"^\s*(?:repeated\s+|optional\s+|map<[^>]+>\s+)?"
    r"(?:string|int32|int64|uint32|uint64|float|double|bool|bytes|enum|message|\w+)\s+"
    r"(\w+)\s*=\s*\d+",
)


def _parse_proto_fields(proto_path: Path) -> list[str]:
    """Extract field names from a .proto file via regex."""
    fields: list[str] = []
    if not proto_path.is_file():
        return fields
    try:
        text = proto_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fields
    for line in text.splitlines():
        m = _PROTO_FIELD_RE.match(line)
        if m:
            fields.append(m.group(1))
    return fields


def verify_schema_fields(
    *,
    gate_id: str,
    task_id: str,
    source_dir: str | Path,
    proto_path: str | Path,
    phase: Phase | str = Phase.FINALIZE_VERIFY,
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Parse .proto field names and check source files for wrong-casing references.

    Detects common errors like using ``productId`` instead of ``product_id``
    (proto uses snake_case; some languages use camelCase).

    Args:
        gate_id: Unique gate identifier.
        task_id: Parent task span ID.
        source_dir: Directory tree to scan.
        proto_path: Path to .proto schema file.
        phase: Execution phase.
        trace_id: Optional trace ID.
        blocking: Whether failures block downstream.

    Returns:
        A :class:`GateResult` with per-mismatch evidence.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    proto = Path(proto_path)
    if not proto.is_file():
        return GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.WARNING,
            reason=f"Proto file not found: {proto_path}. Schema field verification skipped.",
            next_action="Provide a valid .proto path for schema verification.",
            blocking=False,
            evidence=[EvidenceItem(
                type="proto_not_found",
                ref=str(proto_path),
                description=f"Proto file '{proto_path}' does not exist.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    fields = _parse_proto_fields(proto)
    if not fields:
        return GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="No proto fields parsed — schema field verification skipped.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            checked_at=datetime.now(timezone.utc),
        )

    # Build mapping of wrong variants (camelCase, singular/plural) to correct field
    wrong_variants: dict[str, str] = {}
    for field_name in fields:
        # snake_case → camelCase variant
        parts = field_name.split("_")
        if len(parts) > 1:
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
            wrong_variants[camel] = field_name
        # Simple singular/plural: add trailing 's' or strip trailing 's'
        if field_name.endswith("s") and len(field_name) > 2:
            wrong_variants[field_name[:-1]] = field_name
        elif not field_name.endswith("s"):
            wrong_variants[field_name + "s"] = field_name

    evidence: list[EvidenceItem] = []
    source_path = Path(source_dir)

    for fpath in _iter_source_files(source_path):
        if fpath.suffix == ".proto":
            continue  # Don't scan proto files against themselves
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(fpath.relative_to(source_path))
        for variant, correct in wrong_variants.items():
            # Use word boundary to avoid false positives
            if re.search(rf"\b{re.escape(variant)}\b", text):
                # Only flag if the correct field name is NOT also present
                if not re.search(rf"\b{re.escape(correct)}\b", text):
                    evidence.append(EvidenceItem(
                        type="schema_field_mismatch",
                        ref=f"{rel}",
                        description=f"Found '{variant}' but expected proto field '{correct}'.",
                    ))

    if evidence:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=f"Schema field verification failed: {len(evidence)} field mismatch(es).",
            next_action="Fix field names to match proto schema definitions.",
            blocking=blocking,
            evidence=evidence[:20],
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Schema field verification passed: {len(fields)} proto field(s) checked.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[EvidenceItem(
                type="schema_fields_verified",
                ref=str(proto_path),
                description=f"All {len(fields)} proto fields consistent with source references.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info("Gate %s [%s]: %s", gate_id, result.result.value, result.reason)
    return result


# ---------------------------------------------------------------------------
# Gate 3: Import consistency
# ---------------------------------------------------------------------------

# Python standard library modules (subset covering common ones)
_PYTHON_STDLIB = frozenset({
    "abc", "argparse", "ast", "asyncio", "base64", "bisect", "builtins",
    "calendar", "cmath", "codecs", "collections", "concurrent", "configparser",
    "contextlib", "copy", "csv", "ctypes", "dataclasses", "datetime",
    "decimal", "difflib", "email", "enum", "errno", "fcntl", "fileinput",
    "fnmatch", "fractions", "functools", "gc", "getpass", "glob", "gzip",
    "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
    "io", "ipaddress", "itertools", "json", "logging", "math", "mmap",
    "multiprocessing", "numbers", "operator", "os", "pathlib", "pickle",
    "platform", "pprint", "queue", "random", "re", "secrets", "select",
    "shelve", "shlex", "shutil", "signal", "socket", "sqlite3", "ssl",
    "stat", "statistics", "string", "struct", "subprocess", "sys",
    "sysconfig", "tempfile", "textwrap", "threading", "time", "timeit",
    "token", "tokenize", "traceback", "typing", "unicodedata", "unittest",
    "urllib", "uuid", "venv", "warnings", "weakref", "xml", "zipfile",
    "zlib", "_thread", "__future__",
})


def _extract_python_imports(source_dir: Path) -> set[str]:
    """Extract top-level package names from Python import statements."""
    packages: set[str] = set()
    import_re = re.compile(r"^\s*(?:import|from)\s+(\w+)")
    for fpath in source_dir.rglob("*.py"):
        try:
            for line in fpath.read_text(encoding="utf-8", errors="replace").splitlines():
                m = import_re.match(line)
                if m:
                    packages.add(m.group(1))
        except OSError:
            continue
    return packages


def _parse_python_requirements(manifest_path: Path) -> set[str]:
    """Parse package names from requirements.in / requirements.txt."""
    packages: set[str] = set()
    if not manifest_path.is_file():
        return packages
    # Map common PyPI names to import names
    pypi_to_import = {
        "grpcio": "grpc",
        "grpcio-tools": "grpc_tools",
        "grpcio-health-checking": "grpc_health",
        "grpcio-reflection": "grpc_reflection",
        "protobuf": "google",
        "googleapis-common-protos": "google",
        "google-cloud-profiler": "googlecloudprofiler",
        "opentelemetry-api": "opentelemetry",
        "opentelemetry-sdk": "opentelemetry",
        "opentelemetry-exporter-otlp": "opentelemetry",
        "flask": "flask",
        "jinja2": "jinja2",
        "pyyaml": "yaml",
        "python-dotenv": "dotenv",
    }
    try:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip version specifiers
            pkg = re.split(r"[>=<!\[;]", line)[0].strip().lower()
            if pkg:
                # Use mapping if available, otherwise normalize
                import_name = pypi_to_import.get(pkg, pkg.replace("-", "_"))
                packages.add(import_name)
    except OSError:
        pass
    return packages


def verify_import_consistency(
    *,
    gate_id: str,
    task_id: str,
    source_dir: str | Path,
    manifest_path: str | Path,
    phase: Phase | str = Phase.FINALIZE_VERIFY,
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Cross-check imports in source files against the dependency manifest.

    Currently supports Python (requirements.in / requirements.txt).
    Other languages return PASS with a skip note.

    Args:
        gate_id: Unique gate identifier.
        task_id: Parent task span ID.
        source_dir: Directory tree to scan for imports.
        manifest_path: Path to dependency manifest file.
        phase: Execution phase.
        trace_id: Optional trace ID.
        blocking: Whether failures block downstream.

    Returns:
        A :class:`GateResult` with per-missing-package evidence.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    manifest_file = Path(manifest_path)
    source_path = Path(source_dir)

    # Detect language from manifest filename
    manifest_name = manifest_file.name.lower()
    if manifest_name in ("requirements.in", "requirements.txt"):
        imported = _extract_python_imports(source_path)
        declared = _parse_python_requirements(manifest_file)

        # Filter out stdlib and local imports
        third_party = imported - _PYTHON_STDLIB
        # Exclude imports that look like local project modules
        local_modules: set[str] = set()
        for fpath in source_path.rglob("*.py"):
            mod_name = fpath.stem
            if mod_name != "__init__":
                local_modules.add(mod_name)
        # Also exclude parent directory names as potential local packages
        for fpath in source_path.rglob("__init__.py"):
            local_modules.add(fpath.parent.name)
        third_party -= local_modules

        missing = third_party - declared
    elif manifest_name in ("go.mod",):
        # Go stub — return PASS
        return GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="Import consistency for Go: stub (not yet implemented).",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            checked_at=datetime.now(timezone.utc),
        )
    elif manifest_name in ("package.json",):
        # Node.js stub
        return GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="Import consistency for Node.js: stub (not yet implemented).",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            checked_at=datetime.now(timezone.utc),
        )
    else:
        return GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.WARNING,
            reason=f"Unrecognized manifest format: {manifest_name}. Import check skipped.",
            next_action="Provide a supported manifest (requirements.in, go.mod, package.json).",
            blocking=False,
            checked_at=datetime.now(timezone.utc),
        )

    evidence: list[EvidenceItem] = []
    for pkg in sorted(missing):
        evidence.append(EvidenceItem(
            type="missing_dependency",
            ref=pkg,
            description=f"Package '{pkg}' is imported in source but not declared in {manifest_file.name}.",
        ))

    if evidence:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=f"Import consistency failed: {len(evidence)} package(s) imported but not declared.",
            next_action=f"Add missing packages to {manifest_file.name}.",
            blocking=blocking,
            evidence=evidence[:20],
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Import consistency passed: all third-party imports declared in {manifest_file.name}.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[EvidenceItem(
                type="imports_consistent",
                ref=str(manifest_path),
                description=f"All imports resolve to declared dependencies or stdlib.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info("Gate %s [%s]: %s", gate_id, result.result.value, result.reason)
    return result


# ---------------------------------------------------------------------------
# Gate 4: Protocol coherence
# ---------------------------------------------------------------------------

# Indicators of gRPC usage
_GRPC_INDICATORS = re.compile(
    r"grpc_health_probe|grpc\.insecure_channel|grpc\.secure_channel|"
    r"grpc\.aio\.|grpc_reflection|grpc_tools|add_\w+Servicer_to_server|"
    r"stub\s*=\s*\w+Stub\(",
    re.IGNORECASE,
)

# Indicators of HTTP usage
_HTTP_INDICATORS = re.compile(
    r"\burllib\b|\brequests\.\w+|\bhttp\.client\b|\bhttp\.server\b|"
    r"\bFlask\b|\bfastapi\b|\bDjango\b|\baiohttp\b|\bhttpx\b|"
    r"fetch\s*\(|axios\.\w+|net/http",
    re.IGNORECASE,
)


def verify_protocol_coherence(
    *,
    gate_id: str,
    task_id: str,
    source_dir: str | Path,
    transport_protocol: str,
    phase: Phase | str = Phase.FINALIZE_VERIFY,
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Check source/Dockerfiles for protocol mismatches against declared transport.

    Detects ``grpc_health_probe`` in HTTP service Dockerfiles, ``urllib``/
    ``requests`` in gRPC client code, etc.

    Args:
        gate_id: Unique gate identifier.
        task_id: Parent task span ID.
        source_dir: Directory tree to scan.
        transport_protocol: Declared protocol (``grpc``, ``http``, ``grpc-web``).
        phase: Execution phase.
        trace_id: Optional trace ID.
        blocking: Whether failures block downstream.

    Returns:
        A :class:`GateResult` with per-mismatch evidence.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    source_path = Path(source_dir)
    evidence: list[EvidenceItem] = []

    # Scan all source files + Dockerfiles
    scan_files: list[Path] = _iter_source_files(source_path)
    for p in source_path.rglob("Dockerfile*"):
        if p.is_file():
            scan_files.append(p)

    is_grpc = transport_protocol in ("grpc", "grpc-web")
    is_http = transport_protocol == "http"

    for fpath in scan_files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(fpath.relative_to(source_path)) if source_path.is_dir() else fpath.name

        if is_http:
            # HTTP service should NOT have gRPC indicators
            for match in _GRPC_INDICATORS.finditer(text):
                evidence.append(EvidenceItem(
                    type="protocol_mismatch",
                    ref=rel,
                    description=(
                        f"HTTP service has gRPC indicator '{match.group()}' in {rel}."
                    ),
                ))
        elif is_grpc:
            # gRPC service should NOT have HTTP client indicators
            # (but allow HTTP health endpoints — only flag urllib/requests/etc.)
            for match in _HTTP_INDICATORS.finditer(text):
                evidence.append(EvidenceItem(
                    type="protocol_mismatch",
                    ref=rel,
                    description=(
                        f"gRPC service has HTTP indicator '{match.group()}' in {rel}."
                    ),
                ))

    if evidence:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=(
                f"Protocol coherence failed: {len(evidence)} indicator(s) "
                f"mismatch declared protocol '{transport_protocol}'."
            ),
            next_action="Fix protocol usage to match declared transport_protocol.",
            blocking=blocking,
            evidence=evidence[:20],
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Protocol coherence passed: source consistent with '{transport_protocol}'.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[EvidenceItem(
                type="protocol_coherent",
                ref="all",
                description=f"No protocol mismatches for declared '{transport_protocol}'.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info("Gate %s [%s]: %s", gate_id, result.result.value, result.reason)
    return result


# ---------------------------------------------------------------------------
# ContentVerifier — convenience class (mirrors GateChecker)
# ---------------------------------------------------------------------------


class ContentVerifier:
    """
    Convenience wrapper carrying shared context across content verification gates.

    Usage::

        verifier = ContentVerifier(trace_id="trace-123")
        verifier.scan_placeholders(source_dir="src/", task_id="T-001")
        verifier.verify_schema_fields(
            source_dir="src/", proto_path="demo.proto", task_id="T-001",
        )
        if verifier.has_blocking_failure:
            print(verifier.summary())
    """

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id
        self.results: list[GateResult] = []

    # --- Properties --------------------------------------------------------

    @property
    def has_blocking_failure(self) -> bool:
        """``True`` if any gate result is blocking **and** failed."""
        return any(
            r.blocking and r.result == GateOutcome.FAIL for r in self.results
        )

    @property
    def blocking_failures(self) -> list[GateResult]:
        """Return all blocking failures."""
        return [
            r for r in self.results
            if r.blocking and r.result == GateOutcome.FAIL
        ]

    @property
    def all_passed(self) -> bool:
        """``True`` if every gate passed."""
        return all(r.result == GateOutcome.PASS for r in self.results)

    # --- Delegate methods --------------------------------------------------

    def scan_placeholders(
        self,
        *,
        gate_id: str = "content-verify-placeholders",
        task_id: str,
        source_dir: str | Path,
        phase: Phase | str = Phase.FINALIZE_VERIFY,
        blocking: bool = True,
        extra_patterns: list[str] | None = None,
    ) -> GateResult:
        """Run :func:`scan_placeholders` and record the result."""
        result = scan_placeholders(
            gate_id=gate_id,
            task_id=task_id,
            source_dir=source_dir,
            phase=phase,
            trace_id=self.trace_id,
            blocking=blocking,
            extra_patterns=extra_patterns,
        )
        self.results.append(result)
        return result

    def verify_schema_fields(
        self,
        *,
        gate_id: str = "content-verify-schema-fields",
        task_id: str,
        source_dir: str | Path,
        proto_path: str | Path,
        phase: Phase | str = Phase.FINALIZE_VERIFY,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`verify_schema_fields` and record the result."""
        result = verify_schema_fields(
            gate_id=gate_id,
            task_id=task_id,
            source_dir=source_dir,
            proto_path=proto_path,
            phase=phase,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def verify_import_consistency(
        self,
        *,
        gate_id: str = "content-verify-imports",
        task_id: str,
        source_dir: str | Path,
        manifest_path: str | Path,
        phase: Phase | str = Phase.FINALIZE_VERIFY,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`verify_import_consistency` and record the result."""
        result = verify_import_consistency(
            gate_id=gate_id,
            task_id=task_id,
            source_dir=source_dir,
            manifest_path=manifest_path,
            phase=phase,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def verify_protocol_coherence(
        self,
        *,
        gate_id: str = "content-verify-protocol",
        task_id: str,
        source_dir: str | Path,
        transport_protocol: str,
        phase: Phase | str = Phase.FINALIZE_VERIFY,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`verify_protocol_coherence` and record the result."""
        result = verify_protocol_coherence(
            gate_id=gate_id,
            task_id=task_id,
            source_dir=source_dir,
            transport_protocol=transport_protocol,
            phase=phase,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for logging / telemetry."""
        return {
            "total_gates": len(self.results),
            "passed": sum(1 for r in self.results if r.result == GateOutcome.PASS),
            "failed": sum(1 for r in self.results if r.result == GateOutcome.FAIL),
            "blocking_failures": len(self.blocking_failures),
            "all_passed": self.all_passed,
            "gate_ids": [r.gate_id for r in self.results],
        }
