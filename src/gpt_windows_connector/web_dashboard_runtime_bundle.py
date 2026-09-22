from __future__ import annotations

from .web_admin_runtime import ADMIN_SCRIPT
from .web_billing_runtime import BILLING_SCRIPT
from .web_core_runtime import CORE_SCRIPT
from .web_onboarding_runtime import ONBOARDING_SCRIPT
from .web_referral_runtime import REFERRAL_SCRIPT


# Single owner of the Dashboard application script boundary.
# Runtime modules above are intentionally pure JavaScript fragments.
DASHBOARD_RUNTIME_SCRIPT = (
    "<script>\n"
    + BILLING_SCRIPT
    + REFERRAL_SCRIPT
    + CORE_SCRIPT
    + ONBOARDING_SCRIPT
    + ADMIN_SCRIPT
    + "</script>\n</body></html>"
)
