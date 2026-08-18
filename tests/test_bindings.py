from pathlib import Path

from gpt_windows_connector.bindings import BindingStore


def test_project_binding_isolated_per_user(tmp_path: Path):
    store = BindingStore(tmp_path / "gateway.db")
    a = store.set("user-a", "NiceC-WMS", "Office-PC", r"G:\NiceC-WMS", "NiceC-WMS")
    b = store.set("user-b", "NiceC-WMS", "Home-PC", r"D:\NiceC-WMS", "NiceC-WMS")
    assert store.get("user-a", "NiceC-WMS") == a
    assert store.get("user-b", "NiceC-WMS") == b
    assert store.list("user-a") == [a]
    assert store.remove("user-a", "NiceC-WMS") is True
    assert store.get("user-a", "NiceC-WMS") is None
    assert store.get("user-b", "NiceC-WMS") == b
