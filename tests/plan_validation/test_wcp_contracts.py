"""
WCP Self-Validating Gap Verification — ContextCore contracts.

These tests verify that ContextCore contract types required by the WCP epic
exist and have the expected shape.  They are designed to FAIL before the
corresponding WCP task is implemented and PASS afterward.

Run after each WCP task:
    python3 -m pytest tests/plan_validation/test_wcp_contracts.py -v
"""

import pytest


# ---------------------------------------------------------------------------
# SV-001: PropagationStatus enum exists with correct values
# Fixed by: WCP-001
# ---------------------------------------------------------------------------

class TestSV001PropagationStatusEnum:
    """Verify PropagationStatus enum is defined in contracts/types.py."""

    def test_enum_importable(self):
        """PropagationStatus can be imported from contracts.types."""
        from contextcore.contracts.types import PropagationStatus  # noqa: F401

    def test_enum_has_four_values(self):
        """PropagationStatus has exactly 4 members."""
        from contextcore.contracts.types import PropagationStatus

        assert len(PropagationStatus) == 4

    def test_enum_values_lowercase(self):
        """All PropagationStatus values are lowercase strings."""
        from contextcore.contracts.types import PropagationStatus

        for member in PropagationStatus:
            assert member.value == member.value.lower(), (
                f"{member.name} value {member.value!r} is not lowercase"
            )

    def test_enum_expected_members(self):
        """PropagationStatus contains the 4 expected members."""
        from contextcore.contracts.types import PropagationStatus

        expected = {"propagated", "defaulted", "partial", "failed"}
        actual = {m.value for m in PropagationStatus}
        assert actual == expected, f"Expected {expected}, got {actual}"

    def test_convenience_list_exists(self):
        """PROPAGATION_STATUS_VALUES convenience list is defined."""
        from contextcore.contracts.types import PROPAGATION_STATUS_VALUES  # noqa: F401

        assert isinstance(PROPAGATION_STATUS_VALUES, list)
        assert len(PROPAGATION_STATUS_VALUES) == 4
