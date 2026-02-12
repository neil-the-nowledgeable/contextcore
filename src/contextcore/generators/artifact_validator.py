"""
Post-generation validation for observability artifacts.

Validates generated artifacts against schema URLs and reports validation errors.
Used by `contextcore manifest generate` (when implemented) to satisfy post-generation
validation (improvement suggestion #15).

Usage:
    from contextcore.generators.artifact_validator import validate_artifact

    result = validate_artifact(
        artifact_type="service_monitor",
        content="...",
        artifact_id="checkout-api-service-monitor",
    )
    if not result.valid:
        for err in result.errors:
            print(err)
"""

from dataclasses import dataclass, field
from typing import List, Optional

from contextcore.models.artifact_manifest import ArtifactType
from contextcore.utils.onboarding import ARTIFACT_OUTPUT_CONVENTIONS


@dataclass
class ValidationResult:
    """Result of artifact validation."""

    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifact_type: Optional[str] = None
    artifact_id: Optional[str] = None


def validate_artifact(
    artifact_type: str,
    content: str,
    artifact_id: Optional[str] = None,
) -> ValidationResult:
    """
    Validate a generated artifact against basic checks.

    Per improvement suggestion #15: After artifact generation, validate each
    artifact against the schema and report validation errors.

    Current validation:
    - YAML/JSON parseability (for .yaml and .json artifacts)
    - Non-empty content
    - Schema URL presence (for reference; actual schema fetch not implemented)

    Future: Fetch schema from schema_url and validate structure.
    """
    result = ValidationResult(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
    )

    if not content or not content.strip():
        result.valid = False
        result.errors.append("Artifact content is empty")
        return result

    conventions = ARTIFACT_OUTPUT_CONVENTIONS.get(artifact_type, {})
    output_ext = conventions.get("output_ext", ".yaml")
    schema_url = conventions.get("schema_url")

    if output_ext in (".yaml", ".yml"):
        try:
            import yaml

            yaml.safe_load(content)
        except Exception as e:
            result.valid = False
            result.errors.append(f"YAML parse error: {e}")
    elif output_ext == ".json":
        try:
            import json

            json.loads(content)
        except Exception as e:
            result.valid = False
            result.errors.append(f"JSON parse error: {e}")
    elif output_ext == ".md":
        if not content.strip().startswith("#"):
            result.warnings.append("Markdown runbook may not have expected header structure")

    if schema_url and not result.errors:
        result.warnings.append(
            f"Schema validation not implemented; use {schema_url} for manual validation"
        )

    return result


def validate_artifacts(
    artifacts: List[tuple[str, str, Optional[str]]],
) -> List[ValidationResult]:
    """
    Validate multiple artifacts.

    Args:
        artifacts: List of (artifact_type, content, artifact_id) tuples

    Returns:
        List of ValidationResult, one per artifact
    """
    return [
        validate_artifact(artifact_type=at, content=c, artifact_id=aid)
        for at, c, aid in artifacts
    ]
