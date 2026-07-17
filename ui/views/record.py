import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
from pathlib import Path
from main import run_pipeline
from docbot import paths

class RecordView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.recording_active = False
        self.captured_count = 0
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # We will hold two sub-frames: setup_frame and active_frame
        self.setup_frame = ttk.Frame(self, padding=16)
        self.active_frame = ttk.Frame(self, padding=16)
        
        self._build_setup_ui()
        self._build_active_ui()
        
        self.show_setup()
        
    def _build_setup_ui(self):
        f = self.setup_frame
        f.columnconfigure(1, weight=1)
        
        # Title
        ttk.Label(f, text="Record New Module", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))
        
        # Inputs Group
        ttk.Label(f, text="Start URL:").grid(row=1, column=0, sticky="w", pady=6)
        self.url_entry = ttk.Entry(f, font=("Segoe UI", 10))
        self.url_entry.insert(0, "https://google.com")
        self.url_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=6)
        
        ttk.Label(f, text="Module Name:").grid(row=2, column=0, sticky="w", pady=6)
        self.module_name_entry = ttk.Entry(f, font=("Segoe UI", 10))
        self.module_name_entry.insert(0, "User Interface")
        self.module_name_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=6)
        
        ttk.Label(f, text="Module Number:").grid(row=3, column=0, sticky="w", pady=6)
        self.module_num_entry = ttk.Entry(f, font=("Segoe UI", 10), width=10)
        self.module_num_entry.insert(0, "10")
        self.module_num_entry.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=6)
        
        # Description / Guidance
        desc = (
            "How it works:\n"
            "1. Enter the starting web address and module details.\n"
            "2. Click the 'Start Recording' button to launch Playwright.\n"
            "3. Middle-click anywhere on the web page to capture a screenshot.\n"
            "4. Double middle-click when you are finished to stop recording."
        )
        ttk.Label(f, text=desc, style="Muted.TLabel", justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(24, 0))
        
        # Action button
        self.start_btn = ttk.Button(f, text="Start Recording", style="Primary.TButton", command=self.start_recording)
        self.start_btn.grid(row=5, column=0, columnspan=2, pady=24)
        
    def _build_active_ui(self):
        f = self.active_frame
        f.columnconfigure(0, weight=1)
        
        # Indicator Label
        self.indicator_lbl = ttk.Label(f, text="● Recording Session Active", style="Title.TLabel", foreground="#DC2626")
        self.indicator_lbl.grid(row=0, column=0, pady=(20, 10))
        
        # Instruction Label
        inst_text = (
            "Middle-click anywhere in the browser to capture a screen.\n"
            "Double middle-click to save and finalize the session."
        )
        ttk.Label(f, text=inst_text, justify="center").grid(row=1, column=0, pady=10)
        
        # Counter Frame
        self.counter_lbl = ttk.Label(f, text="Screens Captured: 0", font=("Segoe UI Semibold", 13))
        self.counter_lbl.grid(row=2, column=0, pady=20)
        
        # Stop Button
        self.stop_btn = ttk.Button(f, text="Stop & Cancel", style="Danger.TButton", command=self.stop_recording)
        self.stop_btn.grid(row=3, column=0, pady=20)
        
    def show_setup(self):
        self.active_frame.grid_forget()
        self.setup_frame.grid(row=0, column=0, sticky="nsew")
        self.recording_active = False
        
    def show_active(self):
        self.setup_frame.grid_forget()
        self.active_frame.grid(row=0, column=0, sticky="nsew")
        self.recording_active = True
        self.captured_count = 0
        self.counter_lbl.config(text="Screens Captured: 0")
        
    def refresh(self):
        if not self.recording_active:
            self.show_setup()
            
    def start_recording(self):
        start_url = self.url_entry.get().strip()
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
                
        if not self.app.check_and_install_browser():
            return
            
        self.show_active()
        self.app.start_background_recording(start_url, mod_name, mod_num, self)
        
    def stop_recording(self):
        self.app.cancel_background_recording()
        self.show_setup()
        
    def update_count(self, count):
        self.captured_count = count
        self.counter_lbl.config(text=f"Screens Captured: {count}")
