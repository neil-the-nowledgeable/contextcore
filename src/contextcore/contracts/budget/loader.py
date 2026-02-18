"""
YAML contract loader for budget propagation contracts.

Inherits from ``BaseContractLoader`` for caching and validation.

Usage::

    from contextcore.contracts.budget.loader import BudgetLoader

    loader = BudgetLoader()
    contract = loader.load(Path("pipeline-budget.contract.yaml"))
"""

from __future__ import annotations

from contextcore.contracts._loader_base import BaseContractLoader
from contextcore.contracts.budget.schema import BudgetPropagationSpec


class BudgetLoader(BaseContractLoader[BudgetPropagationSpec]):
    """Loads and caches budget propagation contracts from YAML files."""

    _model_class = BudgetPropagationSpec

    def _log_loaded(self, contract: BudgetPropagationSpec, key: str) -> None:
        self._logger.debug(
            "Loaded budget contract: pipeline=%s, budgets=%d",
            contract.pipeline_id,
            len(contract.budgets),
        )
