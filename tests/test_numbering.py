"""
Tests for NumberingTracker (continuous and module-prefixed modes).
"""

from manual_builder.numbering import NumberingTracker
from manual_builder.style_loader import StyleConfig


def test_module_prefixed_numbering():
    tracker = NumberingTracker(mode="module_prefixed")
    
    # Track section numbering
    tracker.set_current_module(10)
    tracker.set_section_number(level=1, number=10)
    
    assert tracker.get_current_section_number() == "10"
    
    # Subsection numbers
    sec_1 = tracker.enter_section(level=2)
    assert sec_1 == "10.1"
    
    sec_2 = tracker.enter_section(level=2)
    assert sec_2 == "10.2"

    # Figures prefix & format
    fig_1 = tracker.next_figure(10)
    assert fig_1 == "10-1"
    
    fig_2 = tracker.next_figure(10)
    assert fig_2 == "10-2"
    
    # Table numbers
    tbl_1 = tracker.next_table(10)
    assert tbl_1 == "10-1"


def test_continuous_numbering():
    # Setup dummy style
    style_data = {
        "numbering": {
            "figure_format": "{fig}",
            "table_format": "{tbl}"
        }
    }
    style = StyleConfig(raw=style_data)
    tracker = NumberingTracker(style_config=style, mode="continuous")

    # Module 1
    tracker.set_current_module(1)
    tracker.set_section_number(level=1, number=1)
    
    # Check global continuous figures
    fig_1 = tracker.next_figure(1)
    assert fig_1 == "1"
    
    fig_2 = tracker.next_figure(1)
    assert fig_2 == "2"

    # Module 2
    tracker.set_current_module(2)
    tracker.set_section_number(level=1, number=2)
    
    fig_3 = tracker.next_figure(2)
    assert fig_3 == "3"

    # Table continuous checks
    tbl_1 = tracker.next_table(1)
    assert tbl_1 == "1"
    tbl_2 = tracker.next_table(2)
    assert tbl_2 == "2"
