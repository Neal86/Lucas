# Lucas Browser Bridge — final product requirements

Revision: 2026-11-05. This revision overrides earlier conflicting Popup requirements.
Baseline: main e40aa214fa9aa216f0b1586725749af4cec3981e and PR #11
542e3ff7cc325a75a2aa128935687f760ab61e79. Requirements are not a claim of acceptance.

## Interface boundaries

| Surface | Required responsibility |
| --- | --- |
| Extension Popup | Exactly three read-only fields: connection; Node/Profile; current Tab state |
| In-page Lucas indicator | Pause AI, take over, resume that Tab only |
| Lucas Dashboard | All browsers, profiles, tasks, tabs, permissions and logs |
| Windows Lucas Settings | Local connection, browser authorization, security |

Popup connection values are Connected / Disconnected. Connected requires a live,
paired connection with heartbeat younger than 45 seconds. Identity comes from the
Node handshake and its paired profile record, not sample labels or a hardcoded
Node. Current Tab values are Human / AI Running / AI Paused / Human Control,
resolved from the active Tab and its task ownership. A missing active Tab displays
an unavailable marker rather than inventing a human or AI state.

There are no buttons, task lists, tab lists, settings, pairing codes, log links,
or global actions in Popup. Pairing proof is available in the extension Options
page through the browser's extension-management UI; local authorization stays in
Windows Settings. No settings link is added to Popup.

## Required execution behavior

- Connect to an existing Chrome/Edge profile through the loopback Bridge without CDP.
- Open AI tabs in the background with active:false; do not activate the human tab or desktop.
- Every command belongs to a stable task; reject unclaimed or other-task tabs.
- Multiple tasks run independently in their own tabs.
- Claim an existing tab only with explicit user authorization.
- Display an in-page Lucas indicator on owned pages.
- Pause/takeover affects only the sender tab. Other tasks continue.
- Resume requires human confirmation. Reclaim must not clear a human pause.
- Automatically reconnect the Node/extension transport; preserve pauses across worker restarts.
- Browser restart must never apply stale tab IDs to unrelated human tabs.
- Enforce local profile/agent permissions and workspace restrictions.
- Record metadata for operations and human control transitions without page/input secrets.
- Support Chrome and Edge, with actual browser acceptance required for both.

## Mandatory real acceptance

Use only N20630, workspace C:\Users\Administrator. Do not substitute ALI or VICKYY.
Do not delete profiles, clear logins or interfere with unrelated tasks. Prioritize
Bridge operation with no CDP. Record actual results/logs for every case:

1. Popup has only three states and no buttons.
2. Disconnect/reconnect updates the connection state.
3. Node and Profile match the real paired identity.
4. Switching active tabs updates current-tab status.
5. Background tab creation does not steal foreground focus.
6. Human and AI tabs remain isolated.
7. Takeover pauses only the selected tab.
8. Another AI task continues during takeover.
9. Human-confirmed resume continues the original task.
10. Extension/browser restart and Node reconnect preserve safe, accurate state.
11. Complete real webpage operations without CDP.
12. Run the acceptance in real Chrome and Edge.

## Delivery gate

Audit main/PR and complete the gap register before changes; review call chains;
run CI, interface and automated tests; run N20630 acceptance and fix regressions;
then deploy/verify Staging; deliver commits, PR and evidence. Unit API doubles are
permitted for regression tests but never replace browser acceptance. Do not claim
final completion while any mandatory acceptance or implementation gap remains.

### Local consent and delivery semantics

A remote claim requests approval on the target page and returns a structured
requires_user_action response until the user clicks Allow AI there. Approval is
bound to a short-lived nonce, sender Tab and task. A caller-supplied boolean alone
is insufficient. A paused Tab can resume only through its trusted local button.
Audit metadata persists in a local outbox until Node acknowledgement; retries can
produce duplicate records with the same event ID (at-least-once delivery).
