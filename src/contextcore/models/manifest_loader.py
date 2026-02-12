"""
Context Manifest version-aware loader.

Provides a unified entrypoint for loading manifests of any version (v1.1 or v2.0),
returning the appropriate model based on the `apiVersion` field.

Usage:
    from contextcore.models.manifest_loader import load_manifest

    # Returns ContextManifest for v1 or ContextManifestV2 for v2
    manifest = load_manifest("path/to/.contextcore.yaml")

    # Type-specific loading
    manifest_v1 = load_manifest_v1("path/to/.contextcore.yaml")
    manifest_v2 = load_manifest_v2("path/to/.contextcore.yaml")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Union

import yaml

from contextcore.models.manifest import ContextManifest, load_context_manifest
from contextcore.models.manifest_v2 import ContextManifestV2

if TYPE_CHECKING:
    from os import PathLike


# Type alias for the unified return type
ManifestType = Union[ContextManifest, ContextManifestV2]


# API versions for version detection
V1_API_VERSION = "contextcore.io/v1alpha1"
V2_API_VERSION = "contextcore.io/v1alpha2"

# Version patterns for flexible matching
V1_PATTERNS = {"contextcore.io/v1alpha1", "contextcore.io/v1", "1.0", "1.1"}
V2_PATTERNS = {"contextcore.io/v1alpha2", "contextcore.io/v2", "2.0"}


def detect_manifest_version(data: Dict[str, Any]) -> str:
    """
    Detect manifest version from raw YAML data.

    Returns:
        "v1.1" or "v2" based on apiVersion field

    Logic:
        - Explicit apiVersion: contextcore.io/v1alpha2 → v2
        - Otherwise → v1.1 (default)
    """
    api_version = data.get("apiVersion", "")

    if api_version in V2_PATTERNS:
        return "v2"

    # Also check for version field (used in v1.1)
    version = data.get("version", "")
    if version.startswith("2"):
        return "v2"

    return "v1.1"


def load_manifest(path: Union[str, "PathLike[str]"]) -> ManifestType:
    """
    Load a context manifest from a YAML file, automatically selecting the
    appropriate model based on the `apiVersion` field.

    Args:
        path: Path to the manifest YAML file

    Returns:
        ContextManifest for v1.x manifests, ContextManifestV2 for v2.x manifests

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If the manifest is invalid
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))

    version = detect_manifest_version(raw_data)

    if version == "v2":
        return ContextManifestV2(**raw_data)
    else:
        # Use the backward-compatible v1.1 loader
        return load_context_manifest(path)


def load_manifest_v1(path: Union[str, "PathLike[str]"]) -> ContextManifest:
    """
    Explicitly load a v1.1 manifest.

    Raises ValueError if the manifest appears to be v2.

    Args:
        path: Path to the manifest YAML file

    Returns:
        ContextManifest instance
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = detect_manifest_version(raw_data)

    if version == "v2":
        raise ValueError(
            f"Expected v1.1 manifest but got v2 (apiVersion: {raw_data.get('apiVersion')}). "
            "Use load_manifest() or load_manifest_v2() instead."
        )

    return load_context_manifest(path)


def load_manifest_v2(path: Union[str, "PathLike[str]"]) -> ContextManifestV2:
    """
    Explicitly load a v2 manifest.

    Raises ValueError if the manifest appears to be v1.x.

    Args:
        path: Path to the manifest YAML file

    Returns:
        ContextManifestV2 instance
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = detect_manifest_version(raw_data)

    if version != "v2":
        raise ValueError(
            f"Expected v2 manifest but got {version} (apiVersion: {raw_data.get('apiVersion')}). "
            "Use load_manifest() or load_manifest_v1() instead, or migrate with "
            "contextcore manifest migrate."
        )

    return ContextManifestV2(**raw_data)


def load_manifest_from_dict(data: Dict[str, Any]) -> ManifestType:
    """
    Load a manifest from an already-parsed dictionary.

    Useful when you've already parsed the YAML yourself.

    Args:
        data: Parsed manifest data

    Returns:
        ContextManifest or ContextManifestV2 based on apiVersion
    """
    version = detect_manifest_version(data)

    if version == "v2":
        return ContextManifestV2(**data)
    else:
        return ContextManifest(**data)
