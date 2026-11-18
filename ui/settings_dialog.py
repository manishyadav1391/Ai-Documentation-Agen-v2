import os
import tkinter as tk
from tkinter import ttk, messagebox
import yaml
import httpx
import threading
from docbot import paths
from config import get_config, save_config, reload_config

from ui.widgets import setup_dialog

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.title("Settings & API Keys")
        setup_dialog(self, parent, min_w=560, min_h=580, modal=True)

        # Load secrets
        self.secrets_path = paths.data_dir() / "secrets.yaml"
        self.secrets = {}
        if self.secrets_path.exists():
            try:
                with self.secrets_path.open("r", encoding="utf-8") as f:
                    self.secrets = yaml.safe_load(f) or {}
            except Exception as e:
                messagebox.showwarning("Warning", f"Could not read secrets.yaml: {e}")

        self.config = get_config()
        self.build_ui()

    def build_ui(self):
        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text="DocBot Settings & API Keys", font=("Segoe UI", 12, "bold"), fg="#1E293B").pack(pady=(0, 15))

        # Active provider used for AI generation
        prov_frame = tk.Frame(main_frame)
        prov_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(prov_frame, text="Active AI provider:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.active_provider_var = tk.StringVar(value=self.config.provider)
        ttk.Combobox(prov_frame, textvariable=self.active_provider_var,
                     values=["browser", "anthropic", "openai_compat", "openrouter", "ollama"],
                     state="readonly", width=18).pack(side=tk.LEFT, padx=8)

        # We'll use a tabbed panel for each provider
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # --- Tab: Anthropic ---
        anthropic_frame = tk.Frame(notebook, padx=10, pady=10)
        notebook.add(anthropic_frame, text="Anthropic")

        tk.Label(anthropic_frame, text="Anthropic API Key:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
        self.anthropic_key_var = tk.StringVar(value=self.secrets.get("anthropic_api_key", ""))
        
        key_entry_frame = tk.Frame(anthropic_frame)
        key_entry_frame.pack(fill=tk.X, pady=(0, 10))
        self.anthropic_key_entry = tk.Entry(key_entry_frame, textvariable=self.anthropic_key_var, show="•", width=50)
        self.anthropic_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.anthropic_show_btn = ttk.Checkbutton(key_entry_frame, text="Show", variable=self._show_var(), command=lambda: self.toggle_show(self.anthropic_key_entry))
        self.anthropic_show_btn.pack(side=tk.RIGHT, padx=5)

        tk.Label(anthropic_frame, text="Model Name:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.anthropic_model_var = tk.StringVar(value=self.config.providers.anthropic.model)
        self.anthropic_model_entry = tk.Entry(anthropic_frame, textvariable=self.anthropic_model_var)
        self.anthropic_model_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(anthropic_frame, text="Max Tokens:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.anthropic_max_tokens_var = tk.StringVar(value=str(self.config.providers.anthropic.max_tokens))
        self.anthropic_max_tokens_entry = tk.Entry(anthropic_frame, textvariable=self.anthropic_max_tokens_var)
        self.anthropic_max_tokens_entry.pack(fill=tk.X, pady=(0, 15))

        self.anthropic_test_btn = tk.Button(anthropic_frame, text="Test Connection", bg="#F1F5F9", command=self.test_anthropic_conn)
        self.anthropic_test_btn.pack(anchor="e")

        # --- Tab: OpenAI Compatible ---
        openai_frame = tk.Frame(notebook, padx=10, pady=10)
        notebook.add(openai_frame, text="OpenAI Compat")

        tk.Label(openai_frame, text="OpenAI API Key:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
        # "openai_api_key" is the legacy name; config.get_api_key() reads "openai_compat_api_key"
        self.openai_key_var = tk.StringVar(value=self.secrets.get("openai_compat_api_key") or self.secrets.get("openai_api_key", ""))
        
        okey_entry_frame = tk.Frame(openai_frame)
        okey_entry_frame.pack(fill=tk.X, pady=(0, 10))
        self.openai_key_entry = tk.Entry(okey_entry_frame, textvariable=self.openai_key_var, show="•", width=50)
        self.openai_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.openai_show_btn = ttk.Checkbutton(okey_entry_frame, text="Show", variable=self._show_var(), command=lambda: self.toggle_show(self.openai_key_entry))
        self.openai_show_btn.pack(side=tk.RIGHT, padx=5)

        tk.Label(openai_frame, text="Base URL Endpoint:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openai_base_url_var = tk.StringVar(value=self.config.providers.openai_compat.base_url)
        self.openai_base_url_entry = tk.Entry(openai_frame, textvariable=self.openai_base_url_var)
        self.openai_base_url_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(openai_frame, text="Model Name:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openai_model_var = tk.StringVar(value=self.config.providers.openai_compat.model)
        self.openai_model_entry = tk.Entry(openai_frame, textvariable=self.openai_model_var)
        self.openai_model_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(openai_frame, text="Max Tokens:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openai_max_tokens_var = tk.StringVar(value=str(self.config.providers.openai_compat.max_tokens))
        self.openai_max_tokens_entry = tk.Entry(openai_frame, textvariable=self.openai_max_tokens_var)
        self.openai_max_tokens_entry.pack(fill=tk.X, pady=(0, 15))

        self.openai_test_btn = tk.Button(openai_frame, text="Test Connection", bg="#F1F5F9", command=self.test_openai_conn)
        self.openai_test_btn.pack(anchor="e")

        # --- Tab: Ollama ---
        ollama_frame = tk.Frame(notebook, padx=10, pady=10)
        notebook.add(ollama_frame, text="Ollama")

        tk.Label(ollama_frame, text="Ollama API Key (Optional for cloud):", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.ollama_key_var = tk.StringVar(value=self.secrets.get("ollama_api_key", ""))
        
        olkey_entry_frame = tk.Frame(ollama_frame)
        olkey_entry_frame.pack(fill=tk.X, pady=(0, 10))
        self.ollama_key_entry = tk.Entry(olkey_entry_frame, textvariable=self.ollama_key_var, show="•", width=50)
        self.ollama_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ollama_show_btn = ttk.Checkbutton(olkey_entry_frame, text="Show", variable=self._show_var(), command=lambda: self.toggle_show(self.ollama_key_entry))
        self.ollama_show_btn.pack(side=tk.RIGHT, padx=5)

        tk.Label(ollama_frame, text="Ollama Host URL:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.ollama_host_var = tk.StringVar(value=self.config.providers.ollama.host)
        self.ollama_host_entry = tk.Entry(ollama_frame, textvariable=self.ollama_host_var)
        self.ollama_host_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(ollama_frame, text="Model Name:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.ollama_model_var = tk.StringVar(value=self.config.providers.ollama.model)
        self.ollama_model_entry = tk.Entry(ollama_frame, textvariable=self.ollama_model_var)
        self.ollama_model_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(ollama_frame, text="Max Tokens:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.ollama_max_tokens_var = tk.StringVar(value=str(self.config.providers.ollama.max_tokens))
        self.ollama_max_tokens_entry = tk.Entry(ollama_frame, textvariable=self.ollama_max_tokens_var)
        self.ollama_max_tokens_entry.pack(fill=tk.X, pady=(0, 15))

        self.ollama_test_btn = tk.Button(ollama_frame, text="Test Connection", bg="#F1F5F9", command=self.test_ollama_conn)
        self.ollama_test_btn.pack(anchor="e")

        # --- Tab: OpenRouter ---
        openrouter_frame = tk.Frame(notebook, padx=10, pady=10)
        notebook.add(openrouter_frame, text="OpenRouter")
        or_cfg = self.config.providers.openrouter

        tk.Label(openrouter_frame, text="OpenRouter API Key:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
        self.openrouter_key_var = tk.StringVar(value=self.secrets.get("openrouter_api_key", ""))

        orkey_entry_frame = tk.Frame(openrouter_frame)
        orkey_entry_frame.pack(fill=tk.X, pady=(0, 2))
        self.openrouter_key_entry = tk.Entry(orkey_entry_frame, textvariable=self.openrouter_key_var, show="•", width=50)
        self.openrouter_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Checkbutton(orkey_entry_frame, text="Show", variable=self._show_var(), command=lambda: self.toggle_show(self.openrouter_key_entry)).pack(side=tk.RIGHT, padx=5)
        if not self.openrouter_key_var.get() and os.environ.get(or_cfg.api_key_env):
            tk.Label(openrouter_frame, text=f"Leave blank to use {or_cfg.api_key_env} from .env (currently set).",
                     font=("Segoe UI", 8, "italic"), fg="#64748B").pack(anchor="w", pady=(0, 8))

        tk.Label(openrouter_frame, text="Model (e.g. ~openai/gpt-sol-latest, ~anthropic/claude-sonnet-latest):",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openrouter_model_var = tk.StringVar(value=or_cfg.model)
        tk.Entry(openrouter_frame, textvariable=self.openrouter_model_var).pack(fill=tk.X, pady=(0, 10))

        tk.Label(openrouter_frame, text="Max Tokens:", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openrouter_max_tokens_var = tk.StringVar(value=str(or_cfg.max_tokens))
        tk.Entry(openrouter_frame, textvariable=self.openrouter_max_tokens_var).pack(fill=tk.X, pady=(0, 10))

        tk.Label(openrouter_frame, text="Site URL (optional, sent as HTTP-Referer):", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openrouter_site_url_var = tk.StringVar(value=or_cfg.site_url)
        tk.Entry(openrouter_frame, textvariable=self.openrouter_site_url_var).pack(fill=tk.X, pady=(0, 10))

        tk.Label(openrouter_frame, text="App name (optional, sent as X-OpenRouter-Title):", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self.openrouter_app_name_var = tk.StringVar(value=or_cfg.app_name)
        tk.Entry(openrouter_frame, textvariable=self.openrouter_app_name_var).pack(fill=tk.X, pady=(0, 15))

        self.openrouter_test_btn = tk.Button(openrouter_frame, text="Test Connection", bg="#F1F5F9", command=self.test_openrouter_conn)
        self.openrouter_test_btn.pack(anchor="e")

        # Bottom Buttons
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(15, 0))

        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Settings", bg="lightgreen", font=("Segoe UI", 10, "bold"), width=15, command=self.save_settings).pack(side=tk.RIGHT, padx=5)

    def _show_var(self):
        """A BooleanVar for a 'Show' checkbox, kept alive for the dialog's lifetime."""
        if not hasattr(self, "_show_vars"):
            self._show_vars = []
        var = tk.BooleanVar(self, value=False)
        self._show_vars.append(var)
        return var

    def toggle_show(self, entry_widget):
        if entry_widget.cget("show") == "•":
            entry_widget.config(show="")
        else:
            entry_widget.config(show="•")

    def test_anthropic_conn(self):
        key = self.anthropic_key_var.get().strip()
        model = self.anthropic_model_var.get().strip()
        
        if not key:
            messagebox.showerror("Error", "Please input an API Key to test.")
            return

        self.anthropic_test_btn.config(state=tk.DISABLED, text="Testing...")
        
        def run_test():
            try:
                # Direct HTTP request to check key
                client = httpx.Client(
                    base_url="https://api.anthropic.com",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=httpx.Timeout(12.0, connect=5.0),
                )
                payload = {
                    "model": model,
                    "max_tokens": 10,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                }
                resp = client.post("/v1/messages", json=payload)
                resp.raise_for_status()
                txt = resp.json()["content"][0]["text"]
                self.show_test_result(True, f"Successfully reached Anthropic API! Response: {txt}")
            except Exception as e:
                self.show_test_result(False, str(e))
            finally:
                self.after(0, lambda: self.anthropic_test_btn.config(state=tk.NORMAL, text="Test Connection"))

        threading.Thread(target=run_test, daemon=True).start()

    def test_openai_conn(self):
        key = self.openai_key_var.get().strip()
        base_url = self.openai_base_url_var.get().strip()
        model = self.openai_model_var.get().strip()
        
        if not key:
            messagebox.showerror("Error", "Please input an API Key to test.")
            return

        self.openai_test_btn.config(state=tk.DISABLED, text="Testing...")
        
        def run_test():
            try:
                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                client = httpx.Client(
                    base_url=base_url,
                    headers=headers,
                    timeout=httpx.Timeout(12.0, connect=5.0),
                )
                payload = {
                    "model": model,
                    "max_tokens": 10,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                }
                resp = client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                txt = resp.json()["choices"][0]["message"]["content"]
                self.show_test_result(True, f"Successfully reached Endpoint! Response: {txt}")
            except Exception as e:
                self.show_test_result(False, str(e))
            finally:
                self.after(0, lambda: self.openai_test_btn.config(state=tk.NORMAL, text="Test Connection"))

        threading.Thread(target=run_test, daemon=True).start()

    def test_ollama_conn(self):
        key = self.ollama_key_var.get().strip()
        host = self.ollama_host_var.get().strip()
        model = self.ollama_model_var.get().strip()

        self.ollama_test_btn.config(state=tk.DISABLED, text="Testing...")

        def run_test():
            try:
                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                client = httpx.Client(
                    base_url=host.rstrip("/"),
                    headers=headers,
                    timeout=httpx.Timeout(12.0, connect=5.0),
                )
                payload = {
                    "model": model,
                    "stream": False,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                    "options": {"num_predict": 10}
                }
                resp = client.post("/api/chat", json=payload)
                resp.raise_for_status()
                txt = resp.json()["message"]["content"]
                self.show_test_result(True, f"Successfully reached Ollama! Response: {txt}")
            except Exception as e:
                self.show_test_result(False, str(e))
            finally:
                self.after(0, lambda: self.ollama_test_btn.config(state=tk.NORMAL, text="Test Connection"))

        threading.Thread(target=run_test, daemon=True).start()

    def test_openrouter_conn(self):
        or_cfg = self.config.providers.openrouter
        key = self.openrouter_key_var.get().strip() or os.environ.get(or_cfg.api_key_env, "")
        model = self.openrouter_model_var.get().strip()

        if not key:
            messagebox.showerror("Error", "Please input an OpenRouter API Key to test.")
            return

        self.openrouter_test_btn.config(state=tk.DISABLED, text="Testing...")

        def run_test():
            try:
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
                if self.openrouter_site_url_var.get().strip():
                    headers["HTTP-Referer"] = self.openrouter_site_url_var.get().strip()
                if self.openrouter_app_name_var.get().strip():
                    headers["X-OpenRouter-Title"] = self.openrouter_app_name_var.get().strip()
                client = httpx.Client(
                    base_url=or_cfg.base_url,
                    headers=headers,
                    timeout=httpx.Timeout(30.0, connect=5.0),
                )
                payload = {
                    "model": model,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                }
                resp = client.post("/chat/completions", json=payload)
                if resp.is_error:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                txt = resp.json()["choices"][0]["message"]["content"]
                self.show_test_result(True, f"Successfully reached OpenRouter! Response: {txt}")
            except Exception as e:
                self.show_test_result(False, str(e))
            finally:
                self.after(0, lambda: self.openrouter_test_btn.config(state=tk.NORMAL, text="Test Connection"))

        threading.Thread(target=run_test, daemon=True).start()

    def show_test_result(self, is_ok, msg):
        self.after(0, lambda: messagebox.showinfo("Connection Test Result", "✓ Connection Successful!\n" + msg) if is_ok else messagebox.showerror("Connection Test Result", "✗ Connection Failed!\n" + msg))

    def save_settings(self):
        # Update config.yaml values
        try:
            token_values = {
                name: int(var.get().strip())
                for name, var in (
                    ("anthropic", self.anthropic_max_tokens_var),
                    ("openai_compat", self.openai_max_tokens_var),
                    ("ollama", self.ollama_max_tokens_var),
                    ("openrouter", self.openrouter_max_tokens_var),
                )
            }
            if any(v <= 0 for v in token_values.values()):
                raise ValueError("max tokens must be positive")
        except ValueError:
            messagebox.showerror("Error", "Max Tokens must be a whole number greater than zero.", parent=self)
            return

        for label, var in (
            ("Anthropic Model Name", self.anthropic_model_var),
            ("OpenAI Compat Model Name", self.openai_model_var),
            ("OpenAI Compat Base URL", self.openai_base_url_var),
            ("Ollama Model Name", self.ollama_model_var),
            ("Ollama Host URL", self.ollama_host_var),
            ("OpenRouter Model", self.openrouter_model_var),
        ):
            if not var.get().strip():
                messagebox.showerror("Error", f"{label} cannot be empty.", parent=self)
                return
        for label, var in (
            ("OpenAI Compat Base URL", self.openai_base_url_var),
            ("Ollama Host URL", self.ollama_host_var),
        ):
            if not var.get().strip().lower().startswith(("http://", "https://")):
                messagebox.showerror("Error", f"{label} must start with http:// or https://", parent=self)
                return

        try:
            self.config.providers.anthropic.model = self.anthropic_model_var.get().strip()
            self.config.providers.anthropic.max_tokens = int(self.anthropic_max_tokens_var.get().strip())

            self.config.providers.openai_compat.base_url = self.openai_base_url_var.get().strip()
            self.config.providers.openai_compat.model = self.openai_model_var.get().strip()
            self.config.providers.openai_compat.max_tokens = int(self.openai_max_tokens_var.get().strip())

            self.config.providers.ollama.host = self.ollama_host_var.get().strip()
            self.config.providers.ollama.model = self.ollama_model_var.get().strip()
            self.config.providers.ollama.max_tokens = int(self.ollama_max_tokens_var.get().strip())

            self.config.providers.openrouter.model = self.openrouter_model_var.get().strip()
            self.config.providers.openrouter.max_tokens = int(self.openrouter_max_tokens_var.get().strip())
            self.config.providers.openrouter.site_url = self.openrouter_site_url_var.get().strip()
            self.config.providers.openrouter.app_name = self.openrouter_app_name_var.get().strip()

            self.config.provider = self.active_provider_var.get()

            save_config(self.config)
            reload_config()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}", parent=self)
            return

        # Update secrets.yaml -- keep any other keys already stored there
        secrets_data = dict(self.secrets) if isinstance(self.secrets, dict) else {}
        secrets_data.pop("openai_api_key", None)   # legacy name, superseded below
        secrets_data.update({
            "anthropic_api_key": self.anthropic_key_var.get().strip(),
            "openai_compat_api_key": self.openai_key_var.get().strip(),
            "ollama_api_key": self.ollama_key_var.get().strip(),
            "openrouter_api_key": self.openrouter_key_var.get().strip(),
        })

        try:
            with self.secrets_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(secrets_data, f, default_flow_style=False)
            
            # Secure key file permissions on non-windows, no-op on windows
            try:
                os.chmod(self.secrets_path, 0o600)
            except Exception:
                pass
                
            self.ui_manager.check_provider_status()
            messagebox.showinfo("Success", "Settings and API keys saved successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save API keys: {e}")
