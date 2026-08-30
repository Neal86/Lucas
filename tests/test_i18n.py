from __future__ import annotations

from gpt_windows_connector.i18n import system_language, tr


def test_explicit_chinese_locale(monkeypatch):
    monkeypatch.setenv("LUCAS_LANGUAGE", "zh-CN")
    assert system_language() == "zh"
    assert tr("中文", "English") == "中文"


def test_explicit_english_locale(monkeypatch):
    monkeypatch.setenv("LUCAS_LANGUAGE", "en-US")
    assert system_language() == "en"
    assert tr("中文", "English") == "English"


def test_non_chinese_locale_defaults_to_english(monkeypatch):
    monkeypatch.setenv("LUCAS_LANGUAGE", "fr-FR")
    assert system_language() == "en"
