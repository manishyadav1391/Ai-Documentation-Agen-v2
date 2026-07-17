import tkinter as tk
from tkinter import ttk

class ProgressWindow(tk.Toplevel):
    def __init__(self, parent, title="Task in Progress", cancel_event=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x380")
        self.resizable(False, False)
        
        # Raise on top initially without grab or topmost
        self.lift()
        self.focus()
        
        self.cancel_event = cancel_event

        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.status_lbl = tk.Label(
            main_frame, 
            text="Initializing...", 
            font=("Segoe UI", 10, "bold"), 
            anchor="w", 
            justify=tk.LEFT,
            fg="#1E293B"
        )
        self.status_lbl.pack(fill=tk.X, pady=(0, 10))

        self.pb = ttk.Progressbar(main_frame, mode="indeterminate")
        self.pb.pack(fill=tk.X, pady=(0, 15))
        self.pb.start(10)  # Start the animation by default

        log_frame = tk.LabelFrame(main_frame, text="Execution Logs", font=("Segoe UI", 9, "bold"), fg="#475569")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9), bg="#F8FAFC", fg="#334155")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(self.log_text, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.cancel_btn = tk.Button(
            main_frame, 
            text="Cancel Task", 
            command=self.on_cancel, 
            bg="#EF4444", 
            fg="white", 
            activebackground="#DC2626",
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            padx=10
        )
        self.cancel_btn.pack(pady=(0, 5))

        # Protocol handler for close button
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def write_log(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def set_status(self, text: str):
        self.status_lbl.config(text=text)

    def set_progress(self, percent: int):
        """Switch progress bar to determinate and set a specific percentage."""
        if self.pb["mode"] != "determinate":
            self.pb.stop()
            self.pb.config(mode="determinate", maximum=100)
        self.pb["value"] = percent

    def on_cancel(self):
        if self.cancel_event:
            self.cancel_event.set()
            self.write_log("Cancellation requested. Aborting cleanly on next step...")
            self.cancel_btn.config(state=tk.DISABLED, text="Cancelling...")
        else:
            self.destroy()
