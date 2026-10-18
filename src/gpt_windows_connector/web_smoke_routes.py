from __future__ import annotations

# Routes that render user-visible pages and must be checked before production.
# expected_status=None uses the explicit authentication-aware allowlist below.
# Missing routes (404), malformed requests and rate limits must never pass.
WEB_SMOKE_ROUTES: tuple[tuple[str, int | None], ...] = (
    ("/", 200),
    ("/features", 200),
    ("/how-it-works", 200),
    ("/security", 200),
    ("/download", 200),
    ("/docs/computer-node", 200),
    ("/pricing", 200),
    ("/privacy", 200),
    ("/terms", 200),
    ("/refunds", 200),
    ("/contact", 200),
    ("/refer", 200),
    ("/dashboard", 200),
    ("/nodes", 200),
    ("/ai-connections", 200),
    ("/task-runs", 200),
    ("/logs", 200),
    ("/account", 200),
    ("/billing", None),
    ("/billing/success", None),
    ("/billing/cancel", None),
    ("/admin", None),
    ("/admin/users", None),
    ("/admin/usage", None),
    ("/admin/nodes", None),
    ("/admin/operations", None),
    ("/admin/subscriptions", None),
    ("/admin/system", None),
)



AUTH_PAGE_STATUSES = frozenset({200, 301, 302, 303, 307, 308, 401, 403})


def expected_statuses(expected: int | None) -> frozenset[int]:
    """Public pages require their exact status; auth pages allow known gates."""
    return AUTH_PAGE_STATUSES if expected is None else frozenset({expected})
