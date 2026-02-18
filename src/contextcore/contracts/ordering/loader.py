"""
YAML contract loader for causal ordering contracts.

Inherits from ``BaseContractLoader`` for caching and validation.

Usage::

    from contextcore.contracts.ordering.loader import OrderingLoader

    loader = OrderingLoader()
    spec = loader.load(Path("pipeline-ordering.contract.yaml"))
"""

from __future__ import annotations

from contextcore.contracts._loader_base import BaseContractLoader
from contextcore.contracts.ordering.schema import OrderingConstraintSpec


class OrderingLoader(BaseContractLoader[OrderingConstraintSpec]):
    """Loads and caches causal ordering contracts from YAML files."""

    _model_class = OrderingConstraintSpec

    def _log_loaded(self, contract: OrderingConstraintSpec, key: str) -> None:
        self._logger.debug(
            "Loaded ordering contract: pipeline=%s, dependencies=%d",
            contract.pipeline_id,
            len(contract.dependencies),
        )
