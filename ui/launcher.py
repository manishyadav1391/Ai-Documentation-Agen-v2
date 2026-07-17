"""
DocBot v3 — Launcher UI.

The primary entry point of the application. Allows selecting the active client
profile, modifying active client style rules, settings, recording new modules,
managing session history, compiling manuals, and automatically opening outputs.
"""

import sys
import os
import queue
import threading
import shutil
import re
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser, simpledialog
from pathlib import Path
from datetime import datetime
import yaml
from loguru import logger

# Add project root to sys.path so launcher can be run directly as python ui/launcher.py
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Imports
from main import run_pipeline
from master_assembler import assemble_master_manual
from config import get_config, save_config, reload_config
from docbot.clients.profile import ClientProfile
from manual_builder.manifest_loader import get_available_clients
from docbot import paths
from ui.settings_dialog import SettingsDialog

# -----------------------------------------------------------------------------
# Single Instance and Process Helpers
# -----------------------------------------------------------------------------

def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        # On Windows, os.kill(pid, 0) throws OSError. We check via ctypes.
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            err = ctypes.windll.kernel32.GetLastError()
            ERROR_ACCESS_DENIED = 5
            return err == ERROR_ACCESS_DENIED
        except Exception:
            return False

def check_single_instance() -> bool:
    lock_file = paths.data_dir() / "docbot.pid"
    if lock_file.exists():
        try:
            with lock_file.open("r") as f:
                old_pid = int(f.read().strip())
            if pid_exists(old_pid):
                logger.warning(f"Another instance of DocBot (PID {old_pid}) is already running.")
                return False
        except Exception:
            pass # stale lock file, overwrite it
            
    try:
        with lock_file.open("w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    return True

def check_chromium_exists() -> bool:
    browsers_dir = paths.data_dir() / "browsers"
    if not browsers_dir.exists():
        return False
    chromes = list(browsers_dir.glob("**/chrome.exe"))
    return len(chromes) > 0

# -----------------------------------------------------------------------------
# Reusable Progress Window
# -----------------------------------------------------------------------------

class ProgressWindow(tk.Toplevel):
    def __init__(self, parent, title="Please Wait", cancel_callback=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("540x380")
        self.resizable(False, False)
        self.grab_set()
        
        self.cancel_callback = cancel_callback
        
        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.title_lbl = tk.Label(main_frame, text=title, font=("Segoe UI", 11, "bold"), fg="#1E293B")
        self.title_lbl.pack(anchor="w", pady=(0, 5))
        
        self.status_lbl = tk.Label(main_frame, text="Initializing...", font=("Segoe UI", 9, "italic"))
        self.status_lbl.pack(anchor="w", pady=(0, 10))
        
        self.pb = ttk.Progressbar(main_frame, mode="indeterminate", length=510)
        self.pb.pack(fill=tk.X, pady=(0, 10))
        self.pb.start(10)
        
        log_frame = tk.LabelFrame(main_frame, text="Activity Log")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=8, font=("Courier New", 9), state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        
        self.cancel_btn = tk.Button(btn_frame, text="Cancel", width=12, command=self.on_cancel)
        self.cancel_btn.pack(side=tk.RIGHT)
        if not cancel_callback:
            self.cancel_btn.config(state=tk.DISABLED)
        
    def on_cancel(self):
        if self.cancel_callback:
            self.cancel_callback()
        self.log("Cancellation requested...")
        self.cancel_btn.config(state=tk.DISABLED)
        
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def set_status(self, text):
        self.status_lbl.config(text=text)

# -----------------------------------------------------------------------------
# Welcome Wizard
# -----------------------------------------------------------------------------

class WelcomeWizard(tk.Toplevel):
    def __init__(self, parent, launcher_ui):
        super().__init__(parent)
        self.parent = parent
        self.launcher_ui = launcher_ui
        self.title("Welcome to DocBot v3")
        self.geometry("560x440")
        self.resizable(False, False)
        self.grab_set()
        
        self.step = 1
        self.config = launcher_ui.config
        
        self.build_ui()
        self.show_step()
        
    def build_ui(self):
        self.main_frame = tk.Frame(self, padx=20, pady=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.container = tk.Frame(self.main_frame)
        self.container.pack(fill=tk.BOTH, expand=True)
        
        self.nav_frame = tk.Frame(self.main_frame)
        self.nav_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(15, 0))
        
        self.prev_btn = tk.Button(self.nav_frame, text="< Back", font=("Segoe UI", 9), command=self.go_back, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT)
        
        self.next_btn = tk.Button(self.nav_frame, text="Next >", font=("Segoe UI", 9, "bold"), bg="#2563EB", fg="white", command=self.go_next)
        self.next_btn.pack(side=tk.RIGHT)
        
    def show_step(self):
        for child in self.container.winfo_children():
            child.destroy()
            
        if self.step == 1:
            self.prev_btn.config(state=tk.DISABLED)
            self.next_btn.config(text="Next >")
            self.show_step1()
        elif self.step == 2:
            self.prev_btn.config(state=tk.NORMAL)
            self.next_btn.config(text="Next >")
            self.show_step2()
        elif self.step == 3:
            self.prev_btn.config(state=tk.NORMAL)
            self.next_btn.config(text="Finish")
            self.show_step3()
            
    def show_step1(self):
        tk.Label(self.container, text="Step 1: Choose Active Client Profile", font=("Segoe UI", 12, "bold"), fg="#1E293B").pack(anchor="w", pady=(0, 10))
        tk.Label(self.container, text="DocBot uses a client profile to format documentation, apply branding colors, fonts, and use glossary terms. Select an existing client profile or create a new one.", wraplength=500, justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 15))
        
        form_frame = tk.Frame(self.container)
        form_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(form_frame, text="Active Client:", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 10))
        self.client_var = tk.StringVar(value=self.config.current_client)
        self.client_combo = ttk.Combobox(form_frame, textvariable=self.client_var, values=self.launcher_ui.client_list, state="readonly", width=22)
        self.client_combo.pack(side=tk.LEFT)
        
        tk.Button(self.container, text="Create New Client...", font=("Segoe UI", 9), command=self.create_new_client).pack(anchor="w", pady=15)
        
    def show_step2(self):
        tk.Label(self.container, text="Step 2: Configure AI Provider", font=("Segoe UI", 12, "bold"), fg="#1E293B").pack(anchor="w", pady=(0, 10))
        tk.Label(self.container, text="Choose your AI model provider and configure API keys. If you don't have keys, you can select 'browser' (copy-paste) mode to start.", wraplength=500, justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 15))
        
        form_frame = tk.Frame(self.container)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(form_frame, text="Provider:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)
        self.provider_var = tk.StringVar(value=self.config.provider)
        self.provider_combo = ttk.Combobox(form_frame, textvariable=self.provider_var, values=["browser", "anthropic", "openai_compat", "ollama"], state="readonly", width=18)
        self.provider_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)
        
        tk.Label(form_frame, text="API Key:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=5)
        
        secrets_path = paths.data_dir() / "secrets.yaml"
        self.secrets = {}
        if secrets_path.exists():
            try:
                with secrets_path.open("r", encoding="utf-8") as f:
                    self.secrets = yaml.safe_load(f) or {}
            except Exception:
                pass
                
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(form_frame, textvariable=self.key_var, show="•", width=35)
        self.key_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        def toggle():
            if self.key_entry.cget("show") == "•":
                self.key_entry.config(show="")
            else:
                self.key_entry.config(show="•")
        self.show_btn = ttk.Checkbutton(form_frame, text="Show", command=toggle)
        self.show_btn.grid(row=1, column=2, sticky="w")
        
        self.test_btn = tk.Button(form_frame, text="Test Connection", font=("Segoe UI", 9), command=self.test_connection)
        self.test_btn.grid(row=2, column=1, sticky="e", pady=10)
        
        self.on_provider_change(None)
        
    def show_step3(self):
        tk.Label(self.container, text="Step 3: Ready to Document!", font=("Segoe UI", 12, "bold"), fg="#1E293B").pack(anchor="w", pady=(0, 10))
        tk.Label(self.container, text="You are fully set up to use DocBot v3!\n\nHere is how to record a user manual:\n"
                 "1. Enter the target application URL in the Start URL field.\n"
                 "2. Click 'Record New Module' to launch the browser.\n"
                 "3. Middle-click to capture screenshots as you navigate.\n"
                 "4. Double middle-click to finish and auto-generate content.\n"
                 "5. Review, adjust callouts, and assemble master manual.\n\n"
                 "Click Finish to launch the Control Panel.", wraplength=500, justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 15))
                 
    def create_new_client(self):
        self.launcher_ui.new_client()
        self.client_combo.config(values=self.launcher_ui.client_list)
        self.client_var.set(self.launcher_ui.client_key)
        
    def on_provider_change(self, event):
        provider = self.provider_var.get()
        if provider == "browser":
            self.key_entry.config(state=tk.DISABLED)
            self.key_var.set("")
            self.test_btn.config(state=tk.DISABLED)
        else:
            self.key_entry.config(state=tk.NORMAL)
            key_name = f"{provider}_api_key"
            self.key_var.set(self.secrets.get(key_name, ""))
            self.test_btn.config(state=tk.NORMAL)
            
    def test_connection(self):
        provider = self.provider_var.get()
        key = self.key_var.get().strip()
        if not key and provider != "ollama":
            messagebox.showerror("Error", "Please enter an API Key to test.")
            return
            
        self.test_btn.config(state=tk.DISABLED, text="Testing...")
        
        def run_test():
            try:
                import httpx
                if provider == "anthropic":
                    client = httpx.Client(
                        base_url="https://api.anthropic.com",
                        headers={"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
                        timeout=httpx.Timeout(12.0, connect=5.0)
                    )
                    payload = {
                        "model": self.config.providers.anthropic.model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "Reply with OK"}]
                    }
                    resp = client.post("/v1/messages", json=payload)
                    resp.raise_for_status()
                elif provider == "openai_compat":
                    client = httpx.Client(
                        base_url=self.config.providers.openai_compat.base_url,
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                        timeout=httpx.Timeout(12.0, connect=5.0)
                    )
                    payload = {
                        "model": self.config.providers.openai_compat.model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "Reply with OK"}]
                    }
                    resp = client.post("/chat/completions", json=payload)
                    resp.raise_for_status()
                elif provider == "ollama":
                    headers = {"Content-Type": "application/json"}
                    if key:
                        headers["Authorization"] = f"Bearer {key}"
                    client = httpx.Client(
                        base_url=self.config.providers.ollama.host.rstrip("/"),
                        headers=headers,
                        timeout=httpx.Timeout(12.0, connect=5.0)
                    )
                    payload = {
                        "model": self.config.providers.ollama.model,
                        "stream": False,
                        "messages": [{"role": "user", "content": "Reply with OK"}],
                        "options": {"num_predict": 10}
                    }
                    resp = client.post("/api/chat", json=payload)
                    resp.raise_for_status()
                
                self.parent.after(0, lambda: messagebox.showinfo("Connection Test", "✓ Connection Successful!"))
            except Exception as e:
                self.parent.after(0, lambda: messagebox.showerror("Connection Test", f"✗ Connection Failed:\n{e}"))
            finally:
                self.parent.after(0, lambda: self.test_btn.config(state=tk.NORMAL, text="Test Connection"))
                
        threading.Thread(target=run_test, daemon=True).start()
        
    def go_back(self):
        if self.step > 1:
            self.step -= 1
            self.show_step()
            
    def go_next(self):
        if self.step == 1:
            client = self.client_var.get()
            self.config.current_client = client
            save_config(self.config)
            reload_config()
            self.launcher_ui.client_key = client
            self.launcher_ui.client_var.set(client)
            self.launcher_ui.refresh_brand_summary()
            
            self.step += 1
            self.show_step()
        elif self.step == 2:
            provider = self.provider_var.get()
            self.config.provider = provider
            save_config(self.config)
            reload_config()
            self.launcher_ui.provider_var.set(provider)
            
            if provider != "browser":
                key = self.key_var.get().strip()
                key_name = f"{provider}_api_key"
                self.secrets[key_name] = key
                try:
                    secrets_path = paths.data_dir() / "secrets.yaml"
                    with secrets_path.open("w", encoding="utf-8") as f:
                        yaml.safe_dump(self.secrets, f, default_flow_style=False)
                except Exception:
                    pass
            self.launcher_ui.check_provider_status()
            
            self.step += 1
            self.show_step()
        elif self.step == 3:
            self.config.first_run_done = True
            save_config(self.config)
            self.destroy()

# -----------------------------------------------------------------------------
# Client Configuration Settings Dialog
# -----------------------------------------------------------------------------

class ClientSettingsDialog(tk.Toplevel):
    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.client_key = ui_manager.client_key
        
        self.title(f"Client Settings — Client: {self.client_key.upper()}")
        self.geometry("640x720")
        self.resizable(False, False)
        self.grab_set()

        # Paths
        self.client_dir = paths.clients_dir() / self.client_key
        self.client_dir.mkdir(parents=True, exist_ok=True)
        
        self.manifest_path = self.client_dir / "manifest.yaml"
        self.style_path = self.client_dir / "style.yaml"
        self.voice_path = self.client_dir / "voice.yaml"
        self.glossary_path = self.client_dir / "glossary.yaml"
        
        default_dir = paths.clients_dir() / "_default"
        
        # Load configs
        self.manifest_data = self._load_yaml(self.manifest_path, default_dir / "manifest.yaml")
        self.style_data = self._load_yaml(self.style_path, default_dir / "style.yaml")
        self.voice_data = self._load_yaml(self.voice_path, default_dir / "voice.yaml")
        self.glossary_data = self._load_yaml(self.glossary_path, default_dir / "glossary.yaml")
        
        # Normalize glossary
        if isinstance(self.glossary_data, list):
            self.glossary_data = {
                entry.get("term", ""): entry.get("definition", "")
                for entry in self.glossary_data
                if isinstance(entry, dict)
            }
        self.glossary_data = self.glossary_data or {}
        
        # Resolve content folder for cover.yaml
        content_sub = self.client_dir / "content"
        self.resolved_content_dir = content_sub if content_sub.exists() else (paths.content_dir() / self.client_key)
        self.cover_path = self.resolved_content_dir / "cover.yaml"
        
        default_content_dir = paths.content_dir() / "_default"
        self.cover_data = self._load_yaml(self.cover_path, default_content_dir / "cover.yaml")
        
        # Sanity check dict structs
        for key in ["fonts", "colors", "logo", "cover"]:
            if key not in self.style_data or not isinstance(self.style_data[key], dict):
                self.style_data[key] = {}
        
        self.build_ui()

    def _load_yaml(self, primary: Path, fallback: Path) -> dict:
        if primary.exists():
            try:
                with primary.open("r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        if fallback.exists():
            try:
                with fallback.open("r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def build_ui(self):
        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text=f"Client Settings Configuration — {self.client_key.upper()}", 
                 font=("Segoe UI", 12, "bold"), fg="#1E293B").pack(pady=(0, 15))

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # --- Tab 1: Identity ---
        t1 = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(t1, text="Identity (manifest)")
        
        tk.Label(t1, text="Client Display Name:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.client_display_name_entry = tk.Entry(t1, width=35)
        self.client_display_name_entry.insert(0, self.manifest_data.get("client_display_name", ""))
        self.client_display_name_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="System Name:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=5)
        self.system_name_entry = tk.Entry(t1, width=35)
        self.system_name_entry.insert(0, self.manifest_data.get("system_name", ""))
        self.system_name_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="System Acronym:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=5)
        self.system_acronym_entry = tk.Entry(t1, width=15)
        self.system_acronym_entry.insert(0, self.manifest_data.get("system_acronym", ""))
        self.system_acronym_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Manual Title:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=5)
        self.manual_title_entry = tk.Entry(t1, width=35)
        self.manual_title_entry.insert(0, self.manifest_data.get("manual_title", "User Manual"))
        self.manual_title_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Document Version:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=5)
        self.version_entry = tk.Entry(t1, width=15)
        self.version_entry.insert(0, self.manifest_data.get("version", "1.0"))
        self.version_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Revision Prepared By:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=5)
        self.prepared_by_entry = tk.Entry(t1, width=35)
        self.prepared_by_entry.insert(0, self.manifest_data.get("prepared_by", ""))
        self.prepared_by_entry.grid(row=5, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Revision Reviewed By:", font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=5)
        self.reviewed_by_entry = tk.Entry(t1, width=35)
        self.reviewed_by_entry.insert(0, self.manifest_data.get("reviewed_by", ""))
        self.reviewed_by_entry.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Revision Approved By:", font=("Segoe UI", 9)).grid(row=7, column=0, sticky="w", pady=5)
        self.approved_by_entry = tk.Entry(t1, width=35)
        self.approved_by_entry.insert(0, self.manifest_data.get("approved_by", ""))
        self.approved_by_entry.grid(row=7, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t1, text="Numbering Mode:", font=("Segoe UI", 9)).grid(row=8, column=0, sticky="w", pady=5)
        self.num_mode_combo = ttk.Combobox(t1, values=["module_prefixed", "continuous"], state="readonly", width=18)
        self.num_mode_combo.set(self.manifest_data.get("numbering_mode", "module_prefixed"))
        self.num_mode_combo.grid(row=8, column=1, sticky="w", padx=5, pady=5)

        # --- Tab 2: Branding ---
        t2 = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(t2, text="Branding (style)")

        tk.Label(t2, text="Font Family:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)
        self.font_combo = ttk.Combobox(t2, values=["Segoe UI", "Arial", "Calibri", "Georgia", "Times New Roman"], state="readonly", width=18)
        self.font_combo.set(self.style_data["fonts"].get("body_family", "Segoe UI"))
        self.font_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t2, text="Body Font Size (pt):", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=5)
        self.font_size_spin = ttk.Spinbox(t2, from_=8, to=24, increment=0.5, width=10)
        self.font_size_spin.set(str(self.style_data["fonts"].get("body_size_pt", 10.5)))
        self.font_size_spin.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t2, text="Primary Color (Hex):", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=5)
        self.primary_entry = tk.Entry(t2, width=12)
        p_val = self.style_data["colors"].get("primary", "1B365D")
        self.primary_entry.insert(0, f"#{p_val}" if not p_val.startswith("#") else p_val)
        self.primary_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        tk.Button(t2, text="Pick...", command=lambda: self.pick_color(self.primary_entry)).grid(row=2, column=2, sticky="w", padx=2, pady=5)

        tk.Label(t2, text="Secondary Color (Hex):", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=5)
        self.secondary_entry = tk.Entry(t2, width=12)
        s_val = self.style_data["colors"].get("secondary", "D97706")
        self.secondary_entry.insert(0, f"#{s_val}" if not s_val.startswith("#") else s_val)
        self.secondary_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        tk.Button(t2, text="Pick...", command=lambda: self.pick_color(self.secondary_entry)).grid(row=3, column=2, sticky="w", padx=2, pady=5)

        tk.Label(t2, text="Company Logo File:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=5)
        self.logo_entry = tk.Entry(t2, width=32)
        self.logo_entry.insert(0, self.style_data["logo"].get("path", ""))
        self.logo_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        tk.Button(t2, text="Browse...", command=self.browse_logo).grid(row=4, column=2, sticky="w", padx=2, pady=5)

        # Cover details
        tk.Label(t2, text="Cover Title text:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=5)
        self.cover_title_entry = tk.Entry(t2, width=35)
        title_lines = self.cover_data.get("title_lines", [])
        self.cover_title_entry.insert(0, title_lines[0] if len(title_lines) > 0 else "")
        self.cover_title_entry.grid(row=5, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        tk.Label(t2, text="Cover Subtitle text:", font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=5)
        self.cover_subtitle_entry = tk.Entry(t2, width=35)
        self.cover_subtitle_entry.insert(0, title_lines[1] if len(title_lines) > 1 else "")
        self.cover_subtitle_entry.grid(row=6, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        # --- Tab 3: Writing Voice ---
        t3 = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(t3, text="Voice (rules)")

        tk.Label(t3, text="App Name in Prose:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)
        self.app_name_entry = tk.Entry(t3, width=35)
        self.app_name_entry.insert(0, self.voice_data.get("app_name", ""))
        self.app_name_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        tk.Label(t3, text="Fields Styling Mode:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=5)
        self.field_style_var = tk.StringVar(value=self.style_data.get("fields", {}).get("style", "table"))
        tk.Radiobutton(t3, text="Grid/Table layout", variable=self.field_style_var, value="table").grid(row=1, column=1, sticky="w", padx=5, pady=5)
        tk.Radiobutton(t3, text="Bullet list layout", variable=self.field_style_var, value="bullets").grid(row=1, column=2, sticky="w", padx=5, pady=5)

        tk.Label(t3, text="Navigation Sentence:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=5)
        self.nav_temp_entry = tk.Entry(t3, width=45)
        self.nav_temp_entry.insert(0, self.voice_data.get("navigation_template", "Navigate to {screen_name}."))
        self.nav_temp_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        tk.Label(t3, text="Tone/Writing Rules (one per line):", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=5)
        self.tone_rules_text = tk.Text(t3, width=50, height=8, font=("Segoe UI", 9))
        self.tone_rules_text.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="we")
        rules = self.voice_data.get("tone_rules", [])
        self.tone_rules_text.insert(tk.END, "\n".join(rules))

        # --- Tab 4: Glossary ---
        t4 = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(t4, text="Glossary terms")

        # Treeview grid
        self.glossary_tree = ttk.Treeview(t4, columns=("Term", "Definition"), show="headings", height=8)
        self.glossary_tree.heading("Term", text="Term / Acronym")
        self.glossary_tree.heading("Definition", text="Definition / Expansion")
        self.glossary_tree.column("Term", width=120)
        self.glossary_tree.column("Definition", width=340)
        self.glossary_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.glossary_tree.bind("<<TreeviewSelect>>", self._on_glossary_select)

        # Editor frame below list
        g_edit = tk.Frame(t4)
        g_edit.pack(fill=tk.X)

        tk.Label(g_edit, text="Term:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.term_entry = tk.Entry(g_edit, width=20)
        self.term_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        tk.Label(g_edit, text="Definition:", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", pady=2)
        self.defn_entry = tk.Entry(g_edit, width=32)
        self.defn_entry.grid(row=0, column=3, sticky="we", padx=5, pady=2)

        btn_g_frame = tk.Frame(t4, pady=5)
        btn_g_frame.pack(fill=tk.X)
        tk.Button(btn_g_frame, text="Add / Update", bg="#EFF6FF", command=self._add_glossary_term).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_g_frame, text="Remove Selected", bg="#FEE2E2", fg="#B91C1C", command=self._remove_glossary_term).pack(side=tk.LEFT, padx=5)

        self._refresh_glossary_tree()

        # Bottom buttons
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Settings", bg="lightgreen", font=("Segoe UI", 10, "bold"), width=15, command=self.save_settings).pack(side=tk.RIGHT, padx=5)

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
            assets_dir = self.client_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            dst_path = assets_dir / Path(file_path).name
            try:
                shutil.copy2(file_path, dst_path)
                self.logo_entry.delete(0, tk.END)
                self.logo_entry.insert(0, f"assets/{dst_path.name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy logo file: {e}")

    def _add_glossary_term(self):
        term = self.term_entry.get().strip()
        defn = self.defn_entry.get().strip()
        if not term:
            messagebox.showerror("Error", "Term cannot be empty.")
            return
        
        self.glossary_data[term] = defn
        self._refresh_glossary_tree()
        self.term_entry.delete(0, tk.END)
        self.defn_entry.delete(0, tk.END)
        
    def _remove_glossary_term(self):
        sel = self.glossary_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a term from the list to remove.")
            return
        term = self.glossary_tree.item(sel[0], "values")[0]
        if term in self.glossary_data:
            del self.glossary_data[term]
        self._refresh_glossary_tree()
        self.term_entry.delete(0, tk.END)
        self.defn_entry.delete(0, tk.END)
        
    def _refresh_glossary_tree(self):
        self.glossary_tree.delete(*self.glossary_tree.get_children())
        for term, defn in sorted(self.glossary_data.items()):
            self.glossary_tree.insert("", tk.END, values=(term, defn))
            
    def _on_glossary_select(self, event):
        sel = self.glossary_tree.selection()
        if sel:
            values = self.glossary_tree.item(sel[0], "values")
            self.term_entry.delete(0, tk.END)
            self.term_entry.insert(0, values[0])
            self.defn_entry.delete(0, tk.END)
            self.defn_entry.insert(0, values[1])

    def save_settings(self):
        # 1. Validation
        disp_name = self.client_display_name_entry.get().strip()
        if not disp_name:
            messagebox.showerror("Validation Error", "Client Display Name cannot be empty.")
            return

        primary = self.primary_entry.get().strip().replace("#", "")
        secondary = self.secondary_entry.get().strip().replace("#", "")
        if len(primary) != 6 or len(secondary) != 6:
            messagebox.showerror("Validation Error", "Accent colors must be valid 6-character hex strings.")
            return

        # 2. Write Tab 1 (Identity -> manifest.yaml)
        self.manifest_data["client_display_name"] = disp_name
        self.manifest_data["system_name"] = self.system_name_entry.get().strip()
        self.manifest_data["system_acronym"] = self.system_acronym_entry.get().strip()
        self.manifest_data["manual_title"] = self.manual_title_entry.get().strip()
        self.manifest_data["version"] = self.version_entry.get().strip()
        self.manifest_data["prepared_by"] = self.prepared_by_entry.get().strip()
        self.manifest_data["reviewed_by"] = self.reviewed_by_entry.get().strip()
        self.manifest_data["approved_by"] = self.approved_by_entry.get().strip()
        self.manifest_data["numbering_mode"] = self.num_mode_combo.get()

        # 3. Write Tab 2 (Branding -> style.yaml)
        self.style_data["fonts"]["body_family"] = self.font_combo.get()
        try:
            self.style_data["fonts"]["body_size_pt"] = float(self.font_size_spin.get().strip())
        except ValueError:
            pass
        self.style_data["colors"]["primary"] = primary
        self.style_data["colors"]["secondary"] = secondary
        self.style_data["logo"]["path"] = self.logo_entry.get().strip()
        self.style_data["fields"] = {"style": self.field_style_var.get()}

        # 4. Write cover page metadata (cover.yaml)
        self.resolved_content_dir.mkdir(parents=True, exist_ok=True)
        cover_data = {
            "document_title": self.manual_title_entry.get().strip(),
            "title_lines": [
                self.cover_title_entry.get().strip(),
                self.cover_subtitle_entry.get().strip()
            ]
        }
        try:
            with self.cover_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cover_data, f, sort_keys=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Failed to save cover.yaml: {e}")

        # 5. Write Tab 3 (Voice -> voice.yaml)
        self.voice_data["app_name"] = self.app_name_entry.get().strip()
        self.voice_data["navigation_template"] = self.nav_temp_entry.get().strip()
        # Parse multiline rules text
        rules_text = self.tone_rules_text.get("1.0", tk.END).strip()
        self.voice_data["tone_rules"] = [r.strip() for r in rules_text.split("\n") if r.strip()]

        # 6. Write Tab 4 (Glossary -> glossary.yaml)
        glossary_output = self.glossary_data

        try:
            with self.manifest_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self.manifest_data, f, sort_keys=False, allow_unicode=True)
            with self.style_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self.style_data, f, sort_keys=False, allow_unicode=True)
            with self.voice_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self.voice_data, f, sort_keys=False, allow_unicode=True)
            with self.glossary_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(glossary_output, f, sort_keys=False, allow_unicode=True)

            self.ui_manager.refresh_brand_summary()
            messagebox.showinfo("Success", "Client Settings saved successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

# -----------------------------------------------------------------------------
# Launcher main UI
# -----------------------------------------------------------------------------

class LauncherUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DocBot v3 — Control Launcher")
        self.root.geometry("740x740")
        self.root.resizable(False, False)
        
        self.config = get_config()
        self.client_key = self.config.current_client

        # Install global exception handlers
        self.setup_global_crash_handler()

        # Check single instance
        if not check_single_instance():
            messagebox.showerror("DocBot Active", "Another copy of DocBot is already running on this machine.")
            self.root.destroy()
            sys.exit(0)

        # Title
        tk.Label(root, text="DocBot v3 — Documentation Orchestrator", font=("Arial", 16, "bold"), fg="#1F3864").pack(pady=15)
        
        # Client Selector & Customization Frame
        client_frame = tk.LabelFrame(root, text="Active Client Configuration", padx=12, pady=10)
        client_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(client_frame, text="Select Client:").grid(row=0, column=0, sticky="w", pady=5)
        
        self.client_list = get_available_clients()
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

        # Inline validation status label next to provider selector (Phase 3.4)
        self.provider_status_lbl = tk.Label(client_frame, text="", font=("Arial", 9, "bold"))
        self.provider_status_lbl.grid(row=1, column=2, sticky="w", padx=5, pady=5)

        # Style & Content Config Buttons
        ctrl_btn_frame = tk.Frame(client_frame)
        ctrl_btn_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=10)
        tk.Button(ctrl_btn_frame, text="Client Settings...", bg="#EFF6FF", font=("Arial", 9, "bold"), command=self.open_style_editor).pack(side=tk.LEFT, padx=5)
        tk.Button(ctrl_btn_frame, text="⚙ Settings / API Keys...", bg="#FFFBEB", fg="#92400E", font=("Arial", 9, "bold"), command=self.open_settings_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(ctrl_btn_frame, text="Open Content Folder...", bg="#F5F5F5", font=("Arial", 9), command=self.open_content_folder).pack(side=tk.LEFT, padx=5)

        # Summary Display Label
        self.brand_label = tk.Label(client_frame, text="", font=("Arial", 9), fg="#475569", anchor="w", justify=tk.LEFT)
        self.brand_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=5)
        self.refresh_brand_summary()
        self.check_provider_status()

        # Section 1: Record New Module
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

        self.record_btn = tk.Button(record_frame, text="Record New Module", bg="#2563EB", fg="white", font=("Arial", 10, "bold"), command=self.start_recording)
        self.record_btn.pack(pady=8)
        
        # Section 2: Assemble Master Manual
        assemble_frame = tk.LabelFrame(root, text="2. Compile Master Client Manual", padx=12, pady=10)
        assemble_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=8)
        
        # Listbox for sessions
        self.session_listbox = tk.Listbox(assemble_frame, selectmode=tk.MULTIPLE, height=5, font=("Arial", 9))
        self.session_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.session_listbox.bind("<Double-1>", self._on_session_double_click)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        
        self.selected_session_indices = []
        self.session_mappings = []
        self.refresh_sessions()
        
        btn_frame = tk.Frame(assemble_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.refresh_btn = tk.Button(btn_frame, text="Refresh Sessions", command=self.refresh_sessions)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        self.review_btn = tk.Button(btn_frame, text="Open Review UI", command=self._open_selected_review)
        self.review_btn.pack(side=tk.LEFT, padx=5)
        self.view_manuals_btn = tk.Button(btn_frame, text="View Generated Manuals", bg="#3B82F6", fg="white", font=("Arial", 9, "bold"), command=self.open_manuals_viewer)
        self.view_manuals_btn.pack(side=tk.LEFT, padx=5)
        self.assemble_btn = tk.Button(btn_frame, text="Assemble Master Manual", bg="#059669", fg="white", font=("Arial", 10, "bold"), command=self.assemble_manual)
        self.assemble_btn.pack(side=tk.RIGHT, padx=5)

        # Trigger Welcome Wizard if first run (Phase 8)
        if not self.config.first_run_done:
            self.root.after(200, self.show_welcome_wizard)
        else:
            # Gentle warning prompt if key missing on launch (Phase 3.3)
            self.root.after(300, self.prompt_missing_key_startup)

    def setup_global_crash_handler(self):
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logger.opt(exception=(exc_type, exc_value, exc_traceback)).error("Uncaught exception in launcher loop")
            log_file = paths.logs_dir() / "docbot.log"
            messagebox.showerror(
                "Something went wrong",
                f"An unexpected critical crash occurred.\n\n"
                f"Details were saved to:\n{log_file.resolve()}\n\n"
                f"Error: {exc_value}"
            )
        sys.excepthook = handle_exception
        self.root.report_callback_exception = handle_exception

    def show_welcome_wizard(self):
        WelcomeWizard(self.root, self)

    def _set_buttons_state(self, state):
        self.record_btn.config(state=state)
        self.assemble_btn.config(state=state)
        self.refresh_btn.config(state=state)
        self.review_btn.config(state=state)
        self.view_manuals_btn.config(state=state)
        self.client_combo.config(state="disabled" if state == tk.DISABLED else "readonly")
        self.provider_combo.config(state="disabled" if state == tk.DISABLED else "readonly")

    def check_provider_status(self):
        provider = self.provider_var.get()
        if provider == "browser":
            self.provider_status_lbl.config(text="✓ Local copy-paste", fg="green")
            return
        
        try:
            from main import get_provider_instance
            p_inst = get_provider_instance(self.config)
            if provider == "ollama":
                is_local = "localhost" in p_inst.host or "127.0.0.1" in p_inst.host
                if is_local or p_inst.api_key:
                    self.provider_status_lbl.config(text="✓ Ollama Ready", fg="green")
                else:
                    self.provider_status_lbl.config(text="✗ API Key missing", fg="red")
            else:
                if p_inst.is_available():
                    self.provider_status_lbl.config(text="✓ Key configured", fg="green")
                else:
                    self.provider_status_lbl.config(text="✗ Key missing", fg="red")
        except Exception:
            self.provider_status_lbl.config(text="✗ Connection error", fg="red")

    def prompt_missing_key_startup(self):
        provider = self.provider_var.get()
        if provider != "browser":
            try:
                from main import get_provider_instance
                p_inst = get_provider_instance(self.config)
                if provider == "ollama" and ("localhost" in p_inst.host or "127.0.0.1" in p_inst.host):
                    return
                if not p_inst.is_available():
                    messagebox.showinfo(
                        "API Key Required",
                        f"The selected provider '{provider}' requires an API key.\n"
                        "Please click the '⚙ Settings / API Keys...' button to configure your API key."
                    )
            except Exception:
                pass

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
        self.check_provider_status()
        self.prompt_missing_key_startup()

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
        ClientSettingsDialog(self.root, self)
        self.refresh_brand_summary()

    def open_settings_dialog(self):
        SettingsDialog(self.root, self)

    def open_content_folder(self):
        folder = paths.clients_dir() / self.client_key
        if not folder.exists():
            folder = paths.content_dir() / self.client_key
        if folder.exists():
            try:
                os.startfile(str(folder.resolve()))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder: {e}")
        else:
            messagebox.showerror("Error", f"Client directory does not exist: {folder}")

    def new_client(self):
        """Scaffold a new client directory under clients/ from defaults."""
        new_key = filedialog.asksaveasfilename(
            initialdir=str(paths.clients_dir()),
            title="Enter New Client Key (Acronym Name)",
            filetypes=[]
        )
        if not new_key:
            return
        
        new_key = Path(new_key).name.lower().replace(" ", "_")
        if not new_key:
            return
            
        new_client_path = paths.clients_dir() / new_key
        
        if new_client_path.exists():
            messagebox.showerror("Error", f"Client '{new_key}' already exists.")
            return
            
        try:
            shutil.copytree(str(paths.clients_dir() / "_default"), str(new_client_path))
            
            new_content_path = new_client_path / "content"
            shutil.copytree(str(paths.content_dir() / "_default"), str(new_content_path))
            
            manifest_file = new_client_path / "manifest.yaml"
            if manifest_file.exists():
                with manifest_file.open("r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f) or {}
                manifest_data["client_key"] = new_key
                manifest_data["client_display_name"] = new_key.upper()
                with manifest_file.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(manifest_data, f, sort_keys=False)

            self.client_list = get_available_clients()
            self.client_combo.config(values=self.client_list)
            self.client_var.set(new_key)
            self.on_client_change(None)
            
            self.open_style_editor()
            messagebox.showinfo("Success", f"Client profile '{new_key}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create new client: {e}")

    def refresh_sessions(self):
        self.session_listbox.delete(0, tk.END)
        self.selected_session_indices = []
        self.session_mappings = []
        
        sessions_dir = paths.sessions_dir()
        if sessions_dir.exists():
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
                        
                        m = re.search(r"(\d{8}_\d{6})", d.name)
                        ts = m.group(1) if m else ""
                        if ts:
                            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                            display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            display_time = "Unknown time"
                            
                        display_name = f"{mod_name}"
                        if mod_num is not None and str(mod_num).strip():
                            display_name = f"Module {mod_num}: {display_name}"
                        display_name = f"{display_name} ({display_time})"
                        
                        session_infos.append((d.stat().st_mtime, d.name, display_name))
                    except Exception:
                        session_infos.append((d.stat().st_mtime, d.name, d.name))
                else:
                    pass
            
            session_infos.sort(key=lambda x: x[0], reverse=True)
            
            for mtime, folder_name, display_name in session_infos:
                self.session_listbox.insert(tk.END, display_name)
                self.session_mappings.append(folder_name)

    def check_and_install_browser(self) -> bool:
        if check_chromium_exists():
            return True
            
        if not messagebox.askyesno(
            "Browser Download Required",
            "DocBot needs to download its browser (~150 MB) before recording. This is a one-time process.\n\n"
            "Do you want to download and install it now?"
        ):
            return False
            
        msg_queue = queue.Queue()
        progress_win = ProgressWindow(self.root, title="Downloading Browser")
        progress_win.log("Starting Chromium browser download...")
        progress_win.set_status("Installing playwright browsers...")
        
        install_success = [False]
        
        def run_install():
            try:
                import sys
                import subprocess
                
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(paths.data_dir() / "browsers")
                
                if paths.is_frozen():
                    progress_win.log("Loading playwright CLI...")
                    from playwright.__main__ import main as pw_main
                    old_argv = sys.argv
                    sys.argv = ["playwright", "install", "chromium"]
                    try:
                        pw_main()
                    finally:
                        sys.argv = old_argv
                else:
                    progress_win.log(f"Running: {sys.executable} -m playwright install chromium")
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                    
                msg_queue.put(("done", "Installed!"))
            except Exception as e:
                logger.exception("Playwright install failed")
                msg_queue.put(("error", str(e)))
                
        worker = threading.Thread(target=run_install, daemon=True)
        worker.start()
        
        def poll_queue():
            try:
                while True:
                    msg_type, data = msg_queue.get_nowait()
                    if msg_type == "done":
                        install_success[0] = True
                        progress_win.destroy()
                        messagebox.showinfo("Success", "Browser downloaded and installed successfully!")
                        return
                    elif msg_type == "error":
                        progress_win.destroy()
                        messagebox.showerror("Download Error", f"Browser download failed: {data}")
                        return
            except queue.Empty:
                pass
            
            if worker.is_alive() or not msg_queue.empty():
                self.root.after(100, poll_queue)
            else:
                progress_win.destroy()
                
        self.root.after(100, poll_queue)
        self.root.wait_window(progress_win)
        return install_success[0]

    def start_recording(self):
        start_url = self.url_entry.get().strip() or "https://google.com"
        mod_name = self.module_name_entry.get().strip()
        mod_num_raw = self.module_num_entry.get().strip()
        
        if not start_url:
            messagebox.showerror("Validation Error", "Start URL cannot be empty.")
            return
        if not (start_url.startswith("http://") or start_url.startswith("https://")):
            messagebox.showerror("Validation Error", "Start URL must start with http:// or https://")
            return
        if not mod_name:
            messagebox.showerror("Validation Error", "Module Name cannot be empty.")
            return
            
        mod_num = None
        if mod_num_raw:
            try:
                mod_num = int(mod_num_raw)
            except ValueError:
                messagebox.showerror("Validation Error", "Module Number must be an integer (or blank).")
                return

        if not self.check_and_install_browser():
            return

        self._set_buttons_state(tk.DISABLED)
        
        cancel_event = threading.Event()
        msg_queue = queue.Queue()
        
        progress_win = ProgressWindow(
            self.root, 
            title="Recording & Generating Module",
            cancel_callback=lambda: cancel_event.set()
        )
        
        def run_thread():
            try:
                resume_evt = threading.Event()
                def progress_cb(msg):
                    if msg.startswith("REQUEST_REVIEW_UI:"):
                        msg_queue.put(("request_review", (msg.split(":", 1)[1], resume_evt)))
                        resume_evt.wait()
                    else:
                        msg_queue.put(("progress", msg))
                run_pipeline(
                    client_key=self.client_key,
                    start_url=start_url,
                    module_name=mod_name,
                    module_number=mod_num,
                    progress_callback=progress_cb,
                    cancel_event=cancel_event
                )
                msg_queue.put(("done", "Pipeline finished successfully!"))
            except KeyboardInterrupt:
                msg_queue.put(("cancelled", "Pipeline execution cancelled by user."))
            except Exception as e:
                logger.exception("Pipeline failed")
                msg_queue.put(("error", str(e)))
                
        worker = threading.Thread(target=run_thread, daemon=True)
        worker.start()
        
        def poll_queue():
            try:
                while True:
                    msg_type, data = msg_queue.get_nowait()
                    if msg_type == "progress":
                        progress_win.log(data)
                        progress_win.set_status(data)
                    elif msg_type == "request_review":
                        session_dir_str, resume_evt = data
                        session_dir = Path(session_dir_str)
                        progress_win.grab_release()
                        progress_win.withdraw()
                        from ui.review import open_review_ui
                        open_review_ui(session_dir, screen_index=1)
                        progress_win.deiconify()
                        progress_win.grab_set()
                        resume_evt.set()
                    elif msg_type == "done":
                        progress_win.destroy()
                        messagebox.showinfo("Success", "Module recorded and processed successfully!")
                        self._set_buttons_state(tk.NORMAL)
                        self.refresh_sessions()
                        return
                    elif msg_type == "cancelled":
                        progress_win.destroy()
                        messagebox.showwarning("Cancelled", "Pipeline execution was cancelled.")
                        self._set_buttons_state(tk.NORMAL)
                        self.refresh_sessions()
                        return
                    elif msg_type == "error":
                        progress_win.destroy()
                        messagebox.showerror("Pipeline Error", f"An error occurred: {data}")
                        self._set_buttons_state(tk.NORMAL)
                        self.refresh_sessions()
                        return
            except queue.Empty:
                pass
            
            if worker.is_alive() or not msg_queue.empty():
                self.root.after(100, poll_queue)
            else:
                progress_win.destroy()
                self._set_buttons_state(tk.NORMAL)
                self.refresh_sessions()
                
        self.root.after(100, poll_queue)

    def _on_listbox_select(self, event):
        current_selection = self.session_listbox.curselection()
        self.selected_session_indices = [idx for idx in self.selected_session_indices if idx in current_selection]
        for idx in current_selection:
            if idx not in self.selected_session_indices:
                self.selected_session_indices.append(idx)

    def _on_session_double_click(self, event):
        self._open_selected_review()

    def _open_selected_review(self):
        sel = self.session_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a session from the list to review.")
            return
        session_name = self.session_mappings[sel[0]]
        session_dir = paths.sessions_dir() / session_name
        
        from ui.review import open_review_ui
        open_review_ui(session_dir, screen_index=1)

    def assemble_manual(self):
        if not hasattr(self, 'selected_session_indices') or not self.selected_session_indices:
            messagebox.showwarning("Warning", "Please select at least one module (session) to assemble.")
            return
            
        sessions_dir = paths.sessions_dir()
        ordered_sessions = []
        for i in self.selected_session_indices:
            session_name = self.session_mappings[i]
            ordered_sessions.append(sessions_dir / session_name)
            
        client_key = self.client_key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{client_key}_{timestamp}.docx"
        output_path = paths.outputs_dir() / output_filename
        
        self._set_buttons_state(tk.DISABLED)
        
        msg_queue = queue.Queue()
        progress_win = ProgressWindow(self.root, title="Compiling Master Client Manual")
        
        def run_thread():
            try:
                progress_win.log("Starting master manual compilation...")
                assemble_master_manual(ordered_sessions, output_path, client_key=self.client_key)
                msg_queue.put(("done", "Compilation finished!"))
            except Exception as e:
                logger.exception("Assembly failed")
                msg_queue.put(("error", str(e)))
                
        worker = threading.Thread(target=run_thread, daemon=True)
        worker.start()
        
        def poll_queue():
            try:
                while True:
                    msg_type, data = msg_queue.get_nowait()
                    if msg_type == "done":
                        progress_win.destroy()
                        messagebox.showinfo("Success", f"Professional Manual compiled successfully!\nSaved to: {output_path.absolute()}")
                        self._set_buttons_state(tk.NORMAL)
                        os.startfile(str(output_path.parent.resolve()))
                        return
                    elif msg_type == "error":
                        progress_win.destroy()
                        messagebox.showerror("Error", f"Failed to assemble manual: {data}")
                        self._set_buttons_state(tk.NORMAL)
                        return
            except queue.Empty:
                pass
            
            if worker.is_alive() or not msg_queue.empty():
                self.root.after(100, poll_queue)
            else:
                progress_win.destroy()
                self._set_buttons_state(tk.NORMAL)
                
        self.root.after(100, poll_queue)

    def open_manuals_viewer(self):
        viewer = tk.Toplevel(self.root)
        viewer.title("Generated Manuals")
        viewer.geometry("750x450")
        viewer.grab_set()  # Modal
        
        # Center in root window
        viewer.transient(self.root)
        
        # Title Label
        tk.Label(viewer, text="Generated Manuals", font=("Arial", 12, "bold"), fg="#1E3A8A").pack(pady=10)
        
        # Main frame
        main_frame = tk.Frame(viewer, padx=15, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars and Treeview
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("name", "type", "modified", "size")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        
        tree.heading("name", text="File Name")
        tree.heading("type", text="Type")
        tree.heading("modified", text="Date Modified")
        tree.heading("size", text="Size")
        
        tree.column("name", width=320, anchor="w")
        tree.column("type", width=120, anchor="center")
        tree.column("modified", width=150, anchor="center")
        tree.column("size", width=80, anchor="e")
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        
        # Buttons frame at bottom
        btn_frame = tk.Frame(main_frame, pady=10)
        btn_frame.pack(fill=tk.X)
        
        outputs_dir = paths.outputs_dir()
        
        def refresh_list():
            # Clear tree
            for item in tree.get_children():
                tree.delete(item)
                
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
                        logger.warning(f"Error reading file stats for {file_path}: {e}")
            
            # Sort files by modified time descending (newest first)
            files.sort(key=lambda x: x[2], reverse=True)
            
            for f_path, m_type, m_time, s_kb in files:
                tree.insert("", tk.END, values=(f_path.name, m_type, m_time, f"{s_kb} KB"), tags=(str(f_path.resolve()),))
                
        def get_selected_path():
            selected = tree.selection()
            if not selected:
                return None
            tags = tree.item(selected[0], "tags")
            if not tags:
                return None
            return Path(tags[0])
            
        def open_selected():
            path = get_selected_path()
            if path:
                if path.exists():
                    os.startfile(str(path))
                else:
                    messagebox.showerror("Error", f"File not found: {path}", parent=viewer)
                    refresh_list()
            else:
                messagebox.showwarning("Warning", "Please select a manual to open.", parent=viewer)
                
        def delete_selected():
            path = get_selected_path()
            if path:
                if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{path.name}'?", parent=viewer):
                    try:
                        path.unlink()
                        refresh_list()
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to delete file: {e}", parent=viewer)
            else:
                messagebox.showwarning("Warning", "Please select a manual to delete.", parent=viewer)
                
        # Double click to open
        tree.bind("<Double-1>", lambda event: open_selected())
        
        # Add buttons
        tk.Button(btn_frame, text="Open Manual", bg="#059669", fg="white", font=("Arial", 9, "bold"), width=15, command=open_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Open Folder", bg="#EFF6FF", fg="#1E40AF", font=("Arial", 9, "bold"), width=15, command=lambda: os.startfile(str(outputs_dir))).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Delete", bg="#FEF2F2", fg="#991B1B", font=("Arial", 9, "bold"), width=10, command=delete_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Refresh", bg="#F3F4F6", font=("Arial", 9), width=10, command=refresh_list).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Close", bg="#F3F4F6", font=("Arial", 9), width=10, command=viewer.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Load initially
        refresh_list()



def main():
    from docbot.logging_setup import setup_logging
    setup_logging()
    root = tk.Tk()
    app = LauncherUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()