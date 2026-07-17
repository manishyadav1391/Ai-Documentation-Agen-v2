from tkinter import ttk, font as tkfont

PAD_S, PAD_M, PAD_L = 4, 8, 16
ACCENT       = "#2563EB"
ACCENT_DARK  = "#1D4ED8"
DANGER       = "#DC2626"
BG           = "#F8FAFC"
SIDEBAR_BG   = "#F1F5F9"
TEXT         = "#0F172A"
TEXT_MUTED   = "#64748B"

def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")   # most stylable cross-version base

    base = tkfont.nametofont("TkDefaultFont")
    base.configure(family="Segoe UI", size=10)
    root.option_add("*Font", base)

    style.configure(".", background=BG, foreground=TEXT, font=base)
    style.configure("TFrame", background=BG)
    style.configure("TLabelframe", background=BG)
    style.configure("TLabelframe.Label", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 10))
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Title.TLabel", font=("Segoe UI Semibold", 15), background=BG)
    style.configure("Muted.TLabel", foreground=TEXT_MUTED, font=("Segoe UI", 9), background=BG)
    style.configure("Status.TLabel", foreground=TEXT_MUTED,
                    font=("Segoe UI", 9), background="#EEF2F7")
    style.configure("Status.TFrame", background="#EEF2F7")

    style.configure("TButton", padding=(12, 6))
    style.configure("Primary.TButton", background=ACCENT, foreground="white",
                    padding=(16, 8), font=("Segoe UI Semibold", 10))
    style.map("Primary.TButton",
              background=[("active", ACCENT_DARK), ("disabled", "#93B4F5")])
    style.configure("Danger.TButton", foreground=DANGER)

    style.configure("Sidebar.TFrame", background=SIDEBAR_BG)
    style.configure("Sidebar.TButton", background=SIDEBAR_BG, anchor="w",
                    padding=(14, 10), relief="flat")
    style.map("Sidebar.TButton", background=[("active", "#E2E8F0")])
    style.configure("SidebarActive.TButton", background="#E2E8F0",
                    anchor="w", padding=(14, 10),
                    font=("Segoe UI Semibold", 10))

    style.configure("TNotebook", background=BG)
    style.configure("TNotebook.Tab", font=("Segoe UI", 10))

    style.configure("Treeview", rowheight=28, fieldbackground="white",
                    background="white")
    style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9),
                    padding=(6, 6))
