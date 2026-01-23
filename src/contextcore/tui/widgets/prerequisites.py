"""Prerequisites checker widget for ContextCore TUI."""

import asyncio
import sys
import socket
import shutil
from typing import List, Tuple

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from ..screens.install import CheckStatus, CheckResult

__all__ = ["PrerequisitesChecker"]


class PrerequisitesChecker(Widget):
    """Widget for checking system prerequisites."""

    all_checks_passed: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    PrerequisitesChecker {
        height: auto;
        padding: 1;
    }

    .section-header {
        text-style: bold;
        margin-bottom: 1;
    }

    #checks-table {
        height: 12;
        margin: 1 0;
    }

    #rerun-btn {
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Checking system prerequisites...", classes="section-header")
        yield DataTable(id="checks-table")
        yield Button("Re-run Checks", id="rerun-btn")

    async def on_mount(self) -> None:
        """Initialize the checks table and run checks."""
        table = self.query_one("#checks-table", DataTable)
        table.add_columns("Check", "Status", "Details")
        await self.run_all_checks()

    async def run_all_checks(self) -> None:
        """Run all prerequisite checks."""
        checks: List[Tuple[str, CheckResult]] = []

        # Run all checks
        checks.append(("Python Version", await self.check_python_version()))
        checks.append(("Docker", await self.check_docker()))
        checks.append(("kubectl", await self.check_kubectl()))
        checks.append(("Ports", await self.check_ports()))
        checks.append(("make", await self.check_make()))

        table = self.query_one("#checks-table", DataTable)
        table.clear()

        all_passed = True
        for name, result in checks:
            table.add_row(
                result.name,
                result.status.value,
                result.message
            )
            if result.status == CheckStatus.FAILED:
                all_passed = False

        self.all_checks_passed = all_passed

    async def check_python_version(self) -> CheckResult:
        """Check Python version requirement."""
        version = sys.version_info
        if version >= (3, 9):
            return CheckResult(
                "Python",
                CheckStatus.PASSED,
                f"Python {version.major}.{version.minor}.{version.micro}"
            )
        else:
            return CheckResult(
                "Python",
                CheckStatus.FAILED,
                f"Python {version.major}.{version.minor} < 3.9 required"
            )

    async def check_docker(self) -> CheckResult:
        """Check Docker availability and status."""
        if not shutil.which("docker"):
            return CheckResult("Docker", CheckStatus.FAILED, "Docker not found")

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            returncode = await proc.wait()

            if returncode == 0:
                return CheckResult("Docker", CheckStatus.PASSED, "Docker daemon running")
            else:
                return CheckResult("Docker", CheckStatus.FAILED, "Docker daemon not running")
        except Exception:
            return CheckResult("Docker", CheckStatus.FAILED, "Failed to check Docker status")

    async def check_kubectl(self) -> CheckResult:
        """Check kubectl availability (optional)."""
        if not shutil.which("kubectl"):
            return CheckResult("kubectl", CheckStatus.WARNING, "kubectl not found (optional)")

        return CheckResult("kubectl", CheckStatus.PASSED, "kubectl available")

    async def check_make(self) -> CheckResult:
        """Check make availability."""
        if not shutil.which("make"):
            return CheckResult("make", CheckStatus.WARNING, "make not found (optional)")

        return CheckResult("make", CheckStatus.PASSED, "make available")

    async def check_ports(self) -> CheckResult:
        """Check if required ports are available."""
        required_ports = [3000, 3100, 3200, 4317, 9009]
        unavailable = []

        for port in required_ports:
            if not await self.is_port_available(port):
                unavailable.append(str(port))

        if unavailable:
            return CheckResult(
                "Ports",
                CheckStatus.WARNING,
                f"Ports in use: {', '.join(unavailable)}"
            )
        else:
            return CheckResult("Ports", CheckStatus.PASSED, "All ports available")

    async def is_port_available(self, port: int) -> bool:
        """Check if a specific port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result != 0
        except Exception:
            return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "rerun-btn":
            asyncio.create_task(self.run_all_checks())
