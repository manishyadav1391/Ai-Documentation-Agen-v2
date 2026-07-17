import tkinter as tk
from tkinter import ttk, messagebox
import os
from pathlib import Path
from datetime import datetime
from docbot import paths

class ManualsView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        
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
        self.vbar = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.tree = ttk.Treeview(self.tree_frame, columns=("name", "type", "date", "size"),
                                 show="headings", selectmode="browse", yscrollcommand=self.vbar.set)
        self.vbar.config(command=self.tree.yview)
        
        self.tree.heading("name", text="Manual Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("date", text="Date Modified")
        self.tree.heading("size", text="Size")
        
        self.tree.column("name", width=300, minwidth=180, anchor="w")
        self.tree.column("type", width=120, minwidth=80, anchor="center")
        self.tree.column("date", width=160, minwidth=120, anchor="center")
        self.tree.column("size", width=100, minwidth=65, anchor="center")
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        
    def _build_buttons(self):
        ttk.Button(self.btn_frame, text="Open Manual", command=self.open_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Open Folder", command=self.open_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=4)
        
    def refresh(self):
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        outputs_dir = paths.outputs_dir()
        if not outputs_dir.exists():
            return
            
        files = []
        for ext in ("*.docx", "*.pdf"):
            for file_path in outputs_dir.glob(ext):
                try:
                    stat = file_path.stat()
                    modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    size_kb = max(1, int(stat.st_size / 1024))
                    manual_type = "Module Manual" if "User_Manual" in file_path.name else "Final Manual"
                    files.append((file_path, manual_type, modified_time, size_kb))
                except Exception as e:
                    import logging
                    logging.warning(f"Error reading file stats for {file_path}: {e}")
                    
        # Sort files by modified time descending (newest first)
        files.sort(key=lambda x: x[2], reverse=True)
        
        for f_path, m_type, m_time, s_kb in files:
            self.tree.insert("", tk.END, values=(f_path.name, m_type, m_time, f"{s_kb} KB"), tags=(str(f_path.resolve()),))
            
    def get_selected_path(self):
        selected = self.tree.selection()
        if not selected:
            return None
        tags = self.tree.item(selected[0], "tags")
        if not tags:
            return None
        return Path(tags[0])
        
    def open_selected(self):
        path = self.get_selected_path()
        if path:
            if path.exists():
                os.startfile(str(path))
            else:
                messagebox.showerror("Error", f"File not found: {path}")
                self.refresh()
        else:
            messagebox.showwarning("Warning", "Please select a manual to open.")
            
    def open_folder(self):
        outputs_dir = paths.outputs_dir()
        if outputs_dir.exists():
            os.startfile(str(outputs_dir.resolve()))
            
    def delete_selected(self):
        path = self.get_selected_path()
        if path:
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{path.name}'?"):
                try:
                    path.unlink()
                    self.refresh()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete file: {e}")
        else:
            messagebox.showwarning("Warning", "Please select a manual to delete.")
