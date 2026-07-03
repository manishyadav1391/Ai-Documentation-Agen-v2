import tkinter as tk
from tkinter import ttk, messagebox
import json

class LLMOrchestratorUI:
    def __init__(self, root, prompt_text: str, default_provider: str = "browser", is_json: bool = True):
        self.root = root
        self.prompt_text = prompt_text
        self.is_json = is_json
        self.result_data = None
        
        self.root.title("LLM Assistant & Input Manager")
        self.root.geometry("900x600")
        
        self.build_ui(default_provider)

    def build_ui(self, default_provider):
        # Top Config Bar
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill=tk.X)
        
        tk.Label(top_frame, text="Select Provider Mode:", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=10)
        
        self.provider_var = tk.StringVar(value=default_provider)
        provider_combo = ttk.Combobox(top_frame, textvariable=self.provider_var, state="readonly", values=["browser", "anthropic", "openai_compat", "ollama"])
        provider_combo.pack(side=tk.LEFT, padx=5)
        provider_combo.bind("<<ComboboxSelected>>", self.toggle_mode_layout)
        
        # Split Layout (Left: Prompt / Right: Input-Output Box)
        paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Left Panel - Prompt Display
        left_frame = tk.LabelFrame(paned_window, text="Generated System Prompt")
        paned_window.add(left_frame, weight=1)
        
        self.prompt_box = tk.Text(left_frame, wrap=tk.WORD, bg="#f4f4f4")
        self.prompt_box.insert(tk.END, self.prompt_text)
        self.prompt_box.config(state=tk.DISABLED)
        self.prompt_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Right Panel - Interaction & Editing Area
        self.right_frame = tk.LabelFrame(paned_window, text="AI Response / User Workspace")
        paned_window.add(self.right_frame, weight=1)
        
        self.workspace_box = tk.Text(self.right_frame, wrap=tk.WORD)
        self.workspace_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Bottom Dynamic Button Box
        self.action_frame = tk.Frame(self.right_frame, pady=5)
        self.action_frame.pack(fill=tk.X)
        
        self.btn_action = tk.Button(self.action_frame, text="Copy Prompt to Clipboard", bg="lightblue", command=self.copy_prompt)
        self.btn_action.pack(side=tk.LEFT, padx=5)
        
        # Bottom Absolute Window Controls
        bottom_bar = tk.Frame(self.root, pady=10)
        bottom_bar.pack(fill=tk.X)
        
        tk.Button(bottom_bar, text="Save & Continue", bg="lightgreen", font=("Arial", 10, "bold"), command=self.save_and_close).pack(side=tk.RIGHT, padx=10)
        
        # Initialize Layout View
        self.toggle_mode_layout()

    def toggle_mode_layout(self, event=None):
        mode = self.provider_var.get()
        # Clean current dynamic button state
        for widget in self.action_frame.winfo_children():
            widget.destroy()
            
        if mode == "browser":
            self.btn_action = tk.Button(self.action_frame, text="Copy Prompt to Clipboard", bg="lightblue", command=self.copy_prompt)
            self.btn_action.pack(side=tk.LEFT, padx=5)
            # Prompt user cleanly inside the edit space
            if not self.workspace_box.get("1.0", tk.END).strip():
                self.workspace_box.insert(tk.END, "--> Paste Claude's Response directly here <--")
        else:
            self.btn_action = tk.Button(self.action_frame, text="Execute Outbound API Request", bg="orange", command=self.call_api)
            self.btn_action.pack(side=tk.LEFT, padx=5)

    def copy_prompt(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.prompt_text)
        messagebox.showinfo("Success", "Prompt copied directly to system clipboard! Paste it into your AI browser portal.")

    def call_api(self):
        """Fetches the raw response from the selected API provider."""
        # 1. Disable the button so the user doesn't spam requests
        self.btn_action.config(state=tk.DISABLED, text="Fetching from AI...")
        self.root.update()
        
        try:
            # 2. Clear the workspace
            self.workspace_box.delete("1.0", tk.END)
            
            mode = self.provider_var.get()
            
            import sys
            from pathlib import Path
            root_dir = Path(__file__).resolve().parent
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))
                
            from providers.anthropic_api import AnthropicProvider
            from providers.openai_compat import OpenAICompatProvider
            from providers.ollama import OllamaProvider
            
            provider_map = {
                "anthropic": AnthropicProvider,
                "openai_compat": OpenAICompatProvider,
                "ollama": OllamaProvider
            }
            
            provider_cls = provider_map.get(mode)
            if not provider_cls:
                raise ValueError(f"Unknown API provider: {mode}")
                
            provider_inst = provider_cls()
            raw_response = provider_inst._chat(self.prompt_text)
            
            # 4. Display the response in the Tkinter text box
            self.workspace_box.insert(tk.END, raw_response)
            
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("API Error", f"The API request failed:\n\n{str(e)}")
            
        finally:
            # 5. Re-enable the button
            self.btn_action.config(state=tk.NORMAL, text="Execute Outbound API Request")

    def save_and_close(self):
        user_input = self.workspace_box.get("1.0", tk.END).strip()
        
        if self.is_json:
            try:
                # User handles errors manually inside the text box if validation fails
                self.result_data = json.loads(user_input)
            except json.JSONDecodeError:
                msg = "The content is not in valid JSON array structure. Please check and correct formatting errors manually inside the workspace before saving."
                messagebox.showerror("JSON Format Error", msg)
                return
        else:
            self.result_data = user_input
            
        self.root.destroy()

def request_llm_processing(prompt_text: str, default_provider: str = "browser", is_json: bool = True):
    """
    Opens the LLM UI safely, preventing root window collisions.
    """
    if tk._default_root:
        root = tk.Toplevel()
        is_subwindow = True
    else:
        root = tk.Tk()
        is_subwindow = False
        
    app = LLMOrchestratorUI(root, prompt_text, default_provider, is_json)
    
    if is_subwindow:
        root.grab_set()
        root.wait_window(root)
    else:
        root.mainloop()
        
    return app.result_data