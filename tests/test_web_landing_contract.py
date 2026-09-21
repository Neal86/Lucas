from __future__ import annotations

from gpt_windows_connector.web_landing import LANDING_HTML
from gpt_windows_connector.web_landing_header import LANDING_HEADER_HTML
from gpt_windows_connector.web_landing_header_styles import LANDING_HEADER_STYLE
from gpt_windows_connector.web_landing_styles import LANDING_BODY_STYLE
from gpt_windows_connector.web_styles import WEB_STYLE


def test_landing_header_has_single_authoritative_style_source():
    assert ".landing-nav" not in WEB_STYLE
    assert "/* Lucas public landing */" not in WEB_STYLE
    assert ".landing-nav" in LANDING_HEADER_STYLE
    assert "<style>" not in LANDING_HEADER_HTML


def test_header_is_fixed_and_above_content():
    assert "position:fixed!important" in LANDING_HEADER_STYLE
    assert "top:0;left:0;right:0" in LANDING_HEADER_STYLE
    assert "z-index:1000!important" in LANDING_HEADER_STYLE


def test_mobile_signin_remains_visible_and_independent():
    assert ".landing-nav>.landing-links{display:none!important}" in LANDING_HEADER_STYLE
    assert ".landing-nav>.landing-signin{display:inline-flex!important" in LANDING_HEADER_STYLE
    assert ".landing-nav>.landing-links,.landing-nav>.landing-signin" not in LANDING_HEADER_STYLE


def test_mobile_menu_is_large_and_borderless():
    assert ".mobile-menu summary{" in LANDING_HEADER_STYLE
    assert "width:42px;height:42px;border:0" in LANDING_HEADER_STYLE
    assert "font-size:26px" in LANDING_HEADER_STYLE


def test_mobile_header_is_pinned_to_viewport():
    assert "position:fixed!important;top:0!important;left:0!important;right:0!important" in LANDING_HEADER_STYLE
    assert "width:100vw!important;max-width:100vw!important" in LANDING_HEADER_STYLE
    assert "transform:translateZ(0)" in LANDING_HEADER_STYLE
    assert "backdrop-filter:none!important" in LANDING_HEADER_STYLE


def test_fixed_mobile_header_does_not_cover_hero():
    assert ".hero{padding:112px 20px 62px!important}" in LANDING_BODY_STYLE


def test_landing_is_composed_from_modules():
    assert LANDING_HEADER_HTML in LANDING_HTML
    assert LANDING_HEADER_STYLE in LANDING_HTML
    assert LANDING_BODY_STYLE in LANDING_HTML
    assert "Start for free" in LANDING_HTML


def test_public_home_does_not_slice_landing_out_of_dashboard():
    from pathlib import Path
    from gpt_windows_connector import webapp

    source = Path(webapp.__file__).read_text(encoding="utf-8")
    assert "landing = LANDING_HTML" in source
    assert "DASHBOARD_HTML.index('\\n<div id=\"auth\"'" not in source
