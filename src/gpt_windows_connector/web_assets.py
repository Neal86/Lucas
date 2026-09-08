from __future__ import annotations

from .web_admin_runtime import ADMIN_SCRIPT
from .web_auth_markup import AUTH_HTML
from .web_billing_runtime import BILLING_SCRIPT
from .web_core_runtime import CORE_SCRIPT
from .web_dashboard_markup import DASHBOARD_MARKUP
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
    + BILLING_SCRIPT
    + CORE_SCRIPT
    + ADMIN_SCRIPT
)
