from pathlib import Path

installer_path = Path("scripts/install-node.ps1")
installer = installer_path.read_text(encoding="utf-8")
old = '& $VenvPython -m pip install --disable-pip-version-check --force-reinstall --no-deps --no-cache-dir $PackageUrl'
new = '& $VenvPython -m pip install --disable-pip-version-check --upgrade --no-cache-dir $PackageUrl'
if old not in installer:
    raise SystemExit("in-app install command not found")
installer = installer.replace(old, new, 1)
installer_path.write_text(installer, encoding="utf-8")

test_path = Path("tests/test_update_ui_contract.py")
test = test_path.read_text(encoding="utf-8")
test = test.replace('assert "--force-reinstall --no-deps --no-cache-dir" in text', 'assert "--upgrade --no-cache-dir $PackageUrl" in text\n    assert "--force-reinstall --no-deps" not in text')
test_path.write_text(test, encoding="utf-8")
