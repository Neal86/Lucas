import re

from starlette.routing import Route

from gpt_windows_connector.web_core_runtime import CORE_SCRIPT
from gpt_windows_connector.webapp import routes


def _route_map():
    return {
        route.path: route.endpoint.__name__
        for route in routes
        if isinstance(route, Route)
    }


def _frontend_paths(const_name: str) -> set[str]:
    match = re.search(rf"const {const_name}=\{{(.*?)\}};", CORE_SCRIPT, re.DOTALL)
    assert match, f"Frontend route map {const_name} was not found"
    return set(re.findall(r":'([^']+)'", match.group(1)))


def test_every_frontend_view_path_has_a_server_route():
    route_map = _route_map()
    frontend_paths = _frontend_paths("viewPaths")
    missing = sorted(frontend_paths - route_map.keys())
    assert not missing, f"Frontend deep links missing backend routes: {missing}"


def test_every_frontend_admin_path_has_a_server_route():
    route_map = _route_map()
    frontend_paths = _frontend_paths("adminPaths")
    missing = sorted(frontend_paths - route_map.keys())
    assert not missing, f"Admin deep links missing backend routes: {missing}"
    assert all(route_map[path] == "admin_page" for path in frontend_paths)


def test_dashboard_shell_routes_still_use_dashboard_handler():
    route_map = _route_map()
    shell_paths = {"/dashboard", "/nodes", "/ai-connections", "/task-runs", "/logs", "/account"}
    assert all(route_map.get(path) == "dashboard" for path in shell_paths)
