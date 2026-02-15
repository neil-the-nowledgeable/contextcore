"""
YAML contract loader with per-path caching.

Loads context propagation contract YAML files, validates them against the
Pydantic schema models, and caches the result per file path.

Follows the ``_VALIDATORS`` cache pattern from ``a2a/validator.py:73``.

Usage::

    from contextcore.contracts.propagation.loader import ContractLoader

    loader = ContractLoader()
    contract = loader.load(Path("artisan-pipeline.contract.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.propagation.schema import ContextContract

logger = logging.getLogger(__name__)


class ContractLoader:
    """Loads and caches context propagation contracts from YAML files."""

    _cache: ClassVar[dict[str, ContextContract]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> ContextContract:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``ContextContract`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Contract cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        contract = ContextContract.model_validate(raw)
        self._cache[key] = contract

        logger.debug(
            "Loaded contract: pipeline=%s, phases=%d, chains=%d",
            contract.pipeline_id,
            len(contract.phases),
            len(contract.propagation_chains),
        )
        return contract

    def load_from_string(self, yaml_str: str) -> ContextContract:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``ContextContract`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return ContextContract.model_validate(raw)
