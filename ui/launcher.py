import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from pathlib import Path

# Add project root directory to sys.path to allow imports from parent directory
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import our core logic functions
from main import run_pipeline
from master_assembler import assemble_master_manual
from config import get_config, save_config, reload_config
from ui.style_editor import StyleEditorDialog
from manual_builder.manifest_loader import get_available_clients

class StyleConfigDialog(tk.Toplevel):
    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.root_parent = parent
        self.title("Configure Document Styling & Branding")
        self.geometry("520x620")
        self.resizable(False, False)
        self.grab_set()  # Make window modal
        
        self.config = get_config()
        self.theme = self.config.theme
        
        self.build_ui()

    def build_ui(self):
        """Constructs style configuration form controls."""
        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text="Document Styling & Branding Configurator", font=("Arial", 12, "bold"), fg="#1E293B").pack(pady=(0, 15))

        # --- Metadata Section ---
        meta_frame = tk.LabelFrame(main_frame, text="1. Document Metadata", padx=10, pady=10)
        meta_frame.pack(fill=tk.X, pady=5)

        tk.Label(meta_frame, text="Company / Org Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.company_entry = tk.Entry(meta_frame, width=35)
        self.company_entry.insert(0, self.theme.company_name)
        self.company_entry.grid(row=0, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        tk.Label(meta_frame, text="Manual Subtitle:").grid(row=1, column=0, sticky="w", pady=5)
        self.subtitle_entry = tk.Entry(meta_frame, width=35)
        self.subtitle_entry.insert(0, self.theme.subtitle)
        self.subtitle_entry.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        # --- Styling Section ---
        style_frame = tk.LabelFrame(main_frame, text="2. Design & Accent Colors", padx=10, pady=10)
        style_frame.pack(fill=tk.X, pady=5)

        # Font Combo
        tk.Label(style_frame, text="Font Family:").grid(row=0, column=0, sticky="w", pady=5)
        self.font_combo = ttk.Combobox(style_frame, values=["Segoe UI", "Arial", "Calibri", "Georgia", "Times New Roman"], state="readonly", width=18)
        self.font_combo.set(self.theme.font_name)
        self.font_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # Primary Color
        tk.Label(style_frame, text="Primary Color (Hex):").grid(row=1, column=0, sticky="w", pady=5)
        self.primary_entry = tk.Entry(style_frame, width=12)
        primary_val = self.theme.primary_color
        if not primary_val.startswith("#"):
            primary_val = f"#{primary_val}"
        self.primary_entry.insert(0, primary_val)
        self.primary_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Pick...", command=lambda: self.pick_color(self.primary_entry)).grid(row=1, column=2, sticky="w", padx=2, pady=5)

        # Secondary Color
        tk.Label(style_frame, text="Secondary Color (Hex):").grid(row=2, column=0, sticky="w", pady=5)
        self.secondary_entry = tk.Entry(style_frame, width=12)
        secondary_val = self.theme.secondary_color
        if not secondary_val.startswith("#"):
            secondary_val = f"#{secondary_val}"
        self.secondary_entry.insert(0, secondary_val)
        self.secondary_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Pick...", command=lambda: self.pick_color(self.secondary_entry)).grid(row=2, column=2, sticky="w", padx=2, pady=5)

        # Logo Path
        tk.Label(style_frame, text="Company Logo:").grid(row=3, column=0, sticky="w", pady=5)
        self.logo_entry = tk.Entry(style_frame, width=28)
        self.logo_entry.insert(0, self.theme.logo_path)
        self.logo_entry.grid(row=3, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        tk.Button(style_frame, text="Browse...", command=self.browse_logo).grid(row=3, column=3, sticky="w", padx=2, pady=5)

        # --- AI Theme Generator Section ---
        ai_frame = tk.LabelFrame(main_frame, text="3. AI Smart-Branding Assistant (Needs API Key)", padx=10, pady=10)
        ai_frame.pack(fill=tk.X, pady=5)

        tk.Label(ai_frame, text="Describe your desired brand theme / vibe:", font=("Arial", 8, "italic")).pack(anchor="w", pady=2)
        
        input_subframe = tk.Frame(ai_frame)
        input_subframe.pack(fill=tk.X, pady=2)
        
        self.ai_desc_entry = tk.Entry(input_subframe, width=36)
        self.ai_desc_entry.insert(0, "professional healthcare in deep teal and gold")
        self.ai_desc_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        tk.Button(input_subframe, text="Auto-Style", bg="#e0f2fe", command=self.ai_suggest_style).pack(side=tk.RIGHT, padx=5)

        # --- Bottom Buttons ---
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Settings", bg="lightgreen", font=("Arial", 10, "bold"), width=15, command=self.save_settings).pack(side=tk.RIGHT, padx=5)

    def pick_color(self, entry_widget):
        """Opens a native color chooser popup and updates the target entry field."""
        curr_val = entry_widget.get()
        initial = curr_val if curr_val.startswith("#") else f"#{curr_val}"
        color_code = colorchooser.askcolor(title="Choose Accent Color", initialcolor=initial)
        if color_code and color_code[1]:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, color_code[1].upper())

    def browse_logo(self):
        """Opens file dialog for selecting a logo image."""
        file_path = filedialog.askopenfilename(
            title="Select Company Logo",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("All Files", "*.*")]
        )
        if file_path:
            self.logo_entry.delete(0, tk.END)
            self.logo_entry.insert(0, file_path)

    def ai_suggest_style(self):
        """Requests design recommendations from active LLM provider."""
        desc = self.ai_desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Warning", "Please enter a brand description first.")
            return

        from llm_ui import request_llm_processing
        
        prompt = (
            f"Generate a professional document style palette based on this request: '{desc}'.\n"
            "Provide colors that match corporate standards. Respond in JSON format only. The JSON must contain exactly these fields:\n"
            "{\n"
            "  \"primary_color\": \"hex color code without # (e.g., 003366)\",\n"
            "  \"secondary_color\": \"hex color code without # (e.g., FF6600)\",\n"
            "  \"font_name\": \"one of: Segoe UI, Arial, Calibri\"\n"
            "}\n"
            "Do not include any Markdown fencing, triple backticks, or text comments. Just the raw JSON object."
        )

        try:
            self.config_cursor("wait")
            self.update()
            
            result = request_llm_processing(prompt, default_provider=self.config.provider, is_json=True)
            if result and isinstance(result, dict):
                p_col = result.get("primary_color", "1B365D").replace("#", "")
                s_col = result.get("secondary_color", "D97706").replace("#", "")
                font = result.get("font_name", "Segoe UI")
                
                self.primary_entry.delete(0, tk.END)
                self.primary_entry.insert(0, f"#{p_col.upper()}")
                
                self.secondary_entry.delete(0, tk.END)
                self.secondary_entry.insert(0, f"#{s_col.upper()}")
                
                self.font_combo.set(font)
                messagebox.showinfo("AI Style Assistant", f"Suggested brand styling successfully applied!\n\nFont: {font}\nPrimary: #{p_col.upper()}\nSecondary: #{s_col.upper()}")
            else:
                messagebox.showerror("Error", "Could not parse style suggestions from LLM. Check provider output.")
        except Exception as e:
            messagebox.showerror("Error", f"AI Styling assistant request failed: {e}")
        finally:
            self.config_cursor("")

    def config_cursor(self, cursor_type):
        try:
            self.config(cursor=cursor_type)
            self.root_parent.config(cursor=cursor_type)
        except Exception:
            pass

    def save_settings(self):
        """Validates settings and writes them permanently to config.yaml."""
        company = self.company_entry.get().strip()
        subtitle = self.subtitle_entry.get().strip()
        font = self.font_combo.get()
        primary = self.primary_entry.get().strip().replace("#", "")
        secondary = self.secondary_entry.get().strip().replace("#", "")
        logo = self.logo_entry.get().strip()

        if not company:
            messagebox.showerror("Error", "Company Name cannot be empty.")
            return

        if len(primary) != 6 or len(secondary) != 6:
            messagebox.showerror("Error", "Colors must be valid 6-character hex strings.")
            return

        # Update config model
        self.theme.company_name = company
        self.theme.subtitle = subtitle
        self.theme.font_name = font
        self.theme.primary_color = primary
        self.theme.secondary_color = secondary
        self.theme.logo_path = logo

        try:
            save_config(self.config)
            reload_config()
            self.ui_manager.refresh_brand_summary()
            messagebox.showinfo("Success", "Styling settings saved successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")


class LauncherUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Documentation Automation Bot v2")
        self.root.geometry("680x620")
        self.root.resizable(False, False)
        
        self.config = get_config()
        self.client_key = self.config.current_client

        # Title
        tk.Label(root, text="Documentation Automation Bot v2", font=("Arial", 16, "bold"), fg="#1F3864").pack(pady=15)
        
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

        # Style & Content Config Buttons
        ctrl_btn_frame = tk.Frame(client_frame)
        ctrl_btn_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=10)

        tk.Button(ctrl_btn_frame, text="Configure Formatting...", bg="#EFF6FF", font=("Arial", 9, "bold"), command=self.open_style_editor).pack(side=tk.LEFT, padx=5)
        tk.Button(ctrl_btn_frame, text="Configure Content Files...", bg="#F5F5F5", font=("Arial", 9), command=self.open_content_folder).pack(side=tk.LEFT, padx=5)

        # Summary Display Label
        self.brand_label = tk.Label(client_frame, text="", font=("Arial", 9), fg="#475569", anchor="w", justify=tk.LEFT)
        self.brand_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=5)
        self.refresh_brand_summary()

        # Section 1: Record New Module
        record_frame = tk.LabelFrame(root, text="1. Capture & Process Module", padx=12, pady=10)
        record_frame.pack(fill=tk.X, padx=20, pady=8)
        
        tk.Label(record_frame, text="Record screens (Middle-Click), add additional states (Shift+Middle-Click), and process.", font=("Arial", 9), fg="#64748B", wraplength=600, justify=tk.LEFT).pack(anchor="w", pady=2)
        tk.Button(record_frame, text="Record New Module", bg="#2563EB", fg="white", font=("Arial", 10, "bold"), command=self.start_recording).pack(pady=5)
        
        # Section 2: Assemble Master Manual
        assemble_frame = tk.LabelFrame(root, text="2. Compile Master Client Manual", padx=12, pady=10)
        assemble_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=8)
        
        tk.Label(assemble_frame, text="Select recorded modules in order to compile the final deliverable.", font=("Arial", 9), fg="#64748B", wraplength=600, justify=tk.LEFT).pack(anchor="w", pady=2)
        
        # Listbox for sessions
        self.session_listbox = tk.Listbox(assemble_frame, selectmode=tk.MULTIPLE, height=5, font=("Arial", 9))
        self.session_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.refresh_sessions()
        
        btn_frame = tk.Frame(assemble_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Refresh List", command=self.refresh_sessions).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Assemble Master Manual", bg="#059669", fg="white", font=("Arial", 10, "bold"), command=self.assemble_manual).pack(side=tk.RIGHT, padx=5)

    def on_client_change(self, event):
        self.client_key = self.client_var.get()
        self.config.current_client = self.client_key
        save_config(self.config)
        reload_config()
        self.refresh_brand_summary()

    def refresh_brand_summary(self):
        """Displays short status of current client from manifest and style config."""
        from manual_builder import load_manifest, load_style
        try:
            m = load_manifest(self.client_key, content_dir=self.config.content_dir)
            s = load_style(self.client_key, styles_dir=self.config.styles_dir)
            summary = (
                f"Client: {m.client_display_name} | System: {m.system_name} ({m.system_acronym})\n"
                f"Manual Title: {m.manual_title} v{m.version}\n"
                f"Colors: Primary #{s.primary_color} | Accent #{s.accent_color} | Font: {s.body_font}"
            )
        except Exception as e:
            summary = f"Error loading details for client '{self.client_key}':\n{e}"
        self.brand_label.config(text=summary)

    def open_style_editor(self):
        """Opens the new 8-tab visual formatting style editor."""
        StyleEditorDialog(self.root, self.client_key)
        self.refresh_brand_summary()

    def open_content_folder(self):
        """Opens the client's content files folder in Windows Explorer."""
        folder = Path("content") / self.client_key
        if folder.exists():
            import os
            try:
                os.startfile(str(folder.resolve()))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder: {e}")
        else:
            messagebox.showerror("Error", f"Content folder does not exist: {folder}")

    def new_client(self):
        """Dialog to create a new client scaffold folder from defaults."""
        new_key = filedialog.asksaveasfilename(
            initialdir="content",
            title="Create New Client Folder (Enter Client Acronym Name)",
            filetypes=[]
        )
        if not new_key:
            return
        
        new_key = Path(new_key).name.lower().replace(" ", "_")
        if not new_key:
            return
            
        content_dir = Path("content")
        styles_dir = Path("styles")
        
        new_content_path = content_dir / new_key
        new_style_path = styles_dir / f"{new_key}.yaml"
        
        if new_content_path.exists() or new_style_path.exists():
            messagebox.showerror("Error", f"Client key '{new_key}' already exists.")
            return
            
        import shutil
        try:
            # 1. Copy content/_default to content/new_key
            shutil.copytree("content/_default", str(new_content_path))
            
            # 2. Copy styles/_default.yaml to styles/new_key.yaml
            shutil.copy("styles/_default.yaml", str(new_style_path))
            
            # 3. Update manifest.yaml in the new client content folder
            manifest_file = new_content_path / "manifest.yaml"
            if manifest_file.exists():
                with manifest_file.open("r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f) or {}
                manifest_data["client_key"] = new_key
                manifest_data["client_display_name"] = new_key.upper()
                with manifest_file.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(manifest_data, f, sort_keys=False)

            # Reload client list
            self.client_list = get_available_clients()
            self.client_combo.config(values=self.client_list)
            self.client_var.set(new_key)
            self.on_client_change(None)
            messagebox.showinfo("Success", f"Client scaffold '{new_key}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create new client: {e}")

    def refresh_sessions(self):
        """Loads available session folders into the listbox."""
        try:
            if not self.session_listbox.winfo_exists():
                return
        except Exception:
            return
        self.session_listbox.delete(0, tk.END)
        sessions_dir = Path("sessions")
        if sessions_dir.exists():
            for session in sorted(sessions_dir.glob("session_*")):
                self.session_listbox.insert(tk.END, session.name)

    def start_recording(self):
        """Triggers the main recording pipeline, then refreshes the list."""
        self.root.iconify()  # Hide launcher during capture
        try:
            run_pipeline(client_key=self.client_key)
            messagebox.showinfo("Success", "Module recorded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during capture: {e}")
        finally:
            try:
                if self.root.winfo_exists():
                    self.refresh_sessions()
                    self.root.deiconify()  # Restore launcher
            except Exception:
                pass

    def assemble_manual(self):
        """Gathers selected sessions and triggers the master assembler."""
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
        except Exception as e:
            messagebox.showerror("Error", f"Failed to assemble manual: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherUI(root)
    root.mainloop()