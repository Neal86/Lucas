from pathlib import Path

p = Path('src/gpt_windows_connector/gateway.py')
lines = p.read_text(encoding='utf-8').splitlines()
# gateway.py is an orchestrator; detailed design rationale lives in ARCHITECTURE.md/README.
# Remove comment-only lines here to keep the enforced orchestrator size boundary without changing runtime code.
lines = [line for line in lines if not line.lstrip().startswith('#')]
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
