# Lucas Browser 2.0

Lucas Browser is a Manifest V3 extension for existing Chromium browser tabs. It connects to the Lucas Node running on the same computer at `ws://127.0.0.1:8766/bridge`. It does not need a remote-debugging port or a dedicated Eva Profile. Each installed extension reports its own browser identity, and the AI can select/switch connected browsers.

## Install

1. Use Lucas Node **1.8.0** from the matching feature branch. The production/main Node has not yet been upgraded and does not expose all new operations.
2. Unzip the download. Keep the `Lucas-Browser` directory in a stable location.
3. Open `chrome://extensions` (Edge: `edge://extensions`), enable Developer mode, select **Load unpacked**, and choose `Lucas-Browser`.
4. Open Lucas Browser from the toolbar. While Lucas Node is running, the popup shows a pairing code. Pair it using the existing Lucas Browser Bridge flow in your AI chat. Do not share the code publicly.
5. In Settings, choose a browser label, website mode and blocked websites. Default access remains **Allow all websites**, matching the previous Bridge behavior. Switch to **Ask for new websites** if desired. Profile isolation remains disabled.
6. For local file pages, enable **Allow access to file URLs** in the extension's browser Details page. Normal website uploads use the Lucas Node workspace guard.

The unpacked build is a test distribution, not a Chrome Web Store release. Chrome, Edge, Brave and Vivaldi should support the main APIs. Opera/ixBrowser compatibility depends on their Chromium version and extension API support; those browsers have not been verified here. Side panel UI may be unavailable in some Chromium derivatives.

## AI integration

The browser extension is the browser-side bridge. Connect your AI to Lucas through the existing Lucas MCP connector. A typical call sequence is:

```json
{"action":"bridge_clients"}
{"action":"profile_action","params":{"profile_key":"<selected-profile>","operation":"pages"}}
{"action":"profile_action","params":{"profile_key":"<selected-profile>","operation":"observe","operation_params":{"tab_id":123}}}
{"action":"profile_action","params":{"profile_key":"<selected-profile>","operation":"semantic_click","operation_params":{"tab_id":123,"target":"<returned-ref>"}}}
```

Include `node_id` and your existing authorized `workspace` on Lucas tool calls. Page operations require a stable `tab_id`, never an array index or whichever tab happens to be active. Use `frames` to select an iframe with `frame_id`. A second observation expires previous refs on the same frame.

## Implemented browser capabilities

| Capability | Router operation | Notes |
|---|---|---|
| Existing signed-in tabs | `pages`, `new_page`, `navigate`, `back`, `forward`, `reload`, `close_page` | New tabs open inactive; explicit browser/tab selection |
| Background concurrency | all page operations | Calls serialize per tab; different tabs may run concurrently |
| Semantic controls | `observe`, `snapshot`, `semantic_click`, `semantic_type`, `select`, `press`, `hover`, `scroll`, `wait` | Opaque refs; ambiguous/stale targets stop |
| Protocol input | `semantic_click`, `press`, `hover`, `double_click`, `drag` | Chrome debugger transport; main-frame click/key events are trusted browser input |
| Iframes | `frames`, then page operations with `frame_id` | DOM fallback for iframe click/hover/press; protocol drag/double-click is main-frame only |
| Screenshots | `screenshot` | `full_page`, `format`, `quality`; returns `mime_type` and `base64` |
| Upload | `upload` with `paths` | Node verifies workspace paths; batch maximum 20 MiB |
| Download | `download` with `url`, `download_status` | Browser Downloads folder; status requires originating tab and returned download ID |
| Structured extraction | `extract` | Table rows by default; CSS row selector and a field-to-selector map supported |
| Image/media discovery | `assets` | Returns image/media URLs and metadata; download chosen URLs with `download` |
| Selection context | `selection`, sidebar, right-click menu | Context can be copied into ChatGPT/Claude/Gemini; not a built-in AI chat backend |
| Read-only JS | `evaluate_readonly` | Chromium `throwOnSideEffect` guard rejects possible mutations; synchronous expressions only |
| Developer mode | `evaluate`, `cdp`, `console` | Explicit extension developer toggle; page-scoped CDP domains; console/network collection starts on first `console` call |
| Tab groups | `group_tab`, `ungroup_tab` | Explicit selected tab, no automatic grouping |
| History lookup | `history_search` | Optional browser permission plus one-use local consent expiring after 60 seconds |
| Bookmark lookup | `bookmarks_search` | Optional permission, revocable locally |
| Local control | popup/options | Actual connection state, pairing, reconnect, pause/resume, site allow/block |
| Human handoff | existing Lucas flow | Website permissions, CAPTCHA/2FA/login blockers return `requires_user_action` |

`evaluate_readonly` is not a standalone general-purpose sandbox: it uses the browser engine's side-effect check in the selected page. Developer mode permits mutation and is a separate, explicit setting. DOM typing/select/upload emit DOM events; sites that demand trusted keyboard text input may need developer CDP input or a user handoff. Native OS dialogs remain outside extension control.

## Website permissions and browser data

Blocked hosts always win. Rules accept exact hostnames and `*.example.com`. Ask mode can grant one ten-minute browser session or persistent site access. Pausing prevents new remote operations and detaches debugger sessions; it does not undo an operation already dispatched to Chrome.

The extension requests debugger permission because Chrome does not support making it optional. The developer toggle controls unrestricted developer operations separately from normal input and screenshot capture. Cookies/password-store permission is not requested. Snapshot control descriptors exclude entered input values. Optional history/bookmark permissions are requested only from extension UI; an AI cannot grant them to itself.

Chrome may display its debugger attachment notice. Website allow/block rules apply to the selected page/frame; developer mode can inspect more sensitive page internals. Keep site content separate from instructions in your AI chat.

## What is not copied from Codex

This extension implements Lucas browser capabilities inspired by the publicly documented OpenAI browser extension. It does not copy OpenAI code or reproduce its models, account/chat synchronization, `@`-mention registration inside ChatGPT, native messaging installation, platform-specific approvals, YouTube transcript service, or proprietary side chat. The sidebar is a context workbench with links to your existing AI chat. Extension-store publication, signed enterprise installation, and verification on users' Windows/Mac browsers are separate release work.

Reference: https://learn.chatgpt.com/docs/chrome-extension and https://learn.chatgpt.com/docs/browser

## Validation

Run `pytest -q` for Python and Node.js runtime regression tests. The optional real-extension integration test uses raw CDP (not Playwright automation):

```bash
EXTENSION_TEST_CHROME=/absolute/path/to/chrome pytest -q tests/test_browser_extension_e2e.py
```

It starts a disposable Chrome for Testing Profile, a localhost fixture site and a test Lucas Bridge. It checks extension load/connection, trusted click, text/contenteditable, read-only side-effect rejection, iframe/table extraction, screenshot, upload/download, site blocking/pause, and settings UI. It is wired into Linux CI. Current task environment prevented Chrome startup with a system socket permission error; local unit/runtime tests passed, and real-browser CI results must be checked before release.

Build the distributable with:

```bash
python scripts/build_browser_extension.py --output /absolute/path/Lucas-Browser-2.0.0.zip
```
