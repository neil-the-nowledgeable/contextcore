"""
Capability Index Schema Validator.

Validates capability manifests against JSON Schema and checks evidence refs.
Complements the existing REQ-CID validator in capability_validator.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml

# Optional: use jsonschema if available
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def load_schema(schema_dir: Path, schema_name: str) -> dict:
    """Load a JSON Schema from the schema directory."""
    schema_path = schema_dir / f"{schema_name}.schema.yaml"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    return load_yaml(schema_path)


def validate_structure(manifest: dict) -> List[str]:
    """Basic structural validation without jsonschema."""
    errors: List[str] = []

    # Required fields
    required = ["manifest_id", "name", "version", "capabilities"]
    for field_name in required:
        if field_name not in manifest:
            errors.append(f"Missing required field: {field_name}")

    # Validate manifest_id format
    if "manifest_id" in manifest:
        mid = manifest["manifest_id"]
        if not isinstance(mid, str) or not mid.replace(".", "").replace("_", "").isalnum():
            errors.append(f"Invalid manifest_id format: {mid}")

    # Validate capabilities
    if "capabilities" in manifest:
        caps = manifest["capabilities"]
        if not isinstance(caps, list):
            errors.append("capabilities must be a list")
        elif len(caps) == 0:
            errors.append("capabilities must have at least one entry")
        else:
            for i, cap in enumerate(caps):
                cap_errors = validate_capability(cap, i)
                errors.extend(cap_errors)

    return errors


def validate_capability(cap: dict, index: int) -> List[str]:
    """Validate a single capability entry."""
    errors: List[str] = []
    prefix = f"capabilities[{index}]"

    # Required fields
    required = ["capability_id", "category", "maturity", "summary"]
    for field_name in required:
        if field_name not in cap:
            errors.append(f"{prefix}: Missing required field: {field_name}")

    # Validate capability_id format
    if "capability_id" in cap:
        cid = cap["capability_id"]
        if not isinstance(cid, str):
            errors.append(f"{prefix}: capability_id must be a string")
        elif not all(
            part.replace("_", "").isalnum() and part[0].isalpha()
            for part in cid.split(".")
        ):
            errors.append(f"{prefix}: Invalid capability_id format: {cid}")

    # Validate category enum
    valid_categories = [
        "transform", "generate", "validate", "query",
        "action", "security", "integration", "observe", "governance",
    ]
    if "category" in cap and cap["category"] not in valid_categories:
        errors.append(f"{prefix}: Invalid category: {cap['category']}")

    # Validate maturity enum (aligned with OTel semantic convention stability levels)
    valid_maturity = [
        "development", "alpha", "beta", "release_candidate", "stable", "deprecated",
    ]
    if "maturity" in cap and cap["maturity"] not in valid_maturity:
        errors.append(f"{prefix}: Invalid maturity: {cap['maturity']}")

    # Validate summary length
    if "summary" in cap and len(cap["summary"]) > 150:
        errors.append(f"{prefix}: Summary exceeds 150 characters")

    # Validate confidence range
    if "confidence" in cap:
        conf = cap["confidence"]
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            errors.append(f"{prefix}: Confidence must be 0.0-1.0")

    # Validate audiences
    valid_audiences = ["agent", "human", "gtm"]
    if "audiences" in cap:
        for aud in cap["audiences"]:
            if aud not in valid_audiences:
                errors.append(f"{prefix}: Invalid audience: {aud}")

    return errors


def check_evidence_refs(manifest: dict, base_path: Path) -> List[str]:
    """Check that evidence references exist."""
    errors: List[str] = []

    def check_ref(evidence: dict, context: str):
        ref = evidence.get("ref", "")

        # Skip URL refs
        if ref.startswith(("http://", "https://", "github://")):
            return

        # Check local file refs
        ref_path = base_path / ref
        if not ref_path.exists():
            errors.append(f"{context}: Evidence ref not found: {ref}")

    # Manifest-level evidence
    for i, ev in enumerate(manifest.get("evidence", [])):
        check_ref(ev, f"evidence[{i}]")

    # Capability-level evidence
    for i, cap in enumerate(manifest.get("capabilities", [])):
        for j, ev in enumerate(cap.get("evidence", [])):
            check_ref(ev, f"capabilities[{i}].evidence[{j}]")

    return errors


def validate_with_jsonschema(
    manifest: dict,
    schema_dir: Path
) -> List[str]:
    """Validate using jsonschema library."""
    if not HAS_JSONSCHEMA:
        return []

    errors: List[str] = []
    try:
        schema = load_schema(schema_dir, "manifest")
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
    except Exception as e:
        errors.append(f"Schema loading error: {e}")

    return errors


def validate_manifest(
    manifest_path: Path,
    schema_dir: Optional[Path] = None,
    check_evidence: bool = False
) -> Tuple[bool, List[str]]:
    """
    Validate a capability manifest.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: List[str] = []

    # Load manifest
    try:
        manifest = load_yaml(manifest_path)
    except Exception as e:
        return False, [f"Failed to load manifest: {e}"]

    # Structural validation
    errors.extend(validate_structure(manifest))

    # JSON Schema validation (if available and schema_dir provided)
    if schema_dir:
        errors.extend(validate_with_jsonschema(manifest, schema_dir))
    else:
        # Try bundled schemas
        bundled = Path(__file__).parent / "capability_schemas"
        if bundled.is_dir():
            errors.extend(validate_with_jsonschema(manifest, bundled))

    # Evidence ref checking
    if check_evidence:
        base_path = manifest_path.parent.parent  # Assume manifest is in capabilities/
        errors.extend(check_evidence_refs(manifest, base_path))

    return len(errors) == 0, errors
