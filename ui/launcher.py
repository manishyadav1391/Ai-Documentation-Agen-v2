import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# Add project root directory to sys.path to allow imports from parent directory
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import our core logic functions
from main import run_pipeline
from master_assembler import assemble_master_manual

class LauncherUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Documentation Automation Bot")
        self.root.geometry("600x500")
        
        # Title
        tk.Label(root, text="Documentation Automation Bot", font=("Arial", 16, "bold")).pack(pady=20)
        
        # Section 1: Record New Module
        record_frame = tk.LabelFrame(root, text="1. Capture & Process", padx=10, pady=10)
        record_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(record_frame, text="Start a new browser session to capture screens and generate content.", wraplength=400).pack(pady=5)
        tk.Button(record_frame, text="Record New Module", bg="lightblue", font=("Arial", 11, "bold"), command=self.start_recording).pack(pady=5)
        
        # Section 2: Assemble Master Manual
        assemble_frame = tk.LabelFrame(root, text="2. Assemble Final Client Manual", padx=10, pady=10)
        assemble_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        tk.Label(assemble_frame, text="Select completed modules (sessions) in the correct order to generate the final Word document.", wraplength=400).pack(pady=5)
        
        # Listbox for sessions
        self.session_listbox = tk.Listbox(assemble_frame, selectmode=tk.MULTIPLE, height=8)
        self.session_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.refresh_sessions()
        
        btn_frame = tk.Frame(assemble_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Refresh List", command=self.refresh_sessions).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Generate Master Manual", bg="lightgreen", font=("Arial", 11, "bold"), command=self.assemble_manual).pack(side=tk.RIGHT, padx=5)

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
            run_pipeline()
            messagebox.showinfo("Success", "Module recorded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
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
            
        output_path = Path("Final_Client_Manual.docx")
        try:
            assemble_master_manual(ordered_sessions, output_path)
            messagebox.showinfo("Success", f"Master Manual generated successfully!\nSaved to: {output_path.absolute()}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to assemble manual: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherUI(root)
    root.mainloop()