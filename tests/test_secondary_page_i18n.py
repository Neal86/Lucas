"""Offline translation contracts; Node executes the actual shared JavaScript.

These tests do not claim browser rendering or provider/device acceptance.
"""
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from gpt_windows_connector.seo_pages import public_info_page, _PAGE_DATA
from gpt_windows_connector.legal_ui import privacy_html, terms_html, refund_html, contact_html
from gpt_windows_connector.referral_ui import dashboard_referral_html, referral_html
from gpt_windows_connector.web_i18n_catalog import WEB_ZH_JS
from gpt_windows_connector.web_i18n_runtime import I18N_SCRIPT
from gpt_windows_connector.web_public_i18n import PUBLIC_I18N_SCRIPT
from gpt_windows_connector.web_admin_runtime import ADMIN_SCRIPT


class Texts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.texts = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'title'):
            self.skip += 1
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'title'):
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip and data.strip():
            self.texts.append(data.strip())


def node(script):
    return subprocess.check_output(['node', '-e', script], text=True).strip()


class SecondaryPageI18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(node('console.log(JSON.stringify(' + WEB_ZH_JS + '))'))

    def assert_translated(self, html):
        parser = Texts()
        parser.feed(html)
        exclusions = {'LUCAS MCP', '← Lucas', 'support@lucasmcp.com', 'fixture'}
        missing = [text for text in parser.texts if re.search('[A-Za-z]', text)
                   and text not in self.catalog and text not in exclusions]
        self.assertEqual(missing, [])

    def test_all_four_information_pages_have_complete_static_copy(self):
        for slug in _PAGE_DATA:
            with self.subTest(slug=slug):
                self.assert_translated(public_info_page(slug))
                for key in ['title', 'description', 'h1', 'lead']:
                    self.assertIn(_PAGE_DATA[slug][key], self.catalog)

    def test_legal_and_contact_existing_copy_is_translated(self):
        for render in [privacy_html, terms_html, refund_html, contact_html]:
            with self.subTest(page=render.__name__):
                self.assert_translated(render())
                self.assertIn('Last updated: September 8, 2026', render())

    def test_referral_copy_and_amounts_preserved(self):
        for html in [dashboard_referral_html(), referral_html({'code':'fixture','url':'fixture','reward_requests':12345})]:
            self.assert_translated(html)
        dashboard = dashboard_referral_html()
        self.assertIn('1,000 bonus Requests', dashboard)
        self.assertIn('10,000 bonus Requests', dashboard)
        self.assertIn('12,345', referral_html({'reward_requests':12345}))

    def test_public_pages_install_shared_runtime(self):
        for html in [public_info_page('download'), privacy_html(), terms_html(), refund_html(), contact_html(), referral_html({})]:
            self.assertIn(PUBLIC_I18N_SCRIPT, html)
            self.assertEqual(html.count('const WEB_LANG='), 1)

    def test_chinese_and_english_browser_language_selection(self):
        script = I18N_SCRIPT.removeprefix('<script>').removesuffix('</script>')
        for language, expected, label in [('zh-CN','zh-CN','隐私政策'),('zh-TW','zh-CN','隐私政策'),('en-US','en','Privacy Policy')]:
            result = node('const navigator={language:'+json.dumps(language)+'};const document={documentElement:{}};'+script+';console.log(JSON.stringify([document.documentElement.lang,wt("Privacy Policy")]))')
            self.assertEqual(json.loads(result), [expected, label])

    def test_text_runtime_changes_text_not_links(self):
        script = I18N_SCRIPT.removeprefix('<script>').removesuffix('</script>')
        harness = '''const navigator={language:'zh-CN'},NodeFilter={SHOW_TEXT:4};
        const nodes=[{nodeValue:'  Privacy Policy  '},{nodeValue:'support@lucasmcp.com'}];
        const document={documentElement:{},body:{querySelectorAll:()=>[]},createTreeWalker:()=>{let i=0;return {nextNode(){this.currentNode=nodes[i++];return !!this.currentNode}}}};
        '''
        result = node(harness+script+';localizeWeb();console.log(JSON.stringify(nodes.map(n=>n.nodeValue)))')
        self.assertEqual(json.loads(result), ['  隐私政策  ', 'support@lucasmcp.com'])

    def test_public_metadata_title_and_description(self):
        script = re.sub(r'</?script>', '', PUBLIC_I18N_SCRIPT)
        harness = '''const navigator={language:'zh-CN'},NodeFilter={SHOW_TEXT:4};
        const meta={content:'Give your AI a secure way to use your computer.'};
        const document={documentElement:{},title:'Privacy Policy · Lucas',body:{querySelectorAll:()=>[]},createTreeWalker:()=>({nextNode:()=>false}),querySelector:()=>meta};
        '''
        result = node(harness+script+';console.log(JSON.stringify([document.title,meta.content]))')
        self.assertEqual(json.loads(result), ['隐私政策 · Lucas','让你的 AI 安全地使用电脑。'])

    def test_admin_missing_labels_now_present(self):
        for label in ['Total users','Active users · 7d','Success rate','No operations.','No nodes.','healthy','Extra quota expires','User updated','Search email or name']:
            self.assertIn(label,self.catalog)
            self.assertNotEqual(label,self.catalog[label])
        self.assertIn("wt('Extra quota expires')", ADMIN_SCRIPT)

    def test_standalone_copy_success_uses_selected_language(self):
        html = referral_html({'url':'https://example.test/invite'})
        copy_script = next(script for script in re.findall(r'<script>(.*?)</script>', html, re.S)
                           if 'async function copyRef' in script)
        language_script = I18N_SCRIPT.removeprefix('<script>').removesuffix('</script>')
        for language, expected in [('zh-CN','已复制'),('en-US','Copied')]:
            harness = 'const navigator={language:'+json.dumps(language)+',clipboard:{writeText:async value=>{if(value!=="fixture")throw Error("wrong URL")}}};const event={target:{textContent:""}};const document={documentElement:{},getElementById:()=>({value:"fixture"})};'
            result = node(harness+language_script+copy_script+';copyRef().then(()=>console.log(event.target.textContent));')
            self.assertEqual(result, expected)

    def test_generated_scripts_parse(self):
        scripts = [I18N_SCRIPT, PUBLIC_I18N_SCRIPT, ADMIN_SCRIPT]
        for script in scripts:
            # ADMIN_SCRIPT includes the final document suffix; keep only JS.
            script = script.split('</script>\n</body>')[0]
            script = re.sub(r'</?script>', '', script)
            result = subprocess.run(['node','--check'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
