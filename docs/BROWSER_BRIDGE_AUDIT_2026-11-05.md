# Browser Bridge audit and delivery evidence

Status: **not final / release blocked**. Date: 2026-11-05.
Reviewed baseline: main e40aa214fa9aa216f0b1586725749af4cec3981e;
PR #11 head 542e3ff7cc325a75a2aa128935687f760ab61e79.
No pre-existing final PRD file was found in the repository tree; browser behavior
was documented in BROWSER_AUTOMATION.md and BROWSER_EXTENSION_PUBLISHING.md.
The current user requirements are preserved in BROWSER_BRIDGE_PRD_FINAL.md.

## Scope reviewed

PR #11 complete diff, extension worker/content/popup/options/manifest, Node startup,
Bridge server and Settings IPC, profile registry/router/policy, extension packaging,
Windows browser setup, CI and browser tests. Also searched web modules for browser
management. This is a source/call-chain audit, not Windows runtime acceptance.

| Gap | Source evidence | Change / remaining work |
| --- | --- | --- |
| Popup includes Settings and pairing code | popup.html / popup.js | Removed; exactly 3 read-only fields |
| Popup omits current tab and Node | popup.js; hello_ack omits Node | Added actual handshake identity and active-tab state |
| Pairing depended on forbidden Popup content | Settings UI and server errors | Proof moved to Options; Windows pairing instructions updated |
| No in-page pause or resume | content.js only had takeover | Added trusted-click pause / takeover / resume |
| Reclaim unpauses taken-over tab | registerTab overwrote state | Existing same-task registration preserves pause |
| Extension claim had no confirmation gate | executeCommand tab.claim | Added gate in extension as well as router |
| Startup races ownership restoration | asynchronous local storage load | Commands/query wait for state initialization |
| Persistent tab IDs can target unrelated tabs after browser restart | local storage restoration | Use session storage for worker continuity; discard persistent ownership on fresh browser session |
| Long page waits continue during takeover | content page.wait loop | Recheck pause/release on each iteration and guard content commands |
| Concurrent audit writes can lose entries | local read-modify-write | Serialize metadata writes; forward live audit metadata to Node logger |
| Browser-restart original-task continuation | tab IDs are not durable identities | Still open: safe reset implemented; reliable restored-tab reconciliation/continuation not implemented |
| Unified Dashboard browser/profile/tab/permission management | web modules lack dedicated management flow | Still open; existing MCP/local management is not the required Dashboard UI |
| Durable audit replay and Dashboard integration | rolling 200-event local buffer, live Node logger | Still open: no acknowledged replay of disconnected human events or dedicated Dashboard browser audit view |
| True user confirmation provenance | claim/resume accept caller user_confirmed boolean | Still open: local per-tab approval proof for remote existing-tab claim/resume needs implementation |
| Full lifecycle/concurrency behavior in Chrome and Edge | no N20630 connection | Blocked, not passed |

## Executed checks

- `node tests/js/browser_bridge_runtime.cjs`: passed. Executes shipped worker/Popup
  code with Chrome API doubles; explicitly **not** real-browser acceptance.
- `python -m pytest -q`: 285 passed, 5 skipped (Windows-only and browser E2E gates).
- `python -m compileall -q src`: passed.
- Runtime regression covers background creation request, cross-task rejection,
  sender-tab-only takeover, second task continuation, pause/reclaim/resume guards,
  all 4 Tab states, live connection/expiry/disconnect and safe session reset.
- Existing interface tests exercise actual loopback WebSocket pairing, disconnect,
  authorization and local Settings IPC. They do not validate Chrome behavior.

## Real environment blockers

Lucas node_list exposed ALI and VICKYY only. Direct workspace_info for N20630,
C:\Users\Administrator returned NODE_EXECUTION_FAILED: Node is offline: N20630.
Audit request ID: 92a864a17bbe487e8c6ffeef24cb8b36. No other node was used.
All 12 required N20630 real-browser cases remain **NOT RUN / BLOCKED**.
No profiles were removed and no browser login data was cleared.

Staging inspection: Lucas-Staging UUID sy5dqdstzetp6s1irb3rrqsb is healthy,
configured branch fix/task-run-friendly-titles-20261030 and shares the production
SQLite mount. Its existing running build is not evidence for this change.
Staging has not been redeployed: required N20630 acceptance precedes deployment.
No production branch, deployment configuration, volume or database was changed.

CI results for the new commit must be checked after push. A draft PR is work in
progress; none of the blocked gates can be counted as final acceptance.
