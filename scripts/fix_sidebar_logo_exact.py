from pathlib import Path

web_assets = Path('src/gpt_windows_connector/web_assets.py')
text = web_assets.read_text(encoding='utf-8')
old_sidebar = '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>'
new_sidebar = '<div id="app" class="shell hidden"><aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal-white.png" alt="Lucas" /></div>'
if old_sidebar not in text:
    raise SystemExit('sidebar logo marker not found')
text = text.replace(old_sidebar, new_sidebar, 1)
old_css = '.logo img{display:block;width:184px;height:auto;background:transparent;border-radius:0;padding:0;filter:brightness(0) invert(1)!important}'
new_css = '.logo img{display:block;width:184px;height:auto;background:transparent;border-radius:0;padding:0;filter:none!important}'
if old_css not in text:
    raise SystemExit('sidebar logo css marker not found')
text = text.replace(old_css, new_css, 1)
web_assets.write_text(text, encoding='utf-8')

webapp = Path('src/gpt_windows_connector/webapp.py')
text = webapp.read_text(encoding='utf-8')
old = 'if name not in {"lucas-logo-horizontal.png", "lucas-logo-square.png"}:'
new = 'if name not in {"lucas-logo-horizontal.png", "lucas-logo-horizontal-white.png", "lucas-logo-square.png"}:'
if old not in text:
    raise SystemExit('brand asset allowlist marker not found')
webapp.write_text(text.replace(old, new, 1), encoding='utf-8')

print('sidebar logo switched to exact white asset with no filters')
