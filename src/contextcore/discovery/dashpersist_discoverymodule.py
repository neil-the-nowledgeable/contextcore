"""
Dashboard discovery module for auto-discovering dashboards from filesystem and entry points.

This module provides functionality to automatically discover Grafana dashboards from:
1. Filesystem locations (grafana/provisioning/dashboards/{extension}/*.json)
2. Python entry points (contextcore.dashboards group)
"""

import json
import logging
from pathlib import Path
from importlib.metadata import entry_points
from typing import Dict, Generator, List, Optional, Any, Union
from dataclasses import dataclass, field

# Set up logging
logger = logging.getLogger(__name__)

__all__ = [
    'EXTENSION_REGISTRY',
    'DashboardConfig', 
    'discover_from_filesystem',
    'discover_from_entry_points',
    'discover_all_dashboards',
    'list_extensions'
]

# Extension registry mapping extension keys to metadata
EXTENSION_REGISTRY: Dict[str, Dict[str, str]] = {
    "core": {
        "name": "ContextCore Core",
        "folder": "ContextCore",
        "folder_uid": "contextcore"
    },
    "squirrel": {
        "name": "Squirrel (Skills)",
        "folder": "ContextCore / Squirrel",
        "folder_uid": "contextcore-squirrel"
    },
    "web": {
        "name": "Web Scraping",
        "folder": "ContextCore / Web",
        "folder_uid": "contextcore-web"
    },
    "analytics": {
        "name": "Analytics",
        "folder": "ContextCore / Analytics",
        "folder_uid": "contextcore-analytics"
    },
    "security": {
        "name": "Security",
        "folder": "ContextCore / Security", 
        "folder_uid": "contextcore-security"
    }
}


@dataclass
class DashboardConfig:
    """
    Configuration for a Grafana dashboard with auto-discovery support.
    
    Attributes:
        uid: Unique identifier for the dashboard
        title: Display title of the dashboard
        description: Optional description text
        tags: List of tags for categorization
        extension: Extension this dashboard belongs to
        file_path: Optional explicit file path to dashboard JSON
    """
    uid: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    extension: str = "core"
    file_path: Optional[Path] = None

    @property
    def effective_file_path(self) -> Path:
        """
        Resolve the effective file path for this dashboard.
        
        Returns the explicit file_path if set and exists, otherwise constructs
        the expected path based on extension and uid.
        
        Returns:
            Path to the dashboard JSON file
            
        Example:
            >>> config = DashboardConfig(uid="my-dash", extension="core")
            >>> str(config.effective_file_path)
            'grafana/provisioning/dashboards/core/my-dash.json'
        """
        if self.file_path and self.file_path.exists():
            return self.file_path
        
        # Construct standard path based on extension and uid
        grafana_root = Path("grafana/provisioning/dashboards")
        return grafana_root / self.extension / f"{self.uid}.json"


def discover_from_filesystem(extension: Optional[str] = None) -> Generator[DashboardConfig, None, None]:
    """
    Discover dashboards from filesystem JSON files.
    
    Scans grafana/provisioning/dashboards/{extension}/ for *.json files
    and parses them into DashboardConfig objects.
    
    Args:
        extension: Optional extension to filter by. If None, scans all extensions.
        
    Yields:
        DashboardConfig: Parsed dashboard configurations
        
    Example:
        >>> list(discover_from_filesystem("core"))
        [DashboardConfig(uid='system-overview', title='System Overview', ...)]
    """
    extensions_to_scan = [extension] if extension else list(EXTENSION_REGISTRY.keys())
    
    for ext in extensions_to_scan:
        if ext not in EXTENSION_REGISTRY:
            logger.warning(f"Unknown extension '{ext}', skipping")
            continue
            
        dashboard_dir = _get_extension_dashboard_dir(ext)
        logger.debug(f"Scanning for dashboards in {dashboard_dir}")
        
        if not dashboard_dir.is_dir():
            logger.debug(f"Directory {dashboard_dir} does not exist, skipping")
            continue
            
        # Scan all JSON files in the extension directory
        for json_file in dashboard_dir.glob("*.json"):
            config = _parse_dashboard_json(json_file, ext)
            if config:
                yield config


def discover_from_entry_points(extension: Optional[str] = None) -> Generator[DashboardConfig, None, None]:
    """
    Discover dashboards from Python entry points.
    
    Loads entry points from the 'contextcore.dashboards' group and calls
    their get_dashboards() function to retrieve dashboard configurations.
    
    Args:
        extension: Optional extension to filter by
        
    Yields:
        DashboardConfig: Dashboard configurations from entry points
        
    Example:
        >>> list(discover_from_entry_points("squirrel"))
        [DashboardConfig(uid='skills-overview', title='Skills Overview', ...)]
    """
    logger.debug("Discovering dashboards from entry points")
    
    try:
        eps = entry_points(group="contextcore.dashboards")
    except TypeError:
        # Fallback for older Python versions
        eps = entry_points().get("contextcore.dashboards", [])
    
    for entry_point in eps:
        # Filter by extension if specified
        if extension and entry_point.name != extension:
            continue
            
        try:
            # Load the entry point module
            module = entry_point.load()
            
            # Call get_dashboards() function
            if not hasattr(module, 'get_dashboards'):
                logger.warning(f"Entry point {entry_point.name} missing get_dashboards() function")
                continue
                
            dashboards = module.get_dashboards()
            
            # Convert each dashboard dict to DashboardConfig
            for dashboard_data in dashboards:
                if _validate_entry_point_dashboard(dashboard_data):
                    config = DashboardConfig(
                        uid=dashboard_data['uid'],
                        title=dashboard_data.get('title', ''),
                        description=dashboard_data.get('description', ''),
                        tags=dashboard_data.get('tags', []),
                        extension=entry_point.name
                    )
                    yield config
                    
        except Exception as e:
            logger.error(f"Failed to load entry point {entry_point.name}: {e}")


def discover_all_dashboards(extension: Optional[str] = None) -> List[DashboardConfig]:
    """
    Discover all dashboards from both filesystem and entry points.
    
    Combines results from filesystem and entry point discovery, with entry points
    taking precedence over filesystem when UIDs conflict (deduplication).
    
    Args:
        extension: Optional extension to filter by
        
    Returns:
        List of unique DashboardConfig objects
        
    Example:
        >>> dashboards = discover_all_dashboards()
        >>> len(dashboards)
        15
        >>> dashboards[0].uid
        'system-overview'
    """
    seen_uids = set()
    dashboards = []
    
    # Entry points take precedence - process them first
    for config in discover_from_entry_points(extension):
        if config.uid not in seen_uids:
            seen_uids.add(config.uid)
            dashboards.append(config)
            logger.debug(f"Added entry point dashboard: {config.uid}")
    
    # Add filesystem dashboards that aren't already present
    for config in discover_from_filesystem(extension):
        if config.uid not in seen_uids:
            seen_uids.add(config.uid)
            dashboards.append(config)
            logger.debug(f"Added filesystem dashboard: {config.uid}")
        else:
            logger.debug(f"Skipped duplicate dashboard: {config.uid}")
    
    logger.info(f"Discovered {len(dashboards)} total dashboards")
    return dashboards


def list_extensions() -> List[Dict[str, Union[str, int]]]:
    """
    List all extensions with their dashboard counts.
    
    Returns information about each registered extension including
    the count of dashboards discovered for that extension.
    
    Returns:
        List of dictionaries with extension metadata and counts
        
    Example:
        >>> extensions = list_extensions()
        >>> extensions[0]
        {'name': 'ContextCore Core', 'extension': 'core', 'count': 5}
    """
    extension_stats = []
    
    for ext_key, metadata in EXTENSION_REGISTRY.items():
        # Count dashboards from both sources for this extension
        fs_count = sum(1 for _ in discover_from_filesystem(ext_key))
        ep_count = sum(1 for _ in discover_from_entry_points(ext_key))
        
        # Total unique dashboards (accounting for potential overlaps)
        total_dashboards = discover_all_dashboards(ext_key)
        
        extension_stats.append({
            "name": metadata["name"],
            "extension": ext_key,
            "count": len(total_dashboards),
            "filesystem_count": fs_count,
            "entry_point_count": ep_count
        })
    
    return extension_stats


def _get_extension_dashboard_dir(extension: str) -> Path:
    """Get the filesystem directory for an extension's dashboards."""
    return Path("grafana/provisioning/dashboards") / extension


def _parse_dashboard_json(file_path: Path, extension: str) -> Optional[DashboardConfig]:
    """
    Parse a dashboard JSON file into a DashboardConfig object.
    
    Args:
        file_path: Path to the JSON file
        extension: Extension this dashboard belongs to
        
    Returns:
        DashboardConfig object or None if parsing failed
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            dashboard_data = json.load(f)
        
        # Validate required fields
        if 'uid' not in dashboard_data:
            logger.warning(f"Missing 'uid' field in {file_path}")
            return None
            
        return DashboardConfig(
            uid=dashboard_data['uid'],
            title=dashboard_data.get('title', ''),
            description=dashboard_data.get('description', ''),
            tags=dashboard_data.get('tags', []),
            extension=extension,
            file_path=file_path
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
    
    return None


def _validate_entry_point_dashboard(dashboard_data: Dict[str, Any]) -> bool:
    """
    Validate dashboard data from an entry point.
    
    Args:
        dashboard_data: Dictionary containing dashboard information
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(dashboard_data, dict):
        logger.warning("Dashboard data is not a dictionary")
        return False
        
    if 'uid' not in dashboard_data:
        logger.warning("Missing 'uid' field in entry point dashboard data")
        return False
        
    if not isinstance(dashboard_data['uid'], str) or not dashboard_data['uid'].strip():
        logger.warning("Invalid 'uid' field in entry point dashboard data")
        return False
    
    return True