"""Welcome screen for ContextCore TUI."""

from textual.screen import Screen
from textual.containers import Container, Grid
from textual.widgets import Static
from textual.binding import Binding
from textual.app import ComposeResult
from contextcore.tui.widgets.navigation_card import NavigationCard

try:
    from contextcore import __version__
except ImportError:
    __version__ = "0.1.0"

__all__ = ["WelcomeScreen"]


class WelcomeScreen(Screen):
    """Main welcome screen with ASCII logo and navigation options."""

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
        background: $surface;
    }

    .welcome-container {
        width: 80%;
        max-width: 120;
        height: auto;
        align: center middle;
    }

    .welcome-logo {
        text-align: center;
        color: $accent;
        margin: 1 0;
        text-style: bold;
    }

    .welcome-tagline {
        text-align: center;
        color: $text;
        margin: 1 0;
        text-style: italic;
    }

    .welcome-benefits {
        text-align: center;
        color: $text-muted;
        margin: 2 0;
    }

    .navigation-grid {
        grid-size: 3 2;
        grid-gutter: 1;
        margin: 2 0;
        align: center middle;
    }

    .welcome-footer {
        text-align: center;
        color: $text-muted;
        margin: 1 0;
        text-style: dim;
    }
    """

    BINDINGS = [
        Binding("i", "navigate('install')", "Install", show=True, priority=True),
        Binding("s", "navigate('status')", "Status", show=True, priority=True),
        Binding("c", "navigate('configure')", "Configure", show=True, priority=True),
        Binding("g", "navigate('script_generator')", "Script", show=True, priority=True),
        Binding("h", "navigate('help')", "Help", show=True, priority=True),
        Binding("q", "app.quit", "Quit", show=True, priority=True),
        Binding("escape", "app.quit", "Quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        """Compose the welcome screen layout with all components."""
        # ASCII art logo as specified
        logo_text = (
            " ╔═╗╔═╗╔╗╔╔╦╗╔═╗═╗ ╦╔╦╗  ╔═╗╔═╗╦═╗╔═╗\n"
            " ║  ║ ║║║║ ║ ╠═ ╔╩╦╝ ║   ║  ║ ║╠╦╝╠═ \n"
            " ╚═╝╚═╝╝╚╝ ╩ ╚═╝╩ ╚═ ╩   ╚═╝╚═╝╩╚═╚═╝"
        )

        # Required tagline
        tagline = "Project Management Observability Framework"

        # Required benefits as bullet points
        benefits = "Tasks as spans • Unified telemetry • Zero manual reports"

        # Footer with instructions and version
        footer_text = f"Press key in brackets or click to navigate | Version: {__version__}"

        # Create navigation cards as specified (2 rows of 3)
        navigation_cards = [
            NavigationCard("I", "Install", "Guided setup wizard", "install"),
            NavigationCard("S", "Status", "Health dashboard", "status"),
            NavigationCard("C", "Configure", "Environment settings", "configure"),
            NavigationCard("G", "Script", "Generate install script", "script_generator"),
            NavigationCard("H", "Help", "Documentation", "help"),
            NavigationCard("Q", "Quit", "Exit TUI", "quit"),
        ]

        with Container(classes="welcome-container"):
            yield Static(logo_text, classes="welcome-logo")
            yield Static(tagline, classes="welcome-tagline")
            yield Static(benefits, classes="welcome-benefits")
            yield Grid(*navigation_cards, classes="navigation-grid")
            yield Static(footer_text, classes="welcome-footer")

    def on_navigation_card_card_clicked(self, message: NavigationCard.CardClicked) -> None:
        """Handle navigation card click events."""
        try:
            if message.action == "quit":
                self.app.exit()
            else:
                self.action_navigate(message.action)
        except Exception as e:
            self.log.error(f"Error handling card navigation: {e}")

    def action_navigate(self, screen_name: str) -> None:
        """Navigate to specified screen with error handling.

        Args:
            screen_name: Name of screen to navigate to
        """
        try:
            self.app.push_screen(screen_name)
        except Exception as e:
            self.log.warning(f"Screen '{screen_name}' not yet implemented: {e}")
            self.app.notify(f"Screen '{screen_name}' is loading...", severity="information")
