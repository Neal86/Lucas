from __future__ import annotations

import hashlib
from pathlib import Path

from gpt_windows_connector import webapp
from gpt_windows_connector.web_landing_brand import LANDING_LOGO_URL, LANDING_NAV_TEXT_COLOR
from gpt_windows_connector.web_landing_header import LANDING_HEADER_HTML
from gpt_windows_connector.web_landing_header_styles import LANDING_HEADER_STYLE
from gpt_windows_connector.web_landing_sections import LANDING_SECTIONS_HTML
from gpt_windows_connector.web_landing_styles import LANDING_BODY_STYLE


EXPECTED_WHITE_LOGO_SHA256 = "f0e1b4a65c311e388ebc92798187f6de69078935c3b7e2c8e3c6ce733a2bfeef"


def test_verified_white_logo_asset_is_unchanged():
    asset = Path(webapp.__file__).with_name("assets") / "lucas-logo-horizontal-white.png"
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == EXPECTED_WHITE_LOGO_SHA256


def test_landing_logo_url_has_one_authoritative_value():
    assert LANDING_LOGO_URL == "/assets/lucas-logo-horizontal-white.png?v=exact-f0e1b4a6"
    assert LANDING_LOGO_URL in LANDING_HEADER_HTML
    assert LANDING_LOGO_URL in LANDING_SECTIONS_HTML
    assert 'src="/assets/lucas-logo-horizontal.png"' not in LANDING_HEADER_HTML
    assert 'src="/assets/lucas-logo-horizontal.png"' not in LANDING_SECTIONS_HTML


def test_landing_menu_color_has_one_authoritative_value():
    assert LANDING_NAV_TEXT_COLOR == "#dfe4f3"
    assert f".landing-links a{{color:{LANDING_NAV_TEXT_COLOR};" in LANDING_HEADER_STYLE
    assert ".landing-links a{" not in LANDING_BODY_STYLE


def test_landing_header_logo_has_no_cross_module_filter_override():
    assert "\n.landing-logo img{" not in LANDING_BODY_STYLE
    assert ".landing-nav>.landing-logo img{" in LANDING_HEADER_STYLE
    assert "filter:none!important" in LANDING_HEADER_STYLE


def test_server_does_not_patch_landing_brand_or_navigation():
    source = Path(webapp.__file__).with_name("server.py").read_text(encoding="utf-8")
    forbidden = (
        "WHITE_LOGO_URL",
        "BLUE_LOGO_URL",
        ".landing-links a,.landing-footer",
        ".landing-logo img{",
        "lucas-logo-horizontal-blue.png",
    )
    for token in forbidden:
        assert token not in source
