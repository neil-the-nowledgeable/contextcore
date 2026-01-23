"""Configuration input widget for ContextCore TUI."""

from __future__ import annotations

from typing import List, Optional

from textual.widgets import Static, Input, Select, Label
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.app import ComposeResult
from textual import on

__all__ = ["ConfigInput"]


class ConfigInput(Static):
    """Widget for configuration input with label and description."""

    class Changed(Message):
        """Message sent when input value changes."""

        def __init__(self, name: str, value: str) -> None:
            super().__init__()
            self.name = name
            self.value = value

    DEFAULT_CSS = """
    ConfigInput {
        height: auto;
        margin: 1 0;
    }

    .config-label {
        width: 30;
        color: $text;
        text-style: bold;
    }

    .config-input {
        width: 40;
    }

    .config-description {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }

    .modified-indicator {
        color: $warning;
        text-style: bold;
    }

    .test-result {
        width: 10;
        text-align: center;
    }

    .test-success {
        color: $success;
    }

    .test-failure {
        color: $error;
    }
    """

    is_modified: bool = reactive(False)
    test_status: str = reactive("")

    def __init__(
        self,
        name: str,
        value: str,
        description: str,
        is_password: bool = False,
        choices: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.description = description
        self.is_password = is_password
        self.choices = choices
        self._initial_value = value
        self._value = value

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        with Vertical():
            with Horizontal():
                mod_indicator = "*" if self.is_modified else ""
                yield Label(
                    f"{self.name}{mod_indicator}",
                    classes="config-label",
                    id="label"
                )
                if self.choices:
                    yield Select(
                        options=[(choice, choice) for choice in self.choices],
                        value=self._value if self._value in self.choices else self.choices[0],
                        allow_blank=False,
                        id="input-select"
                    )
                else:
                    yield Input(
                        value=self._value,
                        placeholder=self.description,
                        password=self.is_password,
                        id="input-text"
                    )
                yield Label(self.test_status, classes="test-result", id="test-result")

            yield Label(self.description, classes="config-description")

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input value changes."""
        new_value = event.value
        self._value = new_value
        self.is_modified = new_value != self._initial_value
        self._update_label()
        self.post_message(self.Changed(self.name, new_value))

    @on(Select.Changed)
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select value changes."""
        new_value = str(event.value)
        self._value = new_value
        self.is_modified = new_value != self._initial_value
        self._update_label()
        self.post_message(self.Changed(self.name, new_value))

    def _update_label(self) -> None:
        """Update the label to show modification indicator."""
        try:
            label = self.query_one("#label", Label)
            mod_indicator = "*" if self.is_modified else ""
            label.update(f"{self.name}{mod_indicator}")
        except Exception:
            pass

    def get_value(self) -> str:
        """Get current input value."""
        return self._value

    def set_value(self, value: str) -> None:
        """Set input value."""
        self._value = value
        self._initial_value = value
        self.is_modified = False
        try:
            if self.choices:
                select = self.query_one("#input-select", Select)
                select.value = value
            else:
                input_widget = self.query_one("#input-text", Input)
                input_widget.value = value
        except Exception:
            pass

    def mark_modified(self, modified: bool = True) -> None:
        """Mark input as modified or unmodified."""
        self.is_modified = modified
        if not modified:
            self._initial_value = self._value
        self._update_label()

    def set_test_result(self, success: bool, message: str = "") -> None:
        """Set test result display."""
        try:
            test_label = self.query_one("#test-result", Label)
            if success:
                self.test_status = "OK"
                test_label.update("OK")
                test_label.add_class("test-success")
                test_label.remove_class("test-failure")
            else:
                self.test_status = "FAIL"
                test_label.update("FAIL")
                test_label.add_class("test-failure")
                test_label.remove_class("test-success")
        except Exception:
            pass
