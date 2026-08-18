from pathlib import Path

from gpt_windows_connector.bindings import BindingStore


def test_project_binding_roundtrip(tmp_path: Path):
    store = BindingStore(tmp_path / "projects.json")
    binding = store.set("NiceC-WMS", "Office-PC", r"G:\NiceC-WMS", "NiceC-WMS")
    assert binding.project_id == "NiceC-WMS"
    assert binding.node_id == "Office-PC"
    assert store.get("NiceC-WMS") == binding
    assert store.list() == [binding]
    assert store.remove("NiceC-WMS") is True
    assert store.get("NiceC-WMS") is None
