"""
Dashboard provisioner for Grafana.

Handles provisioning ContextCore dashboards to Grafana via API.
Supports auto-detection of Grafana URL, idempotent provisioning,
and auto-discovery of dashboards from extension folders.
"""

from __future__ import annotations

import json
import logging
import os
import time as time_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import httpx

from contextcore.contracts.timeouts import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_DELAY_S,
    RETRYABLE_HTTP_STATUS_CODES,
)

from contextcore.dashboards.discovery import (
    EXTENSION_REGISTRY,
    DashboardConfig as DiscoveryConfig,
    discover_all_dashboards,
    get_dashboard_root,
)

logger = logging.getLogger(__name__)


@dataclass
class DashboardConfig:
    """Configuration for a dashboard to provision (legacy format for backwards compatibility)."""

    name: str
    uid: str
    file_name: str
    description: str
    folder: str = "ContextCore"
    tags: list[str] = field(default_factory=lambda: ["contextcore"])


class DashboardProvisioner:
    """
    Provision ContextCore dashboards to Grafana.

    Supports:
    - Auto-discovery of dashboards from extension folders
    - Auto-detection of Grafana URL from environment
    - API key or basic auth authentication
    - Idempotent provisioning (safe to run multiple times)
    - Per-extension folder organization
    - Extension filtering (provision only specific extensions)
    - Dry-run mode for preview

    Example:
        provisioner = DashboardProvisioner(
            grafana_url="http://localhost:3000",
            api_key="your-api-key"
        )

        # Provision all dashboards
        results = provisioner.provision_all()

        # Provision only core dashboards
        results = provisioner.provision_all(extension="core")

        for name, success, message in results:
            print(f"{name}: {'OK' if success else 'FAILED'} - {message}")
    """

    def __init__(
        self,
        grafana_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize the provisioner.

        Args:
            grafana_url: Grafana base URL. Auto-detected from GRAFANA_URL env var.
            api_key: Grafana API key. Auto-detected from GRAFANA_API_KEY env var.
            username: Basic auth username. Auto-detected from GRAFANA_USERNAME env var.
            password: Basic auth password. Auto-detected from GRAFANA_PASSWORD env var.
        """
        self.grafana_url = (
            grafana_url or os.environ.get("GRAFANA_URL", "http://localhost:3000")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("GRAFANA_API_KEY")
        self.username = username or os.environ.get("GRAFANA_USERNAME", "admin")
        self.password = password or os.environ.get("GRAFANA_PASSWORD", "admin")
        self._folder_cache: dict[str, int] = {}  # folder_uid -> folder_id
        self._dashboard_root = get_dashboard_root()

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for Grafana API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_auth(self) -> Optional[tuple[str, str]]:
        """Get basic auth credentials if no API key."""
        if self.api_key:
            return None
        return (self.username, self.password)

    def _request_with_retry(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs,
    ) -> httpx.Response:
        """
        Execute HTTP request with retry logic for transient Grafana failures.

        Retries on 502, 503, 504, 429 and connection/timeout errors
        with exponential backoff.

        Args:
            client: httpx.Client instance
            method: HTTP method (get, post, delete)
            url: Request URL
            max_retries: Max retry attempts
            **kwargs: Additional httpx request kwargs

        Returns:
            httpx.Response

        Raises:
            httpx.ConnectError: If all retries exhausted on connection failure
            httpx.TimeoutException: If all retries exhausted on timeout
        """
        delay = DEFAULT_RETRY_DELAY_S
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = getattr(client, method)(url, **kwargs)

                if response.status_code in RETRYABLE_HTTP_STATUS_CODES:
                    if attempt < max_retries:
                        logger.warning(
                            f"Grafana returned {response.status_code} for {url}, "
                            f"retrying in {delay:.1f}s ({attempt + 1}/{max_retries + 1})"
                        )
                        time_module.sleep(delay)
                        delay *= DEFAULT_RETRY_BACKOFF
                        continue
                    else:
                        logger.error(
                            f"Grafana returned {response.status_code} for {url} "
                            f"after {max_retries + 1} attempts"
                        )

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"Grafana request to {url} failed: {e}, "
                        f"retrying in {delay:.1f}s ({attempt + 1}/{max_retries + 1})"
                    )
                    time_module.sleep(delay)
                    delay *= DEFAULT_RETRY_BACKOFF
                else:
                    logger.error(
                        f"Grafana request to {url} failed after "
                        f"{max_retries + 1} attempts: {e}"
                    )
                    raise

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry loop exit")

    @staticmethod
    def _format_grafana_error(response: httpx.Response) -> str:
        """Format a Grafana API error response for human readability."""
        try:
            data = response.json()
            message = data.get("message", response.text)
        except (json.JSONDecodeError, ValueError):
            message = response.text
        return f"HTTP {response.status_code}: {message}"

    def _ensure_folder(
        self, client: httpx.Client, folder_name: str, folder_uid: str
    ) -> int:
        """
        Ensure a folder exists in Grafana and return its ID.

        Args:
            client: HTTP client
            folder_name: Display name for the folder
            folder_uid: Unique identifier for the folder

        Returns:
            Folder ID for use in dashboard provisioning
        """
        # Check cache first
        if folder_uid in self._folder_cache:
            return self._folder_cache[folder_uid]

        # Check if folder exists by UID
        try:
            response = self._request_with_retry(
                client,
                "get",
                f"{self.grafana_url}/api/folders/{folder_uid}",
                headers=self._get_headers(),
                auth=self._get_auth(),
            )
            if response.status_code == 200:
                folder_data = response.json()
                self._folder_cache[folder_uid] = folder_data["id"]
                return folder_data["id"]
        except Exception:
            pass

        # Check if folder exists by name (fallback)
        response = self._request_with_retry(
            client,
            "get",
            f"{self.grafana_url}/api/folders",
            headers=self._get_headers(),
            auth=self._get_auth(),
        )
        response.raise_for_status()

        folders = response.json()
        for folder in folders:
            if folder.get("title") == folder_name or folder.get("uid") == folder_uid:
                self._folder_cache[folder_uid] = folder["id"]
                return folder["id"]

        # Create folder
        response = self._request_with_retry(
            client,
            "post",
            f"{self.grafana_url}/api/folders",
            headers=self._get_headers(),
            auth=self._get_auth(),
            json={"title": folder_name, "uid": folder_uid},
        )
        response.raise_for_status()
        folder_id = response.json()["id"]
        self._folder_cache[folder_uid] = folder_id
        logger.info(f"Created folder '{folder_name}' (uid: {folder_uid})")
        return folder_id

    def _load_dashboard_json(self, config: DiscoveryConfig) -> dict:
        """
        Load dashboard JSON from file.

        Args:
            config: Discovery config with file path information

        Returns:
            Dashboard JSON as dictionary

        Raises:
            FileNotFoundError: If dashboard file cannot be found
        """
        file_path = config.effective_file_path
        if not file_path.exists():
            # Try alternative paths
            alt_paths = [
                self._dashboard_root / config.extension / config.file_name,
                self._dashboard_root / config.extension / f"{config.uid}.json",
                Path(config.file_name) if config.file_name else None,
            ]
            for alt_path in alt_paths:
                if alt_path and alt_path.exists():
                    file_path = alt_path
                    break
            else:
                raise FileNotFoundError(f"Dashboard file not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    def provision_dashboard(
        self,
        config: DiscoveryConfig,
        dry_run: bool = False,
    ) -> Tuple[str, bool, str]:
        """
        Provision a single dashboard to Grafana.

        Args:
            config: Dashboard configuration from discovery
            dry_run: If True, only validate without applying

        Returns:
            Tuple of (dashboard_title, success, message)
        """
        try:
            dashboard_json = self._load_dashboard_json(config)
        except FileNotFoundError as e:
            return (config.title or config.uid, False, str(e))

        if dry_run:
            return (config.title or config.uid, True, f"Dry run - would provision to {config.folder}")

        try:
            with httpx.Client(timeout=30.0) as client:
                # Get folder for this extension
                folder_id = self._ensure_folder(
                    client, config.folder, config.folder_uid
                )

                # Prepare dashboard payload
                payload = {
                    "dashboard": dashboard_json,
                    "folderId": folder_id,
                    "overwrite": True,
                    "message": f"Provisioned by ContextCore ({config.extension})",
                }

                # Create/update dashboard
                response = self._request_with_retry(
                    client,
                    "post",
                    f"{self.grafana_url}/api/dashboards/db",
                    headers=self._get_headers(),
                    auth=self._get_auth(),
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    return (
                        config.title or config.uid,
                        True,
                        f"Provisioned to {config.folder}: {data.get('url', config.uid)}",
                    )
                else:
                    return (
                        config.title or config.uid,
                        False,
                        self._format_grafana_error(response),
                    )

        except httpx.ConnectError:
            return (
                config.title or config.uid,
                False,
                f"Cannot connect to Grafana at {self.grafana_url}",
            )
        except Exception as e:
            return (config.title or config.uid, False, str(e))

    def provision_all(
        self,
        dry_run: bool = False,
        extension: Optional[str] = None,
    ) -> List[Tuple[str, bool, str]]:
        """
        Provision all discovered dashboards to Grafana.

        Uses auto-discovery to find all dashboards in extension folders
        and provisions them to the appropriate Grafana folders.

        Args:
            dry_run: If True, only validate without applying
            extension: Optional extension to filter by (e.g., "core", "squirrel")

        Returns:
            List of (dashboard_title, success, message) tuples

        Example:
            # Provision all dashboards
            results = provisioner.provision_all()

            # Provision only squirrel dashboards
            results = provisioner.provision_all(extension="squirrel")
        """
        # Discover dashboards using the discovery module
        dashboards = discover_all_dashboards(extension=extension)

        if not dashboards:
            logger.warning(
                f"No dashboards found{f' for extension {extension}' if extension else ''}"
            )
            return []

        logger.info(
            f"Provisioning {len(dashboards)} dashboards"
            f"{f' for extension {extension}' if extension else ''}"
        )

        results = []
        for config in dashboards:
            result = self.provision_dashboard(config, dry_run=dry_run)
            results.append(result)
            status = "OK" if result[1] else "FAILED"
            logger.debug(f"  {result[0]}: {status}")

        # Summary logging
        success_count = sum(1 for _, ok, _ in results if ok)
        fail_count = len(results) - success_count
        if fail_count > 0:
            logger.warning(
                f"Dashboard provisioning: {success_count} succeeded, {fail_count} failed"
            )
        else:
            logger.info(f"Dashboard provisioning: all {success_count} succeeded")

        return results

    def list_provisioned(self, extension: Optional[str] = None) -> List[dict]:
        """
        List ContextCore dashboards currently in Grafana.

        Args:
            extension: Optional extension to filter by

        Returns:
            List of dashboard info dicts with uid, title, url
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                params = {"tag": "contextcore"}

                # If extension specified, also filter by folder
                if extension and extension in EXTENSION_REGISTRY:
                    folder_uid = EXTENSION_REGISTRY[extension]["folder_uid"]
                    params["folderUIDs"] = folder_uid

                response = client.get(
                    f"{self.grafana_url}/api/search",
                    headers=self._get_headers(),
                    auth=self._get_auth(),
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to list dashboards: {e}")
            return []

    def delete_dashboard(self, uid: str) -> Tuple[bool, str]:
        """
        Delete a dashboard by UID.

        Args:
            uid: Dashboard UID

        Returns:
            Tuple of (success, message)
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.delete(
                    f"{self.grafana_url}/api/dashboards/uid/{uid}",
                    headers=self._get_headers(),
                    auth=self._get_auth(),
                )

                if response.status_code == 200:
                    return (True, f"Deleted dashboard {uid}")
                elif response.status_code == 404:
                    return (True, f"Dashboard {uid} not found (already deleted)")
                else:
                    return (False, f"HTTP {response.status_code}: {response.text}")

        except httpx.ConnectError:
            return (False, f"Cannot connect to Grafana at {self.grafana_url}")
        except Exception as e:
            return (False, str(e))

    def delete_all(
        self, extension: Optional[str] = None
    ) -> List[Tuple[str, bool, str]]:
        """
        Delete all ContextCore dashboards from Grafana.

        Uses auto-discovery to find dashboards to delete.

        Args:
            extension: Optional extension to filter by

        Returns:
            List of (uid, success, message) tuples
        """
        # Discover dashboards using the discovery module
        dashboards = discover_all_dashboards(extension=extension)

        results = []
        for config in dashboards:
            success, message = self.delete_dashboard(config.uid)
            results.append((config.uid, success, message))

        return results


# Backwards compatibility: provide DEFAULT_DASHBOARDS for existing code
# This will be populated lazily from discovery
_default_dashboards_cache: Optional[List[DashboardConfig]] = None


def get_default_dashboards() -> List[DashboardConfig]:
    """
    Get default dashboards for backwards compatibility.

    Returns legacy DashboardConfig objects converted from discovery.
    """
    global _default_dashboards_cache
    if _default_dashboards_cache is None:
        _default_dashboards_cache = []
        for config in discover_all_dashboards():
            _default_dashboards_cache.append(
                DashboardConfig(
                    name=config.title or config.uid,
                    uid=config.uid,
                    file_name=config.file_name or f"{config.uid}.json",
                    description=config.description,
                    folder=config.folder,
                    tags=config.tags or ["contextcore"],
                )
            )
    return _default_dashboards_cache


# For backwards compatibility, DEFAULT_DASHBOARDS is now a property-like access
# Code that imports DEFAULT_DASHBOARDS will get an empty list initially,
# but can call get_default_dashboards() for the full list
DEFAULT_DASHBOARDS: List[DashboardConfig] = []
