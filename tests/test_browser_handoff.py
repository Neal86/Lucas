from gpt_windows_connector.browser_handoff import classify_user_action


def test_detects_captcha_as_human_handoff():
    result = classify_user_action(text="Please verify you are human before continuing")
    assert result is not None
    assert result["action_type"] == "captcha"


def test_detects_two_factor_as_human_handoff():
    result = classify_user_action(text="Enter the verification code from your authenticator")
    assert result is not None
    assert result["action_type"] == "2fa"


def test_detects_identity_verification():
    result = classify_user_action(text="Upload your government-issued ID to verify your identity")
    assert result is not None
    assert result["action_type"] == "identity_verification"


def test_password_field_only_counts_as_login_on_login_page():
    assert classify_user_action(text="Account settings", url="https://example.com/settings", has_password=True) is None
    result = classify_user_action(text="Sign in", url="https://example.com/login", has_password=True)
    assert result is not None
    assert result["action_type"] == "login"
