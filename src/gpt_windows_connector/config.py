from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def _split_paths(raw: str) -> tuple[Path, ...]:
    return tuple(Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip())


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _transport_allowlists(public_base_url: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    parsed = urlsplit(public_base_url)
    hostname = parsed.hostname
    if not hostname:
        raise RuntimeError(f"GWC_PUBLIC_BASE_URL must be an absolute URL: {public_base_url}")
    host = parsed.netloc
    origin = f"{parsed.scheme}://{parsed.netloc}"
    hosts = {host, hostname, f"{hostname}:*", "127.0.0.1:*", "localhost:*", "[::1]:*"}
    origins = {origin, f"{parsed.scheme}://{hostname}:*", "http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"}
    return tuple(sorted(hosts)), tuple(sorted(origins))


def _persistent_secret(data_dir: Path, env_name: str, filename: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    path = data_dir / filename
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


@dataclass(frozen=True)
class GatewaySettings:
    host: str
    port: int
    public_base_url: str
    admin_token: str
    data_dir: Path
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    jwt_secret: str
    jwt_ttl_seconds: int
    google_client_id: str | None
    google_client_secret: str | None
    google_redirect_uri: str | None
    auth_success_url: str | None

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        data_dir = Path(os.environ.get("GWC_DATA_DIR", "./data")).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        public_base_url = os.environ.get("GWC_PUBLIC_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
        default_hosts, default_origins = _transport_allowlists(public_base_url)
        allowed_hosts = _split_csv(os.environ.get("GWC_ALLOWED_HOSTS", "")) or default_hosts
        allowed_origins = _split_csv(os.environ.get("GWC_ALLOWED_ORIGINS", "")) or default_origins
        google_client_id = os.environ.get("GWC_GOOGLE_CLIENT_ID", "").strip() or None
        google_client_secret = os.environ.get("GWC_GOOGLE_CLIENT_SECRET", "").strip() or None
        google_redirect_uri = os.environ.get("GWC_GOOGLE_REDIRECT_URI", "").strip() or None
        if google_client_id and google_client_secret and not google_redirect_uri:
            google_redirect_uri = f"{public_base_url}/auth/google/callback"
        return cls(
            host=os.environ.get("GWC_HOST", "0.0.0.0"),
            port=int(os.environ.get("GWC_PORT", "8787")),
            public_base_url=public_base_url,
            admin_token=os.environ.get("GWC_ADMIN_TOKEN", "").strip(),
            data_dir=data_dir,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
            jwt_secret=_persistent_secret(data_dir, "GWC_JWT_SECRET", "jwt-secret.txt"),
            jwt_ttl_seconds=int(os.environ.get("GWC_JWT_TTL_SECONDS", str(60 * 60 * 24 * 30))),
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_redirect_uri=google_redirect_uri,
            auth_success_url=os.environ.get("GWC_AUTH_SUCCESS_URL", "").strip() or public_base_url,
        )


@dataclass(frozen=True)
class NodeSettings:
    node_id: str
    node_name: str
    gateway_ws_url: str
    node_token: str | None
    state_file: Path
    allowed_roots: tuple[Path, ...]
    permission_level: str

    @classmethod
    def from_env(cls) -> "NodeSettings":
        node_id = os.environ.get("GWC_NODE_ID", os.environ.get("COMPUTERNAME", "windows-node")).strip()
        node_name = os.environ.get("GWC_NODE_NAME", node_id).strip()
        roots = _split_paths(os.environ.get("GWC_ALLOWED_ROOTS", ""))
        if not roots:
            roots = (Path.home().resolve(),)
        state_file = Path(
            os.environ.get(
                "GWC_NODE_STATE",
                str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "gpt-windows-connector" / "node.json"),
            )
        ).expanduser().resolve()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        permission_level = os.environ.get("GWC_PERMISSION_LEVEL", "operate").strip().lower()
        if permission_level not in {"read", "operate", "admin"}:
            raise RuntimeError("GWC_PERMISSION_LEVEL must be read, operate, or admin")
        return cls(
            node_id=node_id,
            node_name=node_name,
            gateway_ws_url=os.environ.get("GWC_GATEWAY_WS", "ws://127.0.0.1:8787/ws/node").strip(),
            node_token=os.environ.get("GWC_NODE_TOKEN") or None,
            state_file=state_file,
            allowed_roots=roots,
            permission_level=permission_level,
        )


def validate_workspace(allowed_roots: tuple[Path, ...], workspace: str | Path) -> Path:
    candidate = Path(workspace).expanduser().resolve()
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"Workspace does not exist or is not a directory: {candidate}")
    for root in allowed_roots:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    raise PermissionError(f"Workspace is outside allowed roots: {candidate}")


def resolve_in_workspace(workspace: Path, relative: str | Path = ".") -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise PermissionError(f"Path escapes workspace: {relative}") from exc
    return candidate
