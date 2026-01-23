"""Installation wizard screen for ContextCore TUI."""

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any
import socket
import shutil

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button, DataTable, Input, Static, ProgressBar,
    RadioButton, RichLog, Label
)
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen

__all__ = [
    "InstallScreen", "InstallWizardState", "CheckResult", "CheckStatus"
]


class CheckStatus(Enum):
    PENDING = "⏳"
    PASSED = "✅"
    WARNING = "⚠️"
    FAILED = "❌"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None


@dataclass
class InstallWizardState:
    deployment_method: str = "docker_compose"
    config: Dict[str, str] = field(default_factory=dict)
    prerequisites_passed: bool = False
    deployment_started: bool = False
    deployment_complete: bool = False
    verification_result: Optional[Any] = None


class InstallScreen(Screen[None]):
    """Main installation wizard screen with 5 steps."""

    BINDINGS = [
        ("n", "next_step", "Next"),
        ("b", "prev_step", "Back"),
        ("enter", "confirm", "Confirm"),
        ("escape", "cancel", "Cancel"),
    ]

    current_step: reactive[int] = reactive(1)
    wizard_state: InstallWizardState = InstallWizardState()

    DEFAULT_CSS = """
    InstallScreen {
        padding: 1;
    }

    #header {
        dock: top;
        height: 3;
        text-align: center;
        background: $primary;
        padding: 1;
    }

    #content {
        height: 1fr;
        padding: 1;
    }

    #footer {
        dock: bottom;
        height: 5;
        padding: 1;
    }

    .button-row {
        align: center middle;
        height: 3;
    }

    #wizard-progress {
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the main screen layout."""
        yield Container(
            Static("ContextCore Installation Wizard", classes="header"),
            id="header"
        )
        yield Container(id="content")
        yield Container(
            Static(id="step-indicator"),
            Horizontal(
                Button("Back", id="back-btn", disabled=True),
                Button("Next", id="next-btn"),
                Button("Cancel", id="cancel-btn"),
                classes="button-row"
            ),
            ProgressBar(total=5, show_percentage=False, id="wizard-progress"),
            id="footer"
        )

    async def on_mount(self) -> None:
        """Initialize the wizard on mount."""
        await self.update_step_content()
        self.update_navigation()

    def watch_current_step(self, step: int) -> None:
        """React to step changes."""
        self.call_after_refresh(self.update_step_content)
        self.update_navigation()

    async def update_step_content(self) -> None:
        """Update the content area with the current step widget."""
        content = self.query_one("#content", Container)
        await content.remove_children()

        step_widget = self.get_step_widget(self.current_step)
        await content.mount(step_widget)

        # Update step indicator
        step_name = self.get_step_name(self.current_step)
        indicator = self.query_one("#step-indicator", Static)
        indicator.update(f"Step {self.current_step} of 5: {step_name}")

        # Update progress bar
        progress = self.query_one("#wizard-progress", ProgressBar)
        progress.progress = self.current_step

    def get_step_widget(self, step: int) -> Widget:
        """Get the widget for the specified step."""
        from contextcore.tui.widgets.prerequisites import PrerequisitesChecker
        from contextcore.tui.widgets.deployment_selector import DeploymentSelector
        from contextcore.tui.widgets.config_form import ConfigurationForm
        from contextcore.tui.widgets.progress import DeploymentProgress
        from contextcore.tui.widgets.verification_results import VerificationResults

        widgets = {
            1: PrerequisitesChecker(),
            2: DeploymentSelector(),
            3: ConfigurationForm(self.wizard_state.deployment_method),
            4: DeploymentProgress(self.wizard_state),
            5: VerificationResults()
        }
        return widgets.get(step, Static("Invalid step"))

    def get_step_name(self, step: int) -> str:
        """Get the name for the specified step."""
        names = {
            1: "Prerequisites Check",
            2: "Deployment Method",
            3: "Configuration",
            4: "Stack Deployment",
            5: "Verification"
        }
        return names.get(step, "Unknown")

    def update_navigation(self) -> None:
        """Update navigation button states."""
        back_btn = self.query_one("#back-btn", Button)
        next_btn = self.query_one("#next-btn", Button)

        back_btn.disabled = self.current_step <= 1

        if self.current_step >= 5:
            next_btn.label = "Finish"
        else:
            next_btn.label = "Next"

    async def action_next_step(self) -> None:
        """Handle next step action."""
        if self.current_step >= 5:
            self.dismiss()
            return

        if await self.can_proceed():
            # Update state from current step
            if self.current_step == 2:
                try:
                    selector = self.query_one("DeploymentSelector")
                    self.wizard_state.deployment_method = selector.selected_method
                except Exception:
                    pass
            self.current_step += 1

    async def action_prev_step(self) -> None:
        """Handle previous step action."""
        if self.current_step > 1:
            self.current_step -= 1

    async def action_cancel(self) -> None:
        """Handle cancel action."""
        self.dismiss()

    async def action_confirm(self) -> None:
        """Handle confirm action (same as next)."""
        await self.action_next_step()

    async def can_proceed(self) -> bool:
        """Check if we can proceed to the next step."""
        if self.current_step == 1:
            try:
                checker = self.query_one("PrerequisitesChecker")
                return checker.all_checks_passed
            except Exception:
                return True
        elif self.current_step == 2:
            try:
                selector = self.query_one("DeploymentSelector")
                return selector.method_selected
            except Exception:
                return True
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "back-btn":
            asyncio.create_task(self.action_prev_step())
        elif event.button.id == "next-btn":
            asyncio.create_task(self.action_next_step())
        elif event.button.id == "cancel-btn":
            asyncio.create_task(self.action_cancel())
