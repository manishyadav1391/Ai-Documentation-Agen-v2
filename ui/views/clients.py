import tkinter as tk
from tkinter import ttk, messagebox
import yaml
from pathlib import Path
from docbot import paths
from manual_builder.manifest_loader import get_available_clients

class ClientsView(ttk.Frame):
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
        self.tree = ttk.Treeview(self.tree_frame, columns=("key", "name", "version"),
                                 show="headings", selectmode="browse", yscrollcommand=self.vbar.set)
        self.vbar.config(command=self.tree.yview)
        
        self.tree.heading("key", text="Client Key")
        self.tree.heading("name", text="Display Name")
        self.tree.heading("version", text="Version")
        
        self.tree.column("key", width=120, minwidth=80, anchor="center")
        self.tree.column("name", width=300, minwidth=150, anchor="w")
        self.tree.column("version", width=100, minwidth=60, anchor="center")
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        
        self.tree.bind("<Double-1>", lambda e: self.open_settings())
        
    def _build_buttons(self):
        ttk.Button(self.btn_frame, text="Client Settings...", style="Primary.TButton", command=self.open_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="New Client...", command=self.new_client).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Open Content Folder", command=self.open_content_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=4)
        
    def refresh(self):
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        client_keys = get_available_clients()
        for key in client_keys:
            client_dir = paths.clients_dir() / key
            manifest_path = client_dir / "manifest.yaml"
            display_name = key.upper()
            version = "1.0"
            
            if manifest_path.exists():
                try:
                    with manifest_path.open("r", encoding="utf-8") as f:
                        m_data = yaml.safe_load(f) or {}
                    display_name = m_data.get("client_display_name", display_name)
                    version = m_data.get("version", version)
                except Exception:
                    pass
            
            # Select key if it matches the current client in app
            self.tree.insert("", tk.END, values=(key, display_name, version), tags=(key,))
            
    def get_selected_key(self):
        selected = self.tree.selection()
        if not selected:
            return None
        tags = self.tree.item(selected[0], "tags")
        if not tags:
            return None
        return tags[0]
        
    def open_settings(self):
        key = self.get_selected_key()
        if key:
            # Change the current active client to this select first
            self.app.change_client(key)
            self.app.open_style_editor()
            self.refresh()
        else:
            messagebox.showwarning("Warning", "Please select a client from the list.")
            
    def new_client(self):
        self.app.new_client()
        self.refresh()
        
    def open_content_folder(self):
        key = self.get_selected_key()
        if key:
            self.app.change_client(key)
            self.app.open_content_folder()
        else:
            messagebox.showwarning("Warning", "Please select a client from the list.")
