"""
Tests for InsightQuerier TTL cache.
"""

import time
from unittest.mock import patch, MagicMock

import pytest

from contextcore.agent.insights import InsightQuerier, Insight, InsightType


@pytest.fixture
def querier():
    """Create querier with Tempo disabled, local disabled, short TTL."""
    return InsightQuerier(
        tempo_url=None,
        local_storage_path=None,
        cache_ttl_s=1.0,
    )


class TestInsightCache:
    """Tests for the InsightQuerier cache."""

    def test_cache_hit_returns_cached(self, querier):
        """Identical queries should return cached results."""
        # First call — empty result (no tempo, no local)
        result1 = querier.query(project_id="proj-1", time_range="1h")
        assert result1 == []

        # Manually inject a cached result to verify cache is used
        cache_key = querier._build_cache_key(
            project_id="proj-1",
            insight_type=None,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        fake_insight = MagicMock(spec=Insight)
        querier._cache[cache_key] = ([fake_insight], time.time())

        # Second call should return cached
        result2 = querier.query(project_id="proj-1", time_range="1h")
        assert len(result2) == 1
        assert result2[0] is fake_insight

    def test_cache_ttl_expiry(self, querier):
        """Expired cache entries should be refreshed."""
        # Seed cache with expired entry
        cache_key = querier._build_cache_key(
            project_id="proj-2",
            insight_type=None,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        old_insight = MagicMock(spec=Insight)
        querier._cache[cache_key] = ([old_insight], time.time() - 2.0)  # Expired

        # Should NOT return stale result
        result = querier.query(project_id="proj-2", time_range="1h")
        assert result == []  # Fresh empty result (no backend)

    def test_different_params_different_cache(self, querier):
        """Different query parameters should use different cache keys."""
        key1 = querier._build_cache_key(
            project_id="proj-a",
            insight_type=None,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        key2 = querier._build_cache_key(
            project_id="proj-b",
            insight_type=None,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        assert key1 != key2

    def test_invalidate_cache_clears_all(self, querier):
        """invalidate_cache should clear all entries."""
        # Seed cache
        querier._cache["key1"] = ([], time.time())
        querier._cache["key2"] = ([], time.time())

        querier.invalidate_cache()
        assert len(querier._cache) == 0

    def test_cache_key_with_enum_type(self, querier):
        """Cache key should handle InsightType enum correctly."""
        key1 = querier._build_cache_key(
            project_id="proj",
            insight_type=InsightType.DECISION,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        key2 = querier._build_cache_key(
            project_id="proj",
            insight_type=InsightType.LESSON,
            agent_id=None,
            audience=None,
            min_confidence=None,
            time_range="1h",
            limit=100,
            applies_to=None,
            category=None,
        )
        assert key1 != key2
