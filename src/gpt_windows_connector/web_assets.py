from __future__ import annotations

from .web_auth_markup import AUTH_HTML
from .web_dashboard_markup import DASHBOARD_MARKUP
from .web_dashboard_runtime_bundle import DASHBOARD_RUNTIME_SCRIPT
from .web_document import WEB_BODY_PREFIX, WEB_HEAD
from .web_i18n_runtime import I18N_SCRIPT
from .web_landing import LANDING_HTML
from .web_styles import WEB_STYLE

DASHBOARD_HTML = (
    WEB_HEAD
    + WEB_STYLE
    + WEB_BODY_PREFIX
    + LANDING_HTML
    + AUTH_HTML
    + DASHBOARD_MARKUP
    + I18N_SCRIPT
    + DASHBOARD_RUNTIME_SCRIPT
)
