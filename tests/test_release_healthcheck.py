from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["docker-compose.yml", "docker-compose.test.yml"])
def test_compose_healthcheck_preserves_main_contract(name):
    source = (ROOT / name).read_text()
    for line in ["healthcheck:", "curl -fsS http://127.0.0.1:8787/", "interval: 5s", "timeout: 3s", "retries: 12", "start_period: 10s"]:
        assert line in source
    assert source.count("healthcheck:") == 1


def test_final_image_contains_healthcheck_dependency_and_source_gate():
    source = (ROOT / "Dockerfile").read_text()
    final = source.split("FROM python:3.12-slim\n", 1)[1]
    assert "apt-get install -y --no-install-recommends curl" in final
    assert "COPY --from=quality /quality-ok" in final
    assert 'CMD ["gwc-gateway"]' in final


def test_staging_volume_stays_project_scoped_and_independent():
    source = (ROOT / "docker-compose.test.yml").read_text()
    assert "lucas-staging-data:/data" in source
    assert "volumes:\n  lucas-staging-data:" in source
    assert "external:" not in source
    assert "name:" not in source.split("volumes:\n  lucas-staging-data:", 1)[1]
