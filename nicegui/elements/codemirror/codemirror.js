import * as CM from "nicegui-codemirror";

// A RangeSet StateField whose ranges remap through document edits.
// Dispatching setEffect.of(ranges) replaces the whole set.
function defineRemappableRangeSet() {
  const setEffect = CM.StateEffect.define(); // value: list of ranges (replaces all)
  const field = CM.StateField.define({
    create() {
      return CM.RangeSet.empty;
    },
    update(set, tr) {
      set = set.map(tr.changes);
      for (const effect of tr.effects) {
        if (effect.is(setEffect)) set = CM.RangeSet.of(effect.value, true);
      }
      return set;
    },
  });
  return { setEffect, field };
}

// Line anchors: {id, line} pairs whose positions CM6 auto-remaps through edits. Each AnchorValue carries its id.
class AnchorValue extends CM.RangeValue {
  constructor(id) {
    super();
    this.id = id;
  }
  eq(other) {
    return this.id === other.id;
  }
}
const { setEffect: setAnchorsEffect, field: anchorField } = defineRemappableRangeSet();
const ANCHOR_DEBOUNCE_MS = 50;

function sameAnchorPositions(a, b) {
  const ids = Object.keys(a);
  return ids.length === Object.keys(b).length && ids.every((id) => a[id] === b[id]);
}

// Zero-width range so CM6's RangeSet.map() carries each tooltip through edits.
class TooltipValue extends CM.RangeValue {
  constructor(content) {
    super();
    this.content = content;
  }
}
const { setEffect: setTooltipsEffect, field: tooltipField } = defineRemappableRangeSet();

export default {
  template: `
    <div></div>
  `,
  props: {
    value: String,
    language: String,
    theme: String,
    lineWrapping: Boolean,
    disable: Boolean,
    indent: String,
    highlightWhitespace: Boolean,
    lineAnchors: Object,
    selectionTrackingEnabled: Boolean,
    focusTrackingEnabled: Boolean,
    viewportTrackingEnabled: Boolean,
    geometryTrackingEnabled: Boolean,
    selectionDebounceMs: Number,
    focusDebounceMs: Number,
    viewportDebounceMs: Number,
    geometryDebounceMs: Number,
    diagnostics: Array,
    diagnosticMessageHtml: Boolean,
    completions: Array,
    replaceLanguageCompletions: Boolean,
    completeWordsInDocument: Boolean,
    completionInfoHtml: Boolean,
    tooltipClass: String,
    keymap: Array,
    lineTooltips: Object,
    lineTooltipHtml: Boolean,
    id: String,
  },
  watch: {
    language(newLanguage) {
      this.setLanguage(newLanguage);
    },
    theme(newTheme) {
      this.setTheme(newTheme);
    },
    disable(newDisable) {
      this.setDisabled(newDisable);
    },
    lineWrapping(newLineWrapping) {
      this.setLineWrapping(newLineWrapping);
    },
    lineAnchors(newAnchors) {
      this.applyLineAnchors(newAnchors);
    },
    diagnostics(newDiagnostics) {
      this.applyDiagnostics(newDiagnostics);
    },
    completions() {
      this.rebuildCompletions();
    },
    replaceLanguageCompletions() {
      this.rebuildCompletions();
    },
    completeWordsInDocument() {
      this.rebuildCompletions();
    },
    completionInfoHtml() {
      this.rebuildCompletions();
    },
    tooltipClass() {
      this.rebuildCompletions();
    },
    keymap() {
      this.setKeymap();
    },
    lineTooltips(newTooltips) {
      this.setLineTooltips(newTooltips);
    },
  },
  data() {
    return {
      // To let other methods wait for the editor to be created because
      // they might be called by the server before the editor is created.
      editorPromise: new Promise((resolve) => {
        this.resolveEditor = resolve;
      }),
    };
  },
  beforeUnmount() {
    if (this.editor) {
      const element = mounted_app.elements[this.$props.id.slice(1)];
      if (element) {
        element.props.value = this.editor.state.doc.toString();
        // A client-side remount (e.g. a v-if container) re-applies these props against the restored
        // document, so they have to describe where the anchors are now, not where they were declared.
        if (element.props["line-anchors"]) element.props["line-anchors"] = this.currentAnchorPositions();
      }
    }
    clearTimeout(this._anchorTimer);
  },
  methods: {
    // Find the language's extension by its name. Case insensitive.
    findLanguage(name) {
      for (const language of this.languages)
        for (const alias of [language.name, ...language.alias])
          if (name.toLowerCase() === alias.toLowerCase()) return language;

      console.error(`Language not found: ${name}`);
      console.info("Supported language names:", this.languages.map((lang) => lang.name).join(", "));
      return null;
    },
    // Get the names of all supported languages
    async getLanguages() {
      if (!this.editor) await this.editorPromise;
      // Over 100 supported languages: https://github.com/codemirror/language-data/blob/main/src/language-data.ts
      return this.languages.map((lang) => lang.name).sort(Intl.Collator("en").compare);
    },
    setLanguage(language) {
      if (!language) {
        this.editor.dispatch({
          effects: this.languageConfig.reconfigure([]),
        });
        return;
      }

      const lang_description = this.findLanguage(language);
      if (!lang_description) {
        return;
      }

      lang_description.load().then((extension) => {
        this.editor.dispatch({
          effects: this.languageConfig.reconfigure([extension]),
        });
      });
    },
    async getThemes() {
      if (!this.editor) await this.editorPromise;
      // `this.themes` also contains some non-theme objects
      // The real themes are Arrays
      return Object.keys(this.themes)
        .filter((key) => Array.isArray(this.themes[key]))
        .sort(Intl.Collator("en").compare);
    },
    setTheme(theme) {
      const new_theme = this.themes[theme];
      if (new_theme === undefined) {
        console.error("Theme not found:", theme);
        return;
      }
      this.editor.dispatch({
        effects: this.themeConfig.reconfigure([new_theme]),
      });
    },
    setEditorValueFromProps() {
      this.setEditorValue(this.value);
    },
    setEditorValue(value) {
      if (!this.editor) return;
      const old = this.editor.state.doc.toString();
      if (old === value) return;

      // Find the changed region so we only replace what differs.
      // This preserves cursor positions and selections outside the change.
      let start = 0;
      while (start < old.length && start < value.length && old[start] === value[start]) start++;
      let oldEnd = old.length;
      let newEnd = value.length;
      while (oldEnd > start && newEnd > start && old[oldEnd - 1] === value[newEnd - 1]) {
        oldEnd--;
        newEnd--;
      }

      this.emitting = false;
      this.editor.dispatch({ changes: { from: start, to: oldEnd, insert: value.slice(start, newEnd) } });
      this.emitting = true;
    },
    setDisabled(disabled) {
      this.editor.dispatch({
        effects: this.editableConfig.reconfigure(this.editableStates[!disabled]),
      });
    },
    setLineWrapping(wrap) {
      this.editor.dispatch({
        effects: this.lineWrappingConfig.reconfigure(wrap ? [CM.EditorView.lineWrapping] : []),
      });
    },
    async applyLineAnchors(anchors) {
      // The server marks `line-anchors` as a preserved prop on unrelated updates, so the watcher
      // only fires on a deliberate (re)assignment — re-applying from the declared lines is then intended,
      // snapping anchors back to their declared positions (and restoring any dropped by a delete-across).
      if (!this.editor) await this.editorPromise;
      const doc = this.editor.state.doc;
      const ranges = [];
      for (const [id, line] of Object.entries(anchors || {})) {
        if (line >= 1 && line <= doc.lines) {
          const pos = doc.line(line).from;
          ranges.push(new AnchorValue(id).range(pos, pos));
        } else {
          logAndEmit(
            "warning",
            `line_anchors: anchor ${JSON.stringify(id)} on line ${line} out of range [1, ${doc.lines}]`,
          );
        }
      }
      this.editor.dispatch({ effects: setAnchorsEffect.of(ranges) });
      // The dispatch re-armed the debounced tracker; the immediate emit below supersedes that echo.
      clearTimeout(this._anchorTimer);
      this.emitAnchorPositions({ force: true });
    },
    currentAnchorPositions() {
      const state = this.editor.state;
      const field = state.field(anchorField);
      const doc = state.doc;
      const positions = {};
      const cursor = field.iter();
      while (cursor.value) {
        positions[cursor.value.id] = doc.lineAt(cursor.from).number;
        cursor.next();
      }
      return positions;
    },
    // A deliberate apply forces the emit: the server treats it as the confirmation that its declared
    // anchors have landed, even when they happen to sit where the live ones already were.
    emitAnchorPositions({ force = false } = {}) {
      if (!this.editor) return;
      const positions = this.currentAnchorPositions();
      if (!force && this._lastAnchors && sameAnchorPositions(this._lastAnchors, positions)) return;
      this._lastAnchors = positions;
      this.$emit("anchor-positions", { anchors: positions });
    },
    revealLine(lineNumber) {
      if (!this.editor) return;
      const doc = this.editor.state.doc;
      const lineNum = Math.max(1, Math.min(lineNumber, doc.lines));
      const line = doc.line(lineNum);
      this.editor.dispatch({
        effects: CM.EditorView.scrollIntoView(line.from, { y: "center" }),
      });
    },
    applyDiagnostics(diagnostics) {
      if (!this.editor) return;
      const doc = this.editor.state.doc;
      const useHtml = this.diagnosticMessageHtml;
      const cmDiagnostics = [];
      for (const d of diagnostics || []) {
        if (!Number.isInteger(d.line) || d.line < 1 || d.line > doc.lines) {
          logAndEmit("warning", `diagnostics: line ${d.line} out of range [1, ${doc.lines}]`);
          continue;
        }
        const line = doc.line(d.line);
        // Column values are 1-indexed; end_column is exclusive. Out-of-range values clamp to line bounds.
        const startOffset = Number.isInteger(d.column) ? Math.max(1, d.column) - 1 : 0;
        const endOffset = Number.isInteger(d.end_column) ? Math.max(1, d.end_column) - 1 : line.length;
        const from = Math.min(line.from + startOffset, line.to);
        const to = Math.min(line.from + endOffset, line.to);
        const message = d.message;
        cmDiagnostics.push({
          from,
          to: Math.max(from, to),
          severity: d.severity || "error",
          message,
          source: d.source ?? undefined,
          renderMessage: () => {
            const span = document.createElement("span");
            if (useHtml) {
              span.setHTML(message);
            } else {
              span.textContent = message;
            }
            return span;
          },
        });
      }
      this.editor.dispatch(CM.setDiagnostics(this.editor.state, cmDiagnostics));
    },
    openLintPanel() {
      if (this.editor) CM.openLintPanel(this.editor);
    },
    closeLintPanel() {
      if (this.editor) CM.closeLintPanel(this.editor);
    },
    toggleLintPanel() {
      if (!this.editor) return;
      // @codemirror/lint exposes openLintPanel/closeLintPanel but no public "is open" predicate,
      // so check the rendered panel directly.
      const open = this.editor.dom.querySelector(".cm-panel-lint") !== null;
      (open ? CM.closeLintPanel : CM.openLintPanel)(this.editor);
    },
    getDiagnosticCount() {
      const counts = { error: 0, warning: 0, info: 0, hint: 0, total: 0 };
      if (!this.editor) return counts;
      CM.forEachDiagnostic(this.editor.state, (d) => {
        if (counts[d.severity] !== undefined) counts[d.severity] += 1;
        counts.total += 1;
      });
      return counts;
    },
    buildCompletionSource(completions) {
      const useHtml = this.completionInfoHtml;
      const renderInfo = (info) => () => {
        const div = document.createElement("div");
        if (useHtml) {
          // setHTML (DOMPurify-backed polyfill) sanitizes HTML.
          div.setHTML(info);
        } else {
          div.textContent = info;
        }
        return div;
      };
      return (context) => {
        const word = context.matchBefore(/[\w.]+/);
        if (!word && !context.explicit) return null;
        const from = word ? word.from : context.pos;
        const options = completions.map((c) => {
          if (c.snippet && c.apply) {
            return CM.snippetCompletion(c.apply, {
              label: c.label,
              displayLabel: c.display_label,
              detail: c.detail,
              info: c.info ? renderInfo(c.info) : undefined,
              type: c.type,
              boost: typeof c.boost === "number" ? c.boost : undefined,
              commitCharacters: c.commit_characters,
              section: c.section,
              className: c.class_name,
            });
          }
          const opt = { label: c.label, apply: c.apply ?? c.label };
          if (c.display_label) opt.displayLabel = c.display_label;
          if (c.detail) opt.detail = c.detail;
          if (c.info) opt.info = renderInfo(c.info);
          if (c.type) opt.type = c.type;
          if (typeof c.boost === "number") opt.boost = c.boost;
          if (c.commit_characters) opt.commitCharacters = c.commit_characters;
          if (c.section) opt.section = c.section;
          if (c.class_name) opt.className = c.class_name;
          return opt;
        });
        return { from, options, validFor: /^[\w.]*$/ };
      };
    },
    rebuildCompletions() {
      if (!this.editor || !this.completionsConfig) return;
      const sources = [];
      if (this.completions && this.completions.length > 0) {
        sources.push(this.buildCompletionSource(this.completions));
      }
      if (this.completeWordsInDocument) {
        sources.push(CM.completeAnyWord);
      }
      const exts = [];
      const tooltipClass = this.tooltipClass || "";
      const optionClass = (c) => c.className || "";
      const tooltipClassFn = tooltipClass ? () => tooltipClass : undefined;
      if (this.replaceLanguageCompletions) {
        // Override mode: replaces language-pack completion sources entirely.
        // Register a single autocompletion() carrying both sources and styling so
        // the second autocompletion() call below is skipped (it would stack a
        // duplicate state field).
        exts.push(CM.autocompletion({
          override: sources,
          tooltipClass: tooltipClassFn,
          optionClass,
        }));
      } else {
        // Merge mode: register sources via languageData so they compose with the
        // active language pack's autocompletion (which basicSetup already enables).
        sources.forEach((src) => {
          exts.push(CM.EditorState.languageData.of(() => [{ autocomplete: src }]));
        });
        // Layer styling via Prec.highest only when needed, so it wins over
        // basicSetup's autocompletion config without re-registering the source.
        const hasClassName = this.completions && this.completions.some((c) => c.class_name);
        if (tooltipClass || hasClassName) {
          exts.push(CM.Prec.highest(CM.autocompletion({
            tooltipClass: tooltipClassFn,
            optionClass,
          })));
        }
      }
      // basicSetup's autocompletion() already registers the snippet keymap, so
      // Tab / Shift-Tab cycles snippet placeholders without extra wiring here.
      this.editor.dispatch({
        effects: this.completionsConfig.reconfigure(exts),
      });
    },
    triggerCompletion() {
      if (!this.editor) return;
      CM.startCompletion(this.editor);
    },
    buildUserKeymap() {
      return (this.keymap || []).map(({ key, mac, linux, win, preventDefault }) => ({
        key,
        mac, // unset mac will fall back to key
        linux, // unset linux will fall back to key
        win, // unset win will fall back to key
        run: () => {
          this.$emit("keybinding", { key });
          return preventDefault;
        },
      }));
    },
    setKeymap() {
      if (!this.editor) return;
      this.editor.dispatch({
        effects: this.userKeymapConfig.reconfigure(CM.keymap.of(this.buildUserKeymap())),
      });
      this.validateUserKeymap();
    },
    validateUserKeymap() {
      if (!this.editor || !(this.keymap || []).length) return;
      try {
        // Force CodeMirror to build its combined keymap now instead of lazily on the first keydown:
        // a chord whose prefix is also a standalone binding (incl. basicSetup's, e.g. "Mod-a Mod-b"
        // vs. the built-in Mod-a) throws here rather than silently killing every keybinding later.
        CM.runScopeHandlers(this.editor, new KeyboardEvent("keydown", { key: "Unidentified" }), "editor");
      } catch (error) {
        logAndEmit("error", `ui.codemirror: ${error.message}`);
      }
    },
    setLineTooltips(tooltips) {
      if (!this.editor) return;
      const doc = this.editor.state.doc;
      const ranges = [];
      for (const [line, content] of Object.entries(tooltips || {})) {
        const lineNum = parseInt(line);
        if (lineNum >= 1 && lineNum <= doc.lines) {
          const pos = doc.line(lineNum).from;
          ranges.push(new TooltipValue(content).range(pos, pos));
        } else {
          logAndEmit("warning", `line_tooltips: line ${lineNum} out of range [1, ${doc.lines}]`);
        }
      }
      this.editor.dispatch({ effects: setTooltipsEffect.of(ranges) });
    },
    setupExtensions() {
      const self = this;

      // Sends a ChangeSet https://codemirror.net/docs/ref/#state.ChangeSet
      // containing only the changes made to the document.
      // This could potentially be optimized further by sending updates
      // periodically instead of on every change and accumulating changesets
      // with ChangeSet.compose.
      const changeSender = CM.ViewPlugin.fromClass(
        class {
          update(update) {
            if (!update.docChanged) return;
            if (!self.emitting) return;
            self.$emit("update:value", update.changes);
          }
        },
      );

      // The debounce coalesces bursts (paste, multi-cursor insert) so high-latency
      // connections do not see one event per keystroke. The fire-time callback reads live
      // editor state via emitAnchorPositions(), so a stale timer that survives a clear or
      // re-set transaction will see the up-to-date field rather than its scheduling-time snapshot.
      const anchorTracker = CM.ViewPlugin.fromClass(
        class {
          update(update) {
            if (!update.docChanged) return;
            // Skip only when there is nothing to report before and after — checking just the end state
            // would swallow the last anchor's removal (1 -> 0), leaving the Python mirror stale.
            if (update.state.field(anchorField).size === 0 && update.startState.field(anchorField).size === 0) return;
            clearTimeout(self._anchorTimer);
            self._anchorTimer = setTimeout(() => self.emitAnchorPositions(), ANCHOR_DEBOUNCE_MS);
          }
        },
      );

      // Dispatches per-signal events for ViewUpdate flags the host has opted into via
      // <signal>-tracking-enabled props. Each signal is independently debounced (read fresh
      // from <signal>DebounceMs every emit) and deduped against its last payload.
      // NOTE: timers live on the plugin instance — `destroy()` clears them on plugin teardown,
      // so no Vue beforeUnmount cleanup is needed.
      const updateDispatcher = CM.ViewPlugin.fromClass(
        class {
          constructor() {
            this._timers = {};
            this._last = {};
          }
          destroy() {
            for (const t of Object.values(this._timers)) clearTimeout(t);
          }
          update(u) {
            // A focus transition makes selection state meaningful again: hosts that
            // ignore unfocused selection events (programmatic echoes) must still hear
            // about the first post-focus selection even if it matches the last payload.
            if (u.focusChanged) delete this._last["selection-change"];
            if (self.selectionTrackingEnabled && (u.selectionSet || u.docChanged)) {
              const sel = u.state.selection.main;
              const line = u.state.doc.lineAt(sel.head);
              this._maybeEmit("selection-change", self.selectionDebounceMs, {
                line: line.number,
                column: sel.head - line.from + 1,
                from_line: u.state.doc.lineAt(sel.from).number,
                to_line: u.state.doc.lineAt(sel.to).number,
                empty: sel.empty,
              });
            }
            if (self.focusTrackingEnabled && u.focusChanged) {
              this._maybeEmit("focus-change", self.focusDebounceMs, { focused: u.view.hasFocus });
            }
            if (self.viewportTrackingEnabled && u.viewportChanged) {
              const vp = u.view.viewport;
              this._maybeEmit("viewport-change", self.viewportDebounceMs, {
                from_line: u.state.doc.lineAt(vp.from).number,
                to_line: u.state.doc.lineAt(vp.to).number,
              });
            }
            if (self.geometryTrackingEnabled && u.geometryChanged) {
              this._maybeEmit("geometry-change", self.geometryDebounceMs, {
                width: u.view.dom.clientWidth,
                height: u.view.dom.clientHeight,
                content_height: Math.round(u.view.contentHeight),
              });
            }
          }
          _maybeEmit(name, debounceMs, payload) {
            const last = this._last[name];
            if (last && JSON.stringify(last) === JSON.stringify(payload)) return;
            this._last[name] = payload;
            if (this._timers[name]) clearTimeout(this._timers[name]);
            if (debounceMs > 0) {
              this._timers[name] = setTimeout(() => self.$emit(name, payload), debounceMs);
            } else {
              self.$emit(name, payload);
            }
          }
        },
      );

      const lineTooltip = CM.hoverTooltip((view, pos) => {
        const set = view.state.field(tooltipField);
        const line = view.state.doc.lineAt(pos);
        let content = null;
        set.between(line.from, line.to, (_from, _to, value) => {
          content = value.content;
          return false; // at most one tooltip per line — stop after the first match
        });
        if (content === null) return null;
        const renderHtml = self.lineTooltipHtml;
        return {
          pos: line.from,
          above: true,
          create() {
            const dom = document.createElement("div");
            if (renderHtml) dom.setHTML(content);
            else dom.textContent = content;
            return { dom };
          },
        };
      });

      const extensions = [
        CM.basicSetup,
        changeSender,
        anchorTracker,
        anchorField,
        updateDispatcher,
        // NOTE: do NOT use CM.lintGutter() here — it pulls in lintGutterTooltip,
        // a StateField that registers itself via showTooltip.from(field) and
        // returns null on most transactions. That null provider sits in the
        // showTooltip facet and silently suppresses the autocomplete popup
        // outside of paren contexts. CM.linter() installs lintState (so
        // diagnostics dispatched via CM.setDiagnostics still render as inline
        // marks), and its only tooltip is a hoverTooltip that fires on mouseover,
        // not on every keystroke. The empty source disables auto-linting.
        CM.linter(() => []),
        tooltipField,
        lineTooltip,
        // Enables the Tab key to indent the current lines https://codemirror.net/examples/tab/
        CM.keymap.of([CM.indentWithTab]),
        // User keymap: Prec.high so they win over basicSetup defaults like Mod-z.
        CM.Prec.high(this.userKeymapConfig.of(CM.keymap.of(this.buildUserKeymap()))),
        // Sets indentation https://codemirror.net/docs/ref/#language.indentUnit
        CM.indentUnit.of(this.indent),
        // We will set these Compartments later and dynamically through props
        this.themeConfig.of([]),
        this.languageConfig.of([]),
        this.editableConfig.of([]),
        this.lineWrappingConfig.of([]),
        this.completionsConfig.of([]),
        CM.EditorView.theme({
          "&": { height: "100%" },
          ".cm-scroller": { overflow: "auto" },
        }),
      ];

      if (this.highlightWhitespace) extensions.push([CM.highlightWhitespace()]);

      return extensions;
    },
  },
  async mounted() {
    // This is used to prevent emitting the value we just received from the server.
    this.emitting = true;

    // The Compartments are used to change the properties of the editor ("extensions") dynamically
    this.themes = { ...CM.themes, oneDark: CM.oneDark };
    this.themeConfig = new CM.Compartment();
    this.languages = CM.languages;
    this.languageConfig = new CM.Compartment();
    this.editableConfig = new CM.Compartment();
    this.editableStates = { true: CM.EditorView.editable.of(true), false: CM.EditorView.editable.of(false) };
    this.lineWrappingConfig = new CM.Compartment();
    this.completionsConfig = new CM.Compartment();
    this.userKeymapConfig = new CM.Compartment();

    const extensions = this.setupExtensions();

    this.editor = new CM.EditorView({
      doc: this.value,
      extensions: extensions,
      parent: this.$el,
    });

    this.resolveEditor(this.editor);

    this.setLanguage(this.language);
    this.setTheme(this.theme);
    this.setDisabled(this.disable);
    this.setLineWrapping(this.lineWrapping);
    if (this.lineAnchors && Object.keys(this.lineAnchors).length > 0) {
      this.applyLineAnchors(this.lineAnchors);
    }
    this.applyDiagnostics(this.diagnostics);
    this.rebuildCompletions();
    this.setLineTooltips(this.lineTooltips);
    this.validateUserKeymap();
  },
};
