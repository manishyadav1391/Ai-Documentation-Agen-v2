import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from pathlib import Path


class ReviewWindow:
    def __init__(self, root, session_dir: Path, screen_index: int, total_screens: int):
        self.root = root
        self.session_dir = session_dir
        self.screen_index = screen_index
        self.total_screens = total_screens
        self.nav_action = "next"

        # Zoom state
        self._zoom_level = 1.0          # current zoom multiplier
        self._pan_offset_x = 0
        self._pan_offset_y = 0
        self._pil_image = None          # original PIL image (unscaled)
        self._canvas_image_id = None
        self._drag_start = None         # for canvas pan on right-drag

        self.root.title(f"Review Annotations — Screen {screen_index} of {total_screens}")
        self.root.geometry("1400x900")
        self.root.state("zoomed")       # ← maximise window immediately

        # Force window to foreground (fixes taskbar-buried problem)
        self.root.after(150, self._force_focus)

        # File paths
        self.img_path = self.session_dir / f"screen_{screen_index}.png"
        self.labeled_path = self.session_dir / f"screen_{screen_index}_labeled.json"
        self.final_json_path = self.session_dir / f"screen_{screen_index}_final.json"
        self.annotated_img_path = self.session_dir / f"screen_{screen_index}_annotated.png"
        self.meta_path = self.session_dir / f"screen_{screen_index}_meta.json"

        self.regions_data = []
        self.scale_x = 1.0
        self.scale_y = 1.0

        self.load_data()
        self.build_ui()

    # ── Focus Handling ────────────────────────────────────────────────────────

    def _force_focus(self):
        """Bring the review window to the foreground even if another app has focus."""
        try:
            self.root.attributes("-topmost", True)
            self.root.update()
            self.root.lift()
            self.root.focus_force()
            # Remove topmost after 300ms so user can switch away normally
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    # ── Data Loading ──────────────────────────────────────────────────────────

    def load_data(self):
        """Loads the labeled JSON data and existing screen name from meta."""
        load_path = self.final_json_path if self.final_json_path.exists() else self.labeled_path
        if load_path.exists():
            with load_path.open("r", encoding="utf-8") as f:
                self.regions_data = json.load(f)

        # Load existing screen name from meta.json
        self._saved_screen_name = ""
        if self.meta_path.exists():
            try:
                with self.meta_path.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                self._saved_screen_name = meta.get("screen_name", "")
                # Also try to derive a default from page title / h1 if blank
                if not self._saved_screen_name:
                    h1 = meta.get("h1_text", "")
                    title = meta.get("title", "")
                    self._saved_screen_name = h1 or title or ""
            except Exception:
                pass

    # ── UI Construction ───────────────────────────────────────────────────────

    def build_ui(self):
        """Constructs the full Tkinter interface with zoom + screen name field."""

        # ── Top Bar: Screen Name Field ───────────────────────────────────────
        top_bar = tk.Frame(self.root, bg="#1E293B", pady=6)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(top_bar, text="Screen Name:", font=("Arial", 10, "bold"),
                 bg="#1E293B", fg="white").pack(side=tk.LEFT, padx=(12, 4))

        self._screen_name_var = tk.StringVar(value=self._saved_screen_name)
        name_entry = tk.Entry(top_bar, textvariable=self._screen_name_var,
                              width=45, font=("Arial", 10))
        name_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(top_bar, text="(Used as section heading in the manual)",
                 font=("Arial", 9, "italic"), bg="#1E293B", fg="#94A3B8").pack(side=tk.LEFT)

        # ── Left Panel: Region List & Controls ───────────────────────────────
        left_frame = tk.Frame(self.root, width=460, bg="#F8FAFC")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 4), pady=10)
        left_frame.pack_propagate(False)

        tk.Label(left_frame, text="Detected Regions & Labels",
                 font=("Arial", 12, "bold"), bg="#F8FAFC").pack(pady=(8, 4))

        columns = ("role", "label")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=14)
        self.tree.heading("role", text="Role / Type")
        self.tree.heading("label", text="Label  (double-click to edit)")
        self.tree.column("role", width=130)
        self.tree.column("label", width=290)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.refresh_treeview()
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Action Buttons Row
        btn_frame = tk.Frame(left_frame, bg="#F8FAFC")
        btn_frame.pack(fill=tk.X, pady=4)
        tk.Button(btn_frame, text="➕ Add Region", bg="#BBF7D0", font=("Arial", 9, "bold"),
                  command=self.add_region).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="🗑 Delete Selected", bg="#FCA5A5", fg="white",
                  font=("Arial", 9, "bold"), command=self.delete_selected).pack(side=tk.LEFT, padx=4)

        # Nudge Controls
        nudge_frame = tk.LabelFrame(left_frame, text="Fine-Tune Bounding Box (select first)",
                                    font=("Arial", 9, "bold"), bg="#F8FAFC")
        nudge_frame.pack(fill=tk.X, pady=6, padx=4)

        move_row = tk.Frame(nudge_frame, bg="#F8FAFC")
        move_row.pack(pady=3, fill=tk.X)
        tk.Label(move_row, text="Move:", bg="#F8FAFC").pack(side=tk.LEFT, padx=6)
        for sym, attr, delta in [("↑", "y", -5), ("↓", "y", 5), ("←", "x", -5), ("→", "x", 5)]:
            tk.Button(move_row, text=sym, width=3,
                      command=lambda a=attr, d=delta: self.nudge_selected(a, d)).pack(side=tk.LEFT, padx=2)

        size_row = tk.Frame(nudge_frame, bg="#F8FAFC")
        size_row.pack(pady=3, fill=tk.X)
        tk.Label(size_row, text="Resize:", bg="#F8FAFC").pack(side=tk.LEFT, padx=4)
        for sym, attr, delta in [("W+", "w", 5), ("W−", "w", -5), ("H+", "h", 5), ("H−", "h", -5)]:
            tk.Button(size_row, text=sym, width=3,
                      command=lambda a=attr, d=delta: self.nudge_selected(a, d)).pack(side=tk.LEFT, padx=2)

        # ── Right Panel: Canvas with zoom ────────────────────────────────────
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 10), pady=10)

        # Instruction banner
        banner = tk.Frame(right_frame, bg="#EEF2F7", pady=4)
        banner.pack(fill=tk.X, pady=(0, 4))
        tk.Label(banner,
                 text="🖱️  Left-drag to draw box  |  Click to select  |  Double-click to edit  |  Ctrl+Scroll to zoom  |  Right-drag to pan",
                 font=("Arial", 9), bg="#EEF2F7", fg="#475569").pack()

        # Zoom Controls
        zoom_bar = tk.Frame(right_frame, bg="#F1F5F9", pady=3)
        zoom_bar.pack(fill=tk.X, pady=(0, 4))

        tk.Label(zoom_bar, text="Zoom:", font=("Arial", 9, "bold"), bg="#F1F5F9").pack(side=tk.LEFT, padx=6)
        self._zoom_var = tk.DoubleVar(value=1.0)
        zoom_slider = tk.Scale(zoom_bar, from_=0.2, to=4.0, resolution=0.05,
                               orient=tk.HORIZONTAL, variable=self._zoom_var, length=200,
                               command=self._on_zoom_slider, showvalue=False, bg="#F1F5F9")
        zoom_slider.pack(side=tk.LEFT, padx=4)
        self._zoom_label = tk.Label(zoom_bar, text="100%", width=6, font=("Arial", 9), bg="#F1F5F9")
        self._zoom_label.pack(side=tk.LEFT)

        tk.Button(zoom_bar, text="Fit", font=("Arial", 9), command=self._zoom_fit).pack(side=tk.LEFT, padx=4)
        tk.Button(zoom_bar, text="100%", font=("Arial", 9), command=self._zoom_100).pack(side=tk.LEFT, padx=2)
        tk.Button(zoom_bar, text="200%", font=("Arial", 9), command=self._zoom_200).pack(side=tk.LEFT, padx=2)

        # Canvas with scrollbars
        canvas_frame = tk.Frame(right_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#4A5568", cursor="cross")
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.config(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Load image
        self._load_image_at_zoom()

        # Canvas mouse bindings
        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)

        # Right-drag to pan
        self.canvas.bind("<Button-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)

        # Ctrl+scroll to zoom
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_scroll)
        self.canvas.bind("<MouseWheel>", self._on_plain_scroll)

        # Bottom Controls
        bottom_frame = tk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, pady=(6, 0))

        tk.Button(bottom_frame, text="👁️ Preview Annotations", bg="#BFDBFE",
                  font=("Arial", 10, "bold"), command=self.preview_annotation).pack(side=tk.LEFT, padx=4)

        nav_frame = tk.Frame(bottom_frame)
        nav_frame.pack(side=tk.RIGHT)
        if self.screen_index > 1:
            tk.Button(nav_frame, text="<< Previous", command=self.go_prev).pack(side=tk.LEFT, padx=4)
        tk.Button(nav_frame, text="Quit Session", fg="red", command=self.go_quit).pack(side=tk.LEFT, padx=4)
        next_text = "Next Screen >>" if self.screen_index < self.total_screens else "✔ Done / Accept"
        tk.Button(nav_frame, text=next_text, bg="#BBF7D0",
                  font=("Arial", 10, "bold"), command=self.go_next).pack(side=tk.LEFT, padx=4)

    # ── Image & Zoom Logic ────────────────────────────────────────────────────

    def _load_image_at_zoom(self):
        """(Re)load PIL image and render it at the current zoom level."""
        if not self.img_path.exists():
            return
        if self._pil_image is None:
            self._pil_image = Image.open(self.img_path)
            self.orig_w, self.orig_h = self._pil_image.size
            # Set initial zoom to fit window
            self._zoom_fit(update_slider=False)
            return

        self._render_canvas()

    def _render_canvas(self):
        """Render the image + boxes at the current zoom level onto the canvas."""
        if self._pil_image is None:
            return

        z = self._zoom_level
        new_w = max(1, int(self.orig_w * z))
        new_h = max(1, int(self.orig_h * z))

        # Use LANCZOS for zoom-out, NEAREST for zoom-in (speed)
        resample = Image.LANCZOS if z < 1.0 else Image.NEAREST
        resized = self._pil_image.resize((new_w, new_h), resample)

        self.photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self._canvas_image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))

        # Coordinate scale (original pixel → canvas pixel)
        self.scale_x = 1.0 / z
        self.scale_y = 1.0 / z

        self.draw_existing_boxes()

    def _set_zoom(self, factor: float, update_slider: bool = True):
        """Set zoom to a specific factor and re-render."""
        self._zoom_level = max(0.1, min(factor, 6.0))
        if update_slider:
            self._zoom_var.set(self._zoom_level)
        self._zoom_label.config(text=f"{int(self._zoom_level * 100)}%")
        self._render_canvas()

    def _zoom_fit(self, update_slider: bool = True, event=None):
        """Fit the entire image into the current canvas size."""
        self.canvas.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 700
        if self.orig_w and self.orig_h:
            factor = min(canvas_w / self.orig_w, canvas_h / self.orig_h, 1.0)
            self._set_zoom(factor, update_slider)

    def _zoom_100(self, event=None):
        self._set_zoom(1.0)

    def _zoom_200(self, event=None):
        self._set_zoom(2.0)

    def _on_zoom_slider(self, value):
        self._set_zoom(float(value))

    def _on_ctrl_scroll(self, event):
        """Ctrl + mouse wheel → zoom in/out."""
        if event.delta > 0:
            self._set_zoom(self._zoom_level * 1.15)
        else:
            self._set_zoom(self._zoom_level / 1.15)

    def _on_plain_scroll(self, event):
        """Plain scroll → vertical pan."""
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _pan_start(self, event):
        self._drag_start = (event.x, event.y)
        self.canvas.config(cursor="fleur")

    def _pan_move(self, event):
        if self._drag_start:
            dx = self._drag_start[0] - event.x
            dy = self._drag_start[1] - event.y
            self.canvas.xview_scroll(int(dx / 8), "units")
            self.canvas.yview_scroll(int(dy / 8), "units")
            self._drag_start = (event.x, event.y)

    # ── Canvas coordinate helpers ─────────────────────────────────────────────

    def _canvas_to_orig(self, cx: float, cy: float):
        """Convert canvas-space coordinates to original image coordinates."""
        # Account for scroll offset
        x_scroll_frac = self.canvas.xview()[0]
        y_scroll_frac = self.canvas.yview()[0]
        canvas_w = int(self.orig_w * self._zoom_level)
        canvas_h = int(self.orig_h * self._zoom_level)
        cx_abs = cx + x_scroll_frac * canvas_w
        cy_abs = cy + y_scroll_frac * canvas_h
        return cx_abs * self.scale_x, cy_abs * self.scale_y

    def _orig_to_canvas(self, ox: float, oy: float):
        """Convert original image coordinates to visible canvas coordinates."""
        x_scroll_frac = self.canvas.xview()[0]
        y_scroll_frac = self.canvas.yview()[0]
        canvas_w = int(self.orig_w * self._zoom_level)
        canvas_h = int(self.orig_h * self._zoom_level)
        cx_abs = ox / self.scale_x
        cy_abs = oy / self.scale_y
        return cx_abs - x_scroll_frac * canvas_w, cy_abs - y_scroll_frac * canvas_h

    # ── Region Drawing ────────────────────────────────────────────────────────

    def refresh_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, r in enumerate(self.regions_data):
            if not r.get("deleted"):
                self.tree.insert("", "end", iid=str(idx),
                                 values=(r.get("role", "view_only"), r.get("label", "")))

    def draw_existing_boxes(self):
        """Draw all region bounding boxes on the zoomed canvas."""
        self.canvas.delete("box_overlay")
        z = self._zoom_level
        for idx, r in enumerate(self.regions_data):
            if r.get("deleted"):
                continue
            bbox = r.get("bounding_box", {})
            if not bbox:
                continue
            cx1 = bbox.get("x", 0) * z
            cy1 = bbox.get("y", 0) * z
            cx2 = (bbox.get("x", 0) + bbox.get("width", 0)) * z
            cy2 = (bbox.get("y", 0) + bbox.get("height", 0)) * z

            # Color by role type
            role = r.get("role", "")
            color = "#E53E3E"  # red default
            if "navigation" in role:
                color = "#805AD5"
            elif "table" in role or "column" in role:
                color = "#2B6CB0"
            elif "header" in role or "heading" in role:
                color = "#276749"
            elif "action" in role:
                color = "#C05621"

            self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                          outline=color, width=2, dash=(4, 3),
                                          tags=("box_overlay", f"region_{idx}"))
            # Mini label overlay
            label_text = r.get("label", "")
            if label_text:
                short = label_text[:18] + "…" if len(label_text) > 18 else label_text
                self.canvas.create_text(cx1 + 4, cy1 + 2, text=short, anchor=tk.NW,
                                        font=("Arial", 7), fill=color,
                                        tags=("box_overlay", f"region_{idx}"))

    def on_tree_select(self, event):
        """Highlight the selected region with a thick blue border."""
        self.canvas.delete("highlight_overlay")
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        r = self.regions_data[idx]
        bbox = r.get("bounding_box", {})
        if not bbox:
            return
        z = self._zoom_level
        cx1 = bbox.get("x", 0) * z
        cy1 = bbox.get("y", 0) * z
        cx2 = (bbox.get("x", 0) + bbox.get("width", 0)) * z
        cy2 = (bbox.get("y", 0) + bbox.get("height", 0)) * z
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="#3182CE",
                                      width=3, tags="highlight_overlay")
        # Scroll canvas to show the selected box
        self.canvas.update_idletasks()
        canvas_w = int(self.orig_w * z)
        canvas_h = int(self.orig_h * z)
        if canvas_w > 0:
            self.canvas.xview_moveto(max(0, (cx1 - 50) / canvas_w))
        if canvas_h > 0:
            self.canvas.yview_moveto(max(0, (cy1 - 50) / canvas_h))

    def nudge_selected(self, attr, delta):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a region first.")
            return
        idx = int(selected[0])
        bbox = self.regions_data[idx].get("bounding_box", {})
        if not bbox:
            return
        if attr == "x":
            bbox["x"] = max(0, bbox.get("x", 0) + delta)
        elif attr == "y":
            bbox["y"] = max(0, bbox.get("y", 0) + delta)
        elif attr == "w":
            bbox["width"] = max(5, bbox.get("width", 5) + delta)
        elif attr == "h":
            bbox["height"] = max(5, bbox.get("height", 5) + delta)
        self.draw_existing_boxes()
        self.on_tree_select(None)

    # ── Mouse Draw & Click ────────────────────────────────────────────────────

    def on_drag_start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = None

    def on_drag_motion(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline="#3182CE", width=2, dash=(4, 4))

    def on_drag_end(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        w, h = x2 - x1, y2 - y1

        if w > 5 and h > 5:
            # Drag gesture: create new region
            z = self._zoom_level
            orig_x = int(x1 / z)
            orig_y = int(y1 / z)
            orig_w = int(w / z)
            orig_h = int(h / z)
            self.open_region_dialog(init_coords=(orig_x, orig_y, orig_w, orig_h))
        else:
            # Click gesture: select region under cursor
            orig_x, orig_y = x1 / self._zoom_level, y1 / self._zoom_level
            for idx in range(len(self.regions_data) - 1, -1, -1):
                r = self.regions_data[idx]
                if r.get("deleted"):
                    continue
                bbox = r.get("bounding_box", {})
                rx, ry = bbox.get("x", 0), bbox.get("y", 0)
                rw, rh = bbox.get("width", 0), bbox.get("height", 0)
                if rx <= orig_x <= rx + rw and ry <= orig_y <= ry + rh:
                    self.tree.selection_set(str(idx))
                    self.tree.see(str(idx))
                    return

    def on_canvas_double_click(self, event):
        orig_x, orig_y = event.x / self._zoom_level, event.y / self._zoom_level
        for idx in range(len(self.regions_data) - 1, -1, -1):
            r = self.regions_data[idx]
            if r.get("deleted"):
                continue
            bbox = r.get("bounding_box", {})
            rx, ry = bbox.get("x", 0), bbox.get("y", 0)
            rw, rh = bbox.get("width", 0), bbox.get("height", 0)
            if rx <= orig_x <= rx + rw and ry <= orig_y <= ry + rh:
                self.tree.selection_set(str(idx))
                self.tree.see(str(idx))
                self.open_region_dialog(str(idx))
                return

    def on_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        self.open_region_dialog(selected[0])

    # ── Region Edit Dialog ────────────────────────────────────────────────────

    def open_region_dialog(self, item_id=None, init_coords=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Region" if item_id else "Add Region")
        dialog.geometry("440x380")
        dialog.grab_set()
        dialog.transient(self.root)

        if item_id:
            idx = int(item_id)
            r = self.regions_data[idx]
            init_label = r.get("label", "")
            init_role = r.get("role", "view_only")
            bbox = r.get("bounding_box", {})
            init_x, init_y = str(int(float(bbox.get("x", 0)))), str(int(float(bbox.get("y", 0))))
            init_w, init_h = str(int(float(bbox.get("width", 50)))), str(int(float(bbox.get("height", 50))))
        else:
            init_label, init_role = "", "view_only"
            if init_coords:
                init_x, init_y, init_w, init_h = map(str, init_coords)
            else:
                init_x, init_y, init_w, init_h = "100", "100", "100", "50"

        pad = dict(padx=14, pady=7, sticky=tk.W)
        tk.Label(dialog, text="Label:", font=("Arial", 10)).grid(row=0, column=0, **pad)
        entry_label = tk.Entry(dialog, width=32, font=("Arial", 10))
        entry_label.insert(0, init_label)
        entry_label.grid(row=0, column=1, **pad)
        entry_label.focus_set()

        tk.Label(dialog, text="Role:", font=("Arial", 10)).grid(row=1, column=0, **pad)
        combo_role = ttk.Combobox(dialog, state="readonly", font=("Arial", 10), width=22,
                                   values=["action_button", "filter_form", "action_column",
                                           "table_header", "navigation_bar", "page_header",
                                           "section_heading", "view_only"])
        combo_role.set(init_role)
        combo_role.grid(row=1, column=1, **pad)

        for row_idx, (lbl, var) in enumerate([("X:", init_x), ("Y:", init_y),
                                               ("Width:", init_w), ("Height:", init_h)], start=2):
            tk.Label(dialog, text=lbl, font=("Arial", 10)).grid(row=row_idx, column=0, **pad)
            e = tk.Entry(dialog, width=15, font=("Arial", 10))
            e.insert(0, var)
            e.grid(row=row_idx, column=1, **pad)
            setattr(self, f"_dlg_entry_{['x', 'y', 'w', 'h'][row_idx - 2]}", e)

        def save_values():
            try:
                x_val = int(float(self._dlg_entry_x.get()))
                y_val = int(float(self._dlg_entry_y.get()))
                w_val = int(float(self._dlg_entry_w.get()))
                h_val = int(float(self._dlg_entry_h.get()))
            except ValueError:
                messagebox.showerror("Error", "Coordinates must be integers.", parent=dialog)
                return

            label_val = entry_label.get().strip()
            if not label_val:
                messagebox.showerror("Error", "Label cannot be blank.", parent=dialog)
                return

            r_dict = {"role": combo_role.get(), "label": label_val,
                      "bounding_box": {"x": x_val, "y": y_val, "width": w_val, "height": h_val}}
            if item_id:
                self.regions_data[int(item_id)] = r_dict
            else:
                self.regions_data.append(r_dict)

            self.refresh_treeview()
            self.draw_existing_boxes()
            new_id = item_id or str(len(self.regions_data) - 1)
            self.tree.selection_set(new_id)
            self.tree.see(new_id)
            dialog.destroy()

        tk.Button(dialog, text="Save Region", bg="#BBF7D0",
                  font=("Arial", 10, "bold"), command=save_values).grid(
                      row=6, column=0, columnspan=2, pady=14)

    def add_region(self):
        self.open_region_dialog()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a region to delete.")
            return
        self.regions_data[int(selected[0])]["deleted"] = True
        self.refresh_treeview()
        self.draw_existing_boxes()
        self.canvas.delete("highlight_overlay")

    # ── Preview & Save ────────────────────────────────────────────────────────

    def preview_annotation(self):
        self.save_temp_json()
        from annotate import render_annotations
        try:
            render_annotations(self.session_dir, self.screen_index)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Failed to render preview:\n{e}")
            return

        if self.annotated_img_path.exists():
            self._pil_image = Image.open(self.annotated_img_path)
            self.orig_w, self.orig_h = self._pil_image.size
            self._render_canvas()
            messagebox.showinfo("Preview", "Annotation preview refreshed successfully.")
        else:
            messagebox.showinfo("Preview", "Annotation file could not be generated.")

    def save_temp_json(self):
        """Save current edits to final JSON and persist screen name to meta."""
        final_data = [r for r in self.regions_data if not r.get("deleted")]
        with self.final_json_path.open("w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2)

        # Persist the screen name entered by the user
        screen_name = self._screen_name_var.get().strip()
        if self.meta_path.exists():
            try:
                with self.meta_path.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["screen_name"] = screen_name
                with self.meta_path.open("w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass

    # ── Navigation ────────────────────────────────────────────────────────────

    def go_prev(self):
        self.save_temp_json()
        self.nav_action = "prev"
        self.root.destroy()

    def go_quit(self):
        self.nav_action = "quit"
        self.root.destroy()

    def go_next(self):
        self.save_temp_json()
        self.nav_action = "next"
        self.root.destroy()


# ── Entry Point ───────────────────────────────────────────────────────────────

def open_review_ui(session_dir: Path, screen_index: int, total_screens: int = 1) -> str:
    """
    Opens the review window safely, preventing 'pyimage' errors by using
    a Toplevel window if a main Tkinter root (like the Launcher) exists.
    """
    if tk._default_root:
        root = tk.Toplevel()
        is_subwindow = True
    else:
        root = tk.Tk()
        is_subwindow = False

    app = ReviewWindow(root, session_dir, screen_index, total_screens)

    if is_subwindow:
        root.grab_set()
        root.wait_window(root)
    else:
        root.mainloop()

    return app.nav_action


if __name__ == "__main__":
    open_review_ui(Path("sessions/session_test"), 1, 3)