from starlette.routing import Route

from gpt_windows_connector.webapp import routes


DASHBOARD_ROUTES = {
    "/dashboard",
    "/nodes",
    "/ai-connections",
    "/task-runs",
    "/logs",
    "/account",
}

ADMIN_ROUTES = {
    "/admin",
    "/admin/users",
    "/admin/usage",
    "/admin/nodes",
    "/admin/operations",
    "/admin/subscriptions",
    "/admin/system",
}


def _route_map():
    return {
        route.path: route.endpoint.__name__
        for route in routes
        if isinstance(route, Route)
    }


def test_dashboard_deep_link_routes_are_registered():
    route_map = _route_map()
    missing = sorted(DASHBOARD_ROUTES - route_map.keys())
    assert not missing, f"Missing dashboard deep-link routes: {missing}"
    assert all(route_map[path] == "dashboard" for path in DASHBOARD_ROUTES)


def test_admin_deep_link_routes_are_registered():
    route_map = _route_map()
    missing = sorted(ADMIN_ROUTES - route_map.keys())
    assert not missing, f"Missing admin deep-link routes: {missing}"
    assert all(route_map[path] == "admin_page" for path in ADMIN_ROUTES)
