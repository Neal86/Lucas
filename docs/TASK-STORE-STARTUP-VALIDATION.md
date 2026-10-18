# Concurrent task-store startup

Observed on 2026-10-18 in PR #8 head `03cddd5fd764e24e94028dc53faa900862eb573a`, run [39102751097](https://github.com/Neal86/Lucas/actions/runs/39102751097): Ubuntu 3.12 and Windows failed `test_concurrent_additive_migration_is_idempotent` at `PRAGMA journal_mode=WAL` with SQLITE_BUSY. The original eight-worker test and all its assertions remain unchanged.

The transition from rollback journaling to WAL can fail immediately under simultaneous constructors despite a SQLite busy timeout. `_connect` now handles only SQLITE_BUSY during this transition, with a single monotonic 30-second budget and a short bounded wait. Native waiting is disabled only during that loop, then restored to 30000 ms before returning the connection. Other SQLite errors and exhausted contention propagate, and failed connections close. Initialization also closes its owned connection after preserving commit/rollback behavior. No task identity, owner, operation, or history rules changed.

## Local evidence

`python -m unittest discover -s tests -p test_task_store_startup.py -v`

Four tests pass. One exercises actual disposable SQLite, eight simultaneous constructors across 30 database files (240 constructors), verifying preserved sentinel data, singular schema columns, and WAL mode. This same test failed immediately against the previous exact initializer with the reported SQLITE_BUSY error. Three tests use explicitly synthetic connection/error/time probes to verify busy retry, timeout propagation, non-busy propagation and closing, and restoration of ordinary busy timeout.

Tests extract only the three initializer methods from the actual source via AST. They do not import or validate authentication, Node permissions, providers or the complete application. Actual Windows/Linux complete regression and Chromium results must be established against the new published head. This document does not claim complete PRD acceptance.

## Wall-clock compatibility follow-up

The next hosted head `c511202` exposed three existing history tests that replace the module's business `time` object with `SimpleNamespace(time=...)`. Startup's monotonic budget and sleeping now use a separate `_startup_clock` reference, so business wall-clock freezing cannot replace or freeze the contention budget. Existing history assertions remain unchanged.

Five initializer regressions pass after adding a real SQLite wall-clock-replacement case. A separate local AST harness executes four unchanged original test functions: the eight-thread additive migration test, late/earlier completion timing, caller transaction/replay, and nullable legacy-end behavior. All four pass. That harness uses an explicit empty-metadata sanitizer fixture and patch.object-backed attribute restoration; it does not import gateway/auth and is not the full identity/history test suite. Complete current-head hosted regression remains required.
