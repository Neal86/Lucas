from __future__ import annotations

import json


_PAGE_DATA = {
    "features": {
        "title": "Lucas MCP Features — AI Computer Automation",
        "description": "Explore Lucas MCP features for connecting AI assistants to files, terminals, browsers, desktop apps and remote computers with local permission controls.",
        "h1": "Give your AI a secure way to use your computer.",
        "lead": "Lucas MCP connects MCP-compatible AI assistants to real computer tools so they can work with projects, files, browsers, terminals and desktop applications.",
        "items": [
            ("Files & projects", "Let AI read and work inside folders you explicitly allow, while keeping project boundaries visible and controllable."),
            ("Terminal & code", "Run development and automation workflows on the connected computer instead of moving every step into a cloud execution environment."),
            ("Browser & computer use", "Allow AI to interact with supported browser and desktop workflows when a task needs more than text generation."),
            ("Remote computers", "Connect multiple computers to one Lucas account according to your plan and choose which computer an AI workflow can use."),
        ],
    },
    "how-it-works": {
        "title": "How Lucas MCP Works — Connect AI to Your Computer",
        "description": "Learn how Lucas MCP connects ChatGPT, Claude, Gemini and other MCP-compatible AI assistants to your computer in three steps.",
        "h1": "From AI request to computer action in three steps.",
        "lead": "Lucas acts as the bridge between your AI assistant and a computer you control. The AI talks to Lucas through MCP; Lucas routes approved tool calls to the selected computer.",
        "items": [
            ("1. Connect a computer", "Install Lucas Node on the computer you want to use and approve the connection locally."),
            ("2. Add Lucas MCP to your AI", "Connect a compatible AI platform to Lucas so it can discover the tools exposed for your account."),
            ("3. Start working", "Ask the AI to work with files, code, browsers or desktop apps. Lucas sends the requested tool operations to the connected computer."),
        ],
    },
    "security": {
        "title": "Lucas MCP Security — Local Permission Controls",
        "description": "See how Lucas MCP uses local approvals, allowed folders, account isolation and activity visibility to keep AI computer access under your control.",
        "h1": "Your computer stays behind your permission boundary.",
        "lead": "Lucas is designed so computer access is explicitly granted and managed instead of treating a connected machine as an unrestricted remote shell.",
        "items": [
            ("Local approval", "New computer access can require approval on the computer itself before an account is authorized."),
            ("Allowed folders", "File access can be restricted to folders you choose rather than exposing the entire filesystem by default."),
            ("Account isolation", "Connected users and AI clients are scoped to their own authorization and account context."),
            ("Activity visibility", "Lucas keeps operational activity visible so you can review what connected AI workflows are doing."),
        ],
    },
    "download": {
        "title": "Download Lucas Node — Connect Your Computer to AI",
        "description": "Download Lucas Node for Windows and connect your computer to ChatGPT, Claude, Gemini and other MCP-compatible AI assistants through Lucas MCP.",
        "h1": "Connect your computer with Lucas Node.",
        "lead": "Lucas Node runs on your computer and receives approved Lucas tool operations. Install it, connect it to your Lucas account, then manage access from the local app and dashboard.",
        "items": [
            ("Windows installer", "Use the Lucas Node launcher to install or update the Windows node."),
            ("Local controls", "Manage connection status, allowed folders and computer permissions directly from Lucas Node."),
            ("Automatic reconnect", "Lucas Node can reconnect after network interruptions so approved workflows can resume without repeating setup."),
        ],
    },
}


def public_info_page(slug: str) -> str:
    data = _PAGE_DATA[slug]
    canonical = f"https://lucasmcp.com/{slug}"
    cards = "".join(f"<article><h2>{title}</h2><p>{body}</p></article>" for title, body in data["items"])
    download_cta = "<a class='primary' href='/download/Lucas-Node.bat'>Download Lucas Node</a>" if slug == "download" else "<a class='primary' href='/dashboard'>Get started</a>"
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": data["title"],
        "url": canonical,
        "description": data["description"],
        "isPartOf": {"@type": "WebSite", "name": "Lucas MCP", "alternateName": "lucasmcp", "url": "https://lucasmcp.com/"},
    }, separators=(",", ":"))
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"robots\" content=\"index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1\"><meta name=\"description\" content=\"{data['description']}\"><link rel=\"canonical\" href=\"{canonical}\"><link rel=\"icon\" type=\"image/png\" href=\"/assets/lucas-logo-square.png?v=20260908\"><meta property=\"og:site_name\" content=\"Lucas MCP\"><meta property=\"og:type\" content=\"website\"><meta property=\"og:title\" content=\"{data['title']}\"><meta property=\"og:description\" content=\"{data['description']}\"><meta property=\"og:url\" content=\"{canonical}\"><script type=\"application/ld+json\">{schema}</script><title>{data['title']}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#05070d;color:#f5f7ff;font:15px/1.7 Inter,system-ui,-apple-system,Segoe UI,sans-serif}}a{{color:inherit;text-decoration:none}}.wrap{{max-width:1080px;margin:auto;padding:0 28px 80px}}nav{{height:82px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.09)}}nav img{{width:190px;height:48px;object-fit:contain;object-position:left center}}.links{{display:flex;gap:18px;color:#aab3c6;font-weight:650}}.hero{{padding:90px 0 48px;max-width:850px}}.eyebrow{{font-size:12px;letter-spacing:.15em;color:#8995ad;font-weight:800}}h1{{font-size:clamp(44px,6vw,72px);line-height:1.03;letter-spacing:-.05em;margin:18px 0 22px}}.lead{{font-size:19px;color:#a1acc1;max-width:760px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:24px 0 54px}}article{{padding:28px;border:1px solid rgba(255,255,255,.1);border-radius:16px;background:linear-gradient(180deg,rgba(17,22,36,.96),rgba(9,12,21,.96))}}article h2{{margin:0 0 10px;font-size:22px}}article p{{margin:0;color:#9ba6bc}}.actions{{display:flex;gap:12px;flex-wrap:wrap}}.primary,.ghost{{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:10px;font-weight:800}}.primary{{background:#6373f4;color:#fff}}.ghost{{border:1px solid rgba(255,255,255,.14);color:#dce2ee}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}.links{{display:none}}.hero{{padding-top:60px}}}}</style></head><body><div class=\"wrap\"><nav><a href=\"/\"><img src=\"/assets/lucas-logo-horizontal-white.png\" alt=\"Lucas MCP\"></a><div class=\"links\"><a href=\"/features\">Features</a><a href=\"/how-it-works\">How it works</a><a href=\"/security\">Security</a><a href=\"/pricing\">Pricing</a></div></nav><main><section class=\"hero\"><div class=\"eyebrow\">LUCAS MCP</div><h1>{data['h1']}</h1><p class=\"lead\">{data['lead']}</p></section><section class=\"grid\">{cards}</section><div class=\"actions\">{download_cta}<a class=\"ghost\" href=\"/pricing\">View pricing</a></div></main></div></body></html>"""
