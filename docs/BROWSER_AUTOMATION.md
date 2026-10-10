# Lucas Browser Automation Architecture

Lucas exposes one browser automation surface to GPT, Claude, Gemini and other MCP clients. The MCP client does not need to know whether the target browser is a Lucas-managed Chrome profile or an ixBrowser profile.

## Design goals

- Run normal browser work through Playwright/CDP in the background.
- Avoid Windows mouse/keyboard input and foreground focus changes for ordinary web automation.
- Reuse existing browser login state, cookies, extensions, proxy and fingerprint configuration.
- Keep browser automation separate from desktop automation.
- Surface CAPTCHA, 2FA, passkey, login and identity-verification blockers back to the AI conversation as structured human handoffs.
- Resume the same browser session and tab after the user finishes the manual step.

## Profile Router

Named browser work goes through the local Browser Profile Router. Agents can select by:

- `profile_name`
- `profile_id`
- `alias`
- `tag`
- `group`
- stable Lucas `profile_key`

Profiles are selectable browser targets, not agent isolation boundaries. `profile_open` remembers a selection for convenience. `profile_action` accepts an explicit `profile_key`, `profile_id`, `profile_name`, alias, tag or group and connects/switches to that selection before performing the operation. No prior task binding is required when a profile selector is supplied. Calls without a selector reuse the remembered selection; if there is no selection, callers must choose one rather than guessing.

Legacy per-agent Profile allow/deny rules and the automatic Eva-only restriction are inactive. Existing configuration, profile directories, cookies and login state are preserved. Node/account authorization, local folder guards and foreground approval continue to apply.

## Browser modes

### Lucas-managed browser

Use `ensure_cdp` or `ensure_profile` for a dedicated Lucas browser profile. An explicit endpoint, profile and session are honored; the gateway never forces Eva or port 9222. Existing browser sessions can be selected directly. A browser must expose CDP or have a paired Browser Bridge before Lucas can control it.

### Browser Bridge

Lucas Browser Bridge is a Manifest V3 Chromium extension included with Lucas Node. The Node copies it to:

```text
%LOCALAPPDATA%\Lucas\browser-bridge-extension
```

The extension connects only to the local Node at `ws://127.0.0.1:8766/bridge`. It reports a per-profile installation ID, then Lucas pairs that installation with a local Profile record. Once paired, the Router can operate that existing ixBrowser, Chrome, or Edge profile without opening another browser.

Bridge page work runs in background tabs where Chromium permits it. It reuses the profile's existing authenticated state and does not request cookie-reading permission.

### ixBrowser

Lucas Windows Node includes the official `ixbrowser-local-api` Python client. ixBrowser Local API must be enabled in the ixBrowser desktop application when that transport is used.

Default Local API endpoint:

```text
http://127.0.0.1:53200/api/v2/
```

The high-level flow is:

```text
AI client
   |
Lucas MCP browser_tool
   |
ixBrowser Local API -> open profile
   |
debugging_address
   |
Playwright connect_over_cdp
   |
existing ixBrowser profile/session
```

The Local API profile result is sanitized before it is returned to the AI. Passwords, TOTP secrets, cookies and access tokens are not returned by `ix_profiles`.

## Browser actions

Connection and profile actions:

- `discover`
- `connect_cdp`
- `ensure_cdp`
- `ensure_profile`
- `launch_persistent`
- `ix_status`
- `ix_profiles`
- `ix_attach`
- `ix_close`

Semantic and page actions:

- `pages`
- `resolve`
- `observe`
- `snapshot`
- `new_page`
- `navigate`
- `inspect`
- `semantic_click`
- `semantic_type`
- `click`
- `type`
- `select`
- `press`
- `hover`
- `scroll`
- `wait`
- `reload`
- `back`
- `forward`
- `close_page`

Transfer and diagnostics:

- `upload`
- `download`
- `screenshot`
- `network`
- `diagnostics`

Human handoff:

- `check_user_action`
- `request_user_action`
- `pending_user_actions`
- `resume`

Profile Router and Bridge:

- `bridge_extension`
- `bridge_clients`
- `bridge_pending`
- `bridge_pair`
- `profile_list`
- `profile_resolve`
- `profile_open`
- `profile_action`
- `profile_resume`
- `profile_release`

## Background behavior

Playwright/CDP actions interact with the browser protocol. They do not activate the browser window, move the Windows pointer or type through the foreground keyboard.

A headed browser window may still exist because ixBrowser profiles are intended to preserve their normal fingerprint, extensions and authenticated state. If the site or browser opens a native Windows dialog, CAPTCHA, passkey prompt, file chooser or other UI that cannot be completed through browser protocol access, Lucas stops the browser workflow and requests user action rather than silently taking foreground control.

`computer_tool` remains the explicit fallback for native Windows UI. Foreground-control confirmation continues to apply to those desktop actions.

## Human-in-the-loop contract

When Lucas detects a manual blocker it returns:

```json
{
  "status": "requires_user_action",
  "requires_user_action": true,
  "action_type": "captcha",
  "message": "The site requires a human verification/CAPTCHA.",
  "resume_token": "...",
  "chat_message": "需要你的操作：..."
}
```

The AI must surface `chat_message` to the user and stop browser automation. The browser session and tab remain open.

After the user says the step is complete, the AI calls:

```text
browser_tool(action="resume", params={"resume_token": "..."})
```

and continues from the same browser session.

## Security

Browser-protocol actions are classified as browser control, not foreground desktop control. This distinction prevents background Playwright/CDP work from triggering the foreground-focus approval setting.

Uploads and downloads keep the existing workspace path restrictions. ixBrowser profile metadata is sanitized, and the integration never exposes profile passwords or 2FA secrets through `browser_tool`.

## Operational requirements

The Browser Bridge service starts with Lucas Node and listens on localhost only. Install the unpacked Lucas Browser Bridge extension into any browser profile that should be agent-controllable, then pair it once with a local Profile record.

For ixBrowser Local API mode, ixBrowser must be running and Local API must be enabled. When Local API is unavailable, a connected Browser Bridge can still control an already-open ixBrowser profile. If a requested profile is closed and no configured launcher/API is available, Lucas returns a resumable `requires_user_action` response naming the exact Profile that must be opened.

## Observation references

For Codex-style page interaction, first call `observe` with the selected `session_id` and `page_index` (CDP), or `profile_action(operation="observe", operation_params={"tab_id": ...})` (Bridge). Each visible control includes an opaque `ref`. Pass that exact string as `target` to `semantic_click` or `semantic_type` on the same tab. Bridge `snapshot` also includes references; CDP `snapshot` retains its existing ARIA format, so use `observe` to obtain actionable references.

References retain DOM element identity even when controls are inserted or reordered. They expire on a new observation and cannot be used on another tab. Detached, hidden, disabled or relabeled controls stop the action and require a fresh observation. Semantic targets that match multiple visible controls are rejected instead of clicking the first match. References are in-memory and do not alter page attributes or persist to disk. Control descriptors do not include input values, including passwords.

Example CDP sequence:

```json
{"action":"observe","params":{"session_id":"selected-session","page_index":0}}
{"action":"semantic_click","params":{"session_id":"selected-session","page_index":0,"target":"ref:<returned-id>:0"}}
```

This implements a similar interaction workflow; it does not reuse Codex's proprietary browser runtime. Normal operations continue through background browser protocols. Native dialogs and verification blockers use the existing explicit handoff workflow.
