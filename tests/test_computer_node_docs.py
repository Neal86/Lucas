from gpt_windows_connector.node_docs_ui import computer_node_docs_html
from gpt_windows_connector.web_onboarding_runtime import ONBOARDING_SCRIPT


def test_computer_node_docs_contains_setup_steps_and_faq_heading():
    html = computer_node_docs_html()
    assert '/download/Lucas-Node.bat' in html
    assert 'Node ID' in html
    assert '8-digit Connection Code' in html
    assert 'Foreground / focus confirmation' in html
    assert 'Frequently Asked Questions' in html
    assert 'Connection Code does not work' in html


def test_computer_node_setup_stays_out_of_checklist():
    assert 'Computer setup guide' not in ONBOARDING_SCRIPT
    assert '/docs/computer-node' not in ONBOARDING_SCRIPT
