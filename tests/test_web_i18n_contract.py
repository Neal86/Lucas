from __future__ import annotations

from pathlib import Path

from gpt_windows_connector import web_i18n_catalog, web_i18n_runtime
from gpt_windows_connector.web_i18n_catalog import WEB_ZH_JS
from gpt_windows_connector.web_i18n_runtime import I18N_SCRIPT


def test_browser_ui_language_is_primary_signal():
    assert "navigator.language||navigator.userLanguage" in I18N_SCRIPT
    assert "primary.startsWith('zh')" in I18N_SCRIPT
    assert "?'zh':'en'" in I18N_SCRIPT


def test_core_landing_translations_are_present():
    required = {
        "'Connect your AI':'连接你的 AI'",
        "'Start for free':'免费开始'",
        "'Sign in':'登录'",
        "'How it works':'工作原理'",
        "'Install Lucas and securely connect the computer you want your AI to use.':'安装 Lucas，并安全连接你希望 AI 使用的电脑。'",
    }
    for item in required:
        assert item in WEB_ZH_JS


def test_translation_catalog_is_single_source():
    runtime_source = Path(web_i18n_runtime.__file__).read_text(encoding="utf-8")
    catalog_source = Path(web_i18n_catalog.__file__).read_text(encoding="utf-8")
    assert "const WEB_ZH={" not in runtime_source
    assert "WEB_ZH_JS" in runtime_source
    assert "'Connect your AI':'连接你的 AI'" in catalog_source
