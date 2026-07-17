import tkinter as tk
from tkinter import ttk
from docbot import paths

class ScrollableFrame(ttk.Frame):
    """Vertical-scroll container. Put content in .body. Scrollbar auto-hides."""
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._vbar = ttk.Scrollbar(self, orient="vertical",
                                   command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)

        self.body = ttk.Frame(self._canvas)
        self._win = self._canvas.create_window((0, 0), window=self.body,
                                               anchor="nw")
        self.body.bind("<Configure>", self._on_body_resize)
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfigure(self._win, width=e.width))
        # mousewheel only while pointer is over this widget
        self._canvas.bind("<Enter>",
            lambda e: self._canvas.bind_all("<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>",
            lambda e: self._canvas.unbind_all("<MouseWheel>"))

    def _on_body_resize(self, _e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        need = self.body.winfo_reqheight() > self._canvas.winfo_height()
        (self._vbar.grid if need else self._vbar.grid_remove)()

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-e.delta / 120), "units")


def setup_dialog(dlg: tk.Toplevel, parent: tk.Misc,
                 min_w=420, min_h=300, modal=True):
    dlg.transient(parent.winfo_toplevel())
    dlg.minsize(min_w, min_h)                # resizable stays ON
    
    # Apply app icon to the dialog if it exists
    try:
        icon_path = paths.bundle_dir() / "assets" / "docbot.ico"
        if icon_path.exists():
            dlg.iconbitmap(str(icon_path))
    except Exception:
        pass

    dlg.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    w = max(min_w, dlg.winfo_reqwidth()); h = max(min_h, dlg.winfo_reqheight())
    sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
    x = max(0, min(px + (pw - w)//2, sw - w))
    y = max(0, min(py + (ph - h)//2, sh - h))
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    if modal:
        dlg.grab_set()


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 27
        y = y + self.widget.winfo_rooty() + 27
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()
