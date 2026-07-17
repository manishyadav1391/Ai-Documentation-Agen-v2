"""
Style configuration editor dialog for manual formatting.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from pathlib import Path
import yaml

# Add root folder to import paths
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from manual_builder import load_style, StyleConfig


class StyleEditorDialog(tk.Toplevel):
    def __init__(self, parent, client_key: str):
        super().__init__(parent)
        self.parent = parent
        self.client_key = client_key
        self.title(f"Configure Manual Style - '{client_key}'")
        self.geometry("1000x700")
        self.grab_set()
        
        # Load style config
        from docbot import paths
        self.styles_dir = paths.styles_dir()
        self.style_config = load_style(client_key)
        
        self.build_ui()

    def build_ui(self):
        """Constructs a side-by-side layout: form editor tabs on the left, live preview on the right."""
        # Top banner
        banner = tk.Frame(self, bg="#1F3864", pady=10)
        banner.pack(fill=tk.X, side=tk.TOP)
        tk.Label(banner, text=f"Visual Style Configurator - '{self.client_key}'", 
                 font=("Arial", 14, "bold"), bg="#1F3864", fg="white").pack(anchor="w", padx=15)

        # Main Splitter
        main_pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Left Column: Tabs
        left_frame = tk.Frame(main_pane)
        main_pane.add(left_frame, minsize=550)

        # Right Column: Live Preview Panel
        self.preview_frame = tk.LabelFrame(main_pane, text="Live Style Preview (approximation)", padx=10, pady=10)
        main_pane.add(self.preview_frame, minsize=350)
        self.setup_preview_panel()

        # Build Notebook for tabs
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create 8 tabs
        self.tab_page = ttk.Frame(self.notebook)
        self.tab_fonts = ttk.Frame(self.notebook)
        self.tab_colors = ttk.Frame(self.notebook)
        self.tab_headings = ttk.Frame(self.notebook)
        self.tab_cover = ttk.Frame(self.notebook)
        self.tab_fig_tab = ttk.Frame(self.notebook)
        self.tab_numbering = ttk.Frame(self.notebook)
        self.tab_advanced = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_page, text="Page & Margins")
        self.notebook.add(self.tab_fonts, text="Fonts")
        self.notebook.add(self.tab_colors, text="Colors")
        self.notebook.add(self.tab_headings, text="Headings")
        self.notebook.add(self.tab_cover, text="Cover Layout")
        self.notebook.add(self.tab_fig_tab, text="Figures & Tables")
        self.notebook.add(self.tab_numbering, text="Numbering")
        self.notebook.add(self.tab_advanced, text="Advanced YAML")

        self.setup_page_tab()
        self.setup_fonts_tab()
        self.setup_colors_tab()
        self.setup_headings_tab()
        self.setup_cover_tab()
        self.setup_fig_tab_tab()
        self.setup_numbering_tab()
        self.setup_advanced_tab()

        # Bottom Buttons
        btn_frame = tk.Frame(left_frame, pady=10, padx=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Reset to Defaults", bg="#FCA5A5", width=16, command=self.reset_defaults).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Style settings", bg="#A7F3D0", font=("Arial", 10, "bold"), width=20, command=self.save_style).pack(side=tk.RIGHT, padx=5)

        # Trigger initial preview
        self.update_preview()

    # ── TAB SETUP METHODS ──────────────────────────────────────────────────

    def setup_page_tab(self):
        frame = self.tab_page
        pad = dict(padx=10, pady=8, sticky="w")
        
        tk.Label(frame, text="Page Configuration", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, **pad)

        tk.Label(frame, text="Page Size:").grid(row=1, column=0, **pad)
        self.pg_size_var = tk.StringVar(value=self.style_config.page.get("size", "A4"))
        pg_combo = ttk.Combobox(frame, textvariable=self.pg_size_var, values=["A4", "Letter"], state="readonly", width=12)
        pg_combo.grid(row=1, column=1, **pad)
        pg_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        tk.Label(frame, text="Margins (cm):", font=("Arial", 10, "bold")).grid(row=2, column=0, **pad)

        margins = [("Top Margin:", "margin_top_cm"), ("Bottom Margin:", "margin_bottom_cm"),
                   ("Left Margin:", "margin_left_cm"), ("Right Margin:", "margin_right_cm")]
        
        self.margin_vars = {}
        for idx, (label, key) in enumerate(margins, start=3):
            tk.Label(frame, text=label).grid(row=idx, column=0, **pad)
            val = float(self.style_config.page.get(key, 2.5))
            var = tk.DoubleVar(value=val)
            self.margin_vars[key] = var
            sp = tk.Spinbox(frame, from_=0.5, to=5.0, increment=0.1, textvariable=var, width=8, command=self.update_preview)
            sp.grid(row=idx, column=1, **pad)
            sp.bind("<FocusOut>", lambda e: self.update_preview())

    def setup_fonts_tab(self):
        frame = self.tab_fonts
        pad = dict(padx=10, pady=8, sticky="w")
        
        tk.Label(frame, text="Font Families & Sizes", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, **pad)

        font_families = ["Calibri", "Segoe UI", "Arial", "Georgia", "Times New Roman"]

        # Body Font
        tk.Label(frame, text="Body Font Family:").grid(row=1, column=0, **pad)
        self.body_font_var = tk.StringVar(value=self.style_config.fonts.get("body_family", "Calibri"))
        body_combo = ttk.Combobox(frame, textvariable=self.body_font_var, values=font_families, state="readonly", width=18)
        body_combo.grid(row=1, column=1, **pad)
        body_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        # Body Size
        tk.Label(frame, text="Body Font Size (pt):").grid(row=2, column=0, **pad)
        self.body_size_var = tk.DoubleVar(value=float(self.style_config.fonts.get("body_size_pt", 11)))
        sp = tk.Spinbox(frame, from_=8, to=14, increment=0.5, textvariable=self.body_size_var, width=8, command=self.update_preview)
        sp.grid(row=2, column=1, **pad)

        # Heading Font
        tk.Label(frame, text="Heading Font Family:").grid(row=3, column=0, **pad)
        self.heading_font_var = tk.StringVar(value=self.style_config.fonts.get("heading_family", "Calibri"))
        heading_combo = ttk.Combobox(frame, textvariable=self.heading_font_var, values=font_families, state="readonly", width=18)
        heading_combo.grid(row=3, column=1, **pad)
        heading_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

    def setup_colors_tab(self):
        frame = self.tab_colors
        pad = dict(padx=10, pady=4, sticky="w")

        tk.Label(frame, text="Color Swatches", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=3, padx=10, pady=8, sticky="w")

        color_keys = [
            ("Primary (Headers, Accents):", "primary"),
            ("Secondary (Subheadings):", "secondary"),
            ("Tertiary (Deep Red/Accents):", "tertiary"),
            ("Accent Highlight:", "accent"),
            ("Table Header Background:", "table_header_bg"),
            ("Table Header Text:", "table_header_fg"),
            ("Table Zebra Striping Color:", "table_zebra"),
            ("Body Text:", "body_text"),
            ("Muted Details Text:", "muted")
        ]

        self.color_entries = {}
        self.color_swatches = {}

        for idx, (label, key) in enumerate(color_keys, start=1):
            tk.Label(frame, text=label).grid(row=idx, column=0, **pad)
            
            # Entry field
            val = self.style_config.colors.get(key, "000000").replace("#", "")
            entry = tk.Entry(frame, width=10, font=("Consolas", 10))
            entry.insert(0, f"#{val.upper()}")
            entry.grid(row=idx, column=1, **pad)
            self.color_entries[key] = entry
            
            # Swatch box
            swatch = tk.Label(frame, text="      ", bg=f"#{val}", relief="solid", bd=1)
            swatch.grid(row=idx, column=2, **pad)
            self.color_swatches[key] = swatch

            # Bind picking action
            def picker_func(k=key, e=entry, s=swatch):
                color_code = colorchooser.askcolor(title="Choose Accent Color", initialcolor=e.get())
                if color_code and color_code[1]:
                    e.delete(0, tk.END)
                    e.insert(0, color_code[1].upper())
                    s.config(bg=color_code[1])
                    self.update_preview()
            
            tk.Button(frame, text="Pick...", command=picker_func).grid(row=idx, column=3, padx=5, pady=2)
            entry.bind("<FocusOut>", lambda e, k=key, ent=entry, sw=swatch: self.update_swatch_from_entry(k, ent, sw))

    def update_swatch_from_entry(self, key, entry, swatch):
        val = entry.get().strip().replace("#", "")
        if len(val) == 6:
            swatch.config(bg=f"#{val}")
        self.update_preview()

    def setup_headings_tab(self):
        frame = self.tab_headings
        pad = dict(padx=8, pady=4, sticky="w")

        tk.Label(frame, text="Heading Formatting Rules", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=4, padx=10, pady=8, sticky="w")

        heading_levels = [("H1 (Chapters):", 1), ("H2 (Screens):", 2), ("H3 (Subsections):", 3), ("H4 (Sub-items):", 4)]

        self.heading_size_vars = {}
        self.heading_bold_vars = {}

        for idx, (label, lvl) in enumerate(heading_levels, start=1):
            tk.Label(frame, text=label, font=("Arial", 10, "bold")).grid(row=idx*2 - 1, column=0, **pad)
            
            # Size
            tk.Label(frame, text="Size (pt):").grid(row=idx*2 - 1, column=1, **pad)
            val_size = self.style_config.headings.get(f"h{lvl}_size_pt", 12)
            var_size = tk.IntVar(value=val_size)
            self.heading_size_vars[lvl] = var_size
            sp = tk.Spinbox(frame, from_=10, to=36, increment=1, textvariable=var_size, width=6, command=self.update_preview)
            sp.grid(row=idx*2 - 1, column=2, **pad)
            
            # Bold
            val_bold = self.style_config.headings.get(f"h{lvl}_bold", True)
            var_bold = tk.BooleanVar(value=val_bold)
            self.heading_bold_vars[lvl] = var_bold
            cb = tk.Checkbutton(frame, text="Bold", variable=var_bold, command=self.update_preview)
            cb.grid(row=idx*2 - 1, column=3, **pad)

            # Dividers
            tk.Frame(frame, height=2, bd=1, relief="sunken").grid(row=idx*2, column=0, columnspan=4, sticky="ew", pady=4)

    def setup_cover_tab(self):
        frame = self.tab_cover
        pad = dict(padx=10, pady=6, sticky="w")

        tk.Label(frame, text="Cover Page Visual Design", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, **pad)

        tk.Label(frame, text="Layout Mode:").grid(row=1, column=0, **pad)
        self.cover_layout_var = tk.StringVar(value=self.style_config.cover.get("layout", "centered"))
        combo = ttk.Combobox(frame, textvariable=self.cover_layout_var, 
                             values=["centered", "left_accent_bar", "full_bleed"], state="readonly", width=16)
        combo.grid(row=1, column=1, **pad)
        combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        tk.Label(frame, text="Accent Bar Color:").grid(row=2, column=0, **pad)
        self.cover_accent_color_var = tk.StringVar(value=self.style_config.cover.get("accent_bar_color", "primary"))
        combo_c = ttk.Combobox(frame, textvariable=self.cover_accent_color_var, 
                               values=["primary", "secondary", "tertiary", "accent"], state="readonly", width=12)
        combo_c.grid(row=2, column=1, **pad)
        combo_c.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        tk.Label(frame, text="Title Font Size (pt):").grid(row=3, column=0, **pad)
        self.cover_title_size_var = tk.IntVar(value=self.style_config.cover.get("title_size_pt", 32))
        sp = tk.Spinbox(frame, from_=24, to=48, increment=2, textvariable=self.cover_title_size_var, width=6, command=self.update_preview)
        sp.grid(row=3, column=1, **pad)

        tk.Label(frame, text="Version Block Position:").grid(row=4, column=0, **pad)
        self.cover_ver_pos_var = tk.StringVar(value=self.style_config.cover.get("version_position", "bottom_right"))
        combo_v = ttk.Combobox(frame, textvariable=self.cover_ver_pos_var, 
                               values=["bottom_right", "bottom_center", "under_title"], state="readonly", width=16)
        combo_v.grid(row=4, column=1, **pad)
        combo_v.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

    def setup_fig_tab_tab(self):
        frame = self.tab_fig_tab
        pad = dict(padx=10, pady=6, sticky="w")

        tk.Label(frame, text="Figures & Tables Captions", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, **pad)

        # Figures
        tk.Label(frame, text="Figure Caption Location:").grid(row=1, column=0, **pad)
        self.fig_cap_pos_var = tk.StringVar(value=self.style_config.figures.get("caption_position", "below"))
        combo_fig = ttk.Combobox(frame, textvariable=self.fig_cap_pos_var, values=["above", "below"], state="readonly", width=10)
        combo_fig.grid(row=1, column=1, **pad)

        tk.Label(frame, text="Figure Caption Size (pt):").grid(row=2, column=0, **pad)
        self.fig_cap_size_var = tk.IntVar(value=self.style_config.figures.get("caption_size_pt", 10))
        sp_f = tk.Spinbox(frame, from_=8, to=12, increment=1, textvariable=self.fig_cap_size_var, width=6, command=self.update_preview)
        sp_f.grid(row=2, column=1, **pad)

        # Tables
        tk.Label(frame, text="Table Caption Location:").grid(row=3, column=0, **pad)
        self.tbl_cap_pos_var = tk.StringVar(value=self.style_config.tables.get("caption_position", "below"))
        combo_tbl = ttk.Combobox(frame, textvariable=self.tbl_cap_pos_var, values=["above", "below"], state="readonly", width=10)
        combo_tbl.grid(row=3, column=1, **pad)

        self.zebra_striping_var = tk.BooleanVar(value=self.style_config.tables.get("zebra_striping", True))
        cb_zebra = tk.Checkbutton(frame, text="Enable Table Zebra Striping", variable=self.zebra_striping_var, command=self.update_preview)
        cb_zebra.grid(row=4, column=0, columnspan=2, **pad)

    def setup_numbering_tab(self):
        frame = self.tab_numbering
        pad = dict(padx=10, pady=8, sticky="w")

        tk.Label(frame, text="Manual Numbering Schemes", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, **pad)

        # Figure Prefix
        tk.Label(frame, text="Figure Label Prefix:").grid(row=1, column=0, **pad)
        self.fig_prefix_var = tk.StringVar(value=self.style_config.numbering.get("figure_prefix", "Figure"))
        entry_f = tk.Entry(frame, textvariable=self.fig_prefix_var, width=12)
        entry_f.grid(row=1, column=1, **pad)
        entry_f.bind("<FocusOut>", lambda e: self.update_preview())

        # Figure Format
        tk.Label(frame, text="Figure Format:").grid(row=2, column=0, **pad)
        self.fig_format_var = tk.StringVar(value=self.style_config.numbering.get("figure_format", "{module}-{fig}"))
        entry_ff = tk.Entry(frame, textvariable=self.fig_format_var, width=18)
        entry_ff.grid(row=2, column=1, **pad)
        entry_ff.bind("<FocusOut>", lambda e: self.update_preview())

        # Table Prefix
        tk.Label(frame, text="Table Label Prefix:").grid(row=3, column=0, **pad)
        self.tbl_prefix_var = tk.StringVar(value=self.style_config.numbering.get("table_prefix", "Table"))
        entry_t = tk.Entry(frame, textvariable=self.tbl_prefix_var, width=12)
        entry_t.grid(row=3, column=1, **pad)
        entry_t.bind("<FocusOut>", lambda e: self.update_preview())

        # Table Format
        tk.Label(frame, text="Table Format:").grid(row=4, column=0, **pad)
        self.tbl_format_var = tk.StringVar(value=self.style_config.numbering.get("table_format", "{module}-{tbl}"))
        entry_tf = tk.Entry(frame, textvariable=self.tbl_format_var, width=18)
        entry_tf.grid(row=4, column=1, **pad)
        entry_tf.bind("<FocusOut>", lambda e: self.update_preview())

        # Explanations
        lbl_hint = tk.Label(frame, text="Placeholders available:\n{module} - Module number\n{fig} / {tbl} - Counter index", 
                            font=("Arial", 9, "italic"), justify="left")
        lbl_hint.grid(row=5, column=0, columnspan=2, **pad)

    def setup_advanced_tab(self):
        frame = self.tab_advanced
        tk.Label(frame, text="Direct YAML style config editor:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=5)

        self.txt_yaml = tk.Text(frame, font=("Consolas", 10), wrap="none")
        self.txt_yaml.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Populate YAML text
        yaml_str = yaml.safe_dump(self.style_config.raw, default_flow_style=False, sort_keys=False, allow_unicode=True)
        self.txt_yaml.insert("1.0", yaml_str)

        # Bind validation and update
        self.txt_yaml.bind("<FocusOut>", lambda e: self.parse_yaml_text())

    def parse_yaml_text(self):
        text = self.txt_yaml.get("1.0", tk.END)
        try:
            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                self.style_config.raw = parsed
                self.update_preview()
        except Exception as e:
            # Silent on keystrokes, validation fires on focus loss/save
            pass

    # ── PREVIEW PANEL METHOD ───────────────────────────────────────────────

    def setup_preview_panel(self):
        """Builds a canvas representing a layout page mockup."""
        self.preview_canvas = tk.Canvas(self.preview_frame, bg="white", width=340, height=450, relief="solid", bd=1)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

    def update_preview(self):
        """Draws page layout mockups dynamically based on current values."""
        if not hasattr(self, 'cover_layout_var') or not hasattr(self, 'color_entries'):
            return
        try:
            self.preview_canvas.delete("all")
        except AttributeError:
            return

        # Fetch form values
        primary_col = self.color_entries["primary"].get().strip()
        secondary_col = self.color_entries["secondary"].get().strip()
        muted_col = self.color_entries["muted"].get().strip()
        body_text_col = self.color_entries["body_text"].get().strip()

        # Sanitize hex colors
        if not primary_col.startswith("#"): primary_col = f"#{primary_col}"
        if not secondary_col.startswith("#"): secondary_col = f"#{secondary_col}"
        if not muted_col.startswith("#"): muted_col = f"#{muted_col}"
        if not body_text_col.startswith("#"): body_text_col = f"#{body_text_col}"

        # Get cover layout type
        layout = self.cover_layout_var.get()

        # Canvas bounds (A4 proportions: 340w x 450h)
        w, h = 340, 450

        # Draw cover mock margins
        self.preview_canvas.create_rectangle(15, 15, w-15, h-15, outline="#E2E8F0", width=1)

        # Render simulated page mock
        if layout == "centered":
            # Title
            self.preview_canvas.create_text(w/2, 100, text="USER MANUAL", font=(self.heading_font_var.get(), 14, "bold"), fill=primary_col, justify="center")
            self.preview_canvas.create_line(40, 120, w-40, 120, fill=secondary_col, width=2)
            
            # Subtitle
            self.preview_canvas.create_text(w/2, 145, text="National Economic Offense Records", font=(self.heading_font_var.get(), 9, "italic"), fill=secondary_col, justify="center")
            self.preview_canvas.create_text(w/2, 160, text="For Narcotics Control Bureau", font=(self.body_font_var.get(), 8), fill=muted_col, justify="center")

            # Fake logo circle
            self.preview_canvas.create_oval(w/2-20, 200, w/2+20, 240, outline=primary_col, fill="#F1F5F9", width=2)
            
        elif layout == "left_accent_bar":
            # Left accent sidebar bar
            self.preview_canvas.create_rectangle(15, 15, 45, h-15, fill=primary_col, outline="")
            
            # Title left aligned
            self.preview_canvas.create_text(60, 100, text="USER MANUAL", font=(self.heading_font_var.get(), 14, "bold"), fill=primary_col, anchor="w")
            self.preview_canvas.create_line(60, 120, w-40, 120, fill=secondary_col, width=2)

            self.preview_canvas.create_text(60, 145, text="National Economic Offense Records", font=(self.heading_font_var.get(), 9, "italic"), fill=secondary_col, anchor="w")
            self.preview_canvas.create_text(60, 160, text="For Narcotics Control Bureau", font=(self.body_font_var.get(), 8), fill=muted_col, anchor="w")

            self.preview_canvas.create_rectangle(60, 190, 110, 240, outline=primary_col, fill="#F8FAFC", width=1)

        elif layout == "full_bleed":
            # Full background shading
            self.preview_canvas.create_rectangle(15, 15, w-15, h-15, fill=primary_col, outline="")
            
            # Title white
            self.preview_canvas.create_text(w/2, 120, text="USER MANUAL", font=(self.heading_font_var.get(), 18, "bold"), fill="white", justify="center")
            self.preview_canvas.create_text(w/2, 160, text="National Economic Offense Records", font=(self.heading_font_var.get(), 10), fill="#CBD5E1", justify="center")

        # Draw Bottom Meta table mock (except for full_bleed layout)
        if layout != "full_bleed":
            self.preview_canvas.create_rectangle(40, h-95, w-40, h-40, outline="#E2E8F0", fill="#F8FAFC", width=1)
            self.preview_canvas.create_text(50, h-85, text="Version: 1.1\nDate: 09-07-2026", font=(self.body_font_var.get(), 8), fill=body_text_col, anchor="nw")
            
            # Draw primary colored flag in metadata table
            self.preview_canvas.create_rectangle(w-95, h-95, w-40, h-40, fill=primary_col, outline="")
            self.preview_canvas.create_text(w-67, h-67, text="CONFIDENTIAL", font=(self.heading_font_var.get(), 7, "bold"), fill="white", justify="center")

    # ── SAVE AND RESET METHODS ─────────────────────────────────────────────

    def reset_defaults(self):
        if messagebox.askyesno("Reset Styles", "Reset formatting configuration back to defaults?"):
            self.style_config = load_style("_default", styles_dir=str(self.styles_dir))
            
            # Re-read configurations
            self.destroy()
            StyleEditorDialog(self.parent, self.client_key)

    def save_style(self):
        """Converts form inputs back into self.style_config schema and writes to yaml."""
        try:
            # 1. Page
            self.style_config.raw["page"] = {
                "size": self.pg_size_var.get(),
                "margin_top_cm": self.margin_vars["margin_top_cm"].get(),
                "margin_bottom_cm": self.margin_vars["margin_bottom_cm"].get(),
                "margin_left_cm": self.margin_vars["margin_left_cm"].get(),
                "margin_right_cm": self.margin_vars["margin_right_cm"].get()
            }

            # 2. Fonts
            self.style_config.raw["fonts"] = {
                "body_family": self.body_font_var.get(),
                "body_size_pt": self.body_size_var.get(),
                "heading_family": self.heading_font_var.get()
            }

            # 3. Colors
            self.style_config.raw["colors"] = {
                k: entry.get().strip().replace("#", "") for k, entry in self.color_entries.items()
            }

            # 4. Headings
            self.style_config.raw["headings"] = {
                f"h{lvl}_size_pt": self.heading_size_vars[lvl].get() for lvl in [1, 2, 3, 4]
            }
            for lvl in [1, 2, 3, 4]:
                self.style_config.raw["headings"][f"h{lvl}_bold"] = self.heading_bold_vars[lvl].get()
                self.style_config.raw["headings"][f"h{lvl}_color"] = "primary" # Keep standard primary mapping

            # 5. Cover
            self.style_config.raw["cover"] = {
                "layout": self.cover_layout_var.get(),
                "accent_bar_color": self.cover_accent_color_var.get(),
                "title_size_pt": self.cover_title_size_var.get(),
                "version_position": self.cover_ver_pos_var.get()
            }

            # 6. Figures & Tables
            self.style_config.raw["figures"] = {
                "caption_position": self.fig_cap_pos_var.get(),
                "caption_size_pt": self.fig_cap_size_var.get()
            }
            self.style_config.raw["tables"] = {
                "caption_position": self.tbl_cap_pos_var.get(),
                "zebra_striping": self.zebra_striping_var.get(),
                "zebra_color": "table_zebra"
            }

            # 7. Numbering
            self.style_config.raw["numbering"] = {
                "figure_prefix": self.fig_prefix_var.get(),
                "figure_format": self.fig_format_var.get(),
                "table_prefix": self.tbl_prefix_var.get(),
                "table_format": self.tbl_format_var.get()
            }

            # Save style configuration
            dest_path = self.styles_dir / f"{self.client_key}.yaml"
            self.style_config.save(dest_path)
            messagebox.showinfo("Success", f"Styling settings for client '{self.client_key}' saved successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save style configuration:\n{e}")
