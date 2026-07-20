"""
DocBot v3 — Launcher UI.

The primary entry point of the application. Allows selecting the active client
profile, modifying active client style rules, settings, recording new modules,
managing session history, compiling manuals, and automatically opening outputs.
"""

import sys
import os
import atexit
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
from ui.widgets import ScrollableFrame, setup_dialog, ToolTip
from ui.theme import apply_theme
from ui.views import RecordView, RecordingsView, ManualsView, ClientsView

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

def remove_pid_file():
    try:
        lock_file = paths.data_dir() / "docbot.pid"
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass

atexit.register(remove_pid_file)

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
# Geometry Persistence Helpers
# -----------------------------------------------------------------------------

DEFAULT_W, DEFAULT_H, MIN_W, MIN_H = 900, 640, 640, 480

def restore_geometry(root, config):
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(DEFAULT_W, sw - 80)
    h = min(DEFAULT_H, sh - 120)
    x, y = (sw - w) // 2, max(20, (sh - h) // 3)
    saved = getattr(config, "window_geometry", None)   # "WxH+X+Y"
    if saved:
        try:
            size, xs, ys = saved.split("+")
            w0, h0 = (int(v) for v in size.split("x"))
            x0, y0 = int(xs), int(ys)
            # clamp fully on-screen
            w = min(w0, sw - 20)
            h = min(h0, sh - 60)
            x = max(0, min(x0, sw - w))
            y = max(0, min(y0, sh - h))
        except Exception:
            pass
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(MIN_W, MIN_H)

def save_geometry_on_close(root, config, launcher_instance=None):
    def _on_close():
        if launcher_instance and hasattr(launcher_instance, "cancel_background_recording"):
            launcher_instance.cancel_background_recording()
        config.window_geometry = root.winfo_geometry()  # "WxH+X+Y"
        save_config(config)
        remove_pid_file()
        root.destroy()
        sys.exit(0)
    root.protocol("WM_DELETE_WINDOW", _on_close)

# -----------------------------------------------------------------------------
# Reusable Progress Window
# -----------------------------------------------------------------------------

class ProgressWindow(tk.Toplevel):
    def __init__(self, parent, title="Please Wait", cancel_callback=None):
        super().__init__(parent)
        self.title(title)
        setup_dialog(self, parent, min_w=540, min_h=380, modal=False)
        
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

    def set_progress(self, percent: int):
        """Switch progress bar to determinate and set a specific percentage."""
        if self.pb["mode"] != "determinate":
            self.pb.stop()
            self.pb.config(mode="determinate", maximum=100)
        self.pb["value"] = percent

# -----------------------------------------------------------------------------
# Welcome Wizard
# -----------------------------------------------------------------------------

class WelcomeWizard(tk.Toplevel):
    def __init__(self, parent, launcher_ui):
        super().__init__(parent)
        self.parent = parent
        self.launcher_ui = launcher_ui
        self.title("Welcome to DocBot v3")
        setup_dialog(self, parent, min_w=560, min_h=440, modal=True)
        
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
            self.launcher_ui.change_client(client)
            
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
        setup_dialog(self, parent, min_w=640, min_h=780, modal=True)

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
        for key in ["fonts", "colors", "logo", "cover", "annotations"]:
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
    def build_ui(self):
        scroll = ScrollableFrame(self)
        scroll.pack(fill=tk.BOTH, expand=True)
        
        main_frame = ttk.Frame(scroll.body)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        ttk.Label(main_frame, text=f"Client Settings Configuration — {self.client_key.upper()}", 
                  font=("Segoe UI Semibold", 12)).pack(pady=(0, 15))

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # --- Tab 1: Identity ---
        t1 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(t1, text="Identity (manifest)")
        
        ttk.Label(t1, text="Client Display Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.client_display_name_entry = ttk.Entry(t1, width=35)
        self.client_display_name_entry.insert(0, self.manifest_data.get("client_display_name", ""))
        self.client_display_name_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="System Name:").grid(row=1, column=0, sticky="w", pady=5)
        self.system_name_entry = ttk.Entry(t1, width=35)
        self.system_name_entry.insert(0, self.manifest_data.get("system_name", ""))
        self.system_name_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="System Acronym:").grid(row=2, column=0, sticky="w", pady=5)
        self.system_acronym_entry = ttk.Entry(t1, width=15)
        self.system_acronym_entry.insert(0, self.manifest_data.get("system_acronym", ""))
        self.system_acronym_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Manual Title:").grid(row=3, column=0, sticky="w", pady=5)
        self.manual_title_entry = ttk.Entry(t1, width=35)
        self.manual_title_entry.insert(0, self.manifest_data.get("manual_title", "User Manual"))
        self.manual_title_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Document Version:").grid(row=4, column=0, sticky="w", pady=5)
        self.version_entry = ttk.Entry(t1, width=15)
        self.version_entry.insert(0, self.manifest_data.get("version", "1.0"))
        self.version_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Revision Prepared By:").grid(row=5, column=0, sticky="w", pady=5)
        self.prepared_by_entry = ttk.Entry(t1, width=35)
        self.prepared_by_entry.insert(0, self.prepared_by_entry_value if hasattr(self, 'prepared_by_entry_value') else self.manifest_data.get("prepared_by", ""))
        self.prepared_by_entry.grid(row=5, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Revision Reviewed By:").grid(row=6, column=0, sticky="w", pady=5)
        self.reviewed_by_entry = ttk.Entry(t1, width=35)
        self.reviewed_by_entry.insert(0, self.manifest_data.get("reviewed_by", ""))
        self.reviewed_by_entry.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Revision Approved By:").grid(row=7, column=0, sticky="w", pady=5)
        self.approved_by_entry = ttk.Entry(t1, width=35)
        self.approved_by_entry.insert(0, self.manifest_data.get("approved_by", ""))
        self.approved_by_entry.grid(row=7, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t1, text="Numbering Mode:").grid(row=8, column=0, sticky="w", pady=5)
        self.num_mode_combo = ttk.Combobox(t1, values=["module_prefixed", "continuous"], state="readonly", width=18)
        self.num_mode_combo.set(self.manifest_data.get("numbering_mode", "module_prefixed"))
        self.num_mode_combo.grid(row=8, column=1, sticky="w", padx=5, pady=5)

        # --- Tab 2: Branding ---
        t2 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(t2, text="Branding (style)")

        ttk.Label(t2, text="Font Family:").grid(row=0, column=0, sticky="w", pady=5)
        self.font_combo = ttk.Combobox(t2, values=["Segoe UI", "Arial", "Calibri", "Georgia", "Times New Roman"], state="readonly", width=18)
        self.font_combo.set(self.style_data["fonts"].get("body_family", "Segoe UI"))
        self.font_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t2, text="Body Font Size (pt):").grid(row=1, column=0, sticky="w", pady=5)
        self.font_size_spin = ttk.Spinbox(t2, from_=8, to=24, increment=0.5, width=10)
        self.font_size_spin.set(str(self.style_data["fonts"].get("body_size_pt", 10.5)))
        self.font_size_spin.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t2, text="Primary Color (Hex):").grid(row=2, column=0, sticky="w", pady=5)
        self.primary_entry = ttk.Entry(t2, width=12)
        p_val = self.style_data["colors"].get("primary", "1B365D")
        self.primary_entry.insert(0, f"#{p_val}" if not p_val.startswith("#") else p_val)
        self.primary_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(t2, text="Pick...", command=lambda: self.pick_color(self.primary_entry)).grid(row=2, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(t2, text="Secondary Color (Hex):").grid(row=3, column=0, sticky="w", pady=5)
        self.secondary_entry = ttk.Entry(t2, width=12)
        s_val = self.style_data["colors"].get("secondary", "D97706")
        self.secondary_entry.insert(0, f"#{s_val}" if not s_val.startswith("#") else s_val)
        self.secondary_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(t2, text="Pick...", command=lambda: self.pick_color(self.secondary_entry)).grid(row=3, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(t2, text="Company Logo File:").grid(row=4, column=0, sticky="w", pady=5)
        self.logo_entry = ttk.Entry(t2, width=32)
        self.logo_entry.insert(0, self.style_data["logo"].get("path", ""))
        self.logo_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(t2, text="Browse...", command=self.browse_logo).grid(row=4, column=2, sticky="w", padx=2, pady=5)

        # Cover details
        ttk.Label(t2, text="Cover Title text:").grid(row=5, column=0, sticky="w", pady=5)
        self.cover_title_entry = ttk.Entry(t2, width=35)
        title_lines = self.cover_data.get("title_lines", [])
        self.cover_title_entry.insert(0, title_lines[0] if len(title_lines) > 0 else "")
        self.cover_title_entry.grid(row=5, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(t2, text="Cover Subtitle text:").grid(row=6, column=0, sticky="w", pady=5)
        self.cover_subtitle_entry = ttk.Entry(t2, width=35)
        self.cover_subtitle_entry.insert(0, title_lines[1] if len(title_lines) > 1 else "")
        self.cover_subtitle_entry.grid(row=6, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        # Annotations branding settings
        annot = self.style_data.get("annotations", {})
        
        ttk.Label(t2, text="Callout Style:").grid(row=7, column=0, sticky="w", pady=5)
        self.callout_style_combo = ttk.Combobox(t2, values=["Labeled bubble", "Numbered"], state="readonly", width=18)
        current_style = annot.get("callout_style", "numbered")
        self.callout_style_combo.set("Labeled bubble" if current_style == "bubble_label" else "Numbered")
        self.callout_style_combo.grid(row=7, column=1, sticky="w", padx=5, pady=5)
        
        ttk.Label(t2, text="Callout color:").grid(row=8, column=0, sticky="w", pady=5)
        self.callout_color_entry = ttk.Entry(t2, width=12)
        cc_val = annot.get("callout_border", "E5484D")
        self.callout_color_entry.insert(0, f"#{cc_val}" if not cc_val.startswith("#") else cc_val)
        self.callout_color_entry.grid(row=8, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(t2, text="Pick...", command=lambda: self.pick_color(self.callout_color_entry)).grid(row=8, column=2, sticky="w", padx=2, pady=5)
        
        ttk.Label(t2, text="Pointer tail:").grid(row=9, column=0, sticky="w", pady=5)
        self.callout_tail_var = tk.BooleanVar(value=bool(annot.get("callout_tail", True)))
        self.callout_tail_chk = ttk.Checkbutton(t2, variable=self.callout_tail_var)
        self.callout_tail_chk.grid(row=9, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t2, text="Region style:").grid(row=10, column=0, sticky="w", pady=5)
        self.region_style_combo = ttk.Combobox(t2, values=["Overlay (Translucent fill)", "Outline (No fill)"], state="readonly", width=22)
        current_region = annot.get("region_style", "overlay")
        self.region_style_combo.set("Outline (No fill)" if current_region == "outline" else "Overlay (Translucent fill)")
        self.region_style_combo.grid(row=10, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(t2, text="Connecting line:").grid(row=11, column=0, sticky="w", pady=5)
        self.leader_line_var = tk.BooleanVar(value=bool(annot.get("leader_line", False)))
        self.leader_line_chk = ttk.Checkbutton(t2, variable=self.leader_line_var)
        self.leader_line_chk.grid(row=11, column=1, sticky="w", padx=5, pady=5)

        # --- Tab 3: Writing Voice ---
        t3 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(t3, text="Voice (rules)")

        ttk.Label(t3, text="App Name in Prose:").grid(row=0, column=0, sticky="w", pady=5)
        self.app_name_entry = ttk.Entry(t3, width=35)
        self.app_name_entry.insert(0, self.voice_data.get("app_name", ""))
        self.app_name_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(t3, text="Fields Styling Mode:").grid(row=1, column=0, sticky="w", pady=5)
        self.field_style_var = tk.StringVar(value=self.style_data.get("fields", {}).get("style", "table"))
        ttk.Radiobutton(t3, text="Grid/Table layout", variable=self.field_style_var, value="table").grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Radiobutton(t3, text="Bullet list layout", variable=self.field_style_var, value="bullets").grid(row=1, column=2, sticky="w", padx=5, pady=5)

        ttk.Label(t3, text="Navigation Sentence:").grid(row=2, column=0, sticky="w", pady=5)
        self.nav_temp_entry = ttk.Entry(t3, width=45)
        self.nav_temp_entry.insert(0, self.voice_data.get("navigation_template", "Navigate to {screen_name}."))
        self.nav_temp_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(t3, text="Tone/Writing Rules (one per line):").grid(row=3, column=0, sticky="w", pady=5)
        self.tone_rules_text = tk.Text(t3, width=50, height=8, font=("Segoe UI", 9))
        self.tone_rules_text.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="we")
        rules = self.voice_data.get("tone_rules", [])
        self.tone_rules_text.insert(tk.END, "\n".join(rules))

        # --- Tab 4: Glossary ---
        t4 = ttk.Frame(self.notebook, padding=10)
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
        g_edit = ttk.Frame(t4)
        g_edit.pack(fill=tk.X)

        ttk.Label(g_edit, text="Term:").grid(row=0, column=0, sticky="w", pady=2)
        self.term_entry = ttk.Entry(g_edit, width=20)
        self.term_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(g_edit, text="Definition:").grid(row=0, column=2, sticky="w", pady=2)
        self.defn_entry = ttk.Entry(g_edit, width=32)
        self.defn_entry.grid(row=0, column=3, sticky="we", padx=5, pady=2)

        btn_g_frame = ttk.Frame(t4, padding=5)
        btn_g_frame.pack(fill=tk.X)
        ttk.Button(btn_g_frame, text="Add / Update", command=self._add_glossary_term).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_g_frame, text="Remove Selected", command=self._remove_glossary_term).pack(side=tk.LEFT, padx=5)

        self._refresh_glossary_tree()

        # Bottom buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save Settings", style="Primary.TButton", command=self.save_settings).pack(side=tk.RIGHT, padx=5)

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

        # Save annotations settings
        cc_color = self.callout_color_entry.get().strip().replace("#", "")
        if cc_color and len(cc_color) != 6:
            messagebox.showerror("Validation Error", "Callout color must be a valid 6-character hex string.")
            return
            
        if "annotations" not in self.style_data or not isinstance(self.style_data["annotations"], dict):
            self.style_data["annotations"] = {}
            
        style_sel = self.callout_style_combo.get()
        style_key = "bubble_label" if style_sel == "Labeled bubble" else "numbered"
        self.style_data["annotations"]["callout_style"] = style_key
        self.style_data["annotations"]["callout_border"] = cc_color
        self.style_data["annotations"]["callout_text_color"] = cc_color
        self.style_data["annotations"]["region_border"] = cc_color
        self.style_data["annotations"]["callout_tail"] = self.callout_tail_var.get()
        region_style_sel = self.region_style_combo.get()
        self.style_data["annotations"]["region_style"] = "outline" if "Outline" in region_style_sel else "overlay"
        self.style_data["annotations"]["leader_line"] = self.leader_line_var.get()
        
        # Default options when opting into bubble_label style
        if style_key == "bubble_label":
            if "leader_line" not in self.style_data["annotations"]:
                self.style_data["annotations"]["leader_line"] = False
            if "region_style" not in self.style_data["annotations"]:
                self.style_data["annotations"]["region_style"] = "outline"
            if "region_border_width" not in self.style_data["annotations"]:
                self.style_data["annotations"]["region_border_width"] = 3

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

            self.ui_manager.change_client(self.client_key)
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
        self.root.title("DocBot")
        
        self.config = get_config()
        self.client_key = self.config.current_client
        
        # Load theme
        apply_theme(self.root)
        
        # Geometry Persistence
        restore_geometry(self.root, self.config)
        save_geometry_on_close(self.root, self.config, self)
        
        # Install global exception handlers
        self.setup_global_crash_handler()

        # Check single instance
        if not check_single_instance():
            messagebox.showerror("DocBot Active", "Another copy of DocBot is already running on this machine.")
            self.root.destroy()
            sys.exit(0)

        # Set grid layout weights
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=0)

        # Navigation views mapping
        self.VIEWS = [
            ("record", "▶  Record"),
            ("recordings", "📼  Recordings"),
            ("manuals", "📄  Manuals"),
            ("clients", "👥  Clients")
        ]
        
        VIEW_CLASSES = {
            "record": RecordView,
            "recordings": RecordingsView,
            "manuals": ManualsView,
            "clients": ClientsView
        }

        # Build UI layout
        self.topbar = self._build_topbar()
        self.sidebar = self._build_sidebar()
        
        self.content = ttk.Frame(self.root)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        
        self.statusbar = self._build_statusbar()

        # Key Bindings / Shortcuts (Phase D)
        self.root.bind("<Control-r>", lambda e: self.show("record"))
        self.root.bind("<F5>", lambda e: self.refresh_active_view())
        self.root.bind("<Delete>", lambda e: self.delete_active_view_item())
        self.root.bind("<Control-comma>", lambda e: self.open_settings_dialog())

        # Load views
        self.views = {}
        for key, _ in self.VIEWS:
            view_cls = VIEW_CLASSES[key]
            v = view_cls(self.content, app=self)
            v.grid(row=0, column=0, sticky="nsew")
            self.views[key] = v

        self.active_view_key = "record"
        self.show("record")

        # Welcome wizard / startup warning checks
        if not self.config.first_run_done:
            self.root.after(200, self.show_welcome_wizard)
        else:
            self.root.after(300, self.prompt_missing_key_startup)

    def _build_topbar(self):
        f = ttk.Frame(self.root, padding=(12, 8))
        f.grid(row=0, column=0, columnspan=2, sticky="ew")
        f.columnconfigure(3, weight=1)

        # Logo / Title
        logo_lbl = ttk.Label(f, text="DocBot", style="Title.TLabel")
        logo_lbl.grid(row=0, column=0, sticky="w", padx=(0, 16))

        # Client Combobox
        ttk.Label(f, text="Client:").grid(row=0, column=1, sticky="w")
        self.client_list = get_available_clients()
        self.client_var = tk.StringVar(value=self.client_key)
        self.client_combo = ttk.Combobox(f, textvariable=self.client_var, values=self.client_list, state="readonly", width=18)
        self.client_combo.grid(row=0, column=2, sticky="w", padx=6)
        self.client_combo.bind("<<ComboboxSelected>>", self.on_client_change)

        # Spacer
        ttk.Frame(f).grid(row=0, column=3, sticky="ew")

        # Provider Indicator Dot
        self.provider_dot = tk.Frame(f, width=12, height=12, bg="#EF4444", bd=1, relief="solid")
        self.provider_dot.grid(row=0, column=4, padx=8)

        # Global Settings Button
        settings_btn = ttk.Button(f, text="Settings", command=self.open_settings_dialog)
        settings_btn.grid(row=0, column=5, sticky="e", padx=4)

        return f

    def _build_sidebar(self):
        f = ttk.Frame(self.root, style="Sidebar.TFrame", padding=(0, 10))
        f.grid(row=1, column=0, sticky="ns")

        self.sidebar_buttons = {}
        for row_idx, (key, label) in enumerate(self.VIEWS):
            btn = ttk.Button(f, text=label, style="Sidebar.TButton", command=lambda k=key: self.show(k))
            btn.grid(row=row_idx, column=0, sticky="ew", padx=8, pady=4)
            self.sidebar_buttons[key] = btn

        return f

    def _build_statusbar(self):
        f = ttk.Frame(self.root, padding=(12, 4), style="Status.TFrame")
        f.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.status_lbl = ttk.Label(f, text="", style="Status.TLabel")
        self.status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.update_status_bar("Ready.")
        return f

    def show(self, key):
        self.active_view_key = key
        self.views[key].refresh()
        self.views[key].tkraise()
        self._highlight_sidebar(key)

    def _highlight_sidebar(self, active_key):
        for key, btn in self.sidebar_buttons.items():
            if key == active_key:
                btn.config(style="SidebarActive.TButton")
            else:
                btn.config(style="Sidebar.TButton")

    def refresh_active_view(self):
        if self.active_view_key in self.views:
            self.views[self.active_view_key].refresh()

    def delete_active_view_item(self):
        active_view = self.views.get(self.active_view_key)
        if active_view and hasattr(active_view, "delete_selected"):
            active_view.delete_selected()

    def update_status_bar(self, task_msg="Ready."):
        provider = self.config.provider
        client = self.client_key.upper()
        status_text = f"Client: {client}   ·   Provider: {provider}   ·   {task_msg}"
        self.status_lbl.config(text=status_text)

    def change_client(self, key):
        self.client_key = key
        self.client_var.set(key)
        self.config.current_client = key
        save_config(self.config)
        reload_config()
        self.update_status_bar()
        self.refresh_active_view()

    def on_client_change(self, event):
        self.change_client(self.client_var.get())

    def check_provider_status(self):
        provider = self.config.provider
        if provider == "browser":
            self._update_status_dot(True, "Local copy-paste mode (No API key required)")
            return
        
        try:
            from main import get_provider_instance
            p_inst = get_provider_instance(self.config)
            if p_inst.is_available():
                self._update_status_dot(True, f"Provider {provider.upper()} is ready.")
            else:
                self._update_status_dot(False, f"API Key for {provider.upper()} is missing or invalid.")
        except Exception as e:
            self._update_status_dot(False, f"Connection error: {e}")

    def _update_status_dot(self, is_ok, reason):
        color = "#22C55E" if is_ok else "#EF4444"
        self.provider_dot.config(bg=color)
        if hasattr(self, "provider_dot_tooltip"):
            self.provider_dot_tooltip.text = reason
        else:
            self.provider_dot_tooltip = ToolTip(self.provider_dot, reason)

    def prompt_missing_key_startup(self):
        provider = self.config.provider
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
                        "Please click the 'Settings' button to configure your API key."
                    )
            except Exception:
                pass

    def open_style_editor(self):
        ClientSettingsDialog(self.root, self)

    def open_settings_dialog(self):
        SettingsDialog(self.root, self)
        self.check_provider_status()
        self.update_status_bar()

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
            self.change_client(new_key)
            
            self.open_style_editor()
            messagebox.showinfo("Success", f"Client profile '{new_key}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create new client: {e}")

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

    def start_background_recording(self, start_url, mod_name, mod_num, view_instance):
        self.recording_view = view_instance
        self.recording_cancel_event = threading.Event()
        self.recording_queue = queue.Queue()
        self.recording_progress_win = None
        
        def run_thread():
            try:
                resume_evt = threading.Event()
                def progress_cb(msg):
                    if msg.startswith("REQUEST_REVIEW_UI:"):
                        self.recording_queue.put(("request_review", (msg.split(":", 1)[1], resume_evt)))
                        resume_evt.wait()
                    elif msg.startswith("SCREEN_CAPTURED:"):
                        cnt = int(msg.split(":", 1)[1])
                        self.recording_queue.put(("screen_captured", cnt))
                    else:
                        self.recording_queue.put(("progress", msg))
                        
                run_pipeline(
                    client_key=self.client_key,
                    start_url=start_url,
                    module_name=mod_name,
                    module_number=mod_num,
                    progress_callback=progress_cb,
                    cancel_event=self.recording_cancel_event
                )
                self.recording_queue.put(("done", "Pipeline finished successfully!"))
            except KeyboardInterrupt:
                self.recording_queue.put(("cancelled", "Pipeline execution cancelled by user."))
            except Exception as e:
                logger.exception("Pipeline failed")
                self.recording_queue.put(("error", str(e)))
                
        worker = threading.Thread(target=run_thread, daemon=True)
        worker.start()
        
        def poll_queue():
            try:
                while True:
                    msg_type, data = self.recording_queue.get_nowait()
                    if msg_type == "progress":
                        self.update_status_bar(data)
                        if data.startswith("Processing session data in:") or "PHASE 2" in data or "Pre-generating" in data:
                            if not self.recording_progress_win:
                                self.recording_progress_win = ProgressWindow(
                                    self.root,
                                    title="Processing & Generating Content",
                                    cancel_callback=self.cancel_background_recording
                                )
                        if self.recording_progress_win:
                            self.recording_progress_win.log(data)
                            self.recording_progress_win.set_status(data)
                            import re
                            m = re.search(r"Screen (\d+) of (\d+)", data)
                            if m:
                                current = int(m.group(1))
                                total = int(m.group(2))
                                if total > 0:
                                    percent = int(current / total * 100)
                                    self.recording_progress_win.set_progress(percent)
                    elif msg_type == "screen_captured":
                        self.recording_view.update_count(data)
                        self.update_status_bar(f"Screens captured: {data}")
                    elif msg_type == "request_review":
                        if self.recording_progress_win:
                            self.recording_progress_win.destroy()
                            self.recording_progress_win = None
                        session_dir_str, resume_evt = data
                        session_dir = Path(session_dir_str)
                        self.open_review_window(session_dir)
                        resume_evt.set()
                    elif msg_type == "done":
                        if self.recording_progress_win:
                            self.recording_progress_win.destroy()
                            self.recording_progress_win = None
                        self.recording_view.show_setup()
                        messagebox.showinfo("Success", "Module recorded and processed successfully!")
                        self.update_status_bar("Ready.")
                        self.refresh_active_view()
                        return
                    elif msg_type == "cancelled":
                        if self.recording_progress_win:
                            self.recording_progress_win.destroy()
                            self.recording_progress_win = None
                        self.recording_view.show_setup()
                        messagebox.showwarning("Cancelled", "Pipeline execution was cancelled.")
                        self.update_status_bar("Ready.")
                        self.refresh_active_view()
                        return
                    elif msg_type == "error":
                        if self.recording_progress_win:
                            self.recording_progress_win.destroy()
                            self.recording_progress_win = None
                        self.recording_view.show_setup()
                        messagebox.showerror("Pipeline Error", f"An error occurred: {data}")
                        self.update_status_bar("Error: " + data)
                        self.refresh_active_view()
                        return
            except queue.Empty:
                pass
                
            if worker.is_alive() or not self.recording_queue.empty():
                self.root.after(100, poll_queue)
                
        self.root.after(100, poll_queue)

    def cancel_background_recording(self):
        if hasattr(self, "recording_cancel_event"):
            self.recording_cancel_event.set()

    def open_review_window(self, session_dir):
        from ui.review import open_review_ui
        open_review_ui(session_dir, screen_index=1)

    def assemble_master_manual(self, ordered_sessions):
        client_key = self.client_key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{client_key}_{timestamp}.docx"
        output_path = paths.outputs_dir() / output_filename
        
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
                        os.startfile(str(output_path.parent.resolve()))
                        self.show("manuals")
                        return
                    elif msg_type == "error":
                        progress_win.destroy()
                        messagebox.showerror("Error", f"Failed to assemble manual: {data}")
                        return
            except queue.Empty:
                pass
            
            if worker.is_alive() or not msg_queue.empty():
                self.root.after(100, poll_queue)
            else:
                progress_win.destroy()
                
        self.root.after(100, poll_queue)

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

def enable_windows_dpi_awareness():
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # per-monitor v1
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def apply_tk_scaling(root):
    try:
        dpi = root.winfo_fpixels("1i")     # actual pixels per inch
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass

def main():
    enable_windows_dpi_awareness()
    from docbot.logging_setup import setup_logging
    setup_logging()
    root = tk.Tk()
    apply_tk_scaling(root)
    
    # Apply app icon
    try:
        icon_path = paths.bundle_dir() / "assets" / "docbot.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except Exception as e:
        logger.warning(f"Failed to load application icon: {e}")
        
    app = LauncherUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()