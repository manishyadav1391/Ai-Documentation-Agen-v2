"""
Numbering tracker — central figure/table/section number registry.

All renderers must call this tracker so numbering is consistent
across the entire document.
"""

from typing import Dict, List, Tuple


class NumberingTracker:
    """
    Manages section, figure, and table numbering across the entire document.

    Supports the NCB scheme (module-fig, e.g., "10-1", "10-2") by default.
    Supports NCD scheme (continuous, e.g., "1", "2", "3") across modules.
    Configurable via the style's ``numbering`` block or explicit mode.
    """

    def __init__(self, style_config=None, mode: str = "module_prefixed"):
        self.style = style_config
        self.mode = mode
        # Section stack: [(level, counter)] e.g., [(1, 10), (2, 1)]
        self._section_stack: List[Tuple[int, int]] = []
        # Counters per module: {module_num: count}
        self._figure_counter: Dict[int, int] = {}
        self._table_counter: Dict[int, int] = {}
        # Global counters (for continuous mode)
        self._global_figure_counter: int = 0
        self._global_table_counter: int = 0
        # Preamble counters (for sections before modules like SOP)
        self._preamble_figure_counter: int = 0
        self._preamble_table_counter: int = 0
        # Caption registries for Table of Figures / Table of Tables
        self._figure_captions: List[Dict] = []
        self._table_captions: List[Dict] = []
        # Current section tracking
        self._section_counters: Dict[int, int] = {}  # level -> counter
        self._current_module_num: int = 0


    # ── Section numbering ─────────────────────────────────────────────────

    def enter_section(self, level: int) -> str:
        """
        Push a new section at the given level and return its number string.

        Example: entering level 1 multiple times gives "1", "2", "3".
        Entering level 2 under section 10 gives "10.1", "10.2".
        """
        # Reset all deeper levels
        for deeper in list(self._section_counters.keys()):
            if deeper > level:
                del self._section_counters[deeper]

        self._section_counters[level] = self._section_counters.get(level, 0) + 1

        # Build number string from all levels up to current
        parts = []
        for l in sorted(self._section_counters.keys()):
            if l <= level:
                parts.append(str(self._section_counters[l]))
        return ".".join(parts)

    def set_section_number(self, level: int, number: int):
        """Explicitly set the counter for a level (e.g., for module numbering)."""
        self._section_counters[level] = number
        # Reset deeper levels
        for deeper in list(self._section_counters.keys()):
            if deeper > level:
                del self._section_counters[deeper]

    def get_current_section_number(self) -> str:
        """Return current section number string."""
        parts = []
        for l in sorted(self._section_counters.keys()):
            parts.append(str(self._section_counters[l]))
        return ".".join(parts) if parts else "0"

    # ── Figure numbering ──────────────────────────────────────────────────

    def next_figure(self, module_num: int = 0) -> str:
        """
        Get the next figure number string for a module.
        """
        if self.mode == "continuous":
            self._global_figure_counter += 1
            fig_num = self._global_figure_counter
            fmt = "{fig}"
            if self.style and hasattr(self.style, 'numbering'):
                fmt = self.style.numbering.get("figure_format", fmt)
            return fmt.format(fig=fig_num)

        if module_num == 0:
            self._preamble_figure_counter += 1
            fig_num = self._preamble_figure_counter
            section = self.get_current_section_number()
            return f"{section}-{fig_num}"

        self._figure_counter[module_num] = self._figure_counter.get(module_num, 0) + 1
        fig_num = self._figure_counter[module_num]

        fmt = "{module}-{fig}"
        if self.style and hasattr(self.style, 'numbering'):
            fmt = self.style.numbering.get("figure_format", fmt)

        return fmt.format(module=module_num, fig=fig_num)

    def register_figure(self, number: str, caption: str):
        """Register a figure caption for Table of Figures generation."""
        self._figure_captions.append({
            "number": number,
            "caption": caption,
        })

    # ── Table numbering ───────────────────────────────────────────────────

    def next_table(self, module_num: int = 0) -> str:
        """
        Get the next table number string for a module.
        """
        if self.mode == "continuous":
            self._global_table_counter += 1
            tbl_num = self._global_table_counter
            fmt = "{tbl}"
            if self.style and hasattr(self.style, 'numbering'):
                fmt = self.style.numbering.get("table_format", fmt)
            return fmt.format(tbl=tbl_num)

        if module_num == 0:
            self._preamble_table_counter += 1
            tbl_num = self._preamble_table_counter
            section = self.get_current_section_number()
            return f"{section}-{tbl_num}"

        self._table_counter[module_num] = self._table_counter.get(module_num, 0) + 1
        tbl_num = self._table_counter[module_num]

        fmt = "{module}-{tbl}"
        if self.style and hasattr(self.style, 'numbering'):
            fmt = self.style.numbering.get("table_format", fmt)

        return fmt.format(module=module_num, tbl=tbl_num)

    def register_table(self, number: str, caption: str):
        """Register a table caption for Table of Tables generation."""
        self._table_captions.append({
            "number": number,
            "caption": caption,
        })


    # ── Caption registries ────────────────────────────────────────────────

    def get_all_figures(self) -> List[Dict]:
        """Return all registered figure captions."""
        return list(self._figure_captions)

    def get_all_tables(self) -> List[Dict]:
        """Return all registered table captions."""
        return list(self._table_captions)

    # ── Module tracking ───────────────────────────────────────────────────

    def set_current_module(self, module_num: int):
        """Set the current module number (for renderers that need it)."""
        self._current_module_num = module_num

    @property
    def current_module(self) -> int:
        return self._current_module_num

    # ── Prefix helpers ────────────────────────────────────────────────────

    @property
    def figure_prefix(self) -> str:
        if self.style and hasattr(self.style, 'numbering'):
            return self.style.numbering.get("figure_prefix", "Figure")
        return "Figure"

    @property
    def table_prefix(self) -> str:
        if self.style and hasattr(self.style, 'numbering'):
            return self.style.numbering.get("table_prefix", "Table")
        return "Table"

    @property
    def figure_count(self) -> int:
        """Total figures registered so far (used to decide whether to emit TOF)."""
        return len(self._figure_captions)

    @property
    def table_count(self) -> int:
        """Total tables registered so far (used to decide whether to emit TOT)."""
        return len(self._table_captions)

