"""Deployment progress widget for ContextCore TUI."""

import asyncio
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, ProgressBar, RichLog, Static

from ..screens.install import InstallWizardState

__all__ = ["DeploymentProgress"]


class DeploymentProgress(Widget):
    """Widget for showing deployment progress."""

    DEFAULT_CSS = """
    DeploymentProgress {
        height: auto;
        padding: 1;
    }

    .section-header {
        text-style: bold;
        margin-bottom: 1;
    }

    #deploy-progress {
        margin: 1 0;
    }

    #deploy-log {
        height: 15;
        margin: 1 0;
        border: solid $primary;
    }

    #start-deploy {
        margin-top: 1;
    }
    """

    def __init__(self, wizard_state: InstallWizardState):
        super().__init__()
        self.wizard_state = wizard_state
        self.deployment_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        yield Static("Deploying ContextCore stack...", classes="section-header")
        yield ProgressBar(total=100, id="deploy-progress")
        yield RichLog(id="deploy-log", auto_scroll=True)
        yield Button("Start Deployment", id="start-deploy")

    async def start_deployment(self) -> None:
        """Start the deployment process."""
        if self.deployment_task and not self.deployment_task.done():
            return

        log = self.query_one("#deploy-log", RichLog)
        progress = self.query_one("#deploy-progress", ProgressBar)

        log.clear()
        progress.progress = 0

        self.deployment_task = asyncio.create_task(
            self.run_deployment(self.wizard_state.deployment_method)
        )

    async def run_deployment(self, method: str) -> None:
        """Run the actual deployment."""
        log = self.query_one("#deploy-log", RichLog)
        progress = self.query_one("#deploy-progress", ProgressBar)

        try:
            if method == "docker_compose":
                log.write("[bold green]Starting Docker Compose deployment...[/]")
                progress.progress = 10

                # Run make up
                log.write("Running: make up")
                proc = await asyncio.create_subprocess_exec(
                    "make", "up",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    log.write(line.decode().rstrip())
                    progress.progress = min(progress.progress + 2, 60)

                await proc.wait()

                if proc.returncode == 0:
                    log.write("[bold green]Stack started successfully[/]")
                    progress.progress = 70

                    # Wait for services
                    log.write("Waiting for services to be ready...")
                    await asyncio.sleep(5)
                    progress.progress = 90

                    log.write("[bold green]Deployment complete![/]")
                    progress.progress = 100
                    self.wizard_state.deployment_complete = True
                else:
                    log.write("[bold red]Deployment failed[/]")

            elif method == "kind":
                log.write("[bold green]Starting Kind cluster deployment...[/]")
                progress.progress = 10

                log.write("Creating Kind cluster...")
                proc = await asyncio.create_subprocess_exec(
                    "./scripts/create-cluster.sh",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    log.write(line.decode().rstrip())
                    progress.progress = min(progress.progress + 2, 90)

                await proc.wait()

                if proc.returncode == 0:
                    log.write("[bold green]Kind cluster created successfully![/]")
                    progress.progress = 100
                    self.wizard_state.deployment_complete = True
                else:
                    log.write("[bold red]Kind cluster creation failed[/]")

            else:
                log.write("[bold yellow]Custom deployment selected[/]")
                log.write("Please ensure your infrastructure is ready.")
                log.write("Skipping automated deployment...")
                progress.progress = 100
                self.wizard_state.deployment_complete = True

        except Exception as e:
            log.write(f"[bold red]Deployment failed: {e}[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "start-deploy":
            asyncio.create_task(self.start_deployment())
