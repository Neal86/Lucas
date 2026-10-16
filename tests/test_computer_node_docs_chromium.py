"""Opt-in browser acceptance for the real public Windows Node setup guide.

Uses the existing loopback HTTP/SQLite fixture and isolated raw-CDP Chromium
profile. Only reads the guide and packaged images; never follows downloads,
installs or updates a Node, submits credentials, or contacts a real device.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from test_oauth_login_chromium import chromium, login_server, visible, wait_for


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOGIN_E2E") != "1" or not os.getenv("CHROME_BIN"),
    reason="RUN_LOGIN_E2E=1 and CHROME_BIN required",
)

DESTINATIONS = [
    "/", "/nodes", "/download/Lucas-Node.bat", "/nodes",
    "/download/Lucas-Browser.zip", "/ai-connections",
]


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_public_node_guide_language_accessibility_and_responsive_layout(
    login_server, tmp_path, language,
):
    """Both languages keep local approval, update guidance and safe destinations."""
    server = login_server
    before_counts = server.counts()
    first_request = len(server.requests)
    zh = language == "zh-CN"
    expected = {
        "title": "Lucas Node 设置指南 | Lucas MCP" if zh else "Lucas Node Setup Guide | Lucas MCP",
        "heading": "使用 Lucas Node 连接电脑" if zh else "Connect a computer with Lucas Node",
        "home": "Lucas 首页" if zh else "Lucas home",
        "back": "返回电脑列表" if zh else "Back to Computers",
        "setup_label": "电脑设置步骤" if zh else "Computer setup steps",
        "steps": ["安装 Lucas Node", "查找 Node ID 和连接码", "从网站连接", "在本机批准"] if zh else [
            "Install Lucas Node", "Find Node ID and Connection Code", "Connect from the website", "Approve locally",
        ],
        "code": "8 位连接码" if zh else "8-digit Connection Code",
        "connect": "控制台 → 电脑 → 连接电脑" if zh else "Dashboard → Computers → Connect computer",
        "approval": "新申请访问的 Lucas 账号必须在目标电脑上获得本地批准，即使连接码已验证通过也不例外。" if zh else
                    "A newly requesting Lucas account must be approved locally on the target computer, even after the Connection Code is verified.",
        "permissions": "权限设置保留在本机" if zh else "Permission settings stay on the computer",
        "permission_labels": ["后台操作：", "前台操作 / 焦点确认：", "敏感操作：", "允许的文件夹："] if zh else [
            "Background actions:", "Foreground / focus confirmation:", "Sensitive actions:", "Allowed folders:",
        ],
        "permission_rule": "权限更改则需要在 Windows 电脑的 Lucas 设置中进行。" if zh else
                           "changes are made from Lucas Settings on the Windows computer.",
        "extension_rule": "浏览器断开连接后，授权将失效。" if zh else "Browser disconnects invalidate grants.",
        "update": "更新 Lucas Node" if zh else "Update Lucas Node",
        "settings": "设置 → 常规 → Lucas Node" if zh else "Settings → General → Lucas Node",
        "update_labels": ["检测更新", "更新 Node", "返回", "常规 → Lucas Node", "控制台 → 电脑", "在线", "已授权"] if zh else [
            "Check for updates", "Update Node", "Return", "General → Lucas Node", "Dashboard → Computers", "Online", "Authorized",
        ],
        "update_permissions": "继续使用前，请检查本地权限模式、已批准的账号和允许的文件夹。新申请访问的账号仍需在本机获得批准。" if zh else
                              "Review the local permission mode, approved accounts and allowed folders before continuing. A newly requesting account still requires local approval.",
        "install_source": "下载和更新程序目前从 main 分支安装。" if zh else
                          "The download and updater currently install from the main branch.",
        "install_warning": "指南或源代码的变更不代表这些变更已经安装" if zh else
                           "Changes in a guide or source checkout do not confirm those changes are installed",
        "faq": "常见问题解答" if zh else "Frequently Asked Questions",
        "links": ["下载 Lucas Node", "打开电脑列表", "下载 Lucas Browser", "AI 连接"] if zh else [
            "Download Lucas Node", "Open Computers", "Download Lucas Browser", "AI Connections",
        ],
    }

    async def text_content(cdp, session, selector):
        return await cdp.evaluate(
            f"document.querySelector({json.dumps(selector)}).textContent.trim()", session,
        )

    async def texts(cdp, session, selector):
        return await cdp.evaluate(
            f"[...document.querySelectorAll({json.dumps(selector)})].map(e=>e.textContent.trim())", session,
        )

    async def run():
        async with chromium(tmp_path) as (cdp, session):
            await cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source":
                "Object.defineProperty(navigator,'language',{value:" + json.dumps(language) + "});"}, session)
            await cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": 1365, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            }, session)
            await cdp.call("Page.navigate", {"url": server.base + "/docs/computer-node"}, session)
            await wait_for(cdp, session, visible("#node-guide-title"))
            await wait_for(cdp, session, "document.readyState === 'complete'")
            # A missing-image fallback would hide real header-width regressions.
            await wait_for(cdp, session,
                           "document.querySelector('.brand img')?.complete && document.querySelector('.brand img').naturalWidth > 0")

            assert await cdp.evaluate("document.title", session) == expected["title"]
            assert await cdp.evaluate("document.documentElement.lang", session) == language
            assert await text_content(cdp, session, "#node-guide-title") == expected["heading"]
            assert await texts(cdp, session, "#setup-steps h3") == expected["steps"]
            setup = await text_content(cdp, session, "#setup-steps")
            for required in ("Node ID", expected["code"], expected["connect"], expected["approval"]):
                assert required in setup
            assert await text_content(cdp, session, "#local-permissions h2") == expected["permissions"]
            assert await texts(cdp, session, "#local-permissions li strong") == expected["permission_labels"]
            assert expected["permission_rule"] in await text_content(cdp, session, "#local-permissions")
            assert expected["extension_rule"] in await text_content(cdp, session, "#browser-extension")
            assert await text_content(cdp, session, "#update-node h2") == expected["update"]
            assert expected["settings"] in await text_content(cdp, session, "#update-node > p")
            assert await texts(cdp, session, "#update-node li strong") == expected["update_labels"]
            assert expected["update_permissions"] == await text_content(cdp, session, "#update-node li:last-child")
            install_note = await text_content(cdp, session, "#update-node .note")
            assert expected["install_source"] in install_note and expected["install_warning"] in install_note
            assert await text_content(cdp, session, "#node-faq h2") == expected["faq"]

            # Assert actual accessibility-tree names, including translated ARIA
            # labels and the main landmark's heading reference.
            await cdp.call("Accessibility.enable", session=session)
            tree = (await cdp.call("Accessibility.getFullAXTree", session=session))["nodes"]
            names = [(node.get("role", {}).get("value"), node.get("name", {}).get("value"))
                     for node in tree if not node.get("ignored")]
            assert ("main", expected["heading"]) in names
            assert ("region", expected["setup_label"]) in names
            link_names = [name for role, name in names if role == "link"]
            assert sorted(link_names) == sorted([expected["home"], expected["back"], *expected["links"]])
            assert await cdp.evaluate("[...document.querySelectorAll('img')].every(img=>img.alt.trim())", session)
            assert await cdp.evaluate("[...document.querySelectorAll('a')].map(a=>a.getAttribute('href'))", session) == DESTINATIONS
            assert await cdp.evaluate("document.querySelector('link[rel=canonical]').href", session) == "https://lucasmcp.com/docs/computer-node"

            for width, height, mobile in ((1365, 900, False), (375, 812, True)):
                await cdp.call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile,
                }, session)
                await cdp.evaluate("window.scrollTo(0,0); new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))", session)
                layout = await cdp.evaluate("""(() => {
                    const root=document.documentElement, header=document.querySelector('.top');
                    const cards=[...document.querySelectorAll('#setup-steps .step')].map(e=>{
                        const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};
                    });
                    return {windowWidth:window.innerWidth,viewport:root.clientWidth,
                        width:Math.max(root.scrollWidth,document.body.scrollWidth),
                        headerPosition:getComputedStyle(header).position,headerTop:header.getBoundingClientRect().top,cards};
                })()""", session)
                assert layout["windowWidth"] == width and 0 < layout["viewport"] <= width, layout
                assert layout["width"] <= layout["viewport"] + 1, layout
                assert layout["headerPosition"] == "sticky" and abs(layout["headerTop"]) <= 1, layout
                first, second = layout["cards"][:2]
                if mobile:
                    assert second["top"] >= first["bottom"], layout
                else:
                    assert second["left"] >= first["right"] and abs(second["top"] - first["top"]) <= 1, layout
                await cdp.evaluate("window.scrollTo(0,900); true", session)
                await wait_for(cdp, session, "window.scrollY > 100 && Math.abs(document.querySelector('.top').getBoundingClientRect().top) <= 1")
                assert await cdp.evaluate("""(() => {
                    const r=document.querySelector('.top').getBoundingClientRect();
                    return r.bottom>0 && r.left>=-1 && r.right<=document.documentElement.clientWidth+1;
                })()""", session)

    asyncio.run(run())
    assert server.counts() == before_counts
    assert not server.deliveries and not server.responses
    requests = server.requests[first_request:]
    assert requests and any(request["path"] == "/docs/computer-node" for request in requests)
    assert all(request["method"] == "GET" and (
        request["path"] == "/docs/computer-node" or request["path"].startswith("/assets/")
    ) for request in requests), requests
