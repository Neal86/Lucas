from __future__ import annotations

# Routes that render user-visible pages and must be checked before production.
# expected_status=None means any non-5xx HTTP status is acceptable because the
# page may legitimately redirect to sign-in or reject an unauthenticated user.
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
