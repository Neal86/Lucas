import asyncio
import io
import json
from zipfile import ZipFile

from gpt_windows_connector.browser_extension_archive import EXTENSION_FILES, extension_archive
from gpt_windows_connector.web_browser_extension import download_browser_extension


def test_upload_zip_is_reproducible_and_has_manifest_at_root():
    content = extension_archive()
    assert content == extension_archive()
    with ZipFile(io.BytesIO(content)) as archive:
        assert set(archive.namelist()) == set(EXTENSION_FILES)
        assert archive.testzip() is None
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['version'] == '1.2.0'
        assert manifest['manifest_version'] == 3
        for icon in manifest['icons'].values():
            assert archive.read(icon).startswith(b'\x89PNG')
        assert not any('token' in name or 'node-config' in name for name in archive.namelist())


def test_download_returns_real_zip_with_browser_filename():
    response = asyncio.run(download_browser_extension(None))
    assert response.media_type == 'application/zip'
    assert 'Lucas-Browser-Bridge.zip' in response.headers['content-disposition']
    assert response.body == extension_archive()
