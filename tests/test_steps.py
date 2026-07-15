"""
Tests for deterministic step compilation.
"""

from docbot.models import Event, BBox
from docbot.processing.steps import compile_steps


def test_consecutive_inputs_folding():
    events = [
        Event(id="e1", kind="input", target_name="Username", target_selector="#user", value_summary="admin"),
        Event(id="e2", kind="input", target_name="Password", target_selector="#pass", value_summary="123", redacted=True),
        Event(id="e3", kind="click", target_name="Login", target_selector="#login_btn", target_role="button")
    ]
    
    steps = compile_steps(events)
    
    # Should compile to:
    # 1. Enter the following details:
    # 2.   Username.
    # 3.   Password.
    # 4. Click on the Login button.
    assert len(steps) == 4
    assert steps[0].text == "Enter the following details:"
    assert "Username" in steps[1].text
    assert "Password" in steps[2].text
    assert steps[3].text == "Click on the Login button."


def test_click_and_navigation_result_step():
    events = [
        Event(id="e1", kind="click", target_name="Register", target_selector="#reg_btn", target_role="button", url_before="page1"),
        Event(id="e2", kind="navigate", target_name="Register Confirmation", url_before="page1", url_after="page2")
    ]
    
    steps = compile_steps(events)
    
    # Click + navigation should collapse into an action step followed by a result step
    assert len(steps) == 2
    assert steps[0].text == "Click on the Register button."
    assert steps[1].text == "The Register Confirmation page will be displayed."
    assert steps[1].kind == "result"

