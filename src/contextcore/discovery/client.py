# src/contextcore/discovery/client.py
__all__ = ['DiscoveryClient']


__all__ = ["DiscoveryClient"]

import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List
from urllib.parse import urljoin

from contextcore.models import AgentCard


logger = logging.getLogger(__name__)


class DiscoveryClient:
    """Client for discovering remote agents via HTTP and Tempo.
    
    Supports both A2A HTTP discovery and ContextCore Tempo discovery
    with caching and TTL management.
    """
    
    def __init__(
        self,
        cache_ttl_seconds: int = 300,
        tempo_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Initialize discovery client.
        
        Args:
            cache_ttl_seconds: Cache time-to-live in seconds
            tempo_url: Base URL for Tempo API (optional)
            timeout_seconds: HTTP request timeout
        """
        self._cache: Dict[str, Tuple[AgentCard, datetime]] = {}
        self.cache_ttl = cache_ttl_seconds
        self.tempo_url = tempo_url
        self.timeout = timeout_seconds
        self._http: Optional[httpx.Client] = None

    def __enter__(self) -> "DiscoveryClient":
        """Initialize HTTP client for context manager."""
        self._http = httpx.Client(timeout=self.timeout)
        return self

    def __exit__(self, *args) -> None:
        """Cleanup HTTP client."""
        if self._http:
            self._http.close()

    # HTTP discovery methods
    def discover(self, base_url: str) -> Optional[AgentCard]:
        """Fetch AgentCard from remote agent.
        
        Tries /.well-known/contextcore.json first (has more info),
        falls back to /.well-known/agent.json (A2A standard).
        Results are cached with TTL.
        
        Args:
            base_url: Base URL of the agent
            
        Returns:
            AgentCard if discovered, None otherwise
        """
        # Check cache first using base_url as key
        cached = self.get_cached(base_url)
        if cached is not None:
            return cached

        # Try ContextCore discovery first
        agent_card = self._fetch_contextcore_card(base_url)
        if agent_card is not None:
            return agent_card

        # Fall back to A2A discovery
        return self._fetch_a2a_card(base_url)

    def _fetch_contextcore_card(self, base_url: str) -> Optional[AgentCard]:
        """Fetch ContextCore discovery document."""
        if self._http is None:
            logger.warning("HTTP client not initialized - use context manager")
            return None
            
        try:
            url = urljoin(base_url.rstrip('/') + '/', '.well-known/contextcore.json')
            response = self._http.get(url)
            response.raise_for_status()
            
            agent_card = AgentCard.model_validate_json(response.text)
            # Cache using base_url as key
            self._cache[base_url] = (agent_card, datetime.now())
            logger.debug(f"Discovered ContextCore agent at {base_url}: {agent_card.id}")
            return agent_card
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning(f"Failed to fetch ContextCore card from {base_url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Invalid ContextCore card format from {base_url}: {e}")
            return None

    def _fetch_a2a_card(self, base_url: str) -> Optional[AgentCard]:
        """Fetch A2A agent.json."""
        if self._http is None:
            logger.warning("HTTP client not initialized - use context manager")
            return None
            
        try:
            url = urljoin(base_url.rstrip('/') + '/', '.well-known/agent.json')
            response = self._http.get(url)
            response.raise_for_status()
            
            agent_card = AgentCard.model_validate_json(response.text)
            # Cache using base_url as key
            self._cache[base_url] = (agent_card, datetime.now())
            logger.debug(f"Discovered A2A agent at {base_url}: {agent_card.id}")
            return agent_card
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning(f"Failed to fetch A2A card from {base_url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Invalid A2A card format from {base_url}: {e}")
            return None

    # Tempo discovery methods
    def discover_from_tempo(self, agent_id: str) -> Optional[AgentCard]:
        """Discover agent from Tempo spans.
        
        Queries Tempo for skill manifest spans and builds AgentCard
        from aggregated capabilities.
        
        Args:
            agent_id: ID of the agent to discover
            
        Returns:
            AgentCard if found in Tempo, None otherwise
        """
        # Check cache first using agent_id as key for Tempo discoveries
        cached = self.get_cached(agent_id)
        if cached is not None:
            return cached

        if not self.tempo_url:
            logger.warning("Tempo URL not configured")
            return None

        # Query for skill spans from this agent
        query = f'{{ agent.id = "{agent_id}" && name =~ "skill:.*" }}'
        spans = self._query_tempo(query)
        
        if not spans:
            logger.debug(f"No skill spans found for agent {agent_id}")
            return None

        return self._build_agent_card_from_spans(agent_id, spans)

    def list_agents_from_tempo(self, time_range: str = "24h") -> List[str]:
        """List all agent IDs found in Tempo.
        
        Args:
            time_range: Time range to search (e.g., "24h", "1d")
            
        Returns:
            List of unique agent IDs
        """
        if not self.tempo_url:
            logger.warning("Tempo URL not configured")
            return []

        # Query for all skill spans and extract unique agent IDs
        query = f'{{ name =~ "skill:.*" }} | select(agent.id) | distinct'
        spans = self._query_tempo(query)
        
        if not spans:
            return []

        # Extract agent IDs from spans
        agent_ids = []
        for span in spans:
            if 'agent' in span and 'id' in span['agent']:
                agent_ids.append(span['agent']['id'])
        
        return list(set(agent_ids))  # Remove duplicates

    def _query_tempo(self, query: str) -> Optional[List[dict]]:
        """Execute TraceQL query against Tempo."""
        if self._http is None:
            logger.warning("HTTP client not initialized - use context manager")
            return None
            
        try:
            # Use Tempo's search API with TraceQL query
            url = f"{self.tempo_url.rstrip('/')}/api/search"
            params = {"q": query, "limit": 100}
            
            response = self._http.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            # Tempo API returns traces, we need to extract spans
            spans = []
            if 'traces' in data:
                for trace in data['traces']:
                    if 'spans' in trace:
                        spans.extend(trace['spans'])
            
            return spans
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning(f"Tempo query failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"Invalid Tempo response format: {e}")
            return None

    def _build_agent_card_from_spans(self, agent_id: str, spans: List[dict]) -> Optional[AgentCard]:
        """Build AgentCard from skill manifest spans."""
        try:
            capabilities = []
            
            # Extract capabilities from skill spans
            for span in spans:
                if span.get('operationName', '').startswith('skill:'):
                    # Extract capability info from span attributes/tags
                    skill_name = span.get('operationName', '').replace('skill:', '')
                    
                    # Build capability from span data
                    capability = {
                        'name': skill_name,
                        'description': span.get('tags', {}).get('description', f'{skill_name} capability')
                    }
                    capabilities.append(capability)
            
            if not capabilities:
                logger.warning(f"No capabilities found in spans for agent {agent_id}")
                return None
            
            # Create AgentCard with discovered capabilities
            agent_card = AgentCard(
                id=agent_id,
                name=f"Agent {agent_id}",  # Default name
                capabilities=capabilities
            )
            
            # Cache using agent_id as key
            self._cache[agent_id] = (agent_card, datetime.now())
            logger.debug(f"Built agent card from Tempo for {agent_id} with {len(capabilities)} capabilities")
            return agent_card
            
        except Exception as e:
            logger.warning(f"Failed to build agent card from spans: {e}")
            return None

    # Cache management methods
    def get_cached(self, key: str) -> Optional[AgentCard]:
        """Get agent from cache if not expired.
        
        Args:
            key: Cache key (agent_id or base_url)
            
        Returns:
            Cached AgentCard if valid, None otherwise
        """
        if key not in self._cache:
            return None
            
        agent_card, timestamp = self._cache[key]
        
        # Check if cache entry is still valid
        if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
            return agent_card
        
        # Cache expired, remove entry
        del self._cache[key]
        return None

    def invalidate(self, key: str) -> None:
        """Remove agent from cache.
        
        Args:
            key: Cache key to invalidate (agent_id or base_url)
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Invalidated cache entry for {key}")

    def clear_cache(self) -> None:
        """Clear all cached agents."""
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {count} cached entries")

    def list_known_agents(self) -> List[AgentCard]:
        """Return all cached agents (even if expired).
        
        Returns:
            List of all AgentCards in cache
        """
        return [agent_card for agent_card, _ in self._cache.values()]
