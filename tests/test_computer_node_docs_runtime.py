"""Run the guide's rendered localization scripts in Node with a controlled DOM.

This tests the actual composed catalog and page initialization, not copied i18n
logic. Analytics scripts are deliberately excluded. The Chromium suite owns real
browser layout/DOM acceptance; this harness does not verify the Windows updater.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from gpt_windows_connector.node_docs_ui import computer_node_docs_html


class GuideDocument(HTMLParser):
    """Parse production markup, retaining text-node and attribute boundaries."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "document", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        element = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(element)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if self.stack[-1]["tag"] != tag:
            return
        element = self.stack.pop()
        if tag == "script":
            self.scripts.append("".join(element["children"]))

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for variable in ("HOME", "LOCALAPPDATA", "GWC_DATA_DIR"):
        directory = tmp_path / variable.lower()
        directory.mkdir()
        monkeypatch.setenv(variable, str(directory))


def render_guide(navigator: dict | None = None, repeat: bool = False) -> dict:
    node = shutil.which("node")
    assert node, "Node.js is required for guide localization runtime regressions"
    parsed = GuideDocument(computer_node_docs_html())
    # Run only the actual composed i18n and guide initialization. No tracking or
    # network is needed for these static-document contracts.
    runtime = "\n".join(script for script in parsed.scripts
                        if "const WEB_LANG=" in script or "localizeWeb(" in script)
    harness = r'''
const assert=require('node:assert/strict');
const sideEffects=[];
function forbidden(name){return (...args)=>{sideEffects.push(name);throw Error('Unexpected '+name)}}
const fetch=forbidden('fetch'),XMLHttpRequest=forbidden('XMLHttpRequest');
const localStorage={getItem:forbidden('localStorage.getItem'),setItem:forbidden('localStorage.setItem')};
const sessionStorage={getItem:forbidden('sessionStorage.getItem'),setItem:forbidden('sessionStorage.setItem')};
const NodeFilter={SHOW_TEXT:4};
function descendants(root){return root.children.flatMap(n=>[n,...(n.children?descendants(n):[])])}
function matches(el,selector){
  if(el.nodeType!==1)return false;
  const tag=selector.match(/^[\w-]+/),id=selector.match(/#([\w-]+)/);
  if(tag&&el.tagName!==tag[0])return false;
  if(id&&el.getAttribute('id')!==id[1])return false;
  for(const [,name,value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)){
    if(el.getAttribute(name)===null||(value!==undefined&&el.getAttribute(name)!==value))return false;
  }
  return true;
}
class Element{
  constructor(tag,attrs,children){this.nodeType=1;this.tagName=tag;this.attrs={...attrs};this.children=children}
  getAttribute(name){return this.attrs[name]??null}
  setAttribute(name,value){this.attrs[name]=String(value)}
  querySelectorAll(selector){return descendants(this).filter(n=>selector.split(',').some(s=>matches(n,s.trim())))}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null}
  get textContent(){return this.children.map(n=>n.textContent).join('')}
  set textContent(value){this.children=[textNode(String(value))]}
  get lang(){return this.getAttribute('lang')} set lang(value){this.setAttribute('lang',value)}
  get content(){return this.getAttribute('content')} set content(value){this.setAttribute('content',value)}
}
function textNode(value){return {nodeType:3,nodeValue:value,get textContent(){return this.nodeValue}}}
function build(value){
  if(typeof value==='string')return textNode(value);
  return new Element(value.tag,value.attrs,value.children.filter(n=>typeof n==='string'||!['script','style'].includes(n.tag)).map(build));
}
const dom=build(MARKUP);
const document={
  documentElement:dom.querySelector('html'),head:dom.querySelector('head'),body:dom.querySelector('body'),
  querySelector:selector=>dom.querySelector(selector),querySelectorAll:selector=>dom.querySelectorAll(selector),
  get title(){return this.querySelector('title').textContent},
  set title(value){this.querySelector('title').textContent=value},
  createTreeWalker(root){const nodes=descendants(root).filter(n=>n.nodeType===3);let i=0;return {nextNode(){this.currentNode=nodes[i++];return !!this.currentNode}}}
};
const navigator=NAVIGATOR;
function snapshot(){
  return {lang:document.documentElement.lang,title:document.title,
    description:document.querySelector('meta[name="description"]').content,
    headings:document.body.querySelectorAll('h1,h2,h3').map(el=>el.textContent),
    text:document.body.textContent,
    textNodes:descendants(document.body).filter(n=>n.nodeType===3).map(n=>n.nodeValue),
    labels:document.querySelectorAll('[aria-label]').map(el=>el.getAttribute('aria-label')),
    sections:Object.fromEntries(document.querySelectorAll('section[id]').map(el=>[el.getAttribute('id'),el.textContent])),
    targets:document.querySelectorAll('[href],[src]').map(el=>[el.tagName,el.getAttribute('href'),el.getAttribute('src')]),
    attributes:descendants(dom).filter(n=>n.nodeType===1).map(el=>[el.tagName,{...el.attrs}]),
    controls:document.querySelectorAll('button,input,form,select,textarea').length,
    sideEffects:[...sideEffects]};
}
const before=snapshot();
'''.replace("MARKUP", json.dumps(parsed.root)).replace("NAVIGATOR", json.dumps(navigator or {}))
    finish = r'''
const after=snapshot();
if(REPEAT&&typeof localizeWeb==='function'){localizeWeb();assert.deepEqual(snapshot(),after)}
console.log(JSON.stringify({before,after,catalog:typeof WEB_ZH==='undefined'?{}:WEB_ZH}));
'''.replace("REPEAT", "true" if repeat else "false")
    result = subprocess.run([node, "-"], input=harness + "\n" + runtime + "\n" + finish,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("navigator,expected_lang", [
    ({"language": "en-US", "languages": ["zh-CN"]}, "en"),
    ({"language": "en_GB"}, "en"),
    ({"language": "fr-FR", "languages": ["zh-CN"]}, "en"),
    ({"language": "ja-JP"}, "en"),
    ({"language": ""}, "en"),
    ({}, "en"),
    ({"language": "zh-CN", "languages": ["en-US"]}, "zh-CN"),
    ({"language": "zh-TW"}, "zh-CN"),
    ({"language": "zh_HK"}, "zh-CN"),
    ({"language": "ZH-hans"}, "zh-CN"),
    ({"userLanguage": "zh-CN"}, "zh-CN"),
    ({"language": "", "languages": ["zh-Hant-TW", "en"]}, "zh-CN"),
])
def test_browser_language_variants_and_primary_language_fallback(navigator, expected_lang):
    result = render_guide(navigator, repeat=True)
    after = result["after"]
    assert after["lang"] == expected_lang
    if expected_lang == "en":
        assert after == result["before"], "English is the full unchanged markup fallback"
        assert after["title"] == "Lucas Node Setup Guide | Lucas MCP"
        assert after["headings"][0] == "Connect a computer with Lucas Node"
    else:
        assert after["title"] == "Lucas Node 设置指南 | Lucas MCP"
        assert after["headings"][0] == "使用 Lucas Node 连接电脑"
        assert after["description"].startswith("在 Windows 上安装、连接和管理 Lucas Node")
        assert after["labels"] == ["Lucas 首页", "返回电脑列表", "电脑设置步骤"]


def test_chinese_catalog_covers_every_visible_guide_text_and_accessible_label():
    result = render_guide({"language": "zh-CN"})
    before, after, catalog = result["before"], result["after"], result["catalog"]
    assert len(before["textNodes"]) == len(after["textNodes"])
    for original, translated in zip(before["textNodes"], after["textNodes"]):
        text = original.strip()
        if not re.search(r"[A-Za-z]", text) or text == "Node ID":
            assert original == translated
            continue
        assert text in catalog, f"Untranslated guide fragment: {text}"
        assert catalog[text] != text
        assert translated == original.replace(text, catalog[text])
    for label in before["labels"]:
        assert label in catalog
        assert catalog[label] in after["labels"]
    assert before["title"] in catalog
    assert before["description"] in catalog


@pytest.mark.parametrize("language,expected", [
    ("en", ["Update Lucas Node", "Settings → General → Lucas Node", "Check for updates",
            "Update Node", "Return", "Confirm the installed version", "Online", "Authorized",
            "currently install from the main branch", "verify the version and reconnection on the target Windows computer"]),
    ("zh-CN", ["更新 Lucas Node", "设置 → 常规 → Lucas Node", "检测更新", "更新 Node", "返回",
               "确认已安装的版本", "在线", "已授权", "目前从 main 分支安装", "核对版本并确认已重新连接"]),
])
def test_existing_update_controls_and_post_update_checks_are_documented(language, expected):
    after = render_guide({"language": language})["after"]
    assert "update-node" in after["sections"], "Guide must document the existing Windows updater"
    for text in expected:
        assert text in after["sections"]["update-node"]


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_connection_approval_and_local_permission_boundaries_remain_explicit(language):
    text = render_guide({"language": language})["after"]["text"]
    if language == "en":
        for expected in [
            "A newly requesting Lucas account must be approved locally on the target computer",
            "even after the Connection Code is verified", "Permission settings stay on the computer",
            "Foreground / focus confirmation:", "Sensitive actions:", "Allowed folders:",
            "AI controls only authorized tabs", "Browser disconnects invalidate grants",
            "copy the current code or regenerate it in Lucas Settings",
        ]:
            assert expected in text
    else:
        for expected in [
            "新申请访问的 Lucas 账号必须在目标电脑上获得本地批准", "即使连接码已验证通过也不例外",
            "权限设置保留在本机", "前台操作 / 焦点确认：", "敏感操作：", "允许的文件夹：",
            "AI 只能在后台控制已授权的标签页", "浏览器断开连接后，授权将失效",
            "复制当前连接码，或在 Lucas 设置中重新生成",
        ]:
            assert expected in text
    assert "expired" not in text
    assert "过期" not in text


@pytest.mark.parametrize("language", ["en", "zh-CN", "de-DE"])
def test_localization_preserves_destinations_and_does_not_change_permissions_or_storage(language):
    result = render_guide({"language": language}, repeat=True)
    before, after = result["before"], result["after"]
    assert after["targets"] == before["targets"] == [
        ["link", "https://lucasmcp.com/docs/computer-node", None],
        ["link", "/assets/lucas-logo-square.png?v=20260908", None],
        ["a", "/", None],
        ["img", None, "/assets/lucas-logo-horizontal.png?v=20260902-2"],
        ["a", "/nodes", None],
        ["a", "/download/Lucas-Node.bat", None],
        ["a", "/nodes", None],
        ["a", "/download/Lucas-Browser.zip", None],
        ["a", "/ai-connections", None],
    ]
    assert after["controls"] == 0
    assert after["sideEffects"] == []
    for (old_tag, old_attrs), (new_tag, new_attrs) in zip(before["attributes"], after["attributes"]):
        assert old_tag == new_tag
        for name in old_attrs.keys() | new_attrs.keys():
            if old_attrs.get(name) != new_attrs.get(name):
                assert name in {"lang", "aria-label", "title", "content"}
                if name == "content":
                    assert old_tag == "meta" and old_attrs.get("name") == "description"


def test_update_labels_match_existing_windows_controls_without_running_them():
    from pathlib import Path

    from gpt_windows_connector import settings_constants, update_ui

    catalog = render_guide({"language": "zh-CN"})["catalog"]
    for chinese in ("检测更新", "更新 Node"):
        english = settings_constants.SETTINGS_EN[chinese]
        assert catalog[english] == chinese
        assert f'control, "{chinese}",' in Path(update_ui.__file__).read_text(encoding="utf-8")
    assert settings_constants.SETTINGS_EN["常规"] == "General"
    assert catalog["General → Lucas Node"] == "常规 → Lucas Node"
    assert catalog["Return"] == "返回"
    assert 'self.T("返回", "Return")' in Path(update_ui.__file__).read_text(encoding="utf-8")
    assert "/main/" in settings_constants.INSTALLER_URL
    assert "/main/" in settings_constants.LATEST_VERSION_URL
