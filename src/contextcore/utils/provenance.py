"""
Provenance utilities for tracking artifact generation metadata.

This module provides utilities for capturing comprehensive provenance
information during artifact generation, including:
- Git repository context (commit, branch, dirty state)
- Environment information (hostname, username, working directory)
- Source file checksums for reproducibility
- CLI invocation details
"""

import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextcore.models.artifact_manifest import ExportProvenance, GitContext


def get_file_checksum(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """
    Compute checksum of a file.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hex digest of the file contents, or None if file doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        return None

    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_content_checksum(
    content: str | bytes, algorithm: str = "sha256"
) -> str:
    """
    Compute checksum of string or bytes content.

    Args:
        content: String or bytes to hash
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hex digest of the content
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.new(algorithm, content).hexdigest()


def get_git_context(file_path: str) -> Optional[GitContext]:
    """
    Get git repository context for a file.
    
    Args:
        file_path: Path to a file in the repository
    
    Returns:
        GitContext with commit, branch, dirty state, and remote URL
        Returns None if not in a git repository
    """
    path = Path(file_path).resolve()
    repo_dir = path.parent if path.is_file() else path
    
    def run_git(args: List[str]) -> Optional[str]:
        """Run a git command and return output, or None on error."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
    
    # Check if in a git repo
    if not run_git(["rev-parse", "--git-dir"]):
        return None
    
    # Get commit SHA
    commit_sha = run_git(["rev-parse", "HEAD"])
    
    # Get branch name
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    
    # Check if dirty
    status = run_git(["status", "--porcelain"])
    is_dirty = bool(status) if status is not None else None
    
    # Get remote URL
    remote_url = run_git(["remote", "get-url", "origin"])
    
    return GitContext(
        commit_sha=commit_sha,
        branch=branch,
        is_dirty=is_dirty,
        remote_url=remote_url,
    )


def get_hostname() -> Optional[str]:
    """Get the machine hostname."""
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return None


def get_username() -> Optional[str]:
    """Get the current username."""
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or os.environ.get("USERNAME")


def get_python_version() -> str:
    """Get the Python version string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_contextcore_version() -> str:
    """Get the ContextCore package version."""
    try:
        from contextcore import __version__
        return __version__
    except (ImportError, AttributeError):
        return "2.0.0"  # Default if not available


def capture_provenance(
    source_path: str,
    output_directory: Optional[str] = None,
    output_files: Optional[List[str]] = None,
    cli_args: Optional[List[str]] = None,
    cli_options: Optional[Dict[str, Any]] = None,
    start_time: Optional[datetime] = None,
) -> ExportProvenance:
    """
    Capture full provenance metadata for an export operation.
    
    Args:
        source_path: Path to the source context manifest
        output_directory: Directory where outputs are written
        output_files: List of generated file paths
        cli_args: Raw CLI arguments (sys.argv)
        cli_options: Parsed CLI options dict
        start_time: Operation start time (for duration calculation)
    
    Returns:
        ExportProvenance with all captured metadata
    """
    now = datetime.now()
    
    # Calculate duration if start_time provided
    duration_ms = None
    if start_time:
        delta = now - start_time
        duration_ms = int(delta.total_seconds() * 1000)
    
    # Resolve source path
    source_path_resolved = str(Path(source_path).resolve())
    
    return ExportProvenance(
        generated_at=now,
        duration_ms=duration_ms,
        source_path=source_path_resolved,
        source_checksum=get_file_checksum(source_path_resolved),
        contextcore_version=get_contextcore_version(),
        python_version=get_python_version(),
        hostname=get_hostname(),
        username=get_username(),
        working_directory=os.getcwd(),
        git=get_git_context(source_path_resolved),
        cli_args=cli_args,
        cli_options=cli_options,
        output_directory=output_directory,
        output_files=output_files,
    )


def write_provenance_file(
    provenance: ExportProvenance,
    output_path: str,
    format: str = "json",
) -> str:
    """
    Write provenance metadata to a separate file.
    
    Args:
        provenance: The provenance data to write
        output_path: Path to write the file (directory or full path)
        format: Output format ('json' or 'yaml')
    
    Returns:
        Path to the written file
    """
    import json
    
    path = Path(output_path)
    
    # If output_path is a directory, create filename
    if path.is_dir():
        filename = f"provenance.{format}"
        path = path / filename
    
    # Serialize
    data = provenance.model_dump(by_alias=True, exclude_none=True, mode="json")
    
    if format == "yaml":
        import yaml
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
    else:
        content = json.dumps(data, indent=2, default=str)
    
    path.write_text(content, encoding="utf-8")
    return str(path)
