"""Build the unpacked extension distribution without credentials or local settings."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'src/gpt_windows_connector/browser_bridge_extension'


def build(output: Path) -> None:
    manifest = json.loads((EXT/'manifest.json').read_text())
    expected = [manifest['background']['service_worker'],manifest['options_page'],manifest['side_panel']['default_path'],manifest['action']['default_popup'],*manifest['content_scripts'][0]['js'],*manifest['icons'].values()]
    for name in expected:
        if not (EXT/name).is_file(): raise FileNotFoundError(name)
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path in sorted(EXT.iterdir()):
            if path.is_file():archive.write(path,'Lucas-Browser/'+path.name)
        archive.write(ROOT/'docs/LUCAS_BROWSER_EXTENSION.md','README.md')
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('Lucas-Browser/manifest.json'))['version'] == manifest['version']
    print(output.resolve())


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
