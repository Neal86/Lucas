from pathlib import Path

p=Path('src/gpt_windows_connector/gateway.py')
s=p.read_text(encoding='utf-8')
for block in [
'''            # Every legitimate Node may self-register. Account ownership is not part
            # of Node transport authentication; user access is authorized later by
            # Connection Code plus local approval.
''',
'''        # The Windows Node is the source of truth for security settings. The server
        # mirrors the locally reported values for status/audit only and never sends
        # an older web policy back as an authority.
''',
]:
    s=s.replace(block,'')
p.write_text(s,encoding='utf-8')
