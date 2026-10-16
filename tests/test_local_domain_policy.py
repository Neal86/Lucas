"""Node/account domain restrictions must narrow authority through real preflight."""
import asyncio

import pytest

from gpt_windows_connector import browser
from gpt_windows_connector.access_control import intersect_security, preset_security
from gpt_windows_connector.executor import Executor
from gpt_windows_connector.security import LocalSecurityPolicy


def policy(node_domains, user_domains):
    base = preset_security("auto_approve")
    return intersect_security({**base, "allowed_domains": node_domains}, {**base, "allowed_domains": user_domains})


@pytest.mark.parametrize("host", ["company.example", "partner.example", "unrelated.example"])
def test_disjoint_lists_deny_every_destination(host):
    security = LocalSecurityPolicy({"security": policy(["company.example"], ["partner.example"])})
    with pytest.raises(PermissionError):
        security.authorize("browser.navigate", {"url": "https://" + host})


@pytest.mark.parametrize("left,right,allowed,denied", [
    (["example.com"], ["api.example.com"], "api.example.com", "www.example.com"),
    (["api.example.com"], ["example.com"], "sub.api.example.com", "example.com"),
    (["*.example.com"], ["example.com"], "api.example.com", "example.com"),
    (["*.example.com"], ["*.api.example.com"], "v1.api.example.com", "api.example.com"),
    (["EXAMPLE.COM."], ["Api.Example.Com."], "API.EXAMPLE.COM.", "evilapi.example.com"),
    (["example.com", "elsewhere.example"], ["api.example.com", "elsewhere.example"], "elsewhere.example", "elsewhere.example.evil"),
])
def test_semantic_intersections_preserve_only_shared_scope(left, right, allowed, denied):
    security = LocalSecurityPolicy({"security": policy(left, right)})
    security.authorize("browser.navigate", {"url": "https://" + allowed})
    with pytest.raises(PermissionError):
        security.authorize("browser.navigate", {"url": "https://" + denied})


@pytest.mark.parametrize("left,right", [([], []), ([""], []), ([], [""])])
def test_original_empty_lists_keep_unrestricted_semantics(left, right):
    security = LocalSecurityPolicy({"security": policy(left, right)})
    security.authorize("browser.navigate", {"url": "https://ordinary.example"})


@pytest.mark.parametrize("left,right", [(["example.com"], []), ([], ["example.com"])])
def test_single_restriction_is_preserved(left, right):
    security = LocalSecurityPolicy({"security": policy(left, right)})
    security.authorize("browser.navigate", {"url": "https://api.example.com"})
    with pytest.raises(PermissionError):
        security.authorize("browser.navigate", {"url": "https://notexample.com"})


def test_deny_all_survives_a_second_policy_intersection():
    restricted = policy(["a.example"], ["b.example"])
    effective = intersect_security(restricted, preset_security("auto_approve"))
    with pytest.raises(PermissionError):
        LocalSecurityPolicy({"security": effective}).authorize("browser.navigate", {"url": "https://a.example"})


@pytest.mark.parametrize("method,params", [("browser.navigate", {"url": "file:///tmp/private"}), ("git.push", {})])
def test_restricted_network_requires_a_known_allowed_host(method, params):
    security = LocalSecurityPolicy({"security": policy(["example.com"], ["example.com"])})
    security._prompt = lambda *args: True
    with pytest.raises(PermissionError, match="allowlist"):
        security.authorize(method, params)


def test_disallowed_navigation_never_reaches_executor_browser(tmp_path, monkeypatch):
    called = []

    async def navigate(**params):
        called.append(params)
        return {"ok": True}

    monkeypatch.setattr(browser, "navigate", navigate)
    executor = Executor((tmp_path,), {"security": policy(["a.example"], ["b.example"])})
    with pytest.raises(PermissionError):
        asyncio.run(executor.call("browser.navigate", {"url": "https://unrelated.example"}))
    assert called == []


def test_intersection_matches_both_authorities_across_domain_shapes():
    from gpt_windows_connector.domain_policy import host_allowed, intersect_domains

    grants = [[], ["example.com"], ["*.example.com"], ["api.example.com"],
              ["*.api.example.com"], ["other.test"], ["EXAMPLE.COM."],
              ["example.com", "other.test"], ["."]]
    hosts = ["example.com", "api.example.com", "sub.api.example.com", "other.test",
             "sub.other.test", "example.com.evil", "notexample.com", "", "API.EXAMPLE.COM."]
    for left in grants:
        for right in grants:
            domains, restricted = intersect_domains(left, right)
            for host in hosts:
                assert host_allowed(host, domains, restricted) == (host_allowed(host, left) and host_allowed(host, right))


@pytest.mark.parametrize("malformed,host", [("example.com", "example.m"), ({"example.com": True}, "example.com"),
                                          ([None], "none"), ([123], "123"), (["example.com", None], "example.com"),
                                          (None, "example.com")])
@pytest.mark.parametrize("combined", [False, True])
def test_malformed_domain_configuration_fails_closed(malformed, host, combined):
    settings = {**preset_security("auto_approve"), "allowed_domains": malformed}
    if combined:
        settings = intersect_security(settings, preset_security("auto_approve"))
    security = LocalSecurityPolicy({"security": settings})
    with pytest.raises(PermissionError):
        security.authorize("browser.navigate", {"url": "https://" + host})
