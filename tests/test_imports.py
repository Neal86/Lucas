def test_runtime_modules_import():
    import gpt_windows_connector.auth  # noqa: F401
    import gpt_windows_connector.browser  # noqa: F401
    import gpt_windows_connector.computer  # noqa: F401
    import gpt_windows_connector.executor  # noqa: F401
    import gpt_windows_connector.gateway  # noqa: F401
    import gpt_windows_connector.node  # noqa: F401
    import gpt_windows_connector.processes  # noqa: F401
    import gpt_windows_connector.webapp  # noqa: F401
    import gpt_windows_connector.server  # noqa: F401


def test_managed_processes_are_hidden_background_jobs():
    from gpt_windows_connector import processes

    assert processes.BACKGROUND_CREATION_FLAGS & processes.CREATE_NO_WINDOW
    assert processes.BACKGROUND_CREATION_FLAGS & processes.CREATE_NEW_PROCESS_GROUP
