from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class EvaBrowserTarget:
    label: str
    node_id: str
    endpoint: str
    profile: str
    user_data_dir: str
    executable_path: str


EVA_CLIENT_ID = os.getenv(
    "LUCAS_EVA_CLIENT_ID",
    "lucas_RadfVO6VaiwUY5bEzzq6piO9NApZRJLb",
).strip()

_DEFAULT_ENDPOINT = os.getenv(
    "LUCAS_EVA_BROWSER_ENDPOINT",
    "http://127.0.0.1:9222",
).strip()
_DEFAULT_PROFILE = os.getenv("LUCAS_EVA_BROWSER_PROFILE", "eva").strip()
_DEFAULT_EXECUTABLE = os.getenv(
    "LUCAS_EVA_BROWSER_EXECUTABLE",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
).strip()


def _target(
    *,
    label: str,
    node_env: str,
    node_default: str,
    data_dir_env: str,
    data_dir_default: str,
    endpoint_env: str,
    profile_env: str,
    executable_env: str,
) -> EvaBrowserTarget | None:
    node_id = os.getenv(node_env, node_default).strip()
    if not node_id:
        return None
    return EvaBrowserTarget(
        label=label,
        node_id=node_id,
        endpoint=os.getenv(endpoint_env, _DEFAULT_ENDPOINT).strip() or _DEFAULT_ENDPOINT,
        profile=os.getenv(profile_env, _DEFAULT_PROFILE).strip() or _DEFAULT_PROFILE,
        user_data_dir=os.getenv(data_dir_env, data_dir_default).strip(),
        executable_path=os.getenv(executable_env, _DEFAULT_EXECUTABLE).strip() or _DEFAULT_EXECUTABLE,
    )


def configured_targets() -> tuple[EvaBrowserTarget, ...]:
    targets = (
        _target(
            label="ALI",
            node_env="LUCAS_EVA_ALI_NODE_ID",
            node_default=os.getenv("LUCAS_EVA_NODE_ID", "ali-bc0358dd0a5d"),
            data_dir_env="LUCAS_EVA_ALI_BROWSER_USER_DATA_DIR",
            data_dir_default=os.getenv(
                "LUCAS_EVA_BROWSER_USER_DATA_DIR",
                r"C:\Users\mrwan\.lucas\browser-profiles\eva",
            ),
            endpoint_env="LUCAS_EVA_ALI_BROWSER_ENDPOINT",
            profile_env="LUCAS_EVA_ALI_BROWSER_PROFILE",
            executable_env="LUCAS_EVA_ALI_BROWSER_EXECUTABLE",
        ),
        _target(
            label="Home",
            node_env="LUCAS_EVA_HOME_NODE_ID",
            node_default="N20630",
            data_dir_env="LUCAS_EVA_HOME_BROWSER_USER_DATA_DIR",
            data_dir_default=r"C:\Users\Administrator\.lucas\browser-profiles\eva",
            endpoint_env="LUCAS_EVA_HOME_BROWSER_ENDPOINT",
            profile_env="LUCAS_EVA_HOME_BROWSER_PROFILE",
            executable_env="LUCAS_EVA_HOME_BROWSER_EXECUTABLE",
        ),
    )
    return tuple(target for target in targets if target is not None)


def resolve_eva_browser_target(node_id: str, client_id: str) -> EvaBrowserTarget | None:
    if not EVA_CLIENT_ID or str(client_id or "").strip() != EVA_CLIENT_ID:
        return None
    normalized_node = str(node_id or "").strip()
    for target in configured_targets():
        if target.node_id == normalized_node:
            return target
    return None
