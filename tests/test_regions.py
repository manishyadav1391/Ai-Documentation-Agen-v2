"""
Tests for region detection (IoU merge and double-emit prevention).
"""

from docbot.models import Element, BBox
from docbot.processing.regions import detect_regions


def test_iou_merge_overlapping_regions():
    # Two same-role regions overlapping heavily (IoU > 0.6)
    r1_elements = [
        Element(id="el1", accessible_name="Name Input", element_class="interactive", bounding_box=BBox(x=10, y=10, width=100, height=20)),
        Element(id="el2", accessible_name="Password Input", element_class="interactive", bounding_box=BBox(x=10, y=40, width=100, height=20))
    ]
    
    # Run detect regions on these elements
    regions = detect_regions(r1_elements)
    
    # Should collapse into exactly 1 filter_form region instead of multiple separate ones
    assert len(regions) == 1
    assert regions[0].role == "filter_form"
    assert "Name Input" in regions[0].elements_contained
    assert "Password Input" in regions[0].elements_contained


def test_page_header_parentheses_operator_precedence():
    # Verify W13: (el.type == "label") and (el.tag in ("h1", "h2")) is correctly evaluated
    elements = [
        # Label h1 elements should match page header role
        Element(id="el_h1", accessible_name="User Registration", element_class="static_label", tag="h1", type="label", bounding_box=BBox(x=0, y=0, width=200, height=30)),
        # Standard input label should NOT match page header role
        Element(id="el_lbl", accessible_name="Username:", element_class="static_label", tag="label", type="label", bounding_box=BBox(x=10, y=50, width=50, height=15))
    ]
    
    regions = detect_regions(elements)
    
    # Should only create page_header for User Registration
    header_regions = [r for r in regions if r.role == "page_header"]
    assert len(header_regions) == 1
    assert header_regions[0].elements_contained == ["User Registration"]
