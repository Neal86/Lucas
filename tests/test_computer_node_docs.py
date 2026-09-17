from gpt_windows_connector.node_docs_ui import computer_node_docs_html
from gpt_windows_connector.web_onboarding_runtime import ONBOARDING_SCRIPT


def test_computer_node_docs_contains_setup_steps():
    html = computer_node_docs_html()
    assert '/download/Lucas-Node.bat' in html
    assert 'Node ID' in html
    assert '8-digit Connection Code' in html
    assert 'Foreground / focus confirmation' in html


def test_onboarding_does_not_walk_computer_node():
    assert 'showComputer' not in ONBOARDING_SCRIPT
    assert 'showPermissions' not in ONBOARDING_SCRIPT
    assert '/docs/computer-node' in ONBOARDING_SCRIPT
