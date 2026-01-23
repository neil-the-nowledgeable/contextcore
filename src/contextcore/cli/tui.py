"""CLI commands for the ContextCore Terminal User Interface."""

import sys
from typing import Optional
import click


@click.group()
def tui():
    """Launch the ContextCore Terminal User Interface."""
    pass


@tui.command("launch")
@click.option(
    "--screen", "-s",
    type=click.Choice(["welcome", "install", "status", "configure", "help", "script_generator"]),
    default="welcome",
    help="Initial screen to display"
)
@click.option(
    "--no-auto-refresh",
    is_flag=True,
    help="Disable auto-refresh on status screen"
)
def launch(screen: str, no_auto_refresh: bool) -> None:
    """Launch the interactive TUI.

    Examples:
        contextcore tui launch
        contextcore tui launch --screen install
        contextcore tui launch --screen status --no-auto-refresh
    """
    try:
        from contextcore.tui import ContextCoreTUI
    except ImportError as e:
        click.echo("Error: TUI requires the 'textual' package.", err=True)
        click.echo("Install with: pip install textual aiohttp", err=True)
        click.echo(f"Details: {e}", err=True)
        sys.exit(1)

    try:
        app = ContextCoreTUI(
            initial_screen=screen,
            auto_refresh=not no_auto_refresh
        )
        app.run()
    except KeyboardInterrupt:
        click.echo("\nTUI interrupted by user")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Error launching TUI: {e}", err=True)
        sys.exit(1)


@tui.command("install")
@click.option(
    "--method", "-m",
    type=click.Choice(["docker", "kind", "custom"]),
    default=None,
    help="Pre-select deployment method"
)
@click.option(
    "--auto",
    is_flag=True,
    help="Run with all defaults (non-interactive)"
)
def install_wizard(method: Optional[str], auto: bool) -> None:
    """Launch the installation wizard directly.

    Examples:
        contextcore tui install
        contextcore tui install --method docker --auto
    """
    if auto:
        click.echo("Running automated installation...")
        try:
            from contextcore.tui.installer import run_auto_install
            success = run_auto_install(method=method or "docker")
            if success:
                click.echo("Installation completed successfully")
            else:
                click.echo("Installation failed", err=True)
                sys.exit(1)
        except ImportError as e:
            click.echo(f"Error: Auto-installer not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Installation error: {e}", err=True)
            sys.exit(1)
    else:
        try:
            from contextcore.tui import ContextCoreTUI
        except ImportError as e:
            click.echo("Error: TUI requires the 'textual' package.", err=True)
            click.echo("Install with: pip install textual aiohttp", err=True)
            click.echo(f"Details: {e}", err=True)
            sys.exit(1)

        try:
            app = ContextCoreTUI(
                initial_screen="install",
                install_method=method
            )
            app.run()
        except KeyboardInterrupt:
            click.echo("\nInstallation interrupted by user")
            sys.exit(0)
        except Exception as e:
            click.echo(f"Error during installation: {e}", err=True)
            sys.exit(1)


@tui.command("status")
@click.option(
    "--watch", "-w",
    is_flag=True,
    help="Keep watching (don't exit after first check)"
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON (non-interactive)"
)
def status_check(watch: bool, output_json: bool) -> None:
    """Check service status.

    Examples:
        contextcore tui status
        contextcore tui status --json
        contextcore tui status --watch
    """
    if output_json:
        try:
            import asyncio
            import json
            from contextcore.tui.utils.health_checker import ServiceHealthChecker

            checker = ServiceHealthChecker()
            results = asyncio.run(checker.check_all())

            output = {
                name: {
                    "healthy": health.healthy,
                    "response_time_ms": health.response_time_ms,
                    "error": health.error
                }
                for name, health in results.items()
            }

            click.echo(json.dumps(output, indent=2))
        except ImportError as e:
            click.echo(f"Error: Health checker not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Status check error: {e}", err=True)
            sys.exit(1)
    else:
        try:
            from contextcore.tui import ContextCoreTUI
        except ImportError as e:
            click.echo("Error: TUI requires the 'textual' package.", err=True)
            click.echo("Install with: pip install textual aiohttp", err=True)
            click.echo(f"Details: {e}", err=True)
            sys.exit(1)

        try:
            app = ContextCoreTUI(
                initial_screen="status",
                auto_refresh=watch
            )
            app.run()
        except KeyboardInterrupt:
            click.echo("\nStatus monitoring interrupted by user")
            sys.exit(0)
        except Exception as e:
            click.echo(f"Error checking status: {e}", err=True)
            sys.exit(1)


@tui.command("generate-script")
@click.option(
    "--method", "-m",
    type=click.Choice(["docker", "kind", "custom"]),
    default="docker",
    help="Deployment method"
)
@click.option(
    "--project-dir", "-p",
    default=None,
    help="Project directory path"
)
@click.option(
    "--output", "-o",
    default=None,
    help="Output file path (default: stdout)"
)
def generate_script(method: str, project_dir: Optional[str], output: Optional[str]) -> None:
    """Generate an installation script.

    Examples:
        contextcore tui generate-script --method docker
        contextcore tui generate-script --method kind -o install.sh
    """
    try:
        from contextcore.tui.utils.script_templates import (
            render_docker_compose_script,
            render_kind_script,
            render_custom_script,
        )
        from pathlib import Path

        # Determine project directory
        if project_dir is None:
            project_dir = str(Path.home() / "Documents" / "dev" / "ContextCore")

        # Generate script based on method
        if method == "docker":
            script = render_docker_compose_script(project_dir=project_dir)
        elif method == "kind":
            script = render_kind_script(project_dir=project_dir)
        else:
            script = render_custom_script(project_dir=project_dir)

        # Output
        if output:
            output_path = Path(output)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(script)
            output_path.chmod(0o755)
            click.echo(f"Script saved to: {output_path}")
        else:
            click.echo(script)

    except ImportError as e:
        click.echo(f"Error: Script templates not available: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error generating script: {e}", err=True)
        sys.exit(1)


__all__ = ["tui", "launch", "install_wizard", "status_check", "generate_script"]
