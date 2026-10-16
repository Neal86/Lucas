"""Structural controls for mobile fixes; hosted Chromium verifies real layout."""
from __future__ import annotations

import re

import pytest

from gpt_windows_connector.web_admin_styles import ADMIN_RESPONSIVE_STYLE
from gpt_windows_connector.web_landing_styles import LANDING_BODY_STYLE
from gpt_windows_connector.web_styles import WEB_STYLE


@pytest.mark.parametrize("width", [320, 375, 390, 768, 1365])
def test_decorative_landing_glows_fit_their_containing_viewport(width):
    # Read actual CSS bounds and independently calculate the decorative boxes.
    for name, side, original_width, original_offset in (
        ("glow-a", "left", 650, 15), ("glow-b", "right", 500, 4),
    ):
        rule = re.search(r"\." + name + r"\{([^}]+)\}", LANDING_BODY_STYLE).group(1)
        match = re.search(r"width:min\((\d+)px,(\d+)%\)", rule)
        assert match, "Fixed-width decoration must not enlarge the mobile viewport"
        pixels, percent = map(int, match.groups())
        offset = int(re.search(side + r":(\d+)%", rule).group(1))
        assert (pixels, offset) == (original_width, original_offset)
        rendered_width = min(pixels, width * percent / 100)
        assert rendered_width > 0
        assert width * offset / 100 + rendered_width <= width + 1e-9
        if width == 1365:
            assert rendered_width == original_width
    assert "pointer-events:none" in LANDING_BODY_STYLE


def test_admin_responsive_rules_are_scoped_composed_and_do_not_hide_controls():
    from gpt_windows_connector import server

    assert "@media(max-width:850px)" in ADMIN_RESPONSIVE_STYLE
    assert "#admin .toolbar{flex-wrap:wrap}" in ADMIN_RESPONSIVE_STYLE
    assert "#admin .toolbar>.input,#admin .toolbar>select{min-width:0;max-width:100%}" in ADMIN_RESPONSIVE_STYLE
    assert not re.search(r"overflow\s*:|display\s*:|visibility\s*:", ADMIN_RESPONSIVE_STYLE)
    assert WEB_STYLE.count(ADMIN_RESPONSIVE_STYLE) == 1
    html = server.webapp._dashboard_html()
    assert html.count(ADMIN_RESPONSIVE_STYLE) == 1
    assert html.count('id="adminTabs"') == 1
    assert html.count('id="adminContent"') == 1
