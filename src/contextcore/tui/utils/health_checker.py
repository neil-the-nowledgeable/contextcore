"""Service health checking utilities for ContextCore TUI."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp

__all__ = ["ServiceHealth", "ServiceHealthChecker"]


@dataclass
class ServiceHealth:
    """Health status information for a service."""
    name: str
    healthy: bool
    response_time_ms: Optional[int] = None
    error: Optional[str] = None


class ServiceHealthChecker:
    """Utility class for checking the health of observability services."""

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout

    async def check_http(self, name: str, url: str, timeout: Optional[float] = None) -> ServiceHealth:
        """Check HTTP endpoint health."""
        if timeout is None:
            timeout = self.timeout

        start_time = time.time()

        try:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(url) as response:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    healthy = response.status < 400

                    return ServiceHealth(
                        name=name,
                        healthy=healthy,
                        response_time_ms=response_time_ms,
                        error=None if healthy else f"HTTP {response.status}"
                    )

        except asyncio.TimeoutError:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error="Timeout"
            )
        except aiohttp.ClientConnectorError:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error="Connection refused"
            )
        except Exception as e:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error=str(e)
            )

    async def check_tcp(self, name: str, host: str, port: int, timeout: Optional[float] = None) -> ServiceHealth:
        """Check TCP port connectivity."""
        if timeout is None:
            timeout = self.timeout

        start_time = time.time()

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            response_time_ms = int((time.time() - start_time) * 1000)

            writer.close()
            await writer.wait_closed()

            return ServiceHealth(
                name=name,
                healthy=True,
                response_time_ms=response_time_ms
            )

        except asyncio.TimeoutError:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error="Connection timeout"
            )
        except ConnectionRefusedError:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error="Connection refused"
            )
        except Exception as e:
            return ServiceHealth(
                name=name,
                healthy=False,
                response_time_ms=None,
                error=str(e)
            )

    async def check_all(self) -> Dict[str, ServiceHealth]:
        """Check health of all observability services concurrently."""
        # Define service endpoints
        services = [
            ("Grafana", "http://localhost:3000/api/health"),
            ("Tempo", "http://localhost:3200/ready"),
            ("Mimir", "http://localhost:9009/ready"),
            ("Loki", "http://localhost:3100/ready"),
            ("Alloy", "http://localhost:12345/ready"),
        ]

        # Create HTTP check tasks
        http_tasks = [
            self.check_http(name, url) for name, url in services
        ]

        # Create TCP check task for OTLP gRPC
        tcp_task = self.check_tcp("OTLP gRPC", "localhost", 4317)

        # Execute all checks concurrently
        try:
            results = await asyncio.gather(*http_tasks, tcp_task, return_exceptions=True)

            health_dict = {}
            service_names = [name for name, _ in services] + ["OTLP gRPC"]

            for i, result in enumerate(results):
                service_name = service_names[i]
                if isinstance(result, ServiceHealth):
                    health_dict[service_name] = result
                elif isinstance(result, Exception):
                    health_dict[service_name] = ServiceHealth(
                        name=service_name,
                        healthy=False,
                        response_time_ms=None,
                        error=str(result)
                    )
                else:
                    health_dict[service_name] = ServiceHealth(
                        name=service_name,
                        healthy=False,
                        response_time_ms=None,
                        error="Unknown error"
                    )

            return health_dict

        except Exception as e:
            # Fallback if gather fails entirely
            service_names = [name for name, _ in services] + ["OTLP gRPC"]
            return {
                name: ServiceHealth(name=name, healthy=False, error=str(e))
                for name in service_names
            }
