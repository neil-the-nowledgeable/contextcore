"""
YAML contract loader with per-path caching for budget propagation contracts.

Loads budget propagation contract YAML files, validates them against the
Pydantic schema models, and caches the result per file path.

Follows the caching pattern from ``contracts/propagation/loader.py``.

Usage::

    from contextcore.contracts.budget.loader import BudgetLoader

    loader = BudgetLoader()
    contract = loader.load(Path("pipeline-budget.contract.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.budget.schema import BudgetPropagationSpec

logger = logging.getLogger(__name__)


class BudgetLoader:
    """Loads and caches budget propagation contracts from YAML files."""

    _cache: ClassVar[dict[str, BudgetPropagationSpec]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> BudgetPropagationSpec:
        """Load a budget contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``BudgetPropagationSpec`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Budget contract cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Budget contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        contract = BudgetPropagationSpec.model_validate(raw)
        self._cache[key] = contract

        logger.debug(
            "Loaded budget contract: pipeline=%s, budgets=%d",
            contract.pipeline_id,
            len(contract.budgets),
        )
        return contract

    def load_from_string(self, yaml_str: str) -> BudgetPropagationSpec:
        """Load a budget contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``BudgetPropagationSpec`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return BudgetPropagationSpec.model_validate(raw)
