from pathlib import Path

from gpt_windows_connector.browser_agent_policy import authorize_profile
from gpt_windows_connector.browser_profile_registry import BrowserProfileRegistry


def make_registry(tmp_path: Path) -> BrowserProfileRegistry:
    return BrowserProfileRegistry(
        registry_file=tmp_path / "profiles.json",
        bindings_file=tmp_path / "bindings.json",
    )


def test_profile_resolves_by_id_name_alias_tag_and_group(tmp_path):
    store = make_registry(tmp_path)
    profile = store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_id": "11",
        "profile_name": "Jarvis",
        "aliases": ["jarvis", "marketing-main"],
        "tags": ["US", "Meta"],
        "groups": ["Marketing"],
    })

    assert store.resolve(profile_id="11")["profile"]["profile_key"] == profile["profile_key"]
    assert store.resolve(profile_name="Jarvis")["profile"]["profile_key"] == profile["profile_key"]
    assert store.resolve(alias="marketing-main")["profile"]["profile_key"] == profile["profile_key"]
    assert store.resolve(tag="Meta")["profile"]["profile_key"] == profile["profile_key"]
    assert store.resolve(group="Marketing")["profile"]["profile_key"] == profile["profile_key"]


def test_task_binding_survives_registry_reload(tmp_path):
    store = make_registry(tmp_path)
    profile = store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_id": "11",
        "profile_name": "Jarvis",
    })
    store.bind_task(
        "loopora-pinterest",
        profile["profile_key"],
        actor_key="Jarvis",
        transport="bridge",
        bridge_installation_id="bridge-1",
    )

    reloaded = make_registry(tmp_path)
    binding = reloaded.task_binding("loopora-pinterest")
    assert binding is not None
    assert binding["profile_key"] == profile["profile_key"]
    assert binding["bridge_installation_id"] == "bridge-1"


def test_agent_policy_allows_group_and_denies_finance():
    marketing = {
        "profile_key": "ixbrowser:id:11",
        "profile_name": "Jarvis",
        "aliases": ["jarvis"],
        "groups": ["Marketing"],
        "tags": ["US"],
    }
    finance = {
        "profile_key": "ixbrowser:id:12",
        "profile_name": "Finance",
        "aliases": ["finance"],
        "groups": ["Finance"],
        "tags": ["US"],
    }
    policy = {
        "allow_profiles": [],
        "allow_aliases": [],
        "allow_groups": ["Marketing"],
        "allow_tags": [],
        "deny_profiles": [],
        "deny_groups": ["Finance"],
        "deny_tags": [],
    }

    assert authorize_profile(marketing, policy)["allowed"] is True
    assert authorize_profile(finance, policy)["allowed"] is False


def test_bridge_pairing_is_persisted_in_profile_registry(tmp_path):
    store = make_registry(tmp_path)
    profile = store.upsert_profile({
        "browser_type": "ixbrowser",
        "profile_name": "Eva",
        "aliases": ["eva"],
        "bridge_installation_id": "install-123",
        "extension_id": "extension-abc",
    })

    found = store.profile_for_bridge("install-123")
    assert found is not None
    assert found["profile_key"] == profile["profile_key"]
    assert found["aliases"] == ["eva"]
