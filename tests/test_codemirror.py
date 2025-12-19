import pytest

from nicegui import ui
from nicegui.testing import Screen

# pylint: disable=protected-access


def test_codemirror(screen: Screen):
    @ui.page("/")
    def page():
        ui.codemirror("Line 1\nLine 2\nLine 3")

    screen.open("/")
    screen.should_contain("Line 2")


def test_supported_values(screen: Screen):
    values: dict[str, list[str]] = {}

    @ui.page("/")
    def page():
        editor = ui.codemirror()

        async def fetch():
            values["languages"] = await editor.run_method("getLanguages")
            values["themes"] = await editor.run_method("getThemes")
            values["supported_themes"] = editor.supported_themes
            values["supported_languages"] = editor.supported_languages
            ui.label("Done")

        ui.button("Fetch", on_click=fetch)

    screen.open("/")
    screen.click("Fetch")
    screen.wait_for("Done")
    assert values["languages"] == values["supported_languages"]
    assert values["themes"] == values["supported_themes"]


@pytest.mark.parametrize(
    "doc, sections, inserted, expected",
    [
        ("", [0, 1], [["A"]], "A"),
        ("", [0, 2], [["AB"]], "AB"),
        ("X", [1, 2], [["AB"]], "AB"),
        ("X", [1, -1], [], "X"),
        ("X", [1, -1, 0, 1], [[], ["Y"]], "XY"),
        ("Hello", [5, -1, 0, 8], [[], [", world!"]], "Hello, world!"),
        ("Hello, world!", [5, -1, 7, 0, 1, -1], [], "Hello!"),
        ("Hello, hello!", [2, -1, 3, 1, 4, -1, 3, 1, 1, -1], [[], ["y"], [], ["y"]], "Hey, hey!"),
        ("Hello, world!", [5, -1, 1, 3, 7, -1], [[], [" 🙂"]], "Hello 🙂 world!"),
        ("Hey! 🙂", [7, -1, 0, 4], [[], [" Ho!"]], "Hey! 🙂 Ho!"),
        ("Ha 🙂\nha 🙂", [3, -1, 2, 0, 4, -1, 2, 0], [[], [""], [], [""]], "Ha \nha "),
    ],
)
def test_change_set(screen: Screen, doc: str, sections: list[int], inserted: list[list[str]], expected: str):
    editor = None

    @ui.page("/")
    def page():
        nonlocal editor
        editor = ui.codemirror(doc)

    screen.open("/")
    assert editor._apply_change_set(sections, inserted) == expected


def test_encode_codepoints():
    assert ui.codemirror._encode_codepoints("") == b""
    assert ui.codemirror._encode_codepoints("Hello") == bytes([1, 1, 1, 1, 1])
    assert ui.codemirror._encode_codepoints("🙂") == bytes([0, 1])
    assert ui.codemirror._encode_codepoints("Hello 🙂") == bytes([1, 1, 1, 1, 1, 1, 0, 1])
    assert ui.codemirror._encode_codepoints("😎😎😎") == bytes([0, 1, 0, 1, 0, 1])


def test_custom_completions_initialization(screen: Screen):
    """Test that custom_completions can be passed during initialization."""
    completions = [
        {"label": "test_func", "detail": "()", "type": "function"},
        {"label": "test_var", "detail": "str", "type": "variable"},
    ]

    @ui.page("/")
    def page():
        editor = ui.codemirror("", custom_completions=completions)
        ui.label(f"Completions: {len(editor.custom_completions)}")

    screen.open("/")
    screen.should_contain("Completions: 2")


def test_custom_completions_property(screen: Screen):
    """Test the custom_completions property getter and setter."""
    editor_ref = []

    @ui.page("/")
    def page():
        editor = ui.codemirror("")
        editor_ref.append(editor)

        def update_completions():
            editor.custom_completions = [
                {"label": "new_func", "type": "function"},
            ]
            ui.label(f"Updated: {len(editor.custom_completions)}")

        ui.button("Update", on_click=update_completions)

    screen.open("/")
    assert editor_ref[0].custom_completions == []
    screen.click("Update")
    screen.should_contain("Updated: 1")


def test_set_completions_method(screen: Screen):
    """Test the set_completions() method."""
    editor_ref = []

    @ui.page("/")
    def page():
        editor = ui.codemirror("")
        editor_ref.append(editor)

        def set_math():
            editor.set_completions(
                [
                    {"label": "math.sin", "detail": "(x)", "type": "function"},
                    {"label": "math.cos", "detail": "(x)", "type": "function"},
                ]
            )
            ui.label("Math completions set")

        def clear():
            editor.set_completions([])
            ui.label("Cleared")

        ui.button("Set Math", on_click=set_math)
        ui.button("Clear", on_click=clear)

    screen.open("/")
    assert editor_ref[0].custom_completions == []

    screen.click("Set Math")
    screen.should_contain("Math completions set")
    assert len(editor_ref[0].custom_completions) == 2

    screen.click("Clear")
    screen.should_contain("Cleared")
    assert editor_ref[0].custom_completions == []


def test_custom_completions_with_none():
    """Test that None is handled gracefully for custom_completions."""
    editor = ui.codemirror("", custom_completions=None)
    assert editor.custom_completions == []

    editor.set_completions(None)
    assert editor.custom_completions == []
