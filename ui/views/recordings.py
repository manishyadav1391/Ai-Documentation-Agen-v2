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
        selections = self.tree.selection()
        folders = []
        for sel in selections:
            idx = self.tree.index(sel)
            if 0 <= idx < len(self.session_mappings):
                folders.append(self.session_mappings[idx])
        return folders
        
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
        
        session_paths = [paths.sessions_dir() / f for f in folders]
        self.app.assemble_master_manual(session_paths)
