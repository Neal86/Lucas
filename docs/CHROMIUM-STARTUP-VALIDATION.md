# Chromium debugging-port readiness

PR #8 exact head `6d2f6fc` run [39103311552](https://github.com/Neal86/Lucas/actions/runs/39103311552) passed all ordinary Linux/Windows tests but failed two browser tests before their page assertions. The common startup fixture observed the newly created `DevToolsActivePort` file before Chromium wrote its contents, then indexed an empty list. An earlier head had the same failure.

The fixture now waits for a valid ASCII port and the browser endpoint line, handling absent, empty and partially written files within the original 15-second budget. Process exit still fails promptly. The launch flags, process cleanup, network restrictions, OAuth/401 assertions and browser test count remain unchanged. No timeout increase or skip was added.

Six local regression tests pass using actual temporary port files and explicitly synthetic process/clock objects: complete content; missing/empty/partial writes; invalid port; early process exit; exit after reading; and bounded timeout. They compile the actual helper from its AST without importing the application. These are readiness contract tests, not actual browser acceptance. Full current-head hosted Chromium, Linux and Windows results remain required.
