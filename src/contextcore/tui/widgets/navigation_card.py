"""Navigation card widget for ContextCore TUI."""

from textual.widgets import Static
from textual.message import Message
from textual.reactive import reactive
from typing import Optional

__all__ = ["NavigationCard"]


class NavigationCard(Static):
    """Interactive navigation card widget with hover effects and keyboard shortcuts."""

    DEFAULT_CSS = """
    NavigationCard {
        border: solid $primary;
        padding: 1;
        margin: 1;
        background: $surface;
        color: $text;
        height: 5;
        width: 52;
    }

    NavigationCard:hover {
        border: solid $accent;
        background: $primary-background;
    }

    NavigationCard.highlighted {
        border: solid $accent;
        background: $primary-background;
    }
    """

    class CardClicked(Message):
        """Message sent when navigation card is clicked."""
        def __init__(self, action: str) -> None:
            self.action = action
            super().__init__()

    # Reactive attributes for hover effects
    highlighted: reactive[bool] = reactive(False)

    def __init__(
        self,
        key: str,
        title: str,
        description: str,
        action: str,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None
    ) -> None:
        """Initialize navigation card with key, title, description and action.

        Args:
            key: Keyboard shortcut key
            title: Card title text
            description: Card description text
            action: Action to perform when clicked
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self.key = key.upper()
        self.title = title
        self.description = description
        self.action = action
        self.can_focus = True

    def render(self) -> str:
        """Render the navigation card with formatted content."""
        return f"[{self.key}] {self.title}\n{self.description}"

    def on_enter(self) -> None:
        """Handle mouse enter event."""
        self.highlighted = True

    def on_leave(self) -> None:
        """Handle mouse leave event."""
        self.highlighted = False

    def on_click(self) -> None:
        """Handle mouse click event."""
        try:
            self.post_message(self.CardClicked(self.action))
        except Exception as e:
            self.log.error(f"Error handling card click: {e}")

    def watch_highlighted(self, highlighted: bool) -> None:
        """Watch for changes to highlighted state."""
        if highlighted:
            self.add_class("highlighted")
        else:
            self.remove_class("highlighted")
