from gpt_windows_connector.browser_semantic import score_page


def test_url_match_beats_unrelated_tab():
    coolify = score_page("Coolify - Lucas Staging", "https://coolify.example/project/lucas", query="Lucas Coolify")
    unrelated = score_page("Gmail", "https://mail.google.com/", query="Lucas Coolify")
    assert coolify > unrelated


def test_explicit_url_hint_has_high_priority():
    assert score_page("Any title", "https://example.com/settings", url_contains="example.com/settings") >= 80
