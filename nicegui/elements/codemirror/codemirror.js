import * as CM from "nicegui-codemirror";

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
    customCompletions: Array,
    decorations: Object,
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
    customCompletions(newCompletions) {
      this.setCustomCompletions(newCompletions);
    },
    decorations: {
      deep: true,
      handler(newDecorations) {
        this.setDecorations(newDecorations);
      },
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
  methods: {
    // Find the language's extension by its name. Case insensitive.
    findLanguage(name) {
      for (const language of this.languages)
        for (const alias of [language.name, ...language.alias])
          if (name.toLowerCase() === alias.toLowerCase()) return language;

      console.error(`Language not found: ${this.language}`);
      console.info("Supported language names:", languages.map((lang) => lang.name).join(", "));
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

      const lang_description = this.findLanguage(language, this.languages);
      if (!lang_description) {
        console.error("Language not found:", language);
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
      if (this.editor.state.doc.toString() === value) return;

      this.emitting = false;
      this.editor.dispatch({ changes: { from: 0, to: this.editor.state.doc.length, insert: value } });
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
    highlightLines(lineIndices, cssClass, durationMs) {
      if (!this.editor) return;

      // Build line decorations from indices (0-indexed to 1-indexed)
      const lineDecorations = lineIndices
        .filter(idx => idx >= 0 && idx < this.editor.state.doc.lines)
        .map(idx => ({
          kind: "line",
          line: idx + 1,
          class: cssClass,
        }));

      if (lineDecorations.length === 0) return;

      // Apply decorations using internal _highlight set
      const current = { ...(this.decorations || {}) };
      current._highlight = lineDecorations;
      this.setDecorations(current);

      // Scroll first line into view
      const firstLineNum = Math.min(...lineIndices) + 1;
      const line = this.editor.state.doc.line(
        Math.max(1, Math.min(firstLineNum, this.editor.state.doc.lines))
      );
      this.editor.dispatch({
        effects: CM.EditorView.scrollIntoView(line.from, { y: "center" }),
      });

      // Auto-remove after duration
      if (durationMs > 0) {
        setTimeout(() => {
          const updated = { ...(this.decorations || {}) };
          delete updated._highlight;
          this.setDecorations(updated);
        }, durationMs);
      }
    },
    setCustomCompletions(completions) {
      if (!this.editor || !this.completionsConfig) return;
      if (!completions || completions.length === 0) {
        this.editor.dispatch({
          effects: this.completionsConfig.reconfigure([]),
        });
        return;
      }
      
      // Create a custom completion source from the provided completions
      const customCompletionSource = (context) => {
        // Get word before cursor
        const word = context.matchBefore(/[\w.]+/);
        if (!word && !context.explicit) return null;
        
        const from = word ? word.from : context.pos;
        const text = word ? word.text : "";
        
        // Filter completions that match the current input
        const matchingCompletions = completions.filter(c => {
          const label = c.label || "";
          return label.toLowerCase().startsWith(text.toLowerCase());
        }).map(c => ({
          label: c.label,
          detail: c.detail || "",
          info: c.info || "",
          apply: c.apply || c.label,
          type: c.type || "function",
        }));
        
        if (matchingCompletions.length === 0) return null;
        
        return {
          from: from,
          options: matchingCompletions,
          validFor: /^[\w.]*$/,
        };
      };
      
      // Create autocompletion extension with our custom source
      const completionExtension = CM.autocompletion({
        override: [customCompletionSource],
        activateOnTyping: true,
      });
      
      this.editor.dispatch({
        effects: this.completionsConfig.reconfigure([completionExtension]),
      });
    },
    setDecorations(decorationSets) {
      if (!this.editor || !this.decorationsConfig) return;

      if (!decorationSets || Object.keys(decorationSets).length === 0) {
        this.editor.dispatch({
          effects: this.decorationsConfig.reconfigure([]),
        });
        return;
      }

      const allDecorations = [];
      for (const specs of Object.values(decorationSets)) {
        for (const spec of specs) {
          const dec = this.createDecoration(spec);
          if (dec) allDecorations.push(dec);
        }
      }

      // Sort by position (required by CM6)
      allDecorations.sort((a, b) => a.from - b.from);

      const decorationSet = CM.Decoration.set(allDecorations, true);
      const decorationExtension = CM.EditorView.decorations.of(decorationSet);

      this.editor.dispatch({
        effects: this.decorationsConfig.reconfigure([
          decorationExtension,
          this.getDecorationStyles(),
        ]),
      });
    },
    createDecoration(spec) {
      const doc = this.editor.state.doc;

      if (spec.kind === "mark") {
        const from = Math.max(0, Math.min(spec.from, doc.length));
        const to = Math.max(from, Math.min(spec.to, doc.length));
        const markSpec = {};
        if (spec.class) markSpec.class = spec.class;
        if (spec.attributes) markSpec.attributes = spec.attributes;
        if (spec.inclusiveStart !== undefined) markSpec.inclusiveStart = spec.inclusiveStart;
        if (spec.inclusiveEnd !== undefined) markSpec.inclusiveEnd = spec.inclusiveEnd;
        return CM.Decoration.mark(markSpec).range(from, to);

      } else if (spec.kind === "line") {
        const lineNum = Math.max(1, Math.min(spec.line, doc.lines));
        const line = doc.line(lineNum);
        const lineSpec = {};
        if (spec.class) lineSpec.class = spec.class;
        if (spec.attributes) lineSpec.attributes = spec.attributes;
        return CM.Decoration.line(lineSpec).range(line.from);
      }
      return null;
    },
    getDecorationStyles() {
      return CM.EditorView.baseTheme({
        ".cm-diff-added": {
          backgroundColor: "rgba(0, 255, 0, 0.2)",
          borderRadius: "2px",
        },
        ".cm-diff-deleted": {
          backgroundColor: "rgba(255, 0, 0, 0.2)",
          textDecoration: "line-through",
        },
        ".cm-diff-line-added": {
          backgroundColor: "rgba(0, 255, 0, 0.1)",
        },
        ".cm-diff-line-deleted": {
          backgroundColor: "rgba(255, 0, 0, 0.1)",
        },
        ".cm-highlighted": {
          backgroundColor: "rgba(255, 255, 0, 0.3)",
        },
      });
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
        }
      );

      const extensions = [
        CM.basicSetup,
        changeSender,
        // Enables the Tab key to indent the current lines https://codemirror.net/examples/tab/
        CM.keymap.of([CM.indentWithTab]),
        // Sets indentation https://codemirror.net/docs/ref/#language.indentUnit
        CM.indentUnit.of(this.indent),
        // We will set these Compartments later and dynamically through props
        this.themeConfig.of([]),
        this.languageConfig.of([]),
        this.editableConfig.of([]),
        this.lineWrappingConfig.of([]),
        this.completionsConfig.of([]),
        this.decorationsConfig.of([]),
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
    this.decorationsConfig = new CM.Compartment();

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
    if (this.customCompletions) {
      this.setCustomCompletions(this.customCompletions);
    }
  },
};
