"""
DocBot v3 — Visual Review UI (Phase 7).

A professional, document-level editor that manages the entire session.json.
Allows direct screenshot manipulation (adding/modifying regions), content polishing,
step reordering, field editing, figure management, and single-click regeneration.
"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk, ImageDraw
from loguru import logger

from config import get_config
from docbot.models import SessionStore, SessionModel, Screen, Region, FieldDetail, Step, Figure, BBox
from docbot.processing.generator import Generator
from docbot.processing.annotate import render_annotations
from docbot.processing.crops import extract_crops


class ReviewSessionUI:
    """The document-level session review UI."""

    def __init__(self, root: tk.Tk, session_dir: Path, initial_idx: int = 1):
        self.root = root
        self.session_dir = session_dir
        self.root.title("DocBot v3 — Master Session Review")
        self.root.geometry("1480x950")
        self.root.state("zoomed")

        # Load session model
        self.session = SessionStore.load(self.session_dir)
        if not self.session.screens:
            raise ValueError(f"No screens found in session {session_dir.name}")

        self.current_screen_idx = 0
        for i, s in enumerate(self.session.screens):
            if s.index == initial_idx:
                self.current_screen_idx = i
                break

        # Active state variables
        self.active_region_id: str | None = None
        self.selected_step_idx: int | None = None
        self.selected_field_idx: int | None = None
        
        # Undo stack for drawing
        self._undo_stack: list[list[Region]] = []

        # Setup standard styles
        self._setup_style()

        # Build UI layout
        self._build_layout()

        # Load the initial screen
        self._load_screen(self.current_screen_idx)

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # Color definitions
        bg_dark = "#1E293B"
        bg_light = "#F8FAFC"
        accent_blue = "#3B82F6"
        
        style.configure("TFrame", background=bg_light)
        style.configure("Top.TFrame", background=bg_dark)
        style.configure("Sidebar.TFrame", background="#F1F5F9")
        
        style.configure("TLabel", background=bg_light, font=("Segoe UI", 10))
        style.configure("Top.TLabel", background=bg_dark, foreground="white", font=("Segoe UI", 11, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), foreground="white", background=accent_blue)
        
        style.configure("TNotebook", background=bg_light)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10))

    def _build_layout(self):
        # 1. Top status / control bar
        top_bar = ttk.Frame(self.root, style="Top.TFrame", padding=10)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(top_bar, text="DocBot v3 — Interactive Review", style="Top.TLabel").pack(side=tk.LEFT, padx=10)

        # Global actions
        ttk.Button(top_bar, text="Save Session (Ctrl+S)", command=self._save_session).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_bar, text="Compile Module", command=self._compile_module).pack(side=tk.RIGHT, padx=5)

        # 2. Main horizontal paned window
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel: Sidebar list of screens
        sidebar = ttk.Frame(main_paned, style="Sidebar.TFrame", width=220)
        main_paned.add(sidebar, weight=0)

        ttk.Label(sidebar, text="Screens in Session", style="Header.TLabel", background="#F1F5F9").pack(anchor=tk.W, padx=10, pady=10)

        self.screen_listbox = tk.Listbox(sidebar, font=("Segoe UI", 10), selectbackground="#3B82F6", bd=0, highlightthickness=0)
        self.screen_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.screen_listbox.bind("<<ListboxSelect>>", self._on_screen_selected_from_list)

        # Populate sidebar
        self._refresh_sidebar()

        # Middle panel: Canvas area (image viewing & markup)
        canvas_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(canvas_frame, weight=3)

        ttk.Label(canvas_frame, text="Annotated Screenshot Editor (Drag to draw, click to edit)", font=("Segoe UI", 10, "italic")).pack(anchor=tk.W, pady=2)

        # Canvas container with scrollbars
        canvas_container = ttk.Frame(canvas_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_container, bg="#CBD5E1", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # Canvas drag bindings
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)  # role picker
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<Control-z>", self._on_undo)
        self.root.bind("<Control-s>", lambda e: self._save_session())

        # Right panel: Form inputs / notebook
        right_frame = ttk.Frame(main_paned, width=580)
        main_paned.add(right_frame, weight=2)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Content Editor
        tab_content = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_content, text="Screen Documentation")

        self._build_content_tab(tab_content)

        # Tab 2: Region List & Details
        tab_regions = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_regions, text="Region Structure")

        self._build_regions_tab(tab_regions)

    def _build_content_tab(self, parent: ttk.Frame):
        # Notebook inside Tab 1 to organize steps, fields, and figures
        sub_notebook = ttk.Notebook(parent)
        sub_notebook.pack(fill=tk.BOTH, expand=True)

        # Sub-tab A: Basic Metadata
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

        # Regen block
        regen_frame = ttk.LabelFrame(sub_meta, text="AI Assistance Options", padding=10)
        regen_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=20)

        ttk.Button(regen_frame, text="Regenerate All Content", command=self._regenerate_screen).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(regen_frame, text="Regenerate Steps Only", command=self._regen_steps).grid(row=0, column=1, padx=5, pady=5)

        # Sub-tab B: Steps Editor
        sub_steps = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_steps, text="User Steps")

        steps_ctrl = ttk.Frame(sub_steps)
        steps_ctrl.pack(fill=tk.X, side=tk.TOP, pady=5)
        ttk.Button(steps_ctrl, text="Add Step", command=self._add_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Delete Step", command=self._delete_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Move Up", command=lambda: self._move_step(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(steps_ctrl, text="Move Down", command=lambda: self._move_step(1)).pack(side=tk.LEFT, padx=2)

        self.steps_listbox = tk.Listbox(sub_steps, font=("Segoe UI", 9), selectbackground="#3B82F6")
        self.steps_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.steps_listbox.bind("<<ListboxSelect>>", self._on_step_selected)

        # Sub-tab C: Field Grid
        sub_fields = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_fields, text="Field Reference Table")

        # Treeview to display fields
        self.fields_tree = ttk.Treeview(sub_fields, columns=("name", "utility", "sample"), show="headings")
        self.fields_tree.heading("name", text="Field Name")
        self.fields_tree.heading("utility", text="Utility / Description")
        self.fields_tree.heading("sample", text="Sample Value")
        self.fields_tree.column("name", width=120)
        self.fields_tree.column("utility", width=250)
        self.fields_tree.column("sample", width=80)
        self.fields_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.fields_tree.bind("<Double-1>", self._on_field_edit_dialog)

        # Sub-tab D: Figures & screenshots list
        sub_figs = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(sub_figs, text="Figure Attachments")

        figs_ctrl = ttk.Frame(sub_figs)
        figs_ctrl.pack(fill=tk.X, side=tk.TOP, pady=2)
        ttk.Button(figs_ctrl, text="Toggle full_page vs viewport", command=self._toggle_figure_mode).pack(side=tk.LEFT, padx=2)
        ttk.Button(figs_ctrl, text="Remove Attachment", command=self._remove_figure).pack(side=tk.LEFT, padx=2)

        self.figs_listbox = tk.Listbox(sub_figs, font=("Segoe UI", 9))
        self.figs_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

    def _build_regions_tab(self, parent: ttk.Frame):
        ttk.Label(parent, text="Detected Page Regions list:", style="Header.TLabel").pack(anchor=tk.W, pady=5)
        
        self.regions_listbox = tk.Listbox(parent, font=("Segoe UI", 9), selectbackground="#3B82F6")
        self.regions_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.regions_listbox.bind("<<ListboxSelect>>", self._on_region_selected_from_tab)

        region_edit_frame = ttk.Frame(parent)
        region_edit_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)
        
        ttk.Label(region_edit_frame, text="Region Label:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.region_label_entry = ttk.Entry(region_edit_frame, width=40)
        self.region_label_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        self.region_label_entry.bind("<KeyRelease>", self._on_region_label_changed)

        ttk.Button(region_edit_frame, text="Delete Region", command=self._delete_active_region).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=8)


    # ── Sidebar & Navigation ──────────────────────────────────────────────────

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
        # Save current screen state first
        self._save_active_screen_inputs()
        self._load_screen(sel[0])

    # ── Screen Loading ────────────────────────────────────────────────────────

    def _load_screen(self, index: int):
        self.current_screen_idx = index
        self.screen = self.session.screens[self.current_screen_idx]
        self.active_region_id = None
        self._undo_stack = []

        # Update Listbox selection
        self.screen_listbox.select_clear(0, tk.END)
        self.screen_listbox.select_set(index)

        # Update Metadata Tab Inputs
        self.screen_name_entry.delete(0, tk.END)
        self.screen_name_entry.insert(0, self.screen.content.screen_name)

        self.purpose_text.delete("1.0", tk.END)
        self.purpose_text.insert(tk.END, self.screen.content.purpose)

        self.nav_entry.delete(0, tk.END)
        self.nav_entry.insert(0, self.screen.content.navigation_sentence)

        # Update Steps
        self._refresh_steps_listbox()

        # Update Fields
        self._refresh_fields_tree()

        # Update Figures
        self._refresh_figs_listbox()

        # Update Regions List
        self._refresh_regions_listbox()

        # Load Screenshot image on Canvas
        self._load_canvas_image()

    def _refresh_steps_listbox(self):
        self.steps_listbox.delete(0, tk.END)
        for step in self.screen.content.steps:
            crop_status = "🖼️ " if step.crop_path else "  "
            self.steps_listbox.insert(tk.END, f"{step.n}. {crop_status}{step.text}")

    def _refresh_fields_tree(self):
        # Clear existing
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
                label = r.label or r.elements_contained[0] if r.elements_contained else "Unnamed region"
                self.regions_listbox.insert(tk.END, f"[{r.role}] {label} ({r.id})")
                if r.id == self.active_region_id:
                    active_idx = self.regions_listbox.size() - 1
        if active_idx is not None:
            self.regions_listbox.select_set(active_idx)


    # ── Save States ──────────────────────────────────────────────────────────

    def _save_active_screen_inputs(self):
        """Read UI inputs and save them back into self.screen in-memory model."""
        self.screen.content.screen_name = self.screen_name_entry.get().strip()
        self.screen.content.purpose = self.purpose_text.get("1.0", tk.END).strip()
        self.screen.content.navigation_sentence = self.nav_entry.get().strip()
        self.screen.reviewed = True

    def _save_session(self):
        self._save_active_screen_inputs()
        SessionStore.save(self.session, self.session_dir)
        
        # Also render legacy format final.json files for older compatibility
        self._write_legacy_json_files()
        
        # Render updated annotations for the current screen
        render_annotations(self.session_dir, self.screen.index)
        
        # Extract small inline crops
        extract_crops(self.session, self.screen, self.session_dir)
        
        # Re-save to capture any extracted crop paths
        SessionStore.save(self.session, self.session_dir)

        self._refresh_sidebar()
        logger.info(f"Session data saved atomically for {self.session_dir.name}.")
        messagebox.showinfo("Saved", "Session files saved successfully!")

    def _write_legacy_json_files(self):
        """Write out legacy flat screen_N_final.json regions file for old manual_builder compatibility."""
        final_path = self.session_dir / f"screen_{self.screen.index}_final.json"
        regions = []
        for r in self.screen.regions:
            regions.append({
                "id": r.id,
                "role": r.role,
                "bounding_box": r.bounding_box.model_dump(),
                "elements_contained": r.elements_contained,
                "label": r.label,
                "deleted": r.deleted
            })
        final_path.write_text(json.dumps(regions, indent=2), encoding="utf-8")

    # ── Canvas Graphics & Direct Manipulation ─────────────────────────────────

    def _load_canvas_image(self):
        img_path = self.session_dir / self.screen.screenshot
        if not img_path.exists():
            # try normal viewport or full screenshot fallbacks
            img_path = self.session_dir / f"screen_{self.screen.index}.png"

        if not img_path.exists():
            self.canvas.delete(tk.ALL)
            self.canvas.create_text(300, 200, text="No screenshot file found.", font=("Segoe UI", 12))
            return

        self.pil_image = Image.open(img_path)
        
        # Auto-scale image to fit canvas comfortably
        cw, ch = 850, 700
        iw, ih = self.pil_image.size
        self.scale = min(cw / iw, ch / ih, 1.0)
        
        self.scaled_image = self.pil_image.resize((int(iw * self.scale), int(ih * self.scale)), Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(self.scaled_image, master=self.root)


        self.canvas.delete(tk.ALL)
        self.canvas.config(width=self.photo_image.width(), height=self.photo_image.height())
        self.bg_image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        self.canvas.image = self.photo_image  # Keep reference to prevent garbage collection!


        # Redraw existing regions
        self._redraw_regions()


    def _redraw_regions(self):
        # Clear drawn boxes (but keep the background screenshot)
        bg_id = getattr(self, "bg_image_id", None)
        for item in list(self.canvas.find_all()):
            if item != bg_id:
                self.canvas.delete(item)


        for r in self.screen.regions:
            if r.deleted:
                continue
            bb = r.bounding_box
            x1, y1 = bb.x * self.scale, bb.y * self.scale
            x2, y2 = (bb.x + bb.width) * self.scale, (bb.y + bb.height) * self.scale
            
            # Select colors based on role
            color = "#EF4444"  # red
            if r.role == "view_only":
                color = "#22C55E"  # green
            elif "navigation" in r.role or "header" in r.role:
                color = "#3B82F6"  # blue
                
            # Draw rectangle
            rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, activefill="", stipple="")
            
            # Label background & text
            lbl = r.label or r.role
            lbl_id = self.canvas.create_text(x1 + 5, y1 + 5, anchor=tk.NW, text=lbl, fill=color, font=("Segoe UI", 9, "bold"))
            
            # Keep map from canvas item to region model
            self.canvas.tag_bind(rect_id, "<ButtonPress-1>", lambda e, rid=r.id: self._on_region_clicked(rid))

    def _on_region_clicked(self, rid: str):
        self.active_region_id = rid
        # Select region in tree/listbox
        for i, r in enumerate(self.screen.regions):
            if r.id == rid:
                self.regions_listbox.select_clear(0, tk.END)
                self.regions_listbox.select_set(i)
                self._load_region_inputs(r)
                break

    def _load_region_inputs(self, r: Region):
        self.region_label_entry.delete(0, tk.END)
        self.region_label_entry.insert(0, r.label)

    # ── Canvas Interactive Draw ───────────────────────────────────────────────

    def _on_canvas_press(self, event):
        self.draw_start_x = event.x
        self.draw_start_y = event.y
        self.draw_rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#F59E0B", width=2)

    def _on_canvas_drag(self, event):
        self.canvas.coords(self.draw_rect_id, self.draw_start_x, self.draw_start_y, event.x, event.y)

    def _on_canvas_release(self, event):
        # Calculate real coordinate bounding box
        x1 = min(self.draw_start_x, event.x) / self.scale
        y1 = min(self.draw_start_y, event.y) / self.scale
        w = abs(self.draw_start_x - event.x) / self.scale
        h = abs(self.draw_start_y - event.y) / self.scale
        
        # Clean up temp drag rect
        self.canvas.delete(self.draw_rect_id)

        # Ignore tiny clicks/drags
        if w < 10 or h < 10:
            return

        # Push to undo stack
        self._push_undo()

        # Prompt for role/label
        role_dialog = _RoleDialog(self.root)
        if not role_dialog.result:
            # User cancelled role selection
            return

        role = role_dialog.result

        label = simpledialog.askstring("Region Label", "Enter label name for this region:")
        if label is None:
            # User clicked Cancel on label input
            return
            
        label = label.strip()
        if not label:
            label = f"{role.replace('_', ' ').title()}"

        new_rid = f"r{len(self.screen.regions) + 1}"
        new_region = Region(
            id=new_rid,
            role=role,
            bounding_box=BBox(x=x1, y=y1, width=w, height=h),
            elements_contained=[label],
            label=label
        )
        self.screen.regions.append(new_region)
        self._redraw_regions()
        self._refresh_regions_listbox()


    def _on_canvas_right_click(self, event):
        # Find region under click
        raw_x = event.x / self.scale
        raw_y = event.y / self.scale
        for r in self.screen.regions:
            if not r.deleted:
                bb = r.bounding_box
                if bb.x <= raw_x <= (bb.x + bb.width) and bb.y <= raw_y <= (bb.y + bb.height):
                    # Change role
                    role_dialog = _RoleDialog(self.root)
                    if role_dialog.result:
                        r.role = role_dialog.result
                        self._redraw_regions()
                        self._refresh_regions_listbox()
                    break

    def _on_delete_key(self, event):
        if self.active_region_id:
            for r in self.screen.regions:
                if r.id == self.active_region_id:
                    self._push_undo()
                    r.deleted = True
                    self.active_region_id = None
                    self._redraw_regions()
                    self._refresh_regions_listbox()
                    break

    def _on_undo(self, event):
        if self._undo_stack:
            self.screen.regions = self._undo_stack.pop()
            self._redraw_regions()
            self._refresh_regions_listbox()

    def _push_undo(self):
        # Deepcopy current regions list
        curr = [Region(**r.model_dump()) for r in self.screen.regions]
        self._undo_stack.append(curr)

    # ── Fields editing ────────────────────────────────────────────────────────

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

    # ── Step actions ──────────────────────────────────────────────────────────

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

    def _delete_step(self):
        if self.selected_step_idx is not None:
            self.screen.content.steps.pop(self.selected_step_idx)
            # Re-index remaining steps
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
            # Swap
            steps[idx], steps[target] = steps[target], steps[idx]
            # Re-index
            steps[idx].n = idx + 1
            steps[target].n = target + 1
            
            self._refresh_steps_listbox()
            self.steps_listbox.select_set(target)
            self.selected_step_idx = target

    # ── Region Inputs change ──────────────────────────────────────────────────

    def _on_region_selected_tab(self, event=None):
        pass

    def _on_region_selected_from_tab(self, event):
        sel = self.regions_listbox.curselection()
        if not sel:
            return
        r = self.screen.regions[sel[0]]
        self.active_region_id = r.id
        self._load_region_inputs(r)

    def _on_region_label_changed(self, event):
        if self.active_region_id:
            for r in self.screen.regions:
                if r.id == self.active_region_id:
                    r.label = self.region_label_entry.get().strip()
                    self._redraw_regions()
                    self._refresh_regions_listbox()
                    break

    def _delete_active_region(self):
        if self.active_region_id:
            for r in self.screen.regions:
                if r.id == self.active_region_id:
                    self._push_undo()
                    r.deleted = True
                    self.active_region_id = None
                    self._redraw_regions()
                    self._refresh_regions_listbox()
                    break


    # ── Figures list actions ──────────────────────────────────────────────────

    def _toggle_figure_mode(self):
        sel = self.figs_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Please select a figure attachment first.")
            return
        fig = self.screen.figures[sel[0]]
        fig.source = "full_page" if fig.source == "viewport" else "viewport"
        # Toggle file name extension
        old_path = fig.path
        if fig.source == "full_page" and "_viewport" in old_path:
            fig.path = old_path.replace("_viewport.png", "_full.png")
        elif fig.source == "viewport" and "_full" in old_path:
            fig.path = old_path.replace("_full.png", "_viewport.png")
        self._refresh_figs_listbox()

    def _remove_figure(self):
        sel = self.figs_listbox.curselection()
        if not sel:
            return
        self.screen.figures.pop(sel[0])
        # Re-index remaining
        for i, fig in enumerate(self.screen.figures):
            fig.index = i + 1
        self._refresh_figs_listbox()

    # ── Generator (AI Regenerations) ──────────────────────────────────────────

    def _regenerate_screen(self):
        # Save active edits first
        self._save_active_screen_inputs()
        
        cfg = get_config()
        # Instantiate active provider
        from main import get_provider_instance
        provider = get_provider_instance(cfg)
        gen = Generator(provider)

        # We need client profile for tone rules
        from docbot.clients.profile import ClientProfile
        profile = ClientProfile.load(cfg.current_client)

        logger.info(f"AI regeneration triggered for Screen {self.screen.index}...")
        self.root.config(cursor="watch")
        self.root.update()

        try:
            # Clear caches to force LLM call
            self.screen.content.content_hash = ""
            gen.generate_screen(self.session, self.screen, client_profile=profile.data)
            # Re-load screen inputs into UI
            self._load_screen(self.current_screen_idx)
            messagebox.showinfo("Success", "Documentation generated successfully!")
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            messagebox.showerror("Error", f"AI generation failed: {e}")
        finally:
            self.root.config(cursor="")

    def _regen_steps(self):
        custom = simpledialog.askstring("Custom Instructions", "Enter guide notes for steps (optional):")
        cfg = get_config()
        from main import get_provider_instance
        provider = get_provider_instance(cfg)
        
        # Build mini text prompt for steps
        prompt = (
            f"Here are the current steps:\n"
            f"{self.screen.content.steps}\n\n"
            f"Modify and polish these steps using this instruction: {custom or 'Make steps clean'}.\n"
            f"Return ONLY a JSON array of strings containing the step texts. No other text."
        )
        
        self.root.config(cursor="watch")
        self.root.update()
        try:
            raw = provider.chat(prompt)
            # Clean fences
            from providers.base import _strip_fences
            raw_clean = _strip_fences(raw)
            steps_arr = json.loads(raw_clean)
            if isinstance(steps_arr, list):
                self.screen.content.steps = [
                    Step(n=i + 1, text=str(txt), kind="action")
                    for i, txt in enumerate(steps_arr)
                ]
                self._refresh_steps_listbox()
                messagebox.showinfo("Success", "Steps regenerated successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not regenerate steps: {e}")
        finally:
            self.root.config(cursor="")

    def _compile_module(self):
        # Save session first
        self._save_active_screen_inputs()
        SessionStore.save(self.session, self.session_dir)

        # Call master assembler
        from assemble import assemble_module
        try:
            assemble_module(self.session_dir)
            messagebox.showinfo("Success", f"Draft module compiled inside {self.session_dir.name}!")
        except Exception as e:
            messagebox.showerror("Error", f"Assembly failed: {e}")


# ── Custom Modal Dialogs ──────────────────────────────────────────────────

class _RoleDialog:
    """Quick modal dialog to pick a region semantic role."""
    def __init__(self, parent):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Select Region Role")
        self.dialog.geometry("300x200")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()

        ttk.Label(self.dialog, text="Pick semantic role:", font=("Segoe UI", 10, "bold")).pack(pady=10)

        self.role_var = tk.StringVar(value="filter_form")
        roles = ["filter_form", "action_button", "action_group", "table_header", "view_only"]
        self.combo = ttk.Combobox(self.dialog, textvariable=self.role_var, values=roles, state="readonly")
        self.combo.pack(pady=10)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Select", command=self._on_select).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        
        # Center in parent
        self.dialog.transient(parent)
        parent.wait_window(self.dialog)

    def _on_select(self):
        self.result = self.role_var.get()
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
        # Prevent "image doesn't exist" TclError by using Toplevel inside same Tcl interpreter
        window = tk.Toplevel(tk._default_root)
        app = ReviewSessionUI(window, session_dir, initial_idx=screen_index)
        tk._default_root.wait_window(window)
    else:
        root = tk.Tk()
        app = ReviewSessionUI(root, session_dir, initial_idx=screen_index)
        root.mainloop()
    return "next"

