import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import json
from pathlib import Path

class ReviewWindow:
    def __init__(self, root, session_dir: Path, screen_index: int, total_screens: int):
        self.root = root
        self.session_dir = session_dir
        self.screen_index = screen_index
        self.total_screens = total_screens
        
        # This variable stores what the user clicked so main.py knows where to go next
        self.nav_action = "next" 
        
        self.root.title(f"Review Annotations - Screen {screen_index} of {total_screens}")
        self.root.geometry("1300x850")
        
        # File paths
        self.img_path = self.session_dir / f"screen_{screen_index}.png"
        self.labeled_path = self.session_dir / f"screen_{screen_index}_labeled.json"
        self.final_json_path = self.session_dir / f"screen_{screen_index}_final.json"
        self.annotated_img_path = self.session_dir / f"screen_{screen_index}_annotated.png"
        
        self.regions_data = []
        self.scale_x = 1.0
        self.scale_y = 1.0
        
        self.load_data()
        self.build_ui()

    def load_data(self):
        """Loads the labeled JSON data."""
        # Check if final JSON exists (e.g. if returning to a previously reviewed screen)
        # otherwise load from labeled.json
        load_path = self.final_json_path if self.final_json_path.exists() else self.labeled_path
        if load_path.exists():
            with load_path.open("r", encoding="utf-8") as f:
                self.regions_data = json.load(f)

    def build_ui(self):
        """Constructs the Tkinter interface."""
        # Left panel: Data grid & controls
        left_frame = tk.Frame(self.root, width=450)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        tk.Label(left_frame, text="Detected Regions & Labels", font=("Arial", 12, "bold")).pack(pady=5)
        
        columns = ("role", "label")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("role", text="Role")
        self.tree.heading("label", text="Label (Double-click to edit)")
        self.tree.column("role", width=120)
        self.tree.column("label", width=280)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        self.refresh_treeview()
        
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Action Buttons for Editing
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Add Region", bg="lightgreen", command=self.add_region).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Delete Selected", bg="tomato", fg="white", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        
        # Bounding box nudge controls
        nudge_frame = tk.LabelFrame(left_frame, text="Fine-Tune Bounding Box (Select item first)", font=("Arial", 9, "bold"))
        nudge_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Row 1: Move controls
        move_row = tk.Frame(nudge_frame)
        move_row.pack(pady=5, fill=tk.X)
        tk.Label(move_row, text="Move Box: ").pack(side=tk.LEFT, padx=5)
        tk.Button(move_row, text="↑", width=3, command=lambda: self.nudge_selected("y", -5)).pack(side=tk.LEFT, padx=2)
        tk.Button(move_row, text="↓", width=3, command=lambda: self.nudge_selected("y", 5)).pack(side=tk.LEFT, padx=2)
        tk.Button(move_row, text="←", width=3, command=lambda: self.nudge_selected("x", -5)).pack(side=tk.LEFT, padx=2)
        tk.Button(move_row, text="→", width=3, command=lambda: self.nudge_selected("x", 5)).pack(side=tk.LEFT, padx=2)

        # Row 2: Size controls
        size_row = tk.Frame(nudge_frame)
        size_row.pack(pady=5, fill=tk.X)
        tk.Label(size_row, text="Resize:   ").pack(side=tk.LEFT, padx=5)
        tk.Button(size_row, text="W+", width=3, command=lambda: self.nudge_selected("w", 5)).pack(side=tk.LEFT, padx=2)
        tk.Button(size_row, text="W-", width=3, command=lambda: self.nudge_selected("w", -5)).pack(side=tk.LEFT, padx=2)
        tk.Button(size_row, text="H+", width=3, command=lambda: self.nudge_selected("h", 5)).pack(side=tk.LEFT, padx=2)
        tk.Button(size_row, text="H-", width=3, command=lambda: self.nudge_selected("h", -5)).pack(side=tk.LEFT, padx=2)

        # Right panel: Image canvas & controls
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Instruction Banner
        banner = tk.Frame(right_frame, bg="#eef2f7", pady=5)
        banner.pack(fill=tk.X, pady=(0, 5))
        tk.Label(banner, text="🖱️ Canvas Interaction: Drag to draw new boxes | Click box to select | Double-click box to edit", font=("Arial", 10), bg="#eef2f7", fg="#475569").pack()

        # Canvas with scrollbar integration if the window is resized
        self.canvas = tk.Canvas(right_frame, bg="darkgray", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Load image initially
        self.load_image_preview(self.img_path)
        
        # Bind canvas mouse events
        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        
        # Bottom controls for Preview and Navigation
        bottom_frame = tk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(bottom_frame, text="👁️ Preview Annotation Boxes", bg="lightblue", font=("Arial", 10, "bold"), command=self.preview_annotation).pack(side=tk.LEFT, padx=5)
        
        # Navigation block
        nav_frame = tk.Frame(bottom_frame)
        nav_frame.pack(side=tk.RIGHT)

        if self.screen_index > 1:
            tk.Button(nav_frame, text="<< Previous Screen", command=self.go_prev).pack(side=tk.LEFT, padx=5)
            
        tk.Button(nav_frame, text="Quit Session", fg="red", command=self.go_quit).pack(side=tk.LEFT, padx=5)

        next_text = "Next Screen >>" if self.screen_index < self.total_screens else "Done / Accept Final"
        tk.Button(nav_frame, text=next_text, bg="lightgreen", font=("Arial", 10, "bold"), command=self.go_next).pack(side=tk.LEFT, padx=5)

    def refresh_treeview(self):
        """Clears and re-populates the treeview based on regions_data."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Re-insert non-deleted items
        for idx, r in enumerate(self.regions_data):
            if not r.get("deleted"):
                self.tree.insert("", "end", iid=str(idx), values=(r.get("role", "view_only"), r.get("label", "")))

    def load_image_preview(self, path: Path):
        """Loads and scales the image for the Canvas."""
        if not path.exists(): return
        self.canvas.delete("all")  # Clear previous drawings
        
        img = Image.open(path)
        orig_w, orig_h = img.size
        self.orig_w, self.orig_h = orig_w, orig_h
        
        # Scale to fit 800x800
        img.thumbnail((800, 800)) 
        scaled_w, scaled_h = img.size
        
        self.scale_x = orig_w / scaled_w
        self.scale_y = orig_h / scaled_h
        
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # Draw boundaries of all existing boxes
        self.draw_existing_boxes()

    def draw_existing_boxes(self):
        """Draws boundaries for all active regions on the canvas."""
        self.canvas.delete("box_overlay")  # Clear overlays
        for idx, r in enumerate(self.regions_data):
            if r.get("deleted"):
                continue
            bbox = r.get("bounding_box", {})
            if not bbox:
                continue
                
            # Map back to canvas coordinates
            cx1 = int(bbox.get("x", 0) / self.scale_x)
            cy1 = int(bbox.get("y", 0) / self.scale_y)
            cx2 = int((bbox.get("x", 0) + bbox.get("width", 0)) / self.scale_x)
            cy2 = int((bbox.get("y", 0) + bbox.get("height", 0)) / self.scale_y)
            
            color = "red"
            
            self.canvas.create_rectangle(
                cx1, cy1, cx2, cy2,
                outline=color, width=1, dash=(2, 2), tags=("box_overlay", f"region_{idx}")
            )

    def on_tree_select(self, event):
        """Highlights the selected region on the canvas with a blue outline."""
        self.canvas.delete("highlight_overlay")
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        r = self.regions_data[idx]
        bbox = r.get("bounding_box", {})
        if not bbox:
            return
            
        cx1 = int(bbox.get("x", 0) / self.scale_x)
        cy1 = int(bbox.get("y", 0) / self.scale_y)
        cx2 = int((bbox.get("x", 0) + bbox.get("width", 0)) / self.scale_x)
        cy2 = int((bbox.get("y", 0) + bbox.get("height", 0)) / self.scale_y)
        
        self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline="blue", width=3, tags="highlight_overlay"
        )

    def nudge_selected(self, attr, delta):
        """Nudges the coordinates of the selected region and refreshes overlays."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a region in the list to nudge.")
            return
        idx = int(selected[0])
        r = self.regions_data[idx]
        bbox = r.get("bounding_box", {})
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

    # --- Mouse Drag & Click Handling on Canvas ---
    def on_drag_start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = None

    def on_drag_motion(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline="blue", width=2, dash=(4, 4)
        )

    def on_drag_end(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
            
        end_x, end_y = event.x, event.y
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        
        w = x2 - x1
        h = y2 - y1
        
        if w > 5 and h > 5:
            # Drag drawing gesture: Create new region
            orig_x = int(x1 * self.scale_x)
            orig_y = int(y1 * self.scale_y)
            orig_w = int(w * self.scale_x)
            orig_h = int(h * self.scale_y)
            self.open_region_dialog(init_coords=(orig_x, orig_y, orig_w, orig_h))
        else:
            # Single click gesture: Select region under mouse
            orig_click_x = x1 * self.scale_x
            orig_click_y = y1 * self.scale_y
            
            for idx in range(len(self.regions_data) - 1, -1, -1):
                r = self.regions_data[idx]
                if r.get("deleted"):
                    continue
                bbox = r.get("bounding_box", {})
                rx = bbox.get("x", 0)
                ry = bbox.get("y", 0)
                rw = bbox.get("width", 0)
                rh = bbox.get("height", 0)
                
                if rx <= orig_click_x <= rx + rw and ry <= orig_click_y <= ry + rh:
                    self.tree.selection_set(str(idx))
                    self.tree.see(str(idx))
                    return

    def on_canvas_double_click(self, event):
        """Opens editing dialog for selected element under double click coordinates."""
        orig_click_x = event.x * self.scale_x
        orig_click_y = event.y * self.scale_y
        
        for idx in range(len(self.regions_data) - 1, -1, -1):
            r = self.regions_data[idx]
            if r.get("deleted"):
                continue
            bbox = r.get("bounding_box", {})
            rx = bbox.get("x", 0)
            ry = bbox.get("y", 0)
            rw = bbox.get("width", 0)
            rh = bbox.get("height", 0)
            
            if rx <= orig_click_x <= rx + rw and ry <= orig_click_y <= ry + rh:
                self.tree.selection_set(str(idx))
                self.tree.see(str(idx))
                self.open_region_dialog(str(idx))
                return

    def on_double_click(self, event):
        """Allows editing of the region parameters (label, role, coordinates) from treeview double click."""
        selected = self.tree.selection()
        if not selected: return
        self.open_region_dialog(selected[0])

    # --- Editing and Adding Dialogs ---
    def open_region_dialog(self, item_id=None, init_coords=None):
        """
        Opens a modal dialog to create or edit a region.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Region" if item_id else "Add Region")
        dialog.geometry("420x360")
        dialog.grab_set()
        
        # Focus on parent dialog
        dialog.transient(self.root)

        if item_id:
            idx = int(item_id)
            r = self.regions_data[idx]
            init_label = r.get("label", "")
            init_role = r.get("role", "view_only")
            bbox = r.get("bounding_box", {})
            init_x = str(int(float(bbox.get("x", 0))))
            init_y = str(int(float(bbox.get("y", 0))))
            init_w = str(int(float(bbox.get("width", 50))))
            init_h = str(int(float(bbox.get("height", 50))))
        else:
            init_label = ""
            init_role = "view_only"
            if init_coords:
                init_x, init_y, init_w, init_h = map(str, init_coords)
            else:
                init_x, init_y, init_w, init_h = "100", "100", "100", "50"

        # Construct form
        tk.Label(dialog, text="Label:", font=("Arial", 10)).grid(row=0, column=0, padx=15, pady=8, sticky=tk.W)
        entry_label = tk.Entry(dialog, width=30, font=("Arial", 10))
        entry_label.insert(0, init_label)
        entry_label.grid(row=0, column=1, padx=15, pady=8)
        entry_label.focus_set()

        tk.Label(dialog, text="Role:", font=("Arial", 10)).grid(row=1, column=0, padx=15, pady=8, sticky=tk.W)
        combo_role = ttk.Combobox(dialog, values=["action_button", "filter_form", "action_group", "table_header", "view_only"], state="readonly", font=("Arial", 10))
        combo_role.set(init_role)
        combo_role.grid(row=1, column=1, padx=15, pady=8)

        tk.Label(dialog, text="X Coordinate:", font=("Arial", 10)).grid(row=2, column=0, padx=15, pady=8, sticky=tk.W)
        entry_x = tk.Entry(dialog, width=15, font=("Arial", 10))
        entry_x.insert(0, init_x)
        entry_x.grid(row=2, column=1, padx=15, pady=8, sticky=tk.W)

        tk.Label(dialog, text="Y Coordinate:", font=("Arial", 10)).grid(row=3, column=0, padx=15, pady=8, sticky=tk.W)
        entry_y = tk.Entry(dialog, width=15, font=("Arial", 10))
        entry_y.insert(0, init_y)
        entry_y.grid(row=3, column=1, padx=15, pady=8, sticky=tk.W)

        tk.Label(dialog, text="Box Width:", font=("Arial", 10)).grid(row=4, column=0, padx=15, pady=8, sticky=tk.W)
        entry_w = tk.Entry(dialog, width=15, font=("Arial", 10))
        entry_w.insert(0, init_w)
        entry_w.grid(row=4, column=1, padx=15, pady=8, sticky=tk.W)

        tk.Label(dialog, text="Box Height:", font=("Arial", 10)).grid(row=5, column=0, padx=15, pady=8, sticky=tk.W)
        entry_h = tk.Entry(dialog, width=15, font=("Arial", 10))
        entry_h.insert(0, init_h)
        entry_h.grid(row=5, column=1, padx=15, pady=8, sticky=tk.W)

        def save_values():
            try:
                x_val = int(float(entry_x.get()))
                y_val = int(float(entry_y.get()))
                w_val = int(float(entry_w.get()))
                h_val = int(float(entry_h.get()))
            except ValueError:
                messagebox.showerror("Error", "Coordinate values must be integers.", parent=dialog)
                return

            label_val = entry_label.get().strip()
            if not label_val:
                messagebox.showerror("Error", "Label field cannot be blank.", parent=dialog)
                return
                
            role_val = combo_role.get()

            r_dict = {
                "role": role_val,
                "label": label_val,
                "bounding_box": {
                    "x": x_val,
                    "y": y_val,
                    "width": w_val,
                    "height": h_val
                }
            }

            if item_id:
                idx = int(item_id)
                self.regions_data[idx] = r_dict
            else:
                self.regions_data.append(r_dict)

            self.refresh_treeview()
            self.draw_existing_boxes()
            
            # Select the item
            new_id = item_id or str(len(self.regions_data) - 1)
            self.tree.selection_set(new_id)
            self.tree.see(new_id)
            
            dialog.destroy()

        tk.Button(dialog, text="Save Region", bg="lightgreen", font=("Arial", 10, "bold"), command=save_values).grid(row=6, column=0, columnspan=2, pady=15)

    def add_region(self):
        """Allows user to add a region manually."""
        self.open_region_dialog()

    def delete_selected(self):
        """Removes selected region."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a region to delete.")
            return
        item_id = selected[0]
        self.regions_data[int(item_id)]["deleted"] = True
        self.refresh_treeview()
        self.draw_existing_boxes()
        self.canvas.delete("highlight_overlay")

    def preview_annotation(self):
        """Saves current state, renders annotations on the fly, and shows preview."""
        self.save_temp_json()
        
        # Import and run the actual render function on the fly!
        from annotate import render_annotations
        try:
            render_annotations(self.session_dir, self.screen_index)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Failed to generate annotation preview:\n{e}")
            return
            
        print("Rendering annotations... showing preview.")
        if self.annotated_img_path.exists():
            self.load_image_preview(self.annotated_img_path)
            messagebox.showinfo("Success", "Preview updated successfully with your annotations.")
        else:
            messagebox.showinfo("Preview", "Annotation module could not generate the preview file.")

    def save_temp_json(self):
        """Saves the current edits to the final JSON file."""
        final_data = [r for r in self.regions_data if not r.get("deleted")]
        with self.final_json_path.open("w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2)

    # --- Navigation Handlers ---
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