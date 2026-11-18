"""
Backend regression tests: region detection and the deterministic step
compiler (the fallback text used when LLM generation fails).
"""

from docbot.models import BBox, Element, Event, Region
from docbot.processing.regions import _iou_merge, detect_regions
from docbot.processing.steps import compile_steps


# --- Regions ---------------------------------------------------------------

def test_backend_h2_label_yields_one_region():
    el = Element(id="h", element_class="static_label", tag="h2", type="label",
                 accessible_name="Account", bounding_box=BBox(x=10, y=10, width=200, height=30))
    regions = detect_regions([el])
    assert len(regions) == 1


def test_backend_formless_inputs_not_one_page_box():
    els = [
        Element(id="a", tag="input", accessible_name="Search",
                bounding_box=BBox(x=10, y=10, width=100, height=30)),
        Element(id="b", tag="input", accessible_name="Comment",
                bounding_box=BBox(x=1500, y=900, width=100, height=30)),
        Element(id="c", tag="button", role="button", accessible_name="Log in",
                bounding_box=BBox(x=800, y=10, width=80, height=30)),
    ]
    forms = [r for r in detect_regions(els) if r.role == "filter_form"]
    assert len(forms) == 2
    assert all(r.bounding_box.width < 200 and r.bounding_box.height < 100 for r in forms)
    assert not any("Log in" in r.elements_contained for r in forms)


def test_backend_containment_merge_order_independent():
    big = Region(role="filter_form", bounding_box=BBox(x=0, y=0, width=800, height=600),
                 elements_contained=["big"])
    small = Region(role="filter_form", bounding_box=BBox(x=10, y=10, width=100, height=30),
                   elements_contained=["small"])
    assert len(_iou_merge([big, small])) == 1
    assert len(_iou_merge([small, big])) == 1


# --- Steps -----------------------------------------------------------------

def _texts(events):
    return [s.text for s in compile_steps(events)]


def test_backend_navigate_without_title():
    events = [Event(kind="click", target_name="Save", target_role="button"),
              Event(kind="navigate", url_before="a", url_after="b")]
    assert _texts(events)[-1] == "The next page will be displayed."


def test_backend_navigate_title_ending_in_page():
    events = [Event(kind="navigate", target_name="Login Page", url_before="a", url_after="b")]
    assert _texts(events) == ["The Login Page will be displayed."]


def test_backend_keystroke_inputs_one_line_per_field():
    events = [Event(kind="input", target_name="Username", target_selector="#u")
              for _ in range(3)]
    assert _texts(events) == ["Enter the Username."]


def test_backend_enter_then_submit_is_one_action():
    events = [Event(kind="input", target_name="Search", target_selector="#q"),
              Event(kind="keypress_enter", target_name="Search"),
              Event(kind="submit"),
              Event(kind="navigate", target_name="Results", url_before="a", url_after="b")]
    assert _texts(events) == ["Enter the Search.", "Press Enter to submit the Search.",
                              "The Results page will be displayed."]


def test_backend_click_then_submit_is_one_action():
    events = [Event(kind="click", target_name="Login", target_role="button"),
              Event(kind="submit"),
              Event(kind="navigate", target_name="Dashboard", url_before="a", url_after="b")]
    assert _texts(events) == ["Click on the Login button.", "The Dashboard page will be displayed."]


def test_backend_no_button_button():
    events = [Event(kind="click", target_name="Submit button", target_role="button")]
    assert _texts(events) == ["Click on the Submit button."]


def test_backend_checkbox_not_dropdown():
    assert _texts([Event(kind="change", target_name="Remember me", value_summary="on")]) == \
        ["Select the Remember me checkbox."]
    assert _texts([Event(kind="change", target_name="Remember me", target_role="checkbox",
                         value_summary="false")]) == ["Clear the Remember me checkbox."]
    assert _texts([Event(kind="change", target_name="Country", value_summary="India")]) == \
        ["Select 'India' from the Country dropdown."]
