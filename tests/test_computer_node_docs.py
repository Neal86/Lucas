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


def test_computer_node_docs_composes_shared_localization_and_preserves_layout():
    from gpt_windows_connector.web_i18n_runtime import I18N_SCRIPT

    html = computer_node_docs_html()
    assert html.count(I18N_SCRIPT) == 1
    assert '<html lang="en">' in html
    assert 'localizeWeb();' in html
    assert 'document.title=wt(document.title)' in html
    assert 'nodeGuideDescription.content=wt(nodeGuideDescription.content)' in html
    assert 'position:sticky;top:0;' in html
    assert '@media(max-width:720px)' in html
    assert '.grid{grid-template-columns:1fr}' in html
    assert 'aria-labelledby="node-guide-title"' in html
    assert 'aria-label="Computer setup steps"' in html


def test_computer_node_docs_describes_real_update_controls_and_required_local_approval():
    html = computer_node_docs_html()
    for text in ('Settings → General → Lucas Node', 'Check for updates', 'Update Node',
                 'Confirm the installed version', 'Dashboard → Computers',
                 'A newly requesting Lucas account must be approved locally',
                 'Review the local permission mode, approved accounts and allowed folders'):
        assert text in html
    assert 'may ask you to approve' not in html
    assert 'old one expired' not in html
