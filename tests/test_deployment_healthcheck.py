from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compose(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_production_compose_has_container_healthcheck():
    text = _compose("docker-compose.yml")
    assert "healthcheck:" in text
    assert "curl -fsS http://127.0.0.1:8787/" in text
    assert "interval: 5s" in text
    assert "timeout: 3s" in text
    assert "retries: 12" in text
    assert "start_period: 10s" in text


def test_staging_compose_has_same_container_healthcheck():
    text = _compose("docker-compose.test.yml")
    assert "healthcheck:" in text
    assert "curl -fsS http://127.0.0.1:8787/" in text
    assert "interval: 5s" in text
    assert "timeout: 3s" in text
    assert "retries: 12" in text
    assert "start_period: 10s" in text
