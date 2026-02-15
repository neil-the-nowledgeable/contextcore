"""
YAML contract loader with per-path caching for schema compatibility contracts.

Follows the ``ContractLoader`` pattern from ``propagation/loader.py``.

Usage::

    from contextcore.contracts.schema_compat.loader import SchemaCompatLoader

    loader = SchemaCompatLoader()
    spec = loader.load(Path("cross-service.compat.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.schema_compat.schema import SchemaCompatibilitySpec

logger = logging.getLogger(__name__)


class SchemaCompatLoader:
    """Loads and caches schema compatibility contracts from YAML files."""

    _cache: ClassVar[dict[str, SchemaCompatibilitySpec]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> SchemaCompatibilitySpec:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``SchemaCompatibilitySpec`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Schema compat cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        spec = SchemaCompatibilitySpec.model_validate(raw)
        self._cache[key] = spec

        logger.debug(
            "Loaded schema compat contract: mappings=%d, rules=%d, versions=%d",
            len(spec.mappings),
            len(spec.evolution_rules),
            len(spec.versions),
        )
        return spec

    def load_from_string(self, yaml_str: str) -> SchemaCompatibilitySpec:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``SchemaCompatibilitySpec`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return SchemaCompatibilitySpec.model_validate(raw)
