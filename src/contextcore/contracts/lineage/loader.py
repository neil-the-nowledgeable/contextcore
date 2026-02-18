"""
YAML contract loader for data lineage contracts.

Inherits from ``BaseContractLoader`` for caching and validation.

Usage::

    from contextcore.contracts.lineage.loader import LineageLoader

    loader = LineageLoader()
    contract = loader.load(Path("pipeline-lineage.contract.yaml"))
"""

from __future__ import annotations

from contextcore.contracts._loader_base import BaseContractLoader
from contextcore.contracts.lineage.schema import LineageContract


class LineageLoader(BaseContractLoader[LineageContract]):
    """Loads and caches data lineage contracts from YAML files."""

    _model_class = LineageContract

    def _log_loaded(self, contract: LineageContract, key: str) -> None:
        self._logger.debug(
            "Loaded lineage contract: pipeline=%s, chains=%d",
            contract.pipeline_id,
            len(contract.chains),
        )
