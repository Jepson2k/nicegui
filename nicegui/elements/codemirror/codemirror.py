from __future__ import annotations

from dataclasses import dataclass
from itertools import accumulate, chain, repeat
from typing import Any, Generic, Literal, TypedDict, cast, get_args

from typing_extensions import NotRequired, Self

from ...defaults import DEFAULT_PROP, resolve_defaults
from ...elements.mixins.disableable_element import DisableableElement
from ...elements.mixins.value_element import ValueElement
from ...events import (
    CodeMirrorAnchorChangeEventArguments,
    CodeMirrorFocusChangeEventArguments,
    CodeMirrorGeometryChangeEventArguments,
    CodeMirrorKeyBindingEventArguments,
    CodeMirrorSelectionChangeEventArguments,
    CodeMirrorViewportChangeEventArguments,
    EventT,
    GenericEventArguments,
    Handler,
    ValueChangeEventArguments,
    handle_event,
)
from .constants import SUPPORTED_LANGUAGES, SUPPORTED_THEMES
from .keybindings import KeyBindingElement
from .line_anchors import LineAnchorElement

COMPLETION_ICON_TYPES = Literal[
    'class',
    'constant',
    'enum',
    'function',
    'interface',
    'keyword',
    'method',
    'namespace',
    'property',
    'text',
    'type',
    'variable',
]

# Functional TypedDict syntax because `from` and `class` are Python keywords.
MarkDecorationSpec = TypedDict(
    'MarkDecorationSpec',
    {
        'kind': Literal['mark'],
        'from': int,
        'to': int,
        'class': NotRequired[str],
        'attributes': NotRequired[dict[str, str]],
        'inclusiveStart': NotRequired[bool],
        'inclusiveEnd': NotRequired[bool],
    },
)

LineDecorationSpec = TypedDict(
    'LineDecorationSpec',
    {
        'kind': Literal['line'],
        'line': int,
        'class': NotRequired[str],
        'attributes': NotRequired[dict[str, str]],
    },
)

ReplaceDecorationSpec = TypedDict(
    'ReplaceDecorationSpec',
    {
        'kind': Literal['replace'],
        'from': int,
        'to': int,
        'text': NotRequired[str],
        'class': NotRequired[str],
        'inclusive': NotRequired[bool],
        'block': NotRequired[bool],
    },
)

WidgetDecorationSpec = TypedDict(
    'WidgetDecorationSpec',
    {
        'kind': Literal['widget'],
        'position': int,
        'text': str,
        'class': NotRequired[str],
        'side': NotRequired[Literal[-1, 1]],
    },
)

DecorationSpec = MarkDecorationSpec | LineDecorationSpec | ReplaceDecorationSpec | WidgetDecorationSpec

# Offset fields per kind, and the keys a spec must carry to be applicable at all.
_DECORATION_OFFSETS: dict[str, tuple[str, ...]] = {
    'mark': ('from', 'to'),
    'line': (),
    'replace': ('from', 'to'),
    'widget': ('position',),
}
_DECORATION_REQUIRED: dict[str, tuple[str, ...]] = {
    'mark': ('from', 'to'),
    'line': ('line',),
    'replace': ('from', 'to'),
    'widget': ('position', 'text'),
}


class CompletionItem(TypedDict):
    """Single autocomplete entry for the ``completions`` parameter and property.

    Only ``label`` is required.
    All keys use snake_case; the JS layer maps them to CodeMirror 6's camelCase.

    - ``label``: matched against the user's input and shown in the dropdown.
    - ``apply``: text inserted on accept (defaults to ``label``). When ``snippet`` is ``True``, may contain
      ``${1:foo}`` tab-stop markers.
    - ``snippet``: treat ``apply`` as a snippet template; Tab/Shift-Tab cycles between fields.
    - ``display_label``: shown in the dropdown instead of ``label``; ``label`` is still used for matching.
    - ``detail``: short text shown next to the label (e.g. a type signature).
    - ``info``: longer description shown when the entry is highlighted. Rendered as plain text by default;
      pass ``completion_info_html=True`` to the editor constructor to render as sanitized HTML.
    - ``type``: icon shown next to the entry; one of the 12 built-in CM6 types.
    - ``boost``: sort weight from -99 to 99 (higher floats to the top).
    - ``commit_characters``: extra characters that, when typed, accept this completion (e.g. ``['.', '(']``).
    - ``section``: group heading; entries with the same section are visually grouped.
    - ``class_name``: CSS class added to this entry's ``<li>`` element in the dropdown.
    """
    label: str
    apply: NotRequired[str]
    snippet: NotRequired[bool]
    display_label: NotRequired[str]
    detail: NotRequired[str]
    info: NotRequired[str]
    type: NotRequired[COMPLETION_ICON_TYPES]
    boost: NotRequired[float]
    commit_characters: NotRequired[list[str]]
    section: NotRequired[str]
    class_name: NotRequired[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeMirrorHandlerSpec(Generic[EventT]):
    """Wraps a CodeMirror handler with per-registration config overrides.

    Construct via :meth:`CodeMirror.handler` rather than instantiating directly.
    """
    callback: Handler[EventT]
    debounce_ms: int | None = None


class Diagnostic(TypedDict):
    """Single linting diagnostic entry.

    ``severity`` defaults to ``'error'`` if omitted.
    ``source`` is shown next to the message.
    ``column`` and ``end_column`` (1-indexed; ``end_column`` is exclusive) narrow the mark to a sub-line range.
    If both are omitted the mark spans the whole line.
    """
    line: int
    message: str
    severity: NotRequired[Literal['info', 'warning', 'error', 'hint']]
    source: NotRequired[str]
    column: NotRequired[int]
    end_column: NotRequired[int]


class DiagnosticCount(TypedDict):
    """Per-severity counts returned by :meth:`CodeMirror.get_diagnostic_count`."""
    error: int
    warning: int
    info: int
    hint: int
    total: int


class CodeMirror(KeyBindingElement, LineAnchorElement, ValueElement[str], DisableableElement,
                 component='codemirror.js',
                 esm={'nicegui-codemirror': 'dist'},
                 default_classes='nicegui-codemirror'):
    VALUE_PROP = 'value'
    LOOPBACK = None

    @resolve_defaults
    def __init__(
        self,
        value: str = '',
        *,
        on_change: Handler[ValueChangeEventArguments[str]] | None = None,
        keymap: dict[str, Handler[CodeMirrorKeyBindingEventArguments] | CodeMirror.KeyBinding] | None = None,
        on_selection_change: Handler[CodeMirrorSelectionChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorSelectionChangeEventArguments] | None = None,
        on_focus_change: Handler[CodeMirrorFocusChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorFocusChangeEventArguments] | None = None,
        on_viewport_change: Handler[CodeMirrorViewportChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorViewportChangeEventArguments] | None = None,
        on_geometry_change: Handler[CodeMirrorGeometryChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorGeometryChangeEventArguments] | None = None,
        language: SUPPORTED_LANGUAGES | None = DEFAULT_PROP | None,
        theme: SUPPORTED_THEMES = DEFAULT_PROP | 'basicLight',
        indent: str = DEFAULT_PROP | ' ' * 4,
        line_wrapping: bool = DEFAULT_PROP | False,
        highlight_whitespace: bool = DEFAULT_PROP | False,
        line_anchors: dict[str, int] | None = None,
        on_anchor_change: Handler[CodeMirrorAnchorChangeEventArguments] | None = None,
        diagnostics: list[Diagnostic] | None = DEFAULT_PROP | None,
        diagnostic_message_html: bool = DEFAULT_PROP | False,
        completions: list[CompletionItem] | None = DEFAULT_PROP | None,
        replace_language_completions: bool = DEFAULT_PROP | False,
        complete_words_in_document: bool = DEFAULT_PROP | False,
        completion_info_html: bool = DEFAULT_PROP | False,
        tooltip_class: str | None = DEFAULT_PROP | None,
        decorations: list[DecorationSpec] | None = None,
        decoration_text_html: bool = False,
        line_tooltips: dict[int, str] | None = None,
        line_tooltip_html: bool = False,
    ) -> None:
        """CodeMirror

        An element to create a code editor using `CodeMirror <https://codemirror.net/>`_.

        It supports syntax highlighting for over 140 languages, more than 30 themes, line numbers, code folding, autocompletion, and more.

        Supported languages and themes:
            - Languages: A list of supported languages can be found in the `@codemirror/language-data <https://github.com/codemirror/language-data/blob/main/src/language-data.ts>`_ package.
            - Themes: A list can be found in the `@uiw/codemirror-themes-all <https://github.com/uiwjs/react-codemirror/tree/master/themes/all>`_ package.

        At runtime, the methods `supported_languages` and `supported_themes` can be used to get supported languages and themes.

        Each ``on_*_change`` handler accepts either a bare callable (default debounce) or a wrapped
        :class:`~nicegui.events.CodeMirrorHandlerSpec` for per-registration overrides
        (e.g. ``ui.codemirror.handler(callback, debounce_ms=200)``).

        *Since version 3.13.0:*
        Per-line tooltips can be attached via the ``line_tooltips`` dict.

        *Since version 3.14.0:*
        The ``keymap`` maps keystrokes (CodeMirror key strings) to Python callbacks.
        Pass a bare callable for the default config (prevents the browser default, no per-OS override).
        Wrap with ``KeyBinding`` for per-key overrides such as ``prevent_default=False`` or platform-specific shortcuts (``mac=``, ``linux=``, ``win=``).
        Use ``map_key`` to add keybindings at runtime and ``unmap_key`` to drop them.
        Keybindings do not fire while the editor is disabled.

        *Since version 3.16.0:*
        Line anchors that track document positions through edits can be attached via the ``line_anchors`` dict
        (assign to declare, read back for the current positions).

        *Since version 3.17.0:*
        Decorations style, hide or annotate parts of the document without changing it.
        Assign a list of specs to ``decorations`` or mutate the list in place.

        :param value: initial value of the editor (default: "")
        :param on_change: callback to be executed when the value changes (default: `None`)
        :param keymap: mapping of CodeMirror key strings (e.g. "Mod-s", "F5") to handlers, optionally wrapped with ``KeyBinding`` (default: ``None``, *added in version 3.14.0*)
        :param on_selection_change: callback when cursor line or column changes (debounced 30 ms by default)
        :param on_focus_change: callback when the editor gains or loses focus (no debounce by default)
        :param on_viewport_change: callback when the visible line range changes (debounced 100 ms by default)
        :param on_geometry_change: callback when the editor or content size changes (debounced 100 ms by default)
        :param language: initial language of the editor (case-insensitive, default: `None`)
        :param theme: initial theme of the editor (default: "basicLight")
        :param indent: string to use for indentation (any string consisting entirely of the same whitespace character, default: "    ")
        :param line_wrapping: whether to wrap lines (default: `False`)
        :param highlight_whitespace: whether to highlight whitespace (default: `False`)
        :param line_anchors: initial ``{anchor_id: 1-indexed line}`` mapping of anchors tracking document positions through edits (default: ``None``, *added in version 3.16.0*)
        :param on_anchor_change: callback to be executed when tracked anchor positions change (default: ``None``, *added in version 3.16.0*)
        :param diagnostics: initial list of ``Diagnostic`` dicts rendered as inline marks with hover tooltips (default: ``None``)
        :param diagnostic_message_html: render diagnostic ``message`` content as sanitized HTML rather than plain text (default: ``False``)
        :param completions: list of autocomplete entries shown in the dropdown.
            Each item is a ``CompletionItem`` dict; only ``label`` is required.
            By default these merge with whatever the active language pack provides.
            *Added in version X.Y.Z*
        :param replace_language_completions: if ``True``, suppress the active language pack's
            built-in completions and show only ``completions`` (and word-from-document, if enabled).
            Default: ``False`` (merge).
            *Added in version X.Y.Z*
        :param complete_words_in_document: if ``True``, also suggest identifiers already present
            elsewhere in the document (CodeMirror's ``completeAnyWord`` source). Default: ``False``.
            *Added in version X.Y.Z*
        :param completion_info_html: render the side-panel ``info`` text as sanitized HTML rather than
            plain text. Default: ``False``.
            *Added in version X.Y.Z*
        :param tooltip_class: CSS class added to the autocomplete popup container.
            Combine with ``ui.add_css`` to style the popup.
            *Added in version X.Y.Z*
        :param decorations: initial list of decoration specs applied to the editor;
            spec offsets (``from``/``to``/``position``) are Python ``str`` indices (default: ``None``, *added in version 3.17.0*)
        :param decoration_text_html: render the ``text`` field of replace/widget decorations as sanitized HTML rather than plain text (default: ``False``, *added in version 3.17.0*)
        :param line_tooltips: initial mapping of 1-indexed line numbers to tooltip content (default: ``None``, *added in version 3.13.0*)
        :param line_tooltip_html: render tooltip content as sanitized HTML rather than plain text (default: ``False``, *added in version 3.13.0*)
        """
        # NOTE: validate before super().__init__ registers the element, so a rejected argument
        # does not leave a half-built element behind in the element tree
        _validate_decorations(decorations or [])
        super().__init__(value=value, on_value_change=self._update_codepoints, keymap=keymap,
                         line_anchors=line_anchors, on_anchor_change=on_anchor_change)
        self._codepoints = b''
        self._update_codepoints()
        if on_change is not None:
            super().on_value_change(on_change)

        self._props['language'] = language
        self._props['theme'] = theme
        self._props['indent'] = indent
        self._props['line-wrapping'] = line_wrapping
        self._props['highlight-whitespace'] = highlight_whitespace
        self._props['selection-tracking-enabled'] = False
        self._props['focus-tracking-enabled'] = False
        self._props['viewport-tracking-enabled'] = False
        self._props['geometry-tracking-enabled'] = False
        self._props['selection-debounce-ms'] = 30
        self._props['focus-debounce-ms'] = 0
        self._props['viewport-debounce-ms'] = 100
        self._props['geometry-debounce-ms'] = 100
        self._props['diagnostics'] = diagnostics or []
        self._props['diagnostic-message-html'] = diagnostic_message_html
        self._props['completions'] = completions or []
        self._props['replace-language-completions'] = replace_language_completions
        self._props['complete-words-in-document'] = complete_words_in_document
        self._props['completion-info-html'] = completion_info_html
        self._props['tooltip-class'] = tooltip_class
        self._props['decorations'] = decorations or []
        self._props['decoration-text-html'] = decoration_text_html
        self._props['line-tooltips'] = line_tooltips or {}
        self._props['line-tooltip-html'] = line_tooltip_html
        self._update_method = 'setEditorValueFromProps'

        self._props.add_rename('highlightWhitespace', 'highlight-whitespace')  # DEPRECATED: remove in NiceGUI 4.0
        self._props.add_rename('lineWrapping', 'line-wrapping')  # DEPRECATED: remove in NiceGUI 4.0

        if on_selection_change is not None:
            self.on_selection_change(on_selection_change)
        if on_focus_change is not None:
            self.on_focus_change(on_focus_change)
        if on_viewport_change is not None:
            self.on_viewport_change(on_viewport_change)
        if on_geometry_change is not None:
            self.on_geometry_change(on_geometry_change)

    @staticmethod
    def handler(
        callback: Handler[EventT],
        *,
        debounce_ms: int | None = None,
    ) -> CodeMirrorHandlerSpec[EventT]:
        """Wrap a CodeMirror signal handler with per-registration config overrides.

        Use this to override the default debounce for a single signal registration::

            ui.codemirror(on_viewport_change=ui.codemirror.handler(scroll_cb, debounce_ms=200))

        :param callback: the handler callable
        :param debounce_ms: per-signal debounce override in milliseconds; ``None`` keeps the default
        """
        return CodeMirrorHandlerSpec(callback=callback, debounce_ms=debounce_ms)

    def on_selection_change(
        self,
        handler: Handler[CodeMirrorSelectionChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorSelectionChangeEventArguments],
    ) -> Self:
        """Add a callback for cursor selection changes (line + column).

        Fires on selection moves and on document edits that shift the cursor line or column.
        ``from_line``/``to_line`` span the main selection (equal and ``empty`` is ``True`` for a bare cursor).
        """
        callback, debounce_ms = self._unpack_handler(handler)
        self.on('selection-change', lambda e: handle_event(callback, CodeMirrorSelectionChangeEventArguments(
            sender=self,
            client=self.client,
            line=e.args['line'],
            column=e.args['column'],
            from_line=e.args['from_line'],
            to_line=e.args['to_line'],
            empty=e.args['empty'],
        )))
        self._props['selection-tracking-enabled'] = True
        if debounce_ms is not None:
            self._props['selection-debounce-ms'] = debounce_ms
        return self

    def on_focus_change(
        self,
        handler: Handler[CodeMirrorFocusChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorFocusChangeEventArguments],
    ) -> Self:
        """Add a callback for editor focus changes."""
        callback, debounce_ms = self._unpack_handler(handler)
        self.on('focus-change', lambda e: handle_event(callback, CodeMirrorFocusChangeEventArguments(
            sender=self,
            client=self.client,
            focused=e.args['focused'],
        )))
        self._props['focus-tracking-enabled'] = True
        if debounce_ms is not None:
            self._props['focus-debounce-ms'] = debounce_ms
        return self

    def on_viewport_change(
        self,
        handler: Handler[CodeMirrorViewportChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorViewportChangeEventArguments],
    ) -> Self:
        """Add a callback for viewport (visible line range) changes."""
        callback, debounce_ms = self._unpack_handler(handler)
        self.on('viewport-change', lambda e: handle_event(callback, CodeMirrorViewportChangeEventArguments(
            sender=self,
            client=self.client,
            from_line=e.args['from_line'],
            to_line=e.args['to_line'],
        )))
        self._props['viewport-tracking-enabled'] = True
        if debounce_ms is not None:
            self._props['viewport-debounce-ms'] = debounce_ms
        return self

    def on_geometry_change(
        self,
        handler: Handler[CodeMirrorGeometryChangeEventArguments] |
        CodeMirrorHandlerSpec[CodeMirrorGeometryChangeEventArguments],
    ) -> Self:
        """Add a callback for editor geometry changes (width, height, content height)."""
        callback, debounce_ms = self._unpack_handler(handler)
        self.on('geometry-change', lambda e: handle_event(callback, CodeMirrorGeometryChangeEventArguments(
            sender=self,
            client=self.client,
            width=e.args['width'],
            height=e.args['height'],
            content_height=e.args['content_height'],
        )))
        self._props['geometry-tracking-enabled'] = True
        if debounce_ms is not None:
            self._props['geometry-debounce-ms'] = debounce_ms
        return self

    @staticmethod
    def _unpack_handler(
        handler: Handler[Any] | CodeMirrorHandlerSpec[Any],
    ) -> tuple[Handler[Any], int | None]:
        if isinstance(handler, CodeMirrorHandlerSpec):
            return handler.callback, handler.debounce_ms
        return handler, None

    def reveal_line(self, line_number: int) -> None:
        """Scroll the editor so the given 1-indexed line is visible.

        :param line_number: 1-indexed line number to scroll into view
        """
        self.run_method('revealLine', line_number)

    @property
    def theme(self) -> str:
        """The current theme of the editor."""
        return self._props['theme']

    @theme.setter
    def theme(self, theme: SUPPORTED_THEMES) -> None:
        self._props['theme'] = theme

    def set_theme(self, theme: SUPPORTED_THEMES) -> Self:
        """Sets the theme of the editor."""
        self._props['theme'] = theme
        return self

    @property
    def supported_themes(self) -> list[str]:
        """List of supported themes."""
        return list(get_args(SUPPORTED_THEMES))

    @property
    def language(self) -> str:
        """The current language of the editor."""
        return self._props['language']

    @language.setter
    def language(self, language: SUPPORTED_LANGUAGES | None = None) -> None:
        self._props['language'] = language

    def set_language(self, language: SUPPORTED_LANGUAGES | None = None) -> Self:
        """Sets the language of the editor (case-insensitive)."""
        self._props['language'] = language
        return self

    @property
    def supported_languages(self) -> list[str]:
        """List of supported languages."""
        return list(get_args(SUPPORTED_LANGUAGES))

    @property
    def line_wrapping(self) -> bool:
        """Whether line wrapping is enabled

        *Added in version 3.2.0*
        """
        return self._props['line-wrapping']

    @line_wrapping.setter
    def line_wrapping(self, value: bool) -> None:
        self._props['line-wrapping'] = value

    def set_line_wrapping(self, value: bool) -> Self:
        """Sets whether line wrapping is enabled.

        *Added in version 3.2.0*
        """
        self._props['line-wrapping'] = value
        return self

    @property
    def diagnostics(self) -> list[Diagnostic]:
        """List of linting diagnostics rendered as inline marks with hover tooltips.

        Each entry is a ``Diagnostic`` dict.
        Mutations sync to the client.

        *Added in version X.Y.0*
        """
        return self._props['diagnostics']

    @diagnostics.setter
    def diagnostics(self, diagnostics: list[Diagnostic] | None) -> None:
        self._props['diagnostics'] = diagnostics or []

    def open_lint_panel(self) -> None:
        """Show CodeMirror's lint panel listing all current diagnostics.

        *Added in version X.Y.0*
        """
        self.run_method('openLintPanel')

    def close_lint_panel(self) -> None:
        """Hide CodeMirror's lint panel.

        *Added in version X.Y.0*
        """
        self.run_method('closeLintPanel')

    def toggle_lint_panel(self) -> None:
        """Toggle CodeMirror's lint panel.

        *Added in version X.Y.0*
        """
        self.run_method('toggleLintPanel')

    async def get_diagnostic_count(self) -> DiagnosticCount:
        """Return a count of currently-set diagnostics by severity.

        The returned dict has keys ``'error'``, ``'warning'``, ``'info'``, ``'hint'``,
        plus ``'total'`` for the sum.

        *Added in version X.Y.0*
        """
        return await self.run_method('getDiagnosticCount')

    @property
    def completions(self) -> list[CompletionItem]:
        """The current autocomplete entries shown in the dropdown.

        Each item is a ``CompletionItem`` dict; only ``label`` is required.
        Returns a copy.
        Reassign the property to update the editor (pass ``None`` or an empty list to remove all entries).

        *Added in version X.Y.Z*
        """
        return list(self._props['completions'])

    @completions.setter
    def completions(self, completions: list[CompletionItem] | None) -> None:
        self._props['completions'] = completions or []
        self.update()

    def trigger_completion(self) -> None:
        """Open the autocomplete popup programmatically (equivalent to Ctrl-Space).

        *Added in version X.Y.Z*
        """
        self.run_method('triggerCompletion')

    @property
    def decorations(self) -> list[DecorationSpec]:
        """Decoration specs applied to the editor; mutating this list syncs to the client.

        Decorations style or modify the editor's rendering without changing the underlying document.
        Each entry is a :class:`MarkDecorationSpec`, :class:`LineDecorationSpec`,
        :class:`ReplaceDecorationSpec`, or :class:`WidgetDecorationSpec` dict.
        For mark and line decorations the ``class`` field produces the visible styling, so the host
        application is responsible for shipping CSS for whatever class names it passes here.
        The ``attributes`` field is applied as raw DOM attributes (including event handlers like
        ``onclick``) and is not sanitized.
        Do not pass untrusted input through it.

        The ``from``, ``to`` and ``position`` fields are Python ``str`` indices into ``value``,
        so ``value.index(...)`` addresses what you expect even in a document containing emoji;
        they are translated to CodeMirror's UTF-16 addressing on the way out.

        Reading this property returns the specs as declared, not where the decorations have since
        moved: the browser keeps them pinned to their text as the document changes, but that
        mapping stays on the client.

        A spec that cannot describe a decoration at all — an unknown kind, a missing required key,
        an inverted or negative offset — is rejected right away with a ``ValueError``.
        Whether it fits the document is decided in the browser, which warns and skips just that spec.
        Use ``line_anchors`` when the current position is what you need.

        *Added in version 3.17.0*
        """
        return self._props['decorations']

    @decorations.setter
    def decorations(self, decorations: list[DecorationSpec] | None) -> None:
        decorations = decorations or []
        _validate_decorations(decorations)
        self._props['decorations'] = decorations

    @property
    def line_tooltips(self) -> dict[int, str]:
        """Mapping of 1-indexed line numbers to tooltip content.

        *Added in version 3.13.0*
        """
        return self._props['line-tooltips']

    @line_tooltips.setter
    def line_tooltips(self, value: dict[int, str]) -> None:
        self._props['line-tooltips'] = value

    def _event_args_to_value(self, e: GenericEventArguments) -> str:
        """The event contains a change set which is applied to the current value."""
        return self._apply_change_set(e.args['sections'], e.args['inserted'])

    def _to_dict(self) -> dict[str, Any]:
        dict_ = super()._to_dict()
        props = dict_.get('props')
        if props:
            decorations = _to_utf16_offsets(props.get('decorations') or [], self.value or '', self._codepoints)
            if decorations is not None:
                dict_['props'] = {**props, 'decorations': decorations}
        return dict_

    @staticmethod
    def _encode_codepoints(doc: str) -> bytes:
        return b''.join(b'\0\1' if ord(c) > 0xFFFF else b'\1' for c in doc)

    def _update_codepoints(self) -> None:
        """Update `self._codepoints` as a concatenation of "1" for code points <=0xFFFF and "01" for code points >0xFFFF.

        This captures how many Unicode code points are encoded by each UTF-16 code unit.
        This is used to convert JavaScript string indices to Python by summing `self._codepoints` up to the JavaScript index.
        """
        if not self._send_update_on_value_change:
            return  # the update is triggered by the user and codepoints are updated incrementally
        self._codepoints = self._encode_codepoints(self.value or '')

    def _apply_change_set(self, sections: list[int], inserted: list[list[str]]) -> str:
        document = self.value or ''
        old_lengths = sections[::2]
        new_lengths = sections[1::2]
        end_positions = accumulate(old_lengths)
        document_parts: list[str] = []
        codepoint_parts: list[bytes] = []
        for end, old_len, new_len, insert in zip(
            end_positions, old_lengths, new_lengths, chain(inserted, repeat([])), strict=False,
        ):
            if new_len == -1:
                start = end - old_len
                py_start = self._codepoints[:start].count(1)
                py_end = py_start + self._codepoints[start:end].count(1)
                document_parts.append(document[py_start:py_end])
                codepoint_parts.append(self._codepoints[start:end])
            else:
                joined_insert = '\n'.join(insert)
                document_parts.append(joined_insert)
                codepoint_parts.append(self._encode_codepoints(joined_insert))
        self._codepoints = b''.join(codepoint_parts)
        return ''.join(document_parts)


def _validate_decorations(decorations: list[DecorationSpec]) -> None:
    """Reject specs that cannot describe a decoration, whatever the document says.

    Everything document-dependent — offsets past the end, empty replace ranges, lines that do not
    exist — stays on the JS side, which warns and skips the individual spec.
    """
    for entry in decorations:
        spec = cast('dict[str, Any]', entry)  # the TypedDicts describe intent; at runtime this is user data
        kind = spec.get('kind')
        if kind not in _DECORATION_REQUIRED:
            raise ValueError(f'decorations: unknown kind {kind!r}, expected one of '
                             f'{", ".join(sorted(_DECORATION_REQUIRED))}')
        for key in _DECORATION_REQUIRED[kind]:
            if key not in spec:
                raise ValueError(f'decorations: {kind} decoration is missing required key {key!r}')
        for key in _DECORATION_OFFSETS[kind]:
            offset = spec[key]
            if not isinstance(offset, int) or isinstance(offset, bool):
                raise ValueError(f'decorations: {kind} decoration needs an integer {key!r} (got {offset!r})')
            if offset < 0:
                raise ValueError(f'decorations: {kind} decoration has {key}={offset}, but offsets start at 0')
        if kind in ('mark', 'replace') and spec['from'] > spec['to']:
            raise ValueError(f'decorations: {kind} decoration has from={spec["from"]} > to={spec["to"]}')
        if kind == 'line' and (not isinstance(spec['line'], int) or isinstance(spec['line'], bool)
                               or spec['line'] < 1):
            raise ValueError(f'decorations: line decoration has line={spec["line"]!r}, but lines are 1-indexed')


def _to_utf16_offsets(decorations: list[DecorationSpec], document: str, codepoints: bytes) -> list[DecorationSpec] | None:
    """Translate Python ``str`` indices into the UTF-16 code units CodeMirror addresses by.

    Returns ``None`` when the document is entirely in the Basic Multilingual Plane, where the two
    coincide — the common case, recognized straight from the codepoint map maintained for the
    incoming direction. Offsets that are not integers are left alone for the JS side to report.
    """
    if not decorations or b'\0' not in codepoints:
        return None
    # Each astral code point occupies two UTF-16 units, so an offset shifts by the number of astral
    # code points that precede it; the character an offset addresses does not shift its own start.
    shifts: list[int] = []
    shift = 0
    for character in document:
        shifts.append(shift)
        if ord(character) > 0xFFFF:
            shift += 1
    shifts.append(shift)  # an offset may address the end of the document

    def convert(offset: Any) -> Any:
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset < len(shifts):
            return offset
        return offset + shifts[offset]

    converted: list[DecorationSpec] = []
    for entry in decorations:
        spec = cast('dict[str, Any]', entry)
        keys = _DECORATION_OFFSETS.get(spec.get('kind', ''), ())
        shifted = {**spec, **{key: convert(spec.get(key)) for key in keys}} if keys else spec
        converted.append(cast('DecorationSpec', shifted))
    return converted
