"""
YAML contract loader with per-path caching for capability contracts.

Loads capability propagation contract YAML files, validates them against
the Pydantic schema models, and caches the result per file path.

Follows the ``ContractLoader`` caching pattern from
``contracts/propagation/loader.py``.

Usage::

    from contextcore.contracts.capability.loader import CapabilityLoader

    loader = CapabilityLoader()
    contract = loader.load(Path("artisan-pipeline.capability.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.capability.schema import CapabilityContract

logger = logging.getLogger(__name__)


class CapabilityLoader:
    """Loads and caches capability propagation contracts from YAML files."""

    _cache: ClassVar[dict[str, CapabilityContract]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> CapabilityContract:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``CapabilityContract`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Capability contract cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Capability contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        contract = CapabilityContract.model_validate(raw)
        self._cache[key] = contract

        logger.debug(
            "Loaded capability contract: pipeline=%s, capabilities=%d, "
            "phases=%d, chains=%d",
            contract.pipeline_id,
            len(contract.capabilities),
            len(contract.phases),
            len(contract.chains),
        )
        return contract

    def load_from_string(self, yaml_str: str) -> CapabilityContract:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``CapabilityContract`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return CapabilityContract.model_validate(raw)
