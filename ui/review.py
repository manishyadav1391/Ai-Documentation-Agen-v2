"""
DocBot v3 — Visual Review UI (Phase 7) — EDITOR UPGRADE.

New editor features in this version
-----------------------------------
E1  DRAGGABLE CALLOUTS: every region shows its callout bubble on the canvas.
    Drag the bubble anywhere — the position is stored on the region
    (callout_x / callout_y) and the annotator uses it instead of auto
    placement. Right-click a bubble → "Reset callout to auto".
E2  HANDLE-BASED BOX EDITING: the selected region gets 8 resize handles.
    Drag a handle to resize, drag inside the box to move — like any editor.
    Drag on empty canvas still draws a NEW region.
E3  Extra ease-of-use:
    - Arrow keys nudge the selected region (Shift+Arrows = resize).
    - Right-click a region → context menu (Edit / Delete / Reset callout).
    - Right-click empty area still pans.
    - Ctrl+Right / Ctrl+Left switch screens (auto-saves inputs).
    - Esc deselects. Ctrl+Z undo covers move/resize/callout/draw/delete.
    - Status bar shows live cursor position + selected region info.
    - Hover cursors: arrows over handles, hand over callouts, move inside box.

REQUIRED companion patches (see notes shipped with this file):
  models.py   → Region gains: callout_x: float | None = None
                               callout_y: float | None = None
  annotate.py → if region.callout_x is not None, use (callout_x, callout_y)
                as the bubble anchor instead of the auto-scored candidate.
"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
from loguru import logger

from config import get_config
from docbot.models import SessionStore, Screen, Region, FieldDetail, Step, BBox
from docbot.processing.generator import Generator
from docbot.processing.annotate import render_annotations
from docbot.processing.crops import extract_crops

HANDLE_PX = 7           # on-screen size of resize handles (not zoom-scaled)
CALLOUT_W = 110         # on-screen callout bubble width for hit-testing
CALLOUT_H = 22          # on-screen callout bubble height


class ReviewSessionUI:
    """The document-level session review UI with direct-manipulation editing."""

    def __init__(self, root: tk.Tk, session_dir: Path, initial_idx: int = 1):
        self.root = root
        self.session_dir = session_dir
        self.root.title("DocBot v3 — Master Session Review")
        self.root.geometry("1480x950")
        try:
            self.root.state("zoomed")
        except Exception:
            pass

        self.session = SessionStore.load(self.session_dir)
        if not self.session.screens:
            raise ValueError(f"No screens found in session {session_dir.name}")

        self.current_screen_idx = 0
        for i, s in enumerate(self.session.screens):
            if s.index == initial_idx:
                self.current_screen_idx = i
                break

        self.active_region_id: str | None = None
        self.selected_step_idx: int | None = None
        self.preview_mode = False

        # Drag state machine: None | "draw" | "move" | "resize" | "callout"
        self._drag_mode: str | None = None
        self._drag_region: Region | None = None
        self._drag_handle: str | None = None      # "nw","n","ne","e","se","s","sw","w"
        self._drag_last: tuple[float, float] | None = None
        self._drag_dirty = False                  # push_undo happened for this drag

        self._undo_stack: list[list[Region]] = []
        self._pan_last = None

        self._setup_style()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_screen(self.current_screen_idx)

    # ────────────────────────────────────────────────────────────────────────
    # Styling / layout
    # ────────────────────────────────────────────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg_dark = "#1E293B"
        bg_light = "#F8FAFC"
        accent_blue = "#3B82F6"
        style.configure("TFrame", background=bg_light)
        style.configure("Top.TFrame", background=bg_dark)
        style.configure("Sidebar.TFrame", background="#F1F5F9")
        style.configure("TLabel", background=bg_light, font=("Segoe UI", 10))
        style.configure("Top.TLabel", background=bg_dark, foreground="white",
                        font=("Segoe UI", 11, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                        foreground="white", background=accent_blue)
        style.configure("TNotebook", background=bg_light)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10))

    def _build_layout(self):
        # Top bar
        top_bar = ttk.Frame(self.root, style="Top.TFrame", padding=10)
        top_bar.pack(fill=tk.X, side=tk.TOP)
        ttk.Label(top_bar, text="DocBot v3 — Interactive Review",
                  style="Top.TLabel").pack(side=tk.LEFT, padx=10)
        ttk.Button(top_bar, text="Save Session (Ctrl+S)",
                   command=self._save_session).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_bar, text="Save & Finish", style="Accent.TButton",
                   command=self._save_and_close).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_bar, text="Compile Module",
                   command=self._compile_module).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_bar, text="◀ Prev (Ctrl+←)",
                   command=lambda: self._switch_screen(-1)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_bar, text="Next (Ctrl+→) ▶",
                   command=lambda: self._switch_screen(1)).pack(side=tk.RIGHT, padx=5)

        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Sidebar
        sidebar = ttk.Frame(main_paned, style="Sidebar.TFrame", width=220)
        main_paned.add(sidebar, weight=0)
        ttk.Label(sidebar, text="Screens in Session", style="Header.TLabel",
                  background="#F1F5F9").pack(anchor=tk.W, padx=10, pady=10)
        self.screen_listbox = tk.Listbox(sidebar, font=("Segoe UI", 10),
                                         selectbackground="#3B82F6", bd=0,
                                         highlightthickness=0)
        self.screen_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.screen_listbox.bind("<<ListboxSelect>>", self._on_screen_selected_from_list)
        self._refresh_sidebar()

        # Canvas area
        canvas_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(canvas_frame, weight=3)
        ttk.Label(canvas_frame,
                  text="Editor: drag empty area = new region · drag box = move · "
                       "drag handles = resize · drag bubble = place callout",
                  font=("Segoe UI", 9, "italic")).pack(anchor=tk.W, pady=2)

        self._zoom_level = 1.0
        zoom_bar = ttk.Frame(canvas_frame, padding=3)
        zoom_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(zoom_bar, text="Zoom:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=6)
        self._zoom_var = tk.DoubleVar(value=1.0)
        zoom_slider = tk.Scale(zoom_bar, from_=0.2, to=4.0, resolution=0.05,
                               orient=tk.HORIZONTAL, variable=self._zoom_var, length=200,
                               command=self._on_zoom_slider, showvalue=False,
                               background="#F1F5F9")
        zoom_slider.pack(side=tk.LEFT, padx=4)
        self._zoom_label = ttk.Label(zoom_bar, text="100%", width=6)
        self._zoom_label.pack(side=tk.LEFT)
        ttk.Button(zoom_bar, text="Fit", width=5, command=self._zoom_fit).pack(side=tk.LEFT, padx=4)
        ttk.Button(zoom_bar, text="100%", width=5, command=self._zoom_100).pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_bar, text="200%", width=5, command=self._zoom_200).pack(side=tk.LEFT, padx=2)
        self.callout_visible = tk.BooleanVar(value=True)
        ttk.Checkbutton(zoom_bar, text="Show callouts",
                        variable=self.callout_visible,
                        command=self._render_canvas).pack(side=tk.LEFT, padx=10)
        self.preview_btn = ttk.Button(zoom_bar, text="👁️ Preview", width=10,
                                      command=self._toggle_preview)
        self.preview_btn.pack(side=tk.RIGHT, padx=6)

        canvas_container = ttk.Frame(canvas_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_container, bg="#CBD5E1", cursor="cross")
        h_scroll = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.config(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Status bar (E3)
        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(canvas_frame, textvariable=self.status_var,
                           font=("Segoe UI", 9), foreground="#475569")
        status.pack(anchor=tk.W, pady=(3, 0))

        # Canvas bindings — unified editor state machine
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<Motion>", self._on_canvas_hover)

        # Right-click: context menu on region/callout, pan on empty area
        self.canvas.bind("<ButtonPress-3>", self._on_right_press)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-3>", lambda e: setattr(self, "_pan_last", None))

        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_scroll)
        self.canvas.bind("<MouseWheel>", self._on_plain_scroll)

        # Keyboard (E3)
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<Control-z>", self._on_undo)
        self.root.bind("<Control-s>", lambda e: self._save_session())
        self.root.bind("<Escape>", lambda e: self._deselect())
        self.root.bind("<Control-Right>", lambda e: self._switch_screen(1))
        self.root.bind("<Control-Left>", lambda e: self._switch_screen(-1))
        for key, args in (("<Up>", ("y", -5)), ("<Down>", ("y", 5)),
                          ("<Left>", ("x", -5)), ("<Right>", ("x", 5))):
            self.root.bind(key, lambda e, a=args: self._arrow_nudge(a[0], a[1], resize=False))
        for key, args in (("<Shift-Up>", ("h", -5)), ("<Shift-Down>", ("h", 5)),
                          ("<Shift-Left>", ("w", -5)), ("<Shift-Right>", ("w", 5))):
            self.root.bind(key, lambda e, a=args: self._arrow_nudge(a[0], a[1], resize=True))

        # Right panel notebook
        right_frame = ttk.Frame(main_paned, width=580)
        main_paned.add(right_frame, weight=2)
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        tab_content = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_content, text="Screen Documentation")
        self._build_content_tab(tab_content)
        tab_regions = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_regions, text="Region Structure")
        self._build_regions_tab(tab_regions)

    def _build_content_tab(self, parent: ttk.Frame):
        sub_notebook = ttk.Notebook(parent)
        sub_notebook.pack(fill=tk.BOTH, expand=True)

        sub_meta = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_meta, text="General")
        ttk.Label(sub_meta, text="Screen Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.screen_name_entry = ttk.Entry(sub_meta, width=50)
        self.screen_name_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Label(sub_meta, text="Screen Purpose:").grid(row=1, column=0, sticky=tk.NW, pady=5)
        self.purpose_text = tk.Text(sub_meta, height=3, width=50, font=("Segoe UI", 9))
        self.purpose_text.grid(row=1, column=1, sticky=tk.W, pady=5)
        ttk.Label(sub_meta, text="Navigation path:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.nav_entry = ttk.Entry(sub_meta, width=50)
        self.nav_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        regen_frame = ttk.LabelFrame(sub_meta, text="AI Assistance Options", padding=10)
        regen_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=20)
        ttk.Button(regen_frame, text="Regenerate All Content",
                   command=self._regenerate_screen).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(regen_frame, text="Regenerate Steps Only",
                   command=self._regen_steps).grid(row=0, column=1, padx=5, pady=5)

        sub_steps = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_steps, text="User Steps")
        steps_ctrl = ttk.Frame(sub_steps)
        steps_ctrl.pack(fill=tk.X, side=tk.TOP, pady=5)
        ttk.Button(steps_ctrl, text="Add Step", command=self._add_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Edit Step", command=self._edit_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Delete Step", command=self._delete_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Move Up", command=lambda: self._move_step(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Move Down", command=lambda: self._move_step(1)).pack(side=tk.LEFT, padx=2)
        self.steps_listbox = tk.Listbox(sub_steps, font=("Segoe UI", 9), selectbackground="#3B82F6")
        self.steps_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.steps_listbox.bind("<<ListboxSelect>>", self._on_step_selected)
        self.steps_listbox.bind("<Double-1>", lambda e: self._edit_step())

        sub_fields = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_fields, text="Field Reference Table")
        self.fields_tree = ttk.Treeview(sub_fields, columns=("name", "utility", "sample"),
                                        show="headings")
        self.fields_tree.heading("name", text="Field Name")
        self.fields_tree.heading("utility", text="Utility / Description")
        self.fields_tree.heading("sample", text="Sample Value")
        self.fields_tree.column("name", width=120)
        self.fields_tree.column("utility", width=250)
        self.fields_tree.column("sample", width=80)
        self.fields_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.fields_tree.bind("<Double-1>", self._on_field_edit_dialog)

        sub_figs = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_figs, text="Figure Attachments")
        figs_ctrl = ttk.Frame(sub_figs)
        figs_ctrl.pack(fill=tk.X, side=tk.TOP, pady=2)
        ttk.Button(figs_ctrl, text="Toggle full_page vs viewport",
                   command=self._toggle_figure_mode).pack(side=tk.LEFT, padx=2)
        ttk.Button(figs_ctrl, text="Remove Attachment",
                   command=self._remove_figure).pack(side=tk.LEFT, padx=2)
        self.figs_listbox = tk.Listbox(sub_figs, font=("Segoe UI", 9))
        self.figs_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

    def _build_regions_tab(self, parent: ttk.Frame):
        ttk.Label(parent, text="Detected Page Regions list:",
                  style="Header.TLabel").pack(anchor=tk.W, pady=5)
        self.regions_listbox = tk.Listbox(parent, font=("Segoe UI", 9),
                                          selectbackground="#3B82F6")
        self.regions_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.regions_listbox.bind("<<ListboxSelect>>", self._on_region_selected_from_tab)
        self.regions_listbox.bind("<Double-1>", self.on_region_double_click)

        region_edit_frame = ttk.Frame(parent)
        region_edit_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)
        ttk.Label(region_edit_frame, text="Region Label:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.region_label_entry = ttk.Entry(region_edit_frame, width=40)
        self.region_label_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        self.region_label_entry.bind("<KeyRelease>", self._on_region_label_changed)
        btns = ttk.Frame(region_edit_frame)
        btns.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=8)
        ttk.Button(btns, text="Delete Region",
                   command=self._delete_active_region).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Reset Callout to Auto",
                   command=self._reset_active_callout).pack(side=tk.LEFT, padx=2)

    # ────────────────────────────────────────────────────────────────────────
    # Sidebar & navigation
    # ────────────────────────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        self.screen_listbox.delete(0, tk.END)
        for s in self.session.screens:
            label = s.content.screen_name or s.title or f"Screen {s.index}"
            status = "✓ " if s.reviewed else "  "
            self.screen_listbox.insert(tk.END, f"{status}{label}")

    def _on_screen_selected_from_list(self, event):
        sel = self.screen_listbox.curselection()
        if not sel:
            return
        self._save_active_screen_inputs()
        self._load_screen(sel[0])

    def _switch_screen(self, direction: int):
        """Ctrl+Left/Right screen navigation with autosave (E3)."""
        target = self.current_screen_idx + direction
        if 0 <= target < len(self.session.screens):
            self._save_active_screen_inputs()
            SessionStore.save(self.session, self.session_dir)
            self._load_screen(target)

    # ────────────────────────────────────────────────────────────────────────
    # Screen loading
    # ────────────────────────────────────────────────────────────────────────

    def _load_screen(self, index: int):
        self.current_screen_idx = index
        self.screen = self.session.screens[self.current_screen_idx]
        self.active_region_id = None
        self._undo_stack = []
        self.preview_mode = False
        self.preview_btn.config(text="👁️ Preview")

        self.screen_listbox.select_clear(0, tk.END)
        self.screen_listbox.select_set(index)

        self.screen_name_entry.delete(0, tk.END)
        self.screen_name_entry.insert(0, self.screen.content.screen_name)
        self.purpose_text.delete("1.0", tk.END)
        self.purpose_text.insert(tk.END, self.screen.content.purpose)
        self.nav_entry.delete(0, tk.END)
        self.nav_entry.insert(0, self.screen.content.navigation_sentence)

        self._refresh_steps_listbox()
        self._refresh_fields_tree()
        self._refresh_figs_listbox()
        self._refresh_regions_listbox()
        self._load_canvas_image()
        self.status_var.set(
            f"Screen {self.screen.index}: {len([r for r in self.screen.regions if not r.deleted])} regions."
        )

    def _refresh_steps_listbox(self):
        self.steps_listbox.delete(0, tk.END)
        for step in self.screen.content.steps:
            crop_status = "🖼️ " if step.crop_path else "  "
            self.steps_listbox.insert(tk.END, f"{step.n}. {crop_status}{step.text}")

    def _refresh_fields_tree(self):
        for item in self.fields_tree.get_children():
            self.fields_tree.delete(item)
        for f in self.screen.fields:
            self.fields_tree.insert("", tk.END, values=(f.field_name, f.utility, f.sample))

    def _refresh_figs_listbox(self):
        self.figs_listbox.delete(0, tk.END)
        for fig in self.screen.figures:
            self.figs_listbox.insert(tk.END, f"Fig {fig.index}: {fig.path} {fig.caption_note}")

    def _refresh_regions_listbox(self):
        self.regions_listbox.delete(0, tk.END)
        active_idx = None
        for r in self.screen.regions:
            if not r.deleted:
                label = r.label or (r.elements_contained[0] if r.elements_contained else "Unnamed region")
                pin = " 📌" if r.callout_x is not None else ""
                self.regions_listbox.insert(tk.END, f"[{r.role}] {label}{pin} ({r.id})")
                if r.id == self.active_region_id:
                    active_idx = self.regions_listbox.size() - 1
        if active_idx is not None:
            self.regions_listbox.select_set(active_idx)

    # ────────────────────────────────────────────────────────────────────────
    # Saving
    # ────────────────────────────────────────────────────────────────────────

    def _save_active_screen_inputs(self):
        self.screen.content.screen_name = self.screen_name_entry.get().strip()
        self.screen.content.purpose = self.purpose_text.get("1.0", tk.END).strip()
        self.screen.content.navigation_sentence = self.nav_entry.get().strip()
        self.screen.reviewed = True

    def _save_session(self):
        self._save_active_screen_inputs()
        SessionStore.save(self.session, self.session_dir)
        self._write_legacy_json_files()
        render_annotations(self.session_dir, self.screen.index)
        extract_crops(self.session, self.screen, self.session_dir)
        SessionStore.save(self.session, self.session_dir)
        self._refresh_sidebar()
        logger.info(f"Session data saved atomically for {self.session_dir.name}.")
        self.status_var.set("Session saved. ✓")

    def _save_and_close(self):
        self._save_session()
        self.root.destroy()

    def _on_close(self):
        self._save_session()
        self.root.destroy()

    def _write_legacy_json_files(self):
        final_path = self.session_dir / f"screen_{self.screen.index}_final.json"
        regions = []
        for r in self.screen.regions:
            regions.append({
                "id": r.id,
                "role": r.role,
                "bounding_box": r.bounding_box.model_dump(),
                "elements_contained": r.elements_contained,
                "label": r.label,
                "deleted": r.deleted,
                "callout_x": r.callout_x,
                "callout_y": r.callout_y,
            })
        final_path.write_text(json.dumps(regions, indent=2), encoding="utf-8")

    # ────────────────────────────────────────────────────────────────────────
    # Canvas rendering
    # ────────────────────────────────────────────────────────────────────────

    def _load_canvas_image(self):
        img_path = self.session_dir / self.screen.screenshot
        if not img_path.exists():
            img_path = self.session_dir / f"screen_{self.screen.index}.png"
        if not img_path.exists():
            self.canvas.delete(tk.ALL)
            self.canvas.create_text(300, 200, text="No screenshot file found.",
                                    font=("Segoe UI", 12))
            return

        self.pil_image = Image.open(img_path)
        self.orig_w, self.orig_h = self.pil_image.size
        self.canvas.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 850
        canvas_h = self.canvas.winfo_height() or 700
        if self.orig_h / self.orig_w > 1.2:
            fit_zoom = canvas_w / self.orig_w
        else:
            fit_zoom = min(canvas_w / self.orig_w, canvas_h / self.orig_h, 1.0)
        self._zoom_level = max(0.1, min(fit_zoom, 6.0))
        self._zoom_var.set(self._zoom_level)
        self._zoom_label.config(text=f"{int(self._zoom_level * 100)}%")
        self._render_canvas()

    def _render_canvas(self):
        if not hasattr(self, "pil_image") or self.pil_image is None:
            return
        z = self._zoom_level
        new_w = max(1, int(self.orig_w * z))
        new_h = max(1, int(self.orig_h * z))
        resample = Image.Resampling.LANCZOS if z < 1.0 else Image.Resampling.NEAREST
        self.scaled_image = self.pil_image.resize((new_w, new_h), resample)
        master = tk._default_root if tk._default_root is not None else self.root
        self.photo_image = ImageTk.PhotoImage(self.scaled_image, master=master)
        self.canvas.delete(tk.ALL)
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        self.bg_image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        self.canvas.image = self.photo_image
        self._redraw_regions()

    def _callout_anchor(self, r: Region) -> tuple[float, float]:
        """Callout anchor in IMAGE coordinates: manual if set, else auto default."""
        if r.callout_x is not None and r.callout_y is not None:
            return float(r.callout_x), float(r.callout_y)
        bb = r.bounding_box
        # Auto default: centered above the box (mirrors annotator preference)
        ax = bb.x + bb.width / 2
        ay = max(4.0, bb.y - 34.0)
        return ax, ay

    def _redraw_regions(self):
        if self.preview_mode:
            return
        bg_id = getattr(self, "bg_image_id", None)
        for item in list(self.canvas.find_all()):
            if item != bg_id:
                self.canvas.delete(item)

        z = self._zoom_level
        for r in self.screen.regions:
            if r.deleted:
                continue
            bb = r.bounding_box
            x1, y1 = bb.x * z, bb.y * z
            x2, y2 = (bb.x + bb.width) * z, (bb.y + bb.height) * z
            is_active = (r.id == self.active_region_id)
            color = "#3B82F6" if is_active else "#EF4444"
            width = 3 if is_active else 2
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color,
                                         width=width, tags=("box_overlay",))

            # ── E1: callout bubble + leader line ──
            if self.callout_visible.get():
                ax, ay = self._callout_anchor(r)
                cx, cy = ax * z, ay * z
                lbl = (r.label or r.role)[:20]
                # Leader line from bubble to box top-center
                self.canvas.create_line(cx, cy + CALLOUT_H / 2,
                                        (x1 + x2) / 2, y1,
                                        fill=color, width=1, dash=(3, 2),
                                        tags=("callout_overlay",))
                pinned = r.callout_x is not None
                fill = "#FEF3C7" if pinned else "#FFFFFF"
                self.canvas.create_rectangle(cx - CALLOUT_W / 2, cy - CALLOUT_H / 2,
                                             cx + CALLOUT_W / 2, cy + CALLOUT_H / 2,
                                             fill=fill, outline=color, width=1,
                                             tags=("callout_overlay",))
                self.canvas.create_text(cx, cy, text=lbl, fill="#111827",
                                        font=("Segoe UI", 8, "bold"),
                                        tags=("callout_overlay",))

        # ── E2: resize handles on the active region ──
        r = self._get_active_region()
        if r is not None:
            bb = r.bounding_box
            for name, (hx, hy) in self._handle_positions(bb).items():
                sx, sy = hx * z, hy * z
                self.canvas.create_rectangle(sx - HANDLE_PX / 2, sy - HANDLE_PX / 2,
                                             sx + HANDLE_PX / 2, sy + HANDLE_PX / 2,
                                             fill="#3B82F6", outline="white",
                                             tags=("handle_overlay",))

    @staticmethod
    def _handle_positions(bb: BBox) -> dict[str, tuple[float, float]]:
        x1, y1 = bb.x, bb.y
        x2, y2 = bb.x + bb.width, bb.y + bb.height
        xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
        return {"nw": (x1, y1), "n": (xm, y1), "ne": (x2, y1), "e": (x2, ym),
                "se": (x2, y2), "s": (xm, y2), "sw": (x1, y2), "w": (x1, ym)}

    def _get_active_region(self) -> Region | None:
        if not self.active_region_id:
            return None
        r = next((x for x in self.screen.regions if x.id == self.active_region_id), None)
        return r if (r and not r.deleted) else None

    # ────────────────────────────────────────────────────────────────────────
    # Hit testing (image coordinates)
    # ────────────────────────────────────────────────────────────────────────

    def _hit_test(self, ix: float, iy: float) -> tuple[str, Region | None, str | None]:
        """
        Returns (kind, region, handle_name).
        kind ∈ 'handle' | 'callout' | 'region' | 'empty'.
        Priority: handles (active region) > callout bubbles > region boxes.
        """
        z = self._zoom_level
        tol = (HANDLE_PX / 2 + 3) / z

        active = self._get_active_region()
        if active is not None:
            for name, (hx, hy) in self._handle_positions(active.bounding_box).items():
                if abs(ix - hx) <= tol and abs(iy - hy) <= tol:
                    return "handle", active, name

        if self.callout_visible.get():
            half_w = (CALLOUT_W / 2) / z
            half_h = (CALLOUT_H / 2) / z
            for r in reversed(self.screen.regions):
                if r.deleted:
                    continue
                ax, ay = self._callout_anchor(r)
                if abs(ix - ax) <= half_w and abs(iy - ay) <= half_h:
                    return "callout", r, None

        for r in reversed(self.screen.regions):
            if r.deleted:
                continue
            bb = r.bounding_box
            if bb.x <= ix <= bb.x + bb.width and bb.y <= iy <= bb.y + bb.height:
                return "region", r, None

        return "empty", None, None

    # ────────────────────────────────────────────────────────────────────────
    # Unified mouse state machine (E1 + E2)
    # ────────────────────────────────────────────────────────────────────────

    def _event_to_image(self, event) -> tuple[float, float]:
        z = self._zoom_level
        return self.canvas.canvasx(event.x) / z, self.canvas.canvasy(event.y) / z

    def _on_canvas_press(self, event):
        if self.preview_mode:
            return
        ix, iy = self._event_to_image(event)
        kind, region, handle = self._hit_test(ix, iy)
        self._drag_last = (ix, iy)
        self._drag_dirty = False

        if kind == "handle":
            self._drag_mode = "resize"
            self._drag_region = region
            self._drag_handle = handle
        elif kind == "callout":
            self._drag_mode = "callout"
            self._drag_region = region
            # Select the region whose callout is grabbed
            self.active_region_id = region.id
            self._load_region_inputs(region)
            self._refresh_regions_listbox()
            self._redraw_regions()
        elif kind == "region":
            self._drag_mode = "move"
            self._drag_region = region
            if self.active_region_id != region.id:
                self.active_region_id = region.id
                self._load_region_inputs(region)
                self._refresh_regions_listbox()
                self._redraw_regions()
        else:
            # Empty area → start drawing a new region
            self._drag_mode = "draw"
            cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.draw_start_x, self.draw_start_y = cx, cy
            self.draw_rect_id = self.canvas.create_rectangle(
                cx, cy, cx, cy, outline="#F59E0B", width=2)

    def _on_canvas_drag(self, event):
        if self.preview_mode or self._drag_mode is None:
            return
        ix, iy = self._event_to_image(event)

        if self._drag_mode == "draw":
            cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.canvas.coords(self.draw_rect_id, self.draw_start_x,
                               self.draw_start_y, cx, cy)
            return

        if self._drag_region is None or self._drag_last is None:
            return
        dx, dy = ix - self._drag_last[0], iy - self._drag_last[1]
        if not self._drag_dirty:
            self._push_undo()          # one undo entry per drag gesture
            self._drag_dirty = True

        bb = self._drag_region.bounding_box

        if self._drag_mode == "move":
            bb.x = max(0.0, bb.x + dx)
            bb.y = max(0.0, bb.y + dy)
            # A pinned callout follows the box while moving
            if self._drag_region.callout_x is not None:
                self._drag_region.callout_x += dx
                self._drag_region.callout_y += dy

        elif self._drag_mode == "resize":
            h = self._drag_handle or ""
            if "w" in h:
                new_x = min(bb.x + dx, bb.x + bb.width - 8)
                bb.width = bb.width - (new_x - bb.x)
                bb.x = new_x
            if "e" in h:
                bb.width = max(8.0, bb.width + dx)
            if "n" in h:
                new_y = min(bb.y + dy, bb.y + bb.height - 8)
                bb.height = bb.height - (new_y - bb.y)
                bb.y = new_y
            if "s" in h:
                bb.height = max(8.0, bb.height + dy)

        elif self._drag_mode == "callout":
            ax, ay = self._callout_anchor(self._drag_region)
            self._drag_region.callout_x = max(0.0, min(float(self.orig_w), ax + dx))
            self._drag_region.callout_y = max(0.0, min(float(self.orig_h), ay + dy))

        self._drag_last = (ix, iy)
        self._redraw_regions()
        self.status_var.set(
            f"{self._drag_mode}: x={int(bb.x)} y={int(bb.y)} "
            f"w={int(bb.width)} h={int(bb.height)}"
        )

    def _on_canvas_release(self, event):
        if self.preview_mode:
            return
        mode = self._drag_mode
        self._drag_mode = None
        self._drag_handle = None
        self._drag_last = None

        if mode == "draw":
            cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.canvas.delete(self.draw_rect_id)
            z = self._zoom_level
            x1 = min(self.draw_start_x, cx) / z
            y1 = min(self.draw_start_y, cy) / z
            w = abs(self.draw_start_x - cx) / z
            h = abs(self.draw_start_y - cy) / z
            if w < 10 or h < 10:
                return
            self._push_undo()
            dialog = _RegionAddDialog(self.root)
            if not dialog.result:
                self._undo_stack.pop()   # drawing cancelled → discard undo entry
                return
            new_rid = f"r{len(self.screen.regions) + 1}"
            self.screen.regions.append(Region(
                id=new_rid, role=dialog.result["role"],
                bounding_box=BBox(x=x1, y=y1, width=w, height=h),
                elements_contained=[dialog.result["label"]],
                label=dialog.result["label"]))
            self.active_region_id = new_rid
            self._redraw_regions()
            self._refresh_regions_listbox()
        elif mode in ("move", "resize", "callout") and self._drag_dirty:
            self._refresh_regions_listbox()

        self._drag_region = None
        self._drag_dirty = False

    def _on_canvas_hover(self, event):
        """Cursor feedback + live coordinates in the status bar (E3)."""
        if self.preview_mode or self._drag_mode is not None:
            return
        ix, iy = self._event_to_image(event)
        kind, region, handle = self._hit_test(ix, iy)
        cursors = {
            "nw": "top_left_corner", "se": "bottom_right_corner",
            "ne": "top_right_corner", "sw": "bottom_left_corner",
            "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
            "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
        }
        if kind == "handle":
            self.canvas.config(cursor=cursors.get(handle, "sizing"))
        elif kind == "callout":
            self.canvas.config(cursor="hand2")
        elif kind == "region":
            self.canvas.config(cursor="fleur")
        else:
            self.canvas.config(cursor="cross")
        self.status_var.set(f"x={int(ix)}  y={int(iy)}"
                            + (f"  |  {region.label or region.role} ({region.id})"
                               if region else ""))

    # ── Right-click: context menu on hit, pan on empty (E3) ────────────────

    def _on_right_press(self, event):
        if self.preview_mode:
            self._pan_last = (event.x, event.y)
            return
        ix, iy = self._event_to_image(event)
        kind, region, _ = self._hit_test(ix, iy)
        if kind in ("region", "callout", "handle") and region is not None:
            self.active_region_id = region.id
            self._load_region_inputs(region)
            self._refresh_regions_listbox()
            self._redraw_regions()
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label=f"Edit '{region.label or region.role}'…",
                             command=lambda: self.open_region_edit_dialog(region))
            menu.add_command(label="Reset callout to auto",
                             command=self._reset_active_callout)
            menu.add_separator()
            menu.add_command(label="Delete region",
                             command=self._delete_active_region)
            menu.tk_popup(event.x_root, event.y_root)
        else:
            self._pan_last = (event.x, event.y)
            self.canvas.config(cursor="fleur")

    def _pan_move(self, event):
        if self._pan_last:
            dx = self._pan_last[0] - event.x
            dy = self._pan_last[1] - event.y
            self.canvas.xview_scroll(int(dx / 8), "units")
            self.canvas.yview_scroll(int(dy / 8), "units")
            self._pan_last = (event.x, event.y)

    # ── Keyboard editing (E3) ───────────────────────────────────────────────

    def _arrow_nudge(self, attr: str, delta: int, resize: bool):
        # Do not steal arrow keys while typing in an entry/text widget
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry)):
            return
        r = self._get_active_region()
        if r is None:
            return
        self._push_undo()
        bb = r.bounding_box
        if not resize:
            if attr == "x":
                bb.x = max(0.0, bb.x + delta)
            else:
                bb.y = max(0.0, bb.y + delta)
        else:
            if attr == "w":
                bb.width = max(8.0, bb.width + delta)
            else:
                bb.height = max(8.0, bb.height + delta)
        self._redraw_regions()

    def _deselect(self):
        self.active_region_id = None
        self._redraw_regions()
        self._refresh_regions_listbox()

    def _reset_active_callout(self):
        r = self._get_active_region()
        if r is None:
            messagebox.showwarning("Warning", "Select a region first.")
            return
        self._push_undo()
        r.callout_x = None
        r.callout_y = None
        self._redraw_regions()
        self._refresh_regions_listbox()
        self.status_var.set(f"Callout for {r.id} reset to automatic placement.")

    # ────────────────────────────────────────────────────────────────────────
    # Zoom / scroll
    # ────────────────────────────────────────────────────────────────────────

    def _on_zoom_slider(self, value):
        self._zoom_level = max(0.1, min(float(value), 6.0))
        self._zoom_label.config(text=f"{int(self._zoom_level * 100)}%")
        self._render_canvas()

    def _zoom_fit(self):
        if not hasattr(self, "orig_w") or not self.orig_w:
            return
        self.canvas.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 850
        canvas_h = self.canvas.winfo_height() or 700
        if self.orig_h / self.orig_w > 1.2:
            fit_zoom = canvas_w / self.orig_w
        else:
            fit_zoom = min(canvas_w / self.orig_w, canvas_h / self.orig_h, 1.0)
        self._zoom_level = max(0.1, min(fit_zoom, 6.0))
        self._zoom_var.set(self._zoom_level)
        self._zoom_label.config(text=f"{int(self._zoom_level * 100)}%")
        self._render_canvas()

    def _zoom_100(self):
        self._zoom_level = 1.0
        self._zoom_var.set(1.0)
        self._zoom_label.config(text="100%")
        self._render_canvas()

    def _zoom_200(self):
        self._zoom_level = 2.0
        self._zoom_var.set(2.0)
        self._zoom_label.config(text="200%")
        self._render_canvas()

    def _on_ctrl_scroll(self, event):
        if event.delta > 0:
            self._zoom_level = min(6.0, self._zoom_level * 1.15)
        else:
            self._zoom_level = max(0.1, self._zoom_level / 1.15)
        self._zoom_var.set(self._zoom_level)
        self._zoom_label.config(text=f"{int(self._zoom_level * 100)}%")
        self._render_canvas()

    def _on_plain_scroll(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    # ────────────────────────────────────────────────────────────────────────
    # Undo / delete
    # ────────────────────────────────────────────────────────────────────────

    def _on_delete_key(self, event):
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry)):
            return
        self._delete_active_region()

    def _on_undo(self, event):
        if self._undo_stack:
            self.screen.regions = self._undo_stack.pop()
            self.active_region_id = None
            self._redraw_regions()
            self._refresh_regions_listbox()
            self.status_var.set("Undo. ↩")

    def _push_undo(self):
        curr = [Region(**r.model_dump()) for r in self.screen.regions]
        self._undo_stack.append(curr)
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)

    # ────────────────────────────────────────────────────────────────────────
    # Fields / steps
    # ────────────────────────────────────────────────────────────────────────

    def _on_field_edit_dialog(self, event):
        sel = self.fields_tree.selection()
        if not sel:
            return
        item_idx = self.fields_tree.index(sel[0])
        field = self.screen.fields[item_idx]
        dialog = _FieldEditDialog(self.root, field)
        if dialog.result:
            field.field_name = dialog.result["name"]
            field.utility = dialog.result["utility"]
            field.sample = dialog.result["sample"]
            self._refresh_fields_tree()

    def _on_step_selected(self, event):
        sel = self.steps_listbox.curselection()
        if sel:
            self.selected_step_idx = sel[0]

    def _add_step(self):
        txt = simpledialog.askstring("Add Step", "Enter step instruction text:")
        if txt:
            n = len(self.screen.content.steps) + 1
            self.screen.content.steps.append(Step(n=n, text=txt, kind="action"))
            self._refresh_steps_listbox()

    def _edit_step(self):
        """Edit selected step text in place (E3)."""
        if self.selected_step_idx is None:
            messagebox.showwarning("Warning", "Select a step first.")
            return
        step = self.screen.content.steps[self.selected_step_idx]
        txt = simpledialog.askstring("Edit Step", "Step instruction text:",
                                     initialvalue=step.text)
        if txt:
            step.text = txt.strip()
            self._refresh_steps_listbox()
            self.steps_listbox.select_set(self.selected_step_idx)

    def _delete_step(self):
        if self.selected_step_idx is not None:
            self.screen.content.steps.pop(self.selected_step_idx)
            for idx, s in enumerate(self.screen.content.steps):
                s.n = idx + 1
            self._refresh_steps_listbox()
            self.selected_step_idx = None

    def _move_step(self, direction: int):
        if self.selected_step_idx is None:
            return
        idx = self.selected_step_idx
        target = idx + direction
        if 0 <= target < len(self.screen.content.steps):
            steps = self.screen.content.steps
            steps[idx], steps[target] = steps[target], steps[idx]
            steps[idx].n = idx + 1
            steps[target].n = target + 1
            self._refresh_steps_listbox()
            self.steps_listbox.select_set(target)
            self.selected_step_idx = target

    # ────────────────────────────────────────────────────────────────────────
    # Region list panel
    # ────────────────────────────────────────────────────────────────────────

    def _on_region_selected_from_tab(self, event):
        sel = self.regions_listbox.curselection()
        if not sel:
            return
        active_regions = [r for r in self.screen.regions if not r.deleted]
        if sel[0] < len(active_regions):
            r = active_regions[sel[0]]
            self.active_region_id = r.id
            self._load_region_inputs(r)
            self._redraw_regions()

    def _load_region_inputs(self, r: Region):
        self.region_label_entry.delete(0, tk.END)
        self.region_label_entry.insert(0, r.label)

    def _on_region_label_changed(self, event):
        r = self._get_active_region()
        if r is not None:
            r.label = self.region_label_entry.get().strip()
            self._redraw_regions()

    def _delete_active_region(self):
        r = self._get_active_region()
        if r is not None:
            self._push_undo()
            r.deleted = True
            self.active_region_id = None
            self._redraw_regions()
            self._refresh_regions_listbox()

    def on_region_double_click(self, event):
        sel = self.regions_listbox.curselection()
        if not sel:
            return
        selected_text = self.regions_listbox.get(sel[0])
        import re
        m = re.search(r"\((r\d+)\)$", selected_text)
        if m:
            rid = m.group(1)
            region = next((x for x in self.screen.regions if x.id == rid), None)
            if region:
                self.open_region_edit_dialog(region)

    def on_canvas_double_click(self, event):
        if self.preview_mode:
            return
        ix, iy = self._event_to_image(event)
        kind, region, _ = self._hit_test(ix, iy)
        if kind in ("region", "callout") and region is not None:
            self.open_region_edit_dialog(region)

    def open_region_edit_dialog(self, r: Region):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Region Details")
        dialog.geometry("440x400")
        dialog.grab_set()
        dialog.transient(self.root)

        pad = dict(padx=14, pady=7, sticky=tk.W)
        ttk.Label(dialog, text="Label:", font=("Segoe UI", 10)).grid(row=0, column=0, **pad)
        entry_label = ttk.Entry(dialog, width=32, font=("Segoe UI", 10))
        entry_label.insert(0, r.label)
        entry_label.grid(row=0, column=1, **pad)
        entry_label.focus_set()

        ttk.Label(dialog, text="Role:", font=("Segoe UI", 10)).grid(row=1, column=0, **pad)
        combo_role = ttk.Combobox(dialog, state="readonly", font=("Segoe UI", 10), width=22,
                                  values=["action_button", "filter_form", "action_column",
                                          "table_header", "navigation_bar", "page_header",
                                          "section_heading", "view_only"])
        combo_role.set(r.role)
        combo_role.grid(row=1, column=1, **pad)

        coords = {}
        for row, (label, val) in enumerate([("X:", r.bounding_box.x),
                                            ("Y:", r.bounding_box.y),
                                            ("Width:", r.bounding_box.width),
                                            ("Height:", r.bounding_box.height)], start=2):
            ttk.Label(dialog, text=label).grid(row=row, column=0, **pad)
            e = ttk.Entry(dialog, width=15)
            e.insert(0, str(int(val)))
            e.grid(row=row, column=1, **pad)
            coords[label] = e

        def save_values():
            try:
                x_val = int(coords["X:"].get())
                y_val = int(coords["Y:"].get())
                w_val = int(coords["Width:"].get())
                h_val = int(coords["Height:"].get())
            except ValueError:
                messagebox.showerror("Error", "Coordinates must be integers.", parent=dialog)
                return
            label_val = entry_label.get().strip()
            if not label_val:
                messagebox.showerror("Error", "Label cannot be blank.", parent=dialog)
                return
            self._push_undo()
            r.label = label_val
            r.role = combo_role.get()
            r.bounding_box.x = x_val
            r.bounding_box.y = y_val
            r.bounding_box.width = w_val
            r.bounding_box.height = h_val
            self._redraw_regions()
            self._refresh_regions_listbox()
            self._load_region_inputs(r)
            dialog.destroy()

        ttk.Button(dialog, text="Save Region", style="Accent.TButton",
                   command=save_values).grid(row=6, column=0, columnspan=2, pady=14)

    # ────────────────────────────────────────────────────────────────────────
    # Figures
    # ────────────────────────────────────────────────────────────────────────

    def _toggle_figure_mode(self):
        sel = self.figs_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Please select a figure attachment first.")
            return
        fig = self.screen.figures[sel[0]]
        old_path = fig.path
        if fig.source == "viewport" and "_viewport" in old_path:
            candidate = old_path.replace("_viewport.png", "_full.png")
            new_source = "full_page"
        elif fig.source == "full_page" and "_full" in old_path:
            candidate = old_path.replace("_full.png", "_viewport.png")
            new_source = "viewport"
        else:
            messagebox.showwarning("Warning", "This figure has no counterpart image.")
            return
        # Only toggle if the counterpart file actually exists
        if not (self.session_dir / candidate).exists():
            messagebox.showwarning(
                "Warning",
                f"Counterpart image not found:\n{candidate}\n"
                f"(Capture in 'both' mode to have both variants.)")
            return
        fig.path = candidate
        fig.source = new_source
        self._refresh_figs_listbox()

    def _remove_figure(self):
        sel = self.figs_listbox.curselection()
        if not sel:
            return
        self.screen.figures.pop(sel[0])
        for i, fig in enumerate(self.screen.figures):
            fig.index = i + 1
        self._refresh_figs_listbox()

    # ────────────────────────────────────────────────────────────────────────
    # AI regeneration
    # ────────────────────────────────────────────────────────────────────────

    def _regenerate_screen(self):
        self._save_active_screen_inputs()
        cfg = get_config()
        from main import get_provider_instance
        provider = get_provider_instance(cfg)

        logger.info(f"AI regeneration triggered for Screen {self.screen.index}...")
        self.root.config(cursor="watch")
        self.status_var.set("AI is regenerating screen... Please wait.")
        
        def run_regen():
            try:
                gen = Generator(provider)
                from docbot.clients.profile import ClientProfile
                profile = ClientProfile.load(cfg.current_client)
                self.screen.content.content_hash = ""
                gen.generate_screen(self.session, self.screen, client_profile=profile.data)
                
                def success():
                    self._load_screen(self.current_screen_idx)
                    self.status_var.set("Documentation regenerated. ✓")
                    self.root.config(cursor="")
                self.root.after(0, success)
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                def fail(err=e):
                    messagebox.showerror("Error", f"AI generation failed: {err}")
                    self.status_var.set("Generation failed. ✗")
                    self.root.config(cursor="")
                self.root.after(0, fail)

        import threading
        threading.Thread(target=run_regen, daemon=True).start()

    def _regen_steps(self):
        custom = simpledialog.askstring("Custom Instructions",
                                        "Enter guide notes for steps (optional):")
        cfg = get_config()
        from main import get_provider_instance
        provider = get_provider_instance(cfg)
        prompt = (
            f"Here are the current steps:\n"
            f"{[s.text for s in self.screen.content.steps]}\n\n"
            f"Modify and polish these steps using this instruction: "
            f"{custom or 'Make steps clean'}.\n"
            f"Return ONLY a JSON array of strings containing the step texts. No other text."
        )
        self.root.config(cursor="watch")
        self.status_var.set("AI is regenerating steps...")
        
        def run_steps_regen():
            try:
                raw = provider.chat(prompt)
                from providers.base import _strip_fences
                steps_arr = json.loads(_strip_fences(raw))
                if isinstance(steps_arr, list):
                    def success(arr=steps_arr):
                        self.screen.content.steps = [
                            Step(n=i + 1, text=str(txt), kind="action")
                            for i, txt in enumerate(arr)
                        ]
                        self._refresh_steps_listbox()
                        self.status_var.set("Steps regenerated. ✓")
                        self.root.config(cursor="")
                    self.root.after(0, success)
            except Exception as e:
                def fail(err=e):
                    messagebox.showerror("Error", f"Could not regenerate steps: {err}")
                    self.status_var.set("Steps regeneration failed. ✗")
                    self.root.config(cursor="")
                self.root.after(0, fail)

        import threading
        threading.Thread(target=run_steps_regen, daemon=True).start()

    def _compile_module(self):
        self._save_active_screen_inputs()
        SessionStore.save(self.session, self.session_dir)
        from assemble import assemble_module
        try:
            output_docx = assemble_module(self.session_dir)
            doc_name = output_docx.name
            messagebox.showinfo("Success",
                                f"Draft module compiled inside {self.session_dir.name} "
                                f"and saved to Final_Manuals as {doc_name}!")
        except Exception as e:
            messagebox.showerror("Error", f"Assembly failed: {e}")

    # ────────────────────────────────────────────────────────────────────────
    # Preview
    # ────────────────────────────────────────────────────────────────────────

    def _toggle_preview(self):
        if not self.preview_mode:
            self._save_active_screen_inputs()
            self._write_legacy_json_files()
            # Save session so annotate reads the LATEST callout positions
            SessionStore.save(self.session, self.session_dir)
            cfg = get_config()
            from docbot.clients.profile import ClientProfile
            profile = ClientProfile.load(cfg.current_client)
            self.root.config(cursor="watch")
            self.root.update()
            try:
                render_annotations(self.session_dir, self.screen.index,
                                   client_profile=profile.data)
            except Exception as ex:
                messagebox.showerror("Error", f"Could not render preview annotations: {ex}")
                self.root.config(cursor="")
                return
            self.root.config(cursor="")
            annotated_path = self.session_dir / f"screen_{self.screen.index}_annotated.png"
            if annotated_path.exists():
                self.preview_mode = True
                self.preview_btn.config(text="✏️ Edit Mode")
                self.pil_image = Image.open(annotated_path)
                self.orig_w, self.orig_h = self.pil_image.size
                self._render_canvas()
                self.status_var.set("Preview mode — this is how the figure will "
                                    "appear in the manual.")
            else:
                messagebox.showerror("Error", "Could not load annotated preview image.")
        else:
            self.preview_mode = False
            self.preview_btn.config(text="👁️ Preview")
            img_path = self.session_dir / self.screen.screenshot
            if not img_path.exists():
                img_path = self.session_dir / f"screen_{self.screen.index}.png"
            if img_path.exists():
                self.pil_image = Image.open(img_path)
                self.orig_w, self.orig_h = self.pil_image.size
            self._render_canvas()
            self.status_var.set("Edit mode.")


# ── Custom Modal Dialogs ────────────────────────────────────────────────────

class _RegionAddDialog:
    """Single modal dialog to pick semantic role and enter label name together."""
    def __init__(self, parent):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Add Region Details")
        self.dialog.geometry("380x220")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()

        pad = dict(padx=15, pady=8, sticky=tk.W)
        ttk.Label(self.dialog, text="Region Label:", font=("Segoe UI", 10)).grid(row=0, column=0, **pad)
        self.label_entry = ttk.Entry(self.dialog, width=28, font=("Segoe UI", 10))
        self.label_entry.grid(row=0, column=1, **pad)
        self.label_entry.focus_set()

        ttk.Label(self.dialog, text="Semantic Role:", font=("Segoe UI", 10)).grid(row=1, column=0, **pad)
        self.role_var = tk.StringVar(value="filter_form")
        roles = ["filter_form", "action_button", "action_group", "action_column",
                 "table_header", "view_only", "page_header", "navigation_bar",
                 "section_heading"]
        self.combo = ttk.Combobox(self.dialog, textvariable=self.role_var, values=roles,
                                  state="readonly", font=("Segoe UI", 10), width=26)
        self.combo.grid(row=1, column=1, **pad)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Add Region", style="Accent.TButton",
                   command=self._on_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        self.dialog.bind("<Return>", lambda e: self._on_save())
        self.dialog.transient(parent)
        self.dialog.wait_window(self.dialog)

    def _on_save(self):
        lbl = self.label_entry.get().strip()
        role = self.role_var.get()
        if not lbl:
            lbl = f"{role.replace('_', ' ').title()}"
        self.result = {"role": role, "label": lbl}
        self.dialog.destroy()


class _FieldEditDialog:
    """Modal to edit descriptions of a grid field."""
    def __init__(self, parent, field: FieldDetail):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Edit Field Descriptions")
        self.dialog.geometry("450x320")
        self.dialog.grab_set()

        ttk.Label(self.dialog, text="Field Display Name:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
        self.name_entry = ttk.Entry(self.dialog, width=40)
        self.name_entry.insert(0, field.field_name)
        self.name_entry.grid(row=0, column=1, sticky=tk.W, padx=10, pady=10)

        ttk.Label(self.dialog, text="Utility / Purpose:").grid(row=1, column=0, sticky=tk.NW, padx=10, pady=10)
        self.utility_text = tk.Text(self.dialog, height=4, width=30, font=("Segoe UI", 9))
        self.utility_text.insert(tk.END, field.utility)
        self.utility_text.grid(row=1, column=1, sticky=tk.W, padx=10, pady=10)

        ttk.Label(self.dialog, text="Sample Value:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=10)
        self.sample_entry = ttk.Entry(self.dialog, width=40)
        self.sample_entry.insert(0, field.sample)
        self.sample_entry.grid(row=2, column=1, sticky=tk.W, padx=10, pady=10)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Apply Changes", command=self._apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        self.dialog.transient(parent)
        parent.wait_window(self.dialog)

    def _apply(self):
        self.result = {
            "name": self.name_entry.get().strip(),
            "utility": self.utility_text.get("1.0", tk.END).strip(),
            "sample": self.sample_entry.get().strip()
        }
        self.dialog.destroy()


def open_review_ui(session_dir: Path, screen_index: int, total_screens: int = None) -> str:
    """Wrapper entry point loaded by main.py."""
    if tk._default_root is not None:
        window = tk.Toplevel(tk._default_root)
        app = ReviewSessionUI(window, session_dir, initial_idx=screen_index)
        tk._default_root.wait_window(window)
    else:
        root = tk.Tk()
        app = ReviewSessionUI(root, session_dir, initial_idx=screen_index)
        root.mainloop()
    return "next"