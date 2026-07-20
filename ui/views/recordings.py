import tkinter as tk
from tkinter import ttk, messagebox
import json
import re
from pathlib import Path
from datetime import datetime
from docbot import paths

class RecordingsView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.session_mappings = []
        self._selection_order = []       # Track click-order of tree item ids
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Main Layout: Treeview on top, buttons on bottom
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree_frame.rowconfigure(0, weight=1)
        
        self.btn_frame = ttk.Frame(self)
        self.btn_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 12))
        
        self._build_tree()
        self._build_buttons()
        
    def _build_tree(self):
        # Treeview Scrollbar
        self.vbar = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.tree = ttk.Treeview(self.tree_frame, columns=("num", "name", "date", "screens", "status"),
                                 show="headings", selectmode="extended", yscrollcommand=self.vbar.set)
        self.vbar.config(command=self.tree.yview)
        
        self.tree.heading("num", text="No.")
        self.tree.heading("name", text="Module Name")
        self.tree.heading("date", text="Captured Time")
        self.tree.heading("screens", text="Screens")
        self.tree.heading("status", text="Status")
        
        self.tree.column("num", width=60, minwidth=40, anchor="center")
        self.tree.column("name", width=250, minwidth=150, anchor="w")
        self.tree.column("date", width=180, minwidth=120, anchor="center")
        self.tree.column("screens", width=80, minwidth=60, anchor="center")
        self.tree.column("status", width=100, minwidth=80, anchor="center")
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        
        self.tree.bind("<Double-1>", lambda e: self.open_review())
        # Track selection order as user clicks
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        
    def _on_selection_changed(self, event=None):
        """Maintain a click-ordered list of selected items."""
        current_sel = set(self.tree.selection())
        # Remove deselected items
        self._selection_order = [s for s in self._selection_order if s in current_sel]
        # Add newly selected items (in click order — they won't be in the list yet)
        for s in self.tree.selection():
            if s not in self._selection_order:
                self._selection_order.append(s)

    def _build_buttons(self):
        ttk.Button(self.btn_frame, text="Refresh Sessions", command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Open Review UI", command=self.open_review).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Delete Selected", style="Danger.TButton", command=self.delete_selected).pack(side=tk.LEFT, padx=4)
        
        # Primary Action on Right
        self.assemble_btn = ttk.Button(self.btn_frame, text="Assemble Master Manual", style="Primary.TButton", command=self.assemble_selected)
        self.assemble_btn.pack(side=tk.RIGHT, padx=4)
        
    def refresh(self):
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.session_mappings = []
        self._selection_order = []
        
        sessions_dir = paths.sessions_dir()
        if not sessions_dir.exists():
            return
            
        dirs = [p for p in sessions_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
        session_infos = []
        
        for d in dirs:
            session_file = d / "session.json"
            if session_file.exists():
                try:
                    with session_file.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    mod_name = data.get("module_name", "") or d.name
                    mod_num = data.get("module_number", "")
                    
                    screens = data.get("screens", [])
                    screens_cnt = len(screens)
                    is_reviewed = all(s.get("reviewed", False) for s in screens) if screens else False
                    status_text = "Reviewed ✓" if is_reviewed else "Draft"
                    
                    m = re.search(r"(\d{8}_\d{6})", d.name)
                    ts = m.group(1) if m else ""
                    if ts:
                        dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                        display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        display_time = "Unknown"
                        
                    session_infos.append({
                        "mtime": d.stat().st_mtime,
                        "folder": d.name,
                        "num": str(mod_num) if mod_num is not None else "",
                        "name": mod_name,
                        "date": display_time,
                        "screens": str(screens_cnt),
                        "status": status_text
                    })
                except Exception:
                    session_infos.append({
                        "mtime": d.stat().st_mtime,
                        "folder": d.name,
                        "num": "",
                        "name": d.name,
                        "date": "Unknown",
                        "screens": "0",
                        "status": "Corrupt"
                    })
                    
        # Sort sessions by modified time descending (newest first)
        session_infos.sort(key=lambda x: x["mtime"], reverse=True)
        
        for idx, info in enumerate(session_infos):
            item_id = self.tree.insert("", tk.END, values=(
                info["num"],
                info["name"],
                info["date"],
                info["screens"],
                info["status"]
            ))
            self.session_mappings.append(info["folder"])
            
    def get_selected_folders(self):
        """Return selected folders in the user's click order."""
        folders = []
        for sel in self._selection_order:
            idx = self.tree.index(sel)
            if 0 <= idx < len(self.session_mappings):
                folders.append(self.session_mappings[idx])
        return folders
        
    def _get_ordered_session_paths(self, folders):
        """
        Order session folders by module_number from session.json.
        Falls back to the user's click order if module numbers are missing.
        """
        session_entries = []
        for folder in folders:
            session_dir = paths.sessions_dir() / folder
            session_file = session_dir / "session.json"
            mod_num = None
            mod_name = folder
            if session_file.exists():
                try:
                    with session_file.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    raw_num = data.get("module_number")
                    if raw_num is not None and str(raw_num).strip():
                        try:
                            mod_num = int(raw_num)
                        except (ValueError, TypeError):
                            # Could be a string like "1.2"; use float
                            try:
                                mod_num = float(raw_num)
                            except (ValueError, TypeError):
                                mod_num = None
                    mod_name = data.get("module_name", "") or folder
                except Exception:
                    pass
            session_entries.append({
                "folder": folder,
                "mod_num": mod_num,
                "mod_name": mod_name,
                "path": session_dir,
            })

        # Sort by module_number if all entries have one; otherwise keep click order
        all_have_nums = all(e["mod_num"] is not None for e in session_entries)
        if all_have_nums:
            session_entries.sort(key=lambda e: e["mod_num"])

        return session_entries

    def open_review(self):
        folders = self.get_selected_folders()
        if not folders:
            messagebox.showwarning("Warning", "Select a session from the list to review.")
            return
        # Open review for the first selected session
        session_dir = paths.sessions_dir() / folders[0]
        self.app.open_review_window(session_dir)
        self.refresh()
        
    def delete_selected(self):
        folders = self.get_selected_folders()
        if not folders:
            messagebox.showwarning("Warning", "Please select one or more sessions to delete.")
            return
            
        confirm_msg = f"Are you sure you want to delete {len(folders)} selected session(s)?"
        if len(folders) == 1:
            confirm_msg = f"Are you sure you want to delete the session '{folders[0]}'?"
            
        if messagebox.askyesno("Confirm Delete", confirm_msg):
            import shutil
            for f in folders:
                session_dir = paths.sessions_dir() / f
                try:
                    shutil.rmtree(session_dir)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete '{f}':\n{e}")
            self.refresh()
            
    def assemble_selected(self):
        folders = self.get_selected_folders()
        if not folders:
            messagebox.showwarning("Warning", "Please select one or more modules (sessions) to assemble.")
            return
        
        # Get ordered entries (sorted by module_number)
        ordered_entries = self._get_ordered_session_paths(folders)

        # Show confirmation with assembly order
        order_lines = []
        for i, entry in enumerate(ordered_entries):
            num_str = f"Module {entry['mod_num']}" if entry["mod_num"] is not None else f"#{i+1}"
            order_lines.append(f"  {num_str}: {entry['mod_name']}")
        order_text = "\n".join(order_lines)

        confirm = messagebox.askyesno(
            "Confirm Assembly Order",
            f"The manual will be assembled in this order:\n\n{order_text}\n\nProceed?"
        )
        if not confirm:
            return

        session_paths = [e["path"] for e in ordered_entries]
        self.app.assemble_master_manual(session_paths)

