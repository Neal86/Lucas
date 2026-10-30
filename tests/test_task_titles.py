from gpt_windows_connector.task_runs import TaskRunStore
from gpt_windows_connector.task_titles import display_task_title


def test_legacy_shell_path_title_is_humanized():
    steps = [{
        "action": "shell.run",
        "target": r"C:\\Users\\Administrator",
        "details": {
            "sub_operations": [
                r"Get-Content C:\\Lucas\\logs\\gateway.log",
                r"Select-String -Path C:\\Lucas\\logs\\gateway.log -Pattern ERROR",
            ]
        },
    }]
    assert display_task_title(r"shell.run · C:\\Users\\Administrator", steps) == "Check application logs"


def test_explicit_task_title_always_wins():
    steps = [{
        "action": "shell.run",
        "target": r"C:\\Users\\Administrator",
        "details": {
            "task_title": "检查 Lucas 远程执行日志",
            "sub_operations": [r"Get-Content C:\\Lucas\\logs\\gateway.log"],
        },
    }]
    assert display_task_title(r"shell.run · C:\\Users\\Administrator", steps) == "检查 Lucas 远程执行日志"


def test_shell_edit_and_test_is_described_as_one_plain_language_task():
    steps = [{
        "action": "shell.run",
        "target": r"C:\\Users\\Administrator",
        "details": {
            "sub_operations": [
                r"Set-Content -Path app.py -Value $content",
                "pytest -q",
            ]
        },
    }]
    assert display_task_title(r"shell.run · C:\\Users\\Administrator", steps) == "Update and test project"


def test_task_store_returns_friendly_title_without_migrating_stored_record(tmp_path):
    store = TaskRunStore(tmp_path / "tasks.db")
    store.record_operation(
        owner_id="u1",
        node_id="N20630",
        action="shell.run",
        target=r"C:\\Users\\Administrator",
        started_at=100.0,
        ended_at=101.0,
        status="success",
        details={"sub_operations": ["npm test"]},
        context_key=r"C:\\Users\\Administrator",
    )

    runs = store.list_runs("u1")
    assert len(runs) == 1
    assert runs[0]["title"] == "Run project tests"
    assert runs[0]["steps"][0]["action"] == "shell.run"
    assert runs[0]["steps"][0]["target"] == r"C:\\Users\\Administrator"
