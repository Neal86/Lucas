from gpt_windows_connector.web_auth_markup import AUTH_HTML
from gpt_windows_connector.web_login_runtime import LOGIN_SCRIPT


def test_login_verification_controls_are_present():
    for control in ("loginVerifyForm", "loginVerifyEmailLabel", "loginVerifyCode", "loginResendBtn", "loginRemember"):
        assert f'id="{control}"' in AUTH_HTML
        assert control in LOGIN_SCRIPT


def test_signin_challenge_actions_are_available():
    for handler in ("verifyLogin()", "resendLoginVerification()", "cancelLoginVerification()"):
        assert handler in AUTH_HTML
