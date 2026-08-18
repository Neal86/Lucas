from gpt_windows_connector.config import _transport_allowlists


def test_transport_allowlists_include_public_host_and_localhost():
    hosts, origins = _transport_allowlists("https://gwc.example.com")
    assert "gwc.example.com" in hosts
    assert "gwc.example.com:*" in hosts
    assert "localhost:*" in hosts
    assert "https://gwc.example.com" in origins
    assert "https://gwc.example.com:*" in origins
    assert "http://localhost:*" in origins


def test_transport_allowlists_keep_explicit_port():
    hosts, origins = _transport_allowlists("https://gwc.example.com:9443")
    assert "gwc.example.com:9443" in hosts
    assert "https://gwc.example.com:9443" in origins
