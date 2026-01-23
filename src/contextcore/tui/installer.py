"""Non-interactive installation for CI/CD and automation."""

import asyncio
import subprocess
import sys
import time
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import click

__all__ = ["AutoInstaller", "run_auto_install", "InstallationError"]


class InstallationError(Exception):
    """Raised when installation fails."""
    pass


class AutoInstaller:
    """Non-interactive installer for ContextCore observability stack."""

    def __init__(self, method: str = "docker", verbose: bool = False) -> None:
        self.method = method
        self.verbose = verbose
        self.start_time = time.time()

    def log(self, message: str, error: bool = False) -> None:
        """Log installation progress."""
        timestamp = time.strftime("%H:%M:%S")
        prefix = "ERROR" if error else "INFO"
        output = f"[{timestamp}] {prefix}: {message}"

        if error:
            click.echo(output, err=True)
        else:
            click.echo(output)

    def run_command(self, cmd: List[str], cwd: Optional[Path] = None) -> Tuple[bool, str, str]:
        """Run command and return success, stdout, stderr."""
        try:
            if self.verbose:
                self.log(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            success = result.returncode == 0
            if not success and self.verbose:
                self.log(f"Command failed with exit code {result.returncode}")
                self.log(f"STDERR: {result.stderr}")

            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            self.log("Command timed out after 5 minutes", error=True)
            return False, "", "Command timeout"
        except Exception as e:
            self.log(f"Command execution error: {e}", error=True)
            return False, "", str(e)

    def check_prerequisites(self) -> bool:
        """Check system prerequisites."""
        self.log("Checking prerequisites...")

        # Check Python version
        if sys.version_info < (3, 9):
            self.log(f"Python 3.9+ required, found {sys.version_info.major}.{sys.version_info.minor}", error=True)
            return False

        # Check Docker
        if not shutil.which("docker"):
            self.log("Docker not found", error=True)
            return False

        success, _, _ = self.run_command(["docker", "info"])
        if not success:
            self.log("Docker daemon not running", error=True)
            return False

        # Check make (optional)
        if not shutil.which("make"):
            self.log("make not found (using direct commands)")

        self.log("Prerequisites check passed")
        return True

    async def install_docker_compose(self) -> bool:
        """Install using Docker Compose."""
        self.log("Installing with Docker Compose...")

        # Check if make is available
        if shutil.which("make"):
            success, stdout, stderr = self.run_command(["make", "up"])
            if not success:
                self.log(f"Failed to start stack: {stderr}", error=True)
                return False
        else:
            # Fallback to docker-compose directly
            success, stdout, stderr = self.run_command(["docker-compose", "up", "-d"])
            if not success:
                self.log(f"Failed to start stack: {stderr}", error=True)
                return False

        self.log("Waiting for services to be ready...")
        await asyncio.sleep(10)

        # Verify services
        self.log("Verifying installation...")
        success, stdout, stderr = self.run_command(["contextcore", "install", "verify"])

        return success

    async def install_kind(self) -> bool:
        """Install using Kind cluster."""
        self.log("Installing with Kind cluster...")

        # Check if kind is available
        if not shutil.which("kind"):
            self.log("kind not found, please install it first", error=True)
            return False

        # Create cluster
        success, stdout, stderr = self.run_command([
            "kind", "create", "cluster",
            "--name", "o11y-dev"
        ])

        if not success:
            self.log(f"Failed to create Kind cluster: {stderr}", error=True)
            return False

        self.log("Kind cluster created successfully")
        return True

    async def install(self) -> bool:
        """Run the installation based on the selected method."""
        if not self.check_prerequisites():
            return False

        if self.method == "docker":
            return await self.install_docker_compose()
        elif self.method == "kind":
            return await self.install_kind()
        else:
            self.log(f"Unknown installation method: {self.method}", error=True)
            return False


def run_auto_install(method: str = "docker", verbose: bool = False) -> bool:
    """Run automated installation.

    Args:
        method: Installation method ("docker", "kind", "custom")
        verbose: Enable verbose output

    Returns:
        True if installation succeeded, False otherwise
    """
    installer = AutoInstaller(method=method, verbose=verbose)
    return asyncio.run(installer.install())
