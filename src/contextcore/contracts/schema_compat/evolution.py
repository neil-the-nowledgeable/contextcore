"""
Schema evolution tracker.

Detects changes between ``SchemaVersion`` snapshots and classifies them
against evolution policy rules.

Usage::

    from contextcore.contracts.schema_compat.evolution import EvolutionTracker

    tracker = EvolutionTracker(spec)
    result = tracker.check_evolution(old_version, new_version)
"""

from __future__ import annotations

import logging
from typing import Optional

from contextcore.contracts.schema_compat.schema import (
    EvolutionCheckResult,
    SchemaCompatibilitySpec,
    SchemaEvolutionRule,
    SchemaVersion,
)

logger = logging.getLogger(__name__)

# Change types used consistently across compare and policy checks
CHANGE_ADD_FIELD = "add_field"
CHANGE_REMOVE_FIELD = "remove_field"
CHANGE_CHANGE_FIELD_TYPE = "change_field_type"
CHANGE_ADD_ENUM_VALUE = "add_enum_value"
CHANGE_REMOVE_ENUM_VALUE = "remove_enum_value"
CHANGE_MAKE_REQUIRED = "make_required"
CHANGE_DEPRECATE_FIELD = "deprecate_field"

# Policy defaults — which change types each policy allows out of the box
_POLICY_DEFAULTS: dict[str, set[str]] = {
    "additive_only": {CHANGE_ADD_FIELD, CHANGE_ADD_ENUM_VALUE},
    "backward_compatible": {
        CHANGE_ADD_FIELD,
        CHANGE_ADD_ENUM_VALUE,
        CHANGE_DEPRECATE_FIELD,
    },
    "full": {
        CHANGE_ADD_FIELD,
        CHANGE_REMOVE_FIELD,
        CHANGE_CHANGE_FIELD_TYPE,
        CHANGE_ADD_ENUM_VALUE,
        CHANGE_REMOVE_ENUM_VALUE,
        CHANGE_MAKE_REQUIRED,
        CHANGE_DEPRECATE_FIELD,
    },
}


class EvolutionTracker:
    """Tracks schema evolution and validates changes against rules."""

    def __init__(self, contract: SchemaCompatibilitySpec) -> None:
        self._contract = contract

    def check_evolution(
        self, old_version: SchemaVersion, new_version: SchemaVersion
    ) -> EvolutionCheckResult:
        """Check whether evolving from *old_version* to *new_version* is allowed.

        Args:
            old_version: Previous schema snapshot.
            new_version: Proposed new schema snapshot.

        Returns:
            ``EvolutionCheckResult`` with breaking/compatible change lists.
        """
        changes = self.compare_versions(old_version, new_version)
        rule = self._find_rule(new_version.service)

        breaking: list[dict[str, str]] = []
        compatible: list[dict[str, str]] = []

        for change in changes:
            change_type = change["type"]
            if rule is not None:
                allowed = self.is_change_allowed(
                    change_type,
                    rule.policy,
                    rule.allowed_changes,
                    rule.forbidden_changes,
                )
            else:
                # No rule → all changes allowed
                allowed = True

            if allowed:
                compatible.append(change)
            else:
                breaking.append(change)

        is_compatible = len(breaking) == 0
        rule_id = rule.rule_id if rule else None

        if not is_compatible:
            logger.warning(
                "Schema evolution %s -> %s: %d breaking change(s)",
                old_version.version,
                new_version.version,
                len(breaking),
            )

        return EvolutionCheckResult(
            compatible=is_compatible,
            service=new_version.service,
            old_version=old_version.version,
            new_version=new_version.version,
            total_changes=len(changes),
            breaking_changes=breaking,
            compatible_changes=compatible,
            applicable_rule=rule_id,
            message=self._build_message(is_compatible, breaking, compatible),
        )

    def compare_versions(
        self, old: SchemaVersion, new: SchemaVersion
    ) -> list[dict[str, str]]:
        """Detect changes between two schema versions.

        Returns a list of change dicts with keys: ``type``, ``field``,
        and optional ``old`` / ``new`` values.
        """
        changes: list[dict[str, str]] = []

        old_fields = set(old.fields.keys())
        new_fields = set(new.fields.keys())

        # Added fields
        for field in sorted(new_fields - old_fields):
            changes.append({"type": CHANGE_ADD_FIELD, "field": field})

        # Removed fields
        for field in sorted(old_fields - new_fields):
            changes.append({"type": CHANGE_REMOVE_FIELD, "field": field})

        # Type changes
        for field in sorted(old_fields & new_fields):
            if old.fields[field] != new.fields[field]:
                changes.append({
                    "type": CHANGE_CHANGE_FIELD_TYPE,
                    "field": field,
                    "old": old.fields[field],
                    "new": new.fields[field],
                })

        # Enum changes
        all_enum_keys = set(old.enums.keys()) | set(new.enums.keys())
        for key in sorted(all_enum_keys):
            old_values = set(old.enums.get(key, []))
            new_values = set(new.enums.get(key, []))

            for val in sorted(new_values - old_values):
                changes.append({
                    "type": CHANGE_ADD_ENUM_VALUE,
                    "field": key,
                    "new": val,
                })
            for val in sorted(old_values - new_values):
                changes.append({
                    "type": CHANGE_REMOVE_ENUM_VALUE,
                    "field": key,
                    "old": val,
                })

        # Required field changes
        old_required = set(old.required_fields)
        new_required = set(new.required_fields)
        for field in sorted(new_required - old_required):
            changes.append({"type": CHANGE_MAKE_REQUIRED, "field": field})

        # Deprecated field changes
        old_deprecated = set(old.deprecated_fields)
        new_deprecated = set(new.deprecated_fields)
        for field in sorted(new_deprecated - old_deprecated):
            changes.append({"type": CHANGE_DEPRECATE_FIELD, "field": field})

        return changes

    @staticmethod
    def is_change_allowed(
        change_type: str,
        policy: str,
        allowed_changes: list[str],
        forbidden_changes: list[str],
    ) -> bool:
        """Determine whether a change type is allowed by the given policy.

        Evaluation order:
        1. ``forbidden_changes`` always wins — if listed, denied.
        2. ``allowed_changes`` overrides policy defaults.
        3. Policy defaults from ``_POLICY_DEFAULTS``.
        """
        if change_type in forbidden_changes:
            return False
        if change_type in allowed_changes:
            return True
        default_allowed = _POLICY_DEFAULTS.get(policy, set())
        return change_type in default_allowed

    # -- internal helpers --------------------------------------------------

    def _find_rule(self, service: str) -> Optional[SchemaEvolutionRule]:
        """Find the first evolution rule whose scope matches the service."""
        for rule in self._contract.evolution_rules:
            if service.startswith(rule.scope):
                return rule
        return None

    @staticmethod
    def _build_message(
        compatible: bool,
        breaking: list[dict[str, str]],
        compat: list[dict[str, str]],
    ) -> str:
        total = len(breaking) + len(compat)
        if compatible and total == 0:
            return "No changes detected"
        elif compatible:
            return f"{total} compatible change(s)"
        else:
            return f"{len(breaking)} breaking change(s) out of {total} total"
