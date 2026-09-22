# Lucas Browser Automation Architecture

Lucas exposes one browser automation surface to GPT, Claude, Gemini and other MCP clients. The MCP client does not need to know whether the target browser is a Lucas-managed Chrome profile or an ixBrowser profile.

## Design goals

- Run normal browser work through Playwright/CDP in the background.
- Avoid Windows mouse/keyboard input and foreground focus changes for ordinary web automation.
- Reuse existing browser login state, cookies, extensions, proxy and fingerprint configuration.
- Keep browser automation separate from desktop automation.
- Surface CAPTCHA, 2FA, passkey, login and identity-verification blockers back to the AI conversation as structured human handoffs.
- Resume the same browser session and tab after the user finishes the manual step.

## Browser modes

### Lucas-managed browser

Use `ensure_cdp` or `ensure_profile` for a dedicated Lucas browser profile. Eva remains isolated to the configured dedicated browser profile on each authorized Node.

### ixBrowser

Lucas Windows Node includes the official `ixbrowser-local-api` Python client. ixBrowser Local API must be enabled in the ixBrowser desktop application.

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

## Operational requirement

ixBrowser must be running locally and Local API must be enabled before `ix_profiles` or `ix_attach` can succeed. API availability depends on the ixBrowser plan and local ixBrowser settings.
