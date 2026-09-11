from gpt_windows_connector.gateway import (
    _extract_runtime_shell_operations,
    _shell_operation_count,
    _shell_operations,
)
from gpt_windows_connector.task_runs import TaskRunStore


def test_shell_operation_count_single_and_multiple():
    assert _shell_operation_count("npm test") == 1
    assert _shell_operation_count("npm install && npm test && npm run build") == 3
    assert _shell_operation_count("mkdir demo; cd demo; npm init -y") == 3


def test_shell_operation_count_ignores_here_string_body():
    command = """@'
line one
line two
line three
'@ | Set-Content report.txt
npm test
"""
    assert _shell_operations(command) == ["'<here-string>' | Set-Content report.txt", "npm test"]
    assert _shell_operation_count(command) == 2


def test_shell_operation_count_ignores_powershell_structure_and_data():
    command = """$items = @(\"a\", \"b\")
foreach ($item in $items) {
  $name = $item
  New-Item -ItemType Directory -Path $item
  if (Test-Path $item) {
    Set-Content -Path \"$item\\result.txt\" -Value \"ok\"
  }
}
# comment
Write-Host \"done\"
npm test
"""
    assert _shell_operations(command) == [
        "New-Item -ItemType Directory -Path $item",
        'Set-Content -Path "$item\\result.txt" -Value "ok"',
        "npm test",
    ]
    assert _shell_operation_count(command) == 3


def test_shell_operation_count_counts_command_on_assignment_rhs():
    assert _shell_operations("$content = Get-Content file.txt\n$result = 42") == ["Get-Content file.txt"]


def test_static_shell_operations_ignore_join_path_helpers():
    command = """$root = Join-Path $env:USERPROFILE "demo"
New-Item -ItemType Directory -Force -Path $root
$input = Join-Path $root "input.csv"
Import-Csv -Path $input
"""
    assert _shell_operations(command) == [
        "New-Item -ItemType Directory -Force -Path $root",
        "Import-Csv -Path $input",
    ]


def test_runtime_trace_counts_loop_iterations_and_ignores_helpers():
    stdout = """DEBUG:    3+   >>>> $root = Join-Path $env:TEMP "demo"
DEBUG:    4+   >>>> New-Item -ItemType Directory -Force -Path $root
DEBUG:    5+   >>>> 1..3 | ForEach-Object { Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object  >>>> { Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object {  >>>> Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object { Set-Content -Path (Join-Path $root "$_.txt") -Value $_  >>>> }
DEBUG:    5+   1..3 | ForEach-Object  >>>> { Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object {  >>>> Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object { Set-Content -Path (Join-Path $root "$_.txt") -Value $_  >>>> }
DEBUG:    5+   1..3 | ForEach-Object  >>>> { Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    5+   1..3 | ForEach-Object {  >>>> Set-Content -Path (Join-Path $root "$_.txt") -Value $_ }
DEBUG:    6+   >>>> Get-ChildItem $root
DEBUG:    7+   >>>> Set-PSDebug -Off
visible output
"""
    clean, operations = _extract_runtime_shell_operations(stdout)
    assert clean == "visible output\n"
    assert operations == [
        "New-Item -ItemType Directory -Force -Path $root",
        'Set-Content -Path (Join-Path $root "$_.txt") -Value $_',
        'Set-Content -Path (Join-Path $root "$_.txt") -Value $_',
        'Set-Content -Path (Join-Path $root "$_.txt") -Value $_',
        "Get-ChildItem $root",
    ]


def test_runtime_trace_counts_pipeline_sink_once():
    stdout = 'DEBUG:   10+   >>>> "Count=5" | Set-Content -Path $summary\n'
    clean, operations = _extract_runtime_shell_operations(stdout)
    assert clean == ""
    assert operations == ['Set-Content -Path $summary']


def test_task_title_upgrades_fallback_run_and_preserves_weight(tmp_path):
    store = TaskRunStore(tmp_path / "tasks.db")
    common = dict(owner_id="u1", node_id="n1", target=r"C:\\Work", status="success")
    first = store.record_operation(
        **common,
        action="workspace.info",
        started_at=100.0,
        ended_at=101.0,
        operation_count=1,
        context_key=r"C:\\Work",
    )
    second = store.record_operation(
        **common,
        action="shell.run",
        started_at=102.0,
        ended_at=103.0,
        operation_count=3,
        context_key=r"C:\\Work",
        task_title="Create and review software service contract",
    )
    assert first == second
    runs = store.list_runs("u1")
    assert len(runs) == 1
    assert runs[0]["title"] == "Create and review software service contract"
    assert sum(step["operation_count"] for step in runs[0]["steps"]) == 4
