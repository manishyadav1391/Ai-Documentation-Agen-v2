import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import json
from pathlib import Path

# Note: In the final pipeline, this imports from our annotate.py module
# from annotate import render_annotations

class ReviewWindow:
    def __init__(self, root, session_dir: Path, screen_index: int):
        self.root = root
        self.session_dir = session_dir
        self.screen_index = screen_index
        
        self.root.title(f"Review Annotations - Screen {screen_index}")
        self.root.geometry("1200x800")
        
        # File paths
        self.img_path = self.session_dir / f"screen_{screen_index}.png"
        self.labeled_path = self.session_dir / f"screen_{screen_index}_labeled.json"
        self.final_json_path = self.session_dir / f"screen_{screen_index}_final.json"
        self.annotated_img_path = self.session_dir / f"screen_{screen_index}_annotated.png"
        
        self.regions_data = []
        self.load_data()
        self.build_ui()

    def load_data(self):
        """Loads the labeled JSON data."""
        if self.labeled_path.exists():
            with self.labeled_path.open("r", encoding="utf-8") as f:
                self.regions_data = json.load(f)

    def build_ui(self):
        """Constructs the Tkinter interface."""
        # Left panel: Data grid
        left_frame = tk.Frame(self.root, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        tk.Label(left_frame, text="Detected Regions & Labels", font=("Arial", 12, "bold")).pack(pady=5)
        
        columns = ("role", "label")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=20)
        self.tree.heading("role", text="Role")
        self.tree.heading("label", text="Label (Double-click to edit)")
        self.tree.column("role", width=100)
        self.tree.column("label", width=250)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        for idx, r in enumerate(self.regions_data):
            self.tree.insert("", "end", iid=str(idx), values=(r.get("role"), r.get("label")))
            
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # Action Buttons
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        
        # Right panel: Image preview
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(right_frame, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.load_image_preview(self.img_path)
        
        # Bottom controls for the new Preview -> Regenerate -> Done workflow
        bottom_frame = tk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(bottom_frame, text="Preview Annotation", bg="lightblue", command=self.preview_annotation).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="Done / Accept Final", bg="lightgreen", command=self.accept_final).pack(side=tk.RIGHT, padx=5)

    def on_double_click(self, event):
        """Allows inline editing of the label (FR-30)."""
        selected = self.tree.selection()
        if not selected: return
        
        item_id = selected[0]
        current_label = self.tree.item(item_id, "values")[1]
        
        # Simple popup for editing
        edit_win = tk.Toplevel(self.root)
        edit_win.title("Edit Label")
        
        tk.Label(edit_win, text="New Label:").pack(padx=10, pady=5)
        entry = tk.Entry(edit_win, width=40)
        entry.insert(0, current_label)
        entry.pack(padx=10, pady=5)
        
        def save_edit():
            new_val = entry.get()
            self.tree.item(item_id, values=(self.tree.item(item_id, "values")[0], new_val))
            self.regions_data[int(item_id)]["label"] = new_val
            edit_win.destroy()
            
        tk.Button(edit_win, text="Save", command=save_edit).pack(pady=10)

    def delete_selected(self):
        """Removes a region from the list (FR-31)."""
        selected = self.tree.selection()
        if not selected: return
        item_id = selected[0]
        
        self.tree.delete(item_id)
        # Mark as deleted in our data list
        self.regions_data[int(item_id)]["deleted"] = True

    def load_image_preview(self, path: Path):
        """Loads and scales the image for the Canvas."""
        if not path.exists(): return
        img = Image.open(path)
        img.thumbnail((800, 800)) # Scale to fit UI
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def preview_annotation(self):
        """
        Saves the current state and triggers the annotation render, 
        then updates the canvas so the user can see the result.
        """
        self.save_temp_json()
        
        # Here we would call the actual render function from annotate.py
        # render_annotations(self.img_path, self.final_json_path, self.annotated_img_path)
        
        # Simulate rendering for now by reloading the original image
        # In actual execution, this loads self.annotated_img_path
        print("Rendering annotations... showing preview.")
        
        # If the annotated image exists after generation, show it
        if self.annotated_img_path.exists():
            self.load_image_preview(self.annotated_img_path)
        else:
            messagebox.showinfo("Preview", "Annotation module will draw boxes and update this canvas.")

    def save_temp_json(self):
        """Saves the current edits to the final JSON file for the annotator to read."""
        final_data = [r for r in self.regions_data if not r.get("deleted")]
        with self.final_json_path.open("w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2)

    def accept_final(self):
        """Finalizes the screen review and closes the window (FR-34)."""
        self.save_temp_json()
        
        # Ensure the final render happens if they didn't click preview
        # render_annotations(self.img_path, self.final_json_path, self.annotated_img_path)
        
        print(f"Finalized Screen {self.screen_index}. Data saved to {self.final_json_path.name}")
        self.root.destroy()

def open_review_ui(session_dir: Path, screen_index: int):
    root = tk.Tk()
    app = ReviewWindow(root, session_dir, screen_index)
    root.mainloop()

if __name__ == "__main__":
    # Test execution
    open_review_ui(Path("sessions/session_test"), 1)