"""Protect the test Compose data boundary without requiring Docker or live data."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compose(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def data_sources(source: str) -> list[str]:
    # The repository uses short-form service mounts. Match only mount entries,
    # not environment variables or labels that happen to mention /data.
    return re.findall(r'^      - [\'"]?([^\'"\n]+):/data[\'"]?\s*$', source, re.MULTILINE)


def test_staging_data_mount_is_project_scoped_named_volume():
    source = compose("docker-compose.test.yml")
    assert data_sources(source) == ["lucas-staging-data"]
    blocks = re.findall(r"^    volumes:\n((?:^[ \t]+.*\n|^\n)*)", source, re.MULTILINE)
    assert len(blocks) == 1
    assert blocks[0].strip() == "- lucas-staging-data:/data"


def test_staging_does_not_bind_a_host_path_or_production_volume():
    staging = data_sources(compose("docker-compose.test.yml"))
    production = data_sources(compose("docker-compose.yml"))
    assert staging and production
    assert set(staging).isdisjoint(production)
    assert all(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) for name in staging)
    assert not any("gwc-data" in name or "gwc_data" in name for name in staging)


def test_staging_volume_is_declared_without_external_or_global_name():
    source = compose("docker-compose.test.yml")
    # Empty volume configuration lets Compose scope the name to this project.
    # A fixed `name:` or `external:` entry could reattach another app's data.
    assert re.search(r"^volumes:\n  lucas-staging-data:\s*(?:\{\})?\s*\Z", source, re.MULTILINE)


def test_staging_retains_test_only_service_configuration():
    source = compose("docker-compose.test.yml")
    assert "GWC_PUBLIC_BASE_URL: ${LUCAS_TEST_BASE_URL:" in source
    assert "GWC_AUTH_SUCCESS_URL: ${LUCAS_TEST_BASE_URL:" in source
    assert 'GWC_BYPASS_LOGIN_VERIFICATION: "true"' in source
    for key in ("GWC_SMTP_HOST", "GWC_SMTP_USERNAME", "GWC_SMTP_PASSWORD",
                "GWC_GOOGLE_CLIENT_ID", "GWC_GOOGLE_CLIENT_SECRET",
                "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        assert f'{key}: ""' in source
