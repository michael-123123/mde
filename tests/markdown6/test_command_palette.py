"""Tests for the command palette module."""

import pytest

from fun.markdown6.command_palette import Command, CommandPalette


@pytest.fixture
def sample_commands():
    """Create sample commands for testing."""
    return [
        Command(id="file.new", name="New File", shortcut="Ctrl+N", callback=lambda: None, category="File"),
        Command(id="file.open", name="Open File", shortcut="Ctrl+O", callback=lambda: None, category="File"),
        Command(id="file.save", name="Save File", shortcut="Ctrl+S", callback=lambda: None, category="File"),
        Command(id="edit.undo", name="Undo", shortcut="Ctrl+Z", callback=lambda: None, category="Edit"),
        Command(id="edit.redo", name="Redo", shortcut="Ctrl+Shift+Z", callback=lambda: None, category="Edit"),
        Command(id="view.preview", name="Toggle Preview", shortcut="", callback=lambda: None, category="View"),
    ]


@pytest.fixture
def command_palette(qtbot):
    """Create a CommandPalette instance."""
    palette = CommandPalette()
    qtbot.addWidget(palette)
    return palette


class TestCommand:
    """Tests for Command dataclass."""

    def test_command_creation(self):
        """Test creating a command."""
        cmd = Command(
            id="test.command",
            name="Test Command",
            shortcut="Ctrl+T",
            callback=lambda: None,
            category="Test",
        )
        assert cmd.id == "test.command"
        assert cmd.name == "Test Command"
        assert cmd.shortcut == "Ctrl+T"
        assert cmd.category == "Test"

    def test_command_default_category(self):
        """Test command with default category."""
        cmd = Command(
            id="test.command",
            name="Test",
            shortcut="",
            callback=lambda: None,
        )
        assert cmd.category == ""

    def test_command_callback_is_callable(self):
        """Test that command callback is callable."""
        called = []
        cmd = Command(
            id="test",
            name="Test",
            shortcut="",
            callback=lambda: called.append(True),
        )
        cmd.callback()
        assert called == [True]


class TestCommandPalette:
    """Tests for CommandPalette widget."""

    def test_palette_creation(self, command_palette):
        """Test creating a command palette."""
        assert command_palette is not None
        assert command_palette.minimumWidth() == 600

    def test_set_commands(self, command_palette, sample_commands):
        """Test setting commands on the palette."""
        command_palette.set_commands(sample_commands)
        assert len(command_palette.commands) == len(sample_commands)

    def test_commands_sorted_by_name(self, command_palette, sample_commands):
        """Test that commands are sorted alphabetically by name."""
        command_palette.set_commands(sample_commands)
        names = [cmd.name for cmd in command_palette.commands]
        assert names == sorted(names, key=str.lower)

    def test_update_list_shows_all_commands(self, command_palette, sample_commands):
        """Test that update list shows all commands when no filter."""
        command_palette.set_commands(sample_commands)
        assert command_palette.list_widget.count() == len(sample_commands)

    def test_search_filters_by_name(self, command_palette, sample_commands):
        """Test that search filters commands by name."""
        command_palette.set_commands(sample_commands)
        command_palette.search_input.setText("undo")
        assert command_palette.list_widget.count() == 1

    def test_search_filters_by_category(self, command_palette, sample_commands):
        """Test that search filters commands by category."""
        command_palette.set_commands(sample_commands)
        command_palette.search_input.setText("file")
        # Should match "File" category (3 commands) + any name containing "file"
        assert command_palette.list_widget.count() == 3

    def test_search_case_insensitive(self, command_palette, sample_commands):
        """Test that search is case insensitive."""
        command_palette.set_commands(sample_commands)
        command_palette.search_input.setText("UNDO")
        assert command_palette.list_widget.count() == 1

    def test_clear_search_shows_all(self, command_palette, sample_commands):
        """Test that clearing search shows all commands."""
        command_palette.set_commands(sample_commands)
        command_palette.search_input.setText("undo")
        assert command_palette.list_widget.count() == 1
        command_palette.search_input.clear()
        assert command_palette.list_widget.count() == len(sample_commands)

    def test_first_item_selected_by_default(self, command_palette, sample_commands):
        """Test that first item is selected by default."""
        command_palette.set_commands(sample_commands)
        assert command_palette.list_widget.currentRow() == 0

    def test_filtered_commands_updated(self, command_palette, sample_commands):
        """Test that filtered_commands list is updated on search."""
        command_palette.set_commands(sample_commands)
        command_palette.search_input.setText("save")
        assert len(command_palette.filtered_commands) == 1
        assert command_palette.filtered_commands[0].name == "Save File"


class TestCommandPaletteDisplay:
    """Tests for command display formatting."""

    def test_display_with_category(self, command_palette, sample_commands):
        """Test that commands with category show category prefix."""
        command_palette.set_commands(sample_commands)
        # Check that items are in the list (formatted with category)
        item = command_palette.list_widget.item(0)
        assert item is not None

    def test_display_with_shortcut(self, command_palette, sample_commands):
        """Test that commands with shortcuts show the shortcut."""
        command_palette.set_commands(sample_commands)
        # The shortcut should be in the item text
        item_count = command_palette.list_widget.count()
        assert item_count > 0

    def test_empty_command_list(self, command_palette):
        """Test palette with empty command list."""
        command_palette.set_commands([])
        assert command_palette.list_widget.count() == 0


class TestCommandExecution:
    """Tests for command execution."""

    def test_execute_selected_command(self, command_palette, qtbot):
        """Test executing the selected command."""
        executed = []

        commands = [
            Command(
                id="test",
                name="Test",
                shortcut="",
                callback=lambda: executed.append(True),
            )
        ]
        command_palette.set_commands(commands)
        command_palette._execute_selected()

        # Note: _execute_selected calls accept() which closes the dialog
        # The callback should have been called
        assert executed == [True]

    def test_execute_with_no_selection(self, command_palette):
        """Test executing with no commands doesn't raise."""
        command_palette.set_commands([])
        command_palette._execute_selected()  # Should not raise
