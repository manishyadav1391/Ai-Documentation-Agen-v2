"""
DocBot v3 — Launcher UI.

The primary entry point of the application. Allows selecting the active client
profile, modifying active client style rules, recording new modules with Start URL
and module name/number inputs, managing session history, compiling manuals, and
automatically opening outputs.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from pathlib import Path
import yaml
from loguru import logger

# Add project root directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Imports
from main import run_pipeline
from master_assembler import assemble_master_manual
from config import get_config, save_config, reload_config
from ui.style_editor import StyleEditorDialog
from docbot.clients.profile import ClientProfile


def get_available_clients_v3() -> list[str]:
    """List all clients under clients/ or legacy content/ directories."""
    config = get_config()
    clients = set()
    for d in [Path(config.clients_dir), Path(config.content_dir)]:
        if d.exists():
            for child in d.iterdir():
                if child.is_dir() and child.name != "_default":
                    # Client must have a manifest.yaml
                    if (child / "manifest.yaml").exists():
                        clients.add(child.name)
    return sorted(list(clients))


class StyleConfigDialog(tk.Toplevel):
    """Edits active client branding & styling settings directly inside style.yaml (W16)."""

    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.root_parent = parent
        self.client_key = ui_manager.client_key
        
        self.title(f"Configure Styling — Client: {self.client_key}")
        self.geometry("520x620")
        self.resizable(False, False)
        self.grab_set()

        # Load style config from client directory
        self.client_dir = Path("clients") / self.client_key
        if not self.client_dir.exists():
            self.client_dir = Path("content") / self.client_key  # legacy fallback
        self.client_dir.mkdir(parents=True, exist_ok=True)
        self.style_path = self.client_dir / "style.yaml"

        if not self.style_path.exists():
            # Copy default style (W16/T8.1)
            import shutil
            default_style = Path("clients/_default/style.yaml")
            if not default_style.exists():
                default_style = Path("styles/_default.yaml")
            if default_style.exists():
                shutil.copy(default_style, self.style_path)

        with self.style_path.open("r", encoding="utf-8") as f:
            self.style_data = yaml.safe_load(f) or {}


        # Force null sections to dict to prevent AttributeError / TypeError when saving settings
        for key in ["fonts", "colors", "logo"]:
            if key not in self.style_data or not isinstance(self.style_data[key], dict):
                self.style_data[key] = {}

        self.build_ui()


    def build_ui(self):
        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text=f"Styling Configuration — {self.client_key.upper()}", font=("Arial", 12, "bold"), fg="#1E293B").pack(pady=(0, 15))

        # --- Styling Section ---
        style_frame = tk.LabelFrame(main_frame, text="Design & Accent Colors", padx=10, pady=10)
        style_frame.pack(fill=tk.X, pady=5)

        # Font Combo
        tk.Label(style_frame, text="Font Family:").grid(row=0, column=0, sticky="w", pady=5)
        self.font_combo = ttk.Combobox(style_frame, values=["Segoe UI", "Arial", "Calibri", "Georgia", "Times New Roman"], state="readonly", width=18)
        self.font_combo.set(self.style_data["fonts"].get("body_family", "Segoe UI"))
        self.font_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # Primary Color
        tk.Label(style_frame, text="Primary Color (Hex):").grid(row=1, column=0, sticky="w", pady=5)
        self.primary_entry = tk.Entry(style_frame, width=12)
        primary_val = self.style_data["colors"].get("primary", "1B365D")
        if not primary_val.startswith("#"):
            primary_val = f"#{primary_val}"
        self.primary_entry.insert(0, primary_val)
        self.primary_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Pick...", command=lambda: self.pick_color(self.primary_entry)).grid(row=1, column=2, sticky="w", padx=2, pady=5)

        # Secondary Color
        tk.Label(style_frame, text="Secondary Color (Hex):").grid(row=2, column=0, sticky="w", pady=5)
        self.secondary_entry = tk.Entry(style_frame, width=12)
        secondary_val = self.style_data["colors"].get("secondary", "D97706")
        if not secondary_val.startswith("#"):
            secondary_val = f"#{secondary_val}"
        self.secondary_entry.insert(0, secondary_val)
        self.secondary_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Pick...", command=lambda: self.pick_color(self.secondary_entry)).grid(row=2, column=2, sticky="w", padx=2, pady=5)

        # Logo Path
        tk.Label(style_frame, text="Company Logo:").grid(row=3, column=0, sticky="w", pady=5)
        self.logo_entry = tk.Entry(style_frame, width=28)
        self.logo_entry.insert(0, self.style_data["logo"].get("path", ""))
        self.logo_entry.grid(row=3, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Browse...", command=self.browse_logo).grid(row=3, column=3, sticky="w", padx=2, pady=5)


        # --- Bottom Buttons ---
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Settings", bg="lightgreen", font=("Arial", 10, "bold"), width=15, command=self.save_settings).pack(side=tk.RIGHT, padx=5)

    def pick_color(self, entry_widget):
        curr_val = entry_widget.get()
        initial = curr_val if curr_val.startswith("#") else f"#{curr_val}"
        color_code = colorchooser.askcolor(title="Choose Accent Color", initialcolor=initial)
        if color_code and color_code[1]:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, color_code[1].upper())

    def browse_logo(self):
        file_path = filedialog.askopenfilename(
            title="Select Company Logo",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files", "*.*")]
        )
        if file_path:
            self.logo_entry.delete(0, tk.END)
            self.logo_entry.insert(0, file_path)

    def save_settings(self):
        font = self.font_combo.get()
        primary = self.primary_entry.get().strip().replace("#", "")
        secondary = self.secondary_entry.get().strip().replace("#", "")
        logo = self.logo_entry.get().strip()

        if len(primary) != 6 or len(secondary) != 6:
            messagebox.showerror("Error", "Colors must be valid 6-character hex strings.")
            return

        # Update style dictionary structure
        self.style_data.setdefault("fonts", {})["body_family"] = font
        self.style_data.setdefault("colors", {})["primary"] = primary
        self.style_data.setdefault("colors", {})["secondary"] = secondary
        self.style_data.setdefault("logo", {})["path"] = logo

        try:
            with self.style_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self.style_data, f, sort_keys=False)
            
            self.ui_manager.refresh_brand_summary()
            messagebox.showinfo("Success", "Branding settings saved successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")


class LauncherUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DocBot v3 — Control Launcher")
        self.root.geometry("720x720")
        self.root.resizable(False, False)
        
        self.config = get_config()
        self.client_key = self.config.current_client

        # Title
        tk.Label(root, text="DocBot v3 — Documentation Orchestrator", font=("Arial", 16, "bold"), fg="#1F3864").pack(pady=15)
        
        # Client Selector & Customization Frame
        client_frame = tk.LabelFrame(root, text="Active Client Configuration", padx=12, pady=10)
        client_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(client_frame, text="Select Client:").grid(row=0, column=0, sticky="w", pady=5)
        
        self.client_list = get_available_clients_v3()
        self.client_var = tk.StringVar(value=self.client_key)
        self.client_combo = ttk.Combobox(client_frame, textvariable=self.client_var, values=self.client_list, state="readonly", width=18)
        self.client_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.client_combo.bind("<<ComboboxSelected>>", self.on_client_change)

        tk.Button(client_frame, text="New Client...", bg="#F0FDF4", command=self.new_client).grid(row=0, column=2, sticky="w", padx=5, pady=5)

        # Active LLM Provider selector
        tk.Label(client_frame, text="LLM Provider:").grid(row=1, column=0, sticky="w", pady=5)
        self.provider_var = tk.StringVar(value=self.config.provider)
        self.provider_combo = ttk.Combobox(client_frame, textvariable=self.provider_var, values=["browser", "anthropic", "openai_compat", "ollama"], state="readonly", width=18)
        self.provider_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)

        # Style & Content Config Buttons
        ctrl_btn_frame = tk.Frame(client_frame)
        ctrl_btn_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=10)
        tk.Button(ctrl_btn_frame, text="Branding Settings...", bg="#EFF6FF", font=("Arial", 9, "bold"), command=self.open_style_editor).pack(side=tk.LEFT, padx=5)
        tk.Button(ctrl_btn_frame, text="Open Content Folder...", bg="#F5F5F5", font=("Arial", 9), command=self.open_content_folder).pack(side=tk.LEFT, padx=5)

        # Summary Display Label
        self.brand_label = tk.Label(client_frame, text="", font=("Arial", 9), fg="#475569", anchor="w", justify=tk.LEFT)
        self.brand_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=5)
        self.refresh_brand_summary()


        # Section 1: Record New Module (Expanded Inputs for Start URL, Name, Number)
        record_frame = tk.LabelFrame(root, text="1. Record New Module", padx=12, pady=10)
        record_frame.pack(fill=tk.X, padx=20, pady=8)
        
        # Grid inputs
        inputs_frame = tk.Frame(record_frame)
        inputs_frame.pack(fill=tk.X, pady=2)

        tk.Label(inputs_frame, text="Start URL:").grid(row=0, column=0, sticky="w", pady=3)
        self.url_entry = tk.Entry(inputs_frame, width=50)
        self.url_entry.insert(0, "https://google.com")
        self.url_entry.grid(row=0, column=1, columnspan=3, sticky="w", padx=5, pady=3)

        tk.Label(inputs_frame, text="Module Name:").grid(row=1, column=0, sticky="w", pady=3)
        self.module_name_entry = tk.Entry(inputs_frame, width=28)
        self.module_name_entry.insert(0, "Search Interface")
        self.module_name_entry.grid(row=1, column=1, sticky="w", padx=5, pady=3)

        tk.Label(inputs_frame, text="Number:").grid(row=1, column=2, sticky="w", pady=3)
        self.module_num_entry = tk.Entry(inputs_frame, width=8)
        self.module_num_entry.insert(0, "10")
        self.module_num_entry.grid(row=1, column=3, sticky="w", padx=5, pady=3)

        tk.Button(record_frame, text="Record New Module", bg="#2563EB", fg="white", font=("Arial", 10, "bold"), command=self.start_recording).pack(pady=8)
        
        # Section 2: Assemble Master Manual
        assemble_frame = tk.LabelFrame(root, text="2. Compile Master Client Manual", padx=12, pady=10)
        assemble_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=8)
        
        # Listbox for sessions
        self.session_listbox = tk.Listbox(assemble_frame, selectmode=tk.MULTIPLE, height=5, font=("Arial", 9))
        self.session_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.session_listbox.bind("<Double-1>", self._on_session_double_click)
        
        self.refresh_sessions()
        
        btn_frame = tk.Frame(assemble_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Refresh Sessions", command=self.refresh_sessions).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Open Review UI", command=self._open_selected_review).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Assemble Master Manual", bg="#059669", fg="white", font=("Arial", 10, "bold"), command=self.assemble_manual).pack(side=tk.RIGHT, padx=5)

    def on_client_change(self, event):
        self.client_key = self.client_var.get()
        self.config.current_client = self.client_key
        save_config(self.config)
        reload_config()
        self.refresh_brand_summary()

    def on_provider_change(self, event):
        provider = self.provider_var.get()
        self.config.provider = provider
        save_config(self.config)
        reload_config()
        logger.info(f"Active LLM provider updated to: {provider}")


    def refresh_brand_summary(self):
        try:
            profile = ClientProfile.load(self.client_key)
            summary = (
                f"Client: {profile.client_display_name} | System: {profile.system_name}\n"
                f"App Name: {profile.app_name} | Style: {profile.field_style} fields\n"
                f"Colors: Primary #{profile.get_color('primary')} | Secondary #{profile.get_color('secondary')} | Mode: {profile.numbering_mode}"
            )
        except Exception as e:
            summary = f"Error loading profile for '{self.client_key}':\n{e}"
        self.brand_label.config(text=summary)

    def open_style_editor(self):
        StyleConfigDialog(self.root, self)
        self.refresh_brand_summary()

    def open_content_folder(self):
        folder = Path("clients") / self.client_key
        if not folder.exists():
            folder = Path("content") / self.client_key
        if folder.exists():
            import os
            try:
                os.startfile(str(folder.resolve()))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder: {e}")
        else:
            messagebox.showerror("Error", f"Client directory does not exist: {folder}")

    def new_client(self):
        """Scaffold a new client directory under clients/ from defaults (T8.1)."""
        new_key = filedialog.asksaveasfilename(
            initialdir="clients",
            title="Enter New Client Key (Acronym Name)",
            filetypes=[]
        )
        if not new_key:
            return
        
        new_key = Path(new_key).name.lower().replace(" ", "_")
        if not new_key:
            return
            
        new_client_path = Path("clients") / new_key
        
        if new_client_path.exists():
            messagebox.showerror("Error", f"Client '{new_key}' already exists.")
            return
            
        import shutil
        try:
            shutil.copytree("clients/_default", str(new_client_path))
            
            # Update manifest client_key
            manifest_file = new_client_path / "manifest.yaml"
            if manifest_file.exists():
                with manifest_file.open("r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f) or {}
                manifest_data["client_key"] = new_key
                manifest_data["client_display_name"] = new_key.upper()
                with manifest_file.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(manifest_data, f, sort_keys=False)

            # Reload client list
            self.client_list = get_available_clients_v3()
            self.client_combo.config(values=self.client_list)
            self.client_var.set(new_key)
            self.on_client_change(None)
            messagebox.showinfo("Success", f"Client profile '{new_key}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create new client: {e}")

    def refresh_sessions(self):
        self.session_listbox.delete(0, tk.END)
        sessions_dir = Path("sessions")
        if sessions_dir.exists():
            for session in sorted(sessions_dir.glob("session_*")):
                self.session_listbox.insert(tk.END, session.name)

    def start_recording(self):
        start_url = self.url_entry.get().strip() or "https://google.com"
        mod_name = self.module_name_entry.get().strip()
        try:
            mod_num = int(self.module_num_entry.get().strip())
        except ValueError:
            mod_num = None

        self.root.iconify()
        try:
            run_pipeline(
                client_key=self.client_key,
                start_url=start_url,
                module_name=mod_name,
                module_number=mod_num
            )
            messagebox.showinfo("Success", "Module recorded and processed successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during capture: {e}")
        finally:
            try:
                if self.root.winfo_exists():
                    self.refresh_sessions()
                    self.root.deiconify()
            except Exception:
                pass

    def _on_session_double_click(self, event):
        self._open_selected_review()

    def _open_selected_review(self):
        sel = self.session_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a session from the list to review.")
            return
        session_name = self.session_listbox.get(sel[0])
        session_dir = Path("sessions") / session_name
        
        # Open in new v3 review UI
        from ui.review import open_review_ui
        open_review_ui(session_dir, screen_index=1)

    def assemble_manual(self):
        selected_indices = self.session_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select at least one module (session) to assemble.")
            return
            
        sessions_dir = Path("sessions")
        ordered_sessions = []
        for i in selected_indices:
            session_name = self.session_listbox.get(i)
            ordered_sessions.append(sessions_dir / session_name)
            
        output_path = Path("Final_Manuals/Final_Client_Manual.docx")
        try:
            assemble_master_manual(ordered_sessions, output_path, client_key=self.client_key)
            messagebox.showinfo("Success", f"Professional Manual compiled successfully!\nSaved to: {output_path.absolute()}")
            
            # Automatically open output folder (T8.1)
            import os
            os.startfile(str(output_path.parent.resolve()))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to assemble manual: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherUI(root)
    root.mainloop()