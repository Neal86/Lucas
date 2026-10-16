from __future__ import annotations

from .web_document import TRACKING_HEAD
from .web_i18n_runtime import I18N_SCRIPT


def computer_node_docs_html() -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="description" content="Install, connect and manage Lucas Node on Windows, including connection codes, access modes, folder permissions and foreground confirmation." />
<link rel="canonical" href="https://lucasmcp.com/docs/computer-node" />
<link rel="icon" type="image/png" href="/assets/lucas-logo-square.png?v=20260908" />
<title>Lucas Node Setup Guide | Lucas MCP</title>
{TRACKING_HEAD}
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f7f9fc;color:#172033;font:15px/1.65 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}}a{{color:#1769ff;text-decoration:none}}a:hover{{text-decoration:underline}}.top{{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);border-bottom:1px solid #e4e9f2}}.topin{{max-width:1040px;margin:auto;padding:15px 24px;display:flex;align-items:center;justify-content:space-between;gap:20px}}.brand{{display:flex;align-items:center;gap:10px;font-weight:800;color:#172033}}.brand img{{height:28px}}.back{{font-weight:700}}main{{max-width:1040px;margin:auto;padding:58px 24px 90px}}.hero{{max-width:760px;margin-bottom:38px}}.eyebrow{{font-size:12px;font-weight:800;letter-spacing:.14em;color:#1769ff}}h1{{font-size:44px;line-height:1.1;margin:10px 0 14px}}h2{{font-size:25px;margin:0 0 12px}}h3{{font-size:18px;margin:0 0 8px}}p{{margin:0 0 14px;color:#556177}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.card{{background:#fff;border:1px solid #e0e6ef;border-radius:16px;padding:24px;box-shadow:0 8px 28px rgba(31,45,70,.05)}}.step{{display:flex;gap:16px}}.num{{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:grid;place-items:center;background:#1769ff;color:#fff;font-weight:800}}.actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.btn{{display:inline-flex;align-items:center;justify-content:center;border-radius:10px;padding:11px 15px;font-weight:800}}.primary{{background:#1769ff;color:#fff}}.secondary{{background:#eef3fb;color:#24334e}}code{{background:#eef2f7;padding:2px 6px;border-radius:6px}}.note{{border-left:4px solid #1769ff;background:#eef5ff;padding:14px 16px;border-radius:8px;margin-top:14px}}.section{{margin-top:34px}}ul,ol{{margin:8px 0 0;padding-left:22px;color:#556177}}li{{margin:6px 0}}@media(max-width:720px){{h1{{font-size:34px}}.grid{{grid-template-columns:1fr}}main{{padding-top:36px}}}}
</style>
</head>
<body>
<header class="top"><div class="topin"><a class="brand" href="/" aria-label="Lucas home"><img src="/assets/lucas-logo-horizontal.png?v=20260902-2" alt="Lucas"></a><a class="back" href="/nodes" aria-label="Back to Computers">← Computers</a></div></header>
<main aria-labelledby="node-guide-title">
<section class="hero"><div class="eyebrow">LUCAS DOCUMENTATION</div><h1 id="node-guide-title">Connect a computer with Lucas Node</h1><p>Install Lucas Node on the Windows computer you want AI to use, connect it to your Lucas account, then choose the local permissions that fit your workflow.</p><div class="actions"><a class="btn primary" href="/download/Lucas-Node.bat">Download Lucas Node</a><a class="btn secondary" href="/nodes">Open Computers</a></div></section>
<section class="section card" id="browser-extension"><h2>Lucas Browser extension</h2><p><a href="/download/Lucas-Browser.zip">Download Lucas Browser</a>, extract the ZIP, then use Load unpacked in Chrome or Edge Developer mode. Open Browser in Lucas Settings to copy the local pairing token. In the extension popup pair with your Node, choose an approved Lucas account and authorize the current tab.</p><p>AI controls only authorized tabs in the background. Revoke access at any time. Browser disconnects invalidate grants. No dedicated Profile is required.</p></section>
<section class="grid" id="setup-steps" aria-label="Computer setup steps">
<div class="card step"><div class="num">1</div><div><h3>Install Lucas Node</h3><p>Download Lucas Node on the Windows computer you want to connect. Run the installer/launcher and keep Lucas running in the system tray.</p></div></div>
<div class="card step"><div class="num">2</div><div><h3>Find Node ID and Connection Code</h3><p>Open Lucas Settings from the Windows tray. Copy the <strong>Node ID</strong> and the current <strong>8-digit Connection Code</strong>.</p></div></div>
<div class="card step"><div class="num">3</div><div><h3>Connect from the website</h3><p>Go to <strong>Dashboard → Computers → Connect computer</strong>, enter the Node ID and 8-digit code, then send the access request.</p></div></div>
<div class="card step"><div class="num">4</div><div><h3>Approve locally</h3><p>A newly requesting Lucas account must be approved locally on the target computer, even after the Connection Code is verified. After approval, the computer appears as Authorized in your dashboard.</p></div></div>
</section>
<section class="section card" id="local-permissions"><h2>Permission settings stay on the computer</h2><p>Lucas keeps computer-control permissions local. The website shows the reported state, but changes are made from Lucas Settings on the Windows computer.</p><ul><li><strong>Background actions:</strong> file, shell and other work that does not need to interrupt your current screen.</li><li><strong>Foreground / focus confirmation:</strong> controls whether actions that must activate a window, browser or desktop UI require confirmation first.</li><li><strong>Sensitive actions:</strong> higher-risk actions can still require explicit approval even when normal access is enabled.</li><li><strong>Allowed folders:</strong> limit file access to the folders or workspaces you choose.</li></ul><div class="note"><strong>Tip:</strong> use background-capable browser, shell and file tools whenever possible. Foreground control should be reserved for actions that truly need the visible desktop.</div></section>
<section class="section card" id="update-node"><h2>Update Lucas Node</h2><p>Open the Lucas tray icon → Settings → General → Lucas Node on the Windows computer.</p><ol><li>Choose <strong>Check for updates</strong>. If a newer version is available, choose <strong>Update Node</strong>. Keep Lucas open while the updater runs.</li><li>Wait for the update to finish. Settings may refresh automatically; otherwise choose <strong>Return</strong>. Confirm the installed version under <strong>General → Lucas Node</strong>.</li><li>Refresh <strong>Dashboard → Computers</strong> and check that the computer is <strong>Online</strong> and <strong>Authorized</strong>. If it stays offline, check the tray app and internet connection, then restart Lucas Node if needed.</li><li>Review the local permission mode, approved accounts and allowed folders before continuing. A newly requesting account still requires local approval.</li></ol><p class="note">The download and updater currently install from the main branch. Changes in a guide or source checkout do not confirm those changes are installed; verify the version and reconnection on the target Windows computer.</p></section>
<section class="section" id="node-faq"><div class="eyebrow">FAQ</div><h2>Frequently Asked Questions</h2><p>Common questions about connecting and managing your Lucas Computer.</p></section>\n<section class="grid"><div class="card"><h2>Connection Code does not work</h2><p>Confirm the Node ID is exact, the code is the current 8-digit code shown by Lucas Settings, and the Node is online. If it does not match, copy the current code or regenerate it in Lucas Settings.</p></div><div class="card"><h2>Computer shows offline</h2><p>Check that Lucas Node is running in the tray and has internet access. Restart Lucas Node if needed; the Node should reconnect automatically.</p></div><div class="card"><h2>Why can’t I read Node logs?</h2><p>Node logs can contain local operational details. Lucas only exposes them when the local permission mode allows that level of access.</p></div><div class="card"><h2>Changing access mode</h2><p>Open the Lucas tray icon → Settings on the target computer. Change the permission preset or individual confirmation controls there, then refresh the Computers page.</p></div></section>
<section class="section card"><h2>After setup</h2><p>Once your computer is Authorized, connect an AI from <a href="/ai-connections">AI Connections</a>. The AI can then use Lucas MCP according to the permissions set on your computer.</p></section>
</main>
{I18N_SCRIPT}
<script>
localizeWeb();
document.title=wt(document.title);
const nodeGuideDescription=document.querySelector('meta[name="description"]');
if(nodeGuideDescription)nodeGuideDescription.content=wt(nodeGuideDescription.content);
</script>
</body></html>'''
