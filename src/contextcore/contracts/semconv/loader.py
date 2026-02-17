"""
YAML contract loader with per-path caching for semantic convention contracts.

Follows the ``ContractLoader`` pattern from ``propagation/loader.py``.

Usage::

    from contextcore.contracts.semconv.loader import ConventionLoader

    loader = ConventionLoader()
    contract = loader.load(Path("otel-semconv.contract.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.semconv.schema import ConventionContract

logger = logging.getLogger(__name__)


class ConventionLoader:
    """Loads and caches semantic convention contracts from YAML files."""

    _cache: ClassVar[dict[str, ConventionContract]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> ConventionContract:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``ConventionContract`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Convention cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        contract = ConventionContract.model_validate(raw)
        self._cache[key] = contract

        logger.debug(
            "Loaded convention contract: namespace=%s, attributes=%d, enums=%d",
            contract.namespace,
            len(contract.attributes),
            len(contract.enums),
        )
        return contract

    def load_from_string(self, yaml_str: str) -> ConventionContract:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``ConventionContract`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return ConventionContract.model_validate(raw)
