from __future__ import annotations

from .web_landing_header import LANDING_HEADER_HTML
from .web_landing_header_styles import LANDING_HEADER_STYLE
from .web_landing_hero import LANDING_HERO_HTML
from .web_landing_sections import LANDING_SECTIONS_HTML
from .web_landing_styles import LANDING_BODY_STYLE

LANDING_HTML = (
    '<section id="landing" class="landing">'
    + LANDING_HEADER_STYLE
    + LANDING_BODY_STYLE
    + LANDING_HEADER_HTML
    + LANDING_HERO_HTML
    + LANDING_SECTIONS_HTML
    + '</section>'
)
