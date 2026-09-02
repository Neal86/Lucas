from pathlib import Path

webapp = Path('src/gpt_windows_connector/webapp.py')
s = webapp.read_text(encoding='utf-8')
s = s.replace('if name not in {"lucas-logo-horizontal.png", "lucas-logo-square.png"}:', 'if name not in {"lucas-logo-horizontal.png", "lucas-logo-horizontal-white.png", "lucas-logo-square.png"}:')
webapp.write_text(s, encoding='utf-8')

assets = Path('src/gpt_windows_connector/web_assets.py')
s = assets.read_text(encoding='utf-8')
s = s.replace('/assets/lucas-logo-horizontal-white.png" alt="Lucas"', '/assets/lucas-logo-horizontal-white.png?v=20260902-2" alt="Lucas"')
assets.write_text(s, encoding='utf-8')
print('sidebar logo delivery patched')
