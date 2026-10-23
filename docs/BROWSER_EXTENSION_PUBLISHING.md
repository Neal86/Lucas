# Lucas Browser Bridge distribution

Node 1.7.71 adds a Settings > Browser installation and management flow.
Browser Bridge 1.1.0 adds reliable connection status and Lucas extension icons.

## Installation flow

1. Open Lucas Settings > Browser and select Install for the intended browser.
2. A configured, validated store link opens the extension store. Until a real
   listing exists, Install opens the local unpacked-install guide instead.
3. Install/enable the extension in the browser profile you intend to control.
4. Lucas detects the live connection within a few seconds and shows Manage.
5. Select Manage > Pair. Enter the six-digit code shown in that browser's
   extension popup. Only then does the browser show Connected and accept commands.
6. Manage > Disconnect revokes authorization without deleting the profile or
   changing agent policies. Reconnecting requires a fresh pairing code.

An extension folder on disk is not evidence that a browser has installed it.
Closed/disconnected browsers show Not connected. The popup never uses a historic
paired flag as proof of a live connection; its heartbeat expires after 45 seconds.

The existing advanced profile editor remains below the browser connection cards.
Existing folder boundaries, local access policy and agent/profile permissions still
apply. No automatic all-browser or all-profile authorization is granted.

## Build and public download

```sh
python scripts/package_browser_extension.py dist/Lucas-Browser-Bridge-1.1.0.zip
```

The same reproducible package is available at
`https://lucasmcp.com/download/Lucas-Browser-Bridge.zip` after this release is deployed.
The archive has manifest.json at its root, contains only extension assets, and
does not contain local configuration, account credentials or pairing secrets.

## Store configuration

No Chrome/Edge listing ID is fabricated. Set the actual approved URLs in
`src/gpt_windows_connector/browser_extension_stores.json` and release the updated
Node. A local `browser-extension-stores.json` in Lucas's configuration directory
may override the distribution links for testing. Only HTTPS links to actual
Chrome Web Store/Edge Add-ons item paths are accepted.

```json
{
  "chrome": null,
  "edge": null,
  "ixbrowser": null
}
```

Replace null only with your real published listing URL. Local unpacked
installation remains available before approval; no store submission is automatic.

## Chrome Web Store submission material

Upload the generated ZIP through your developer account at
https://chrome.google.com/webstore/devconsole.
Official publishing instructions: https://developer.chrome.com/docs/webstore/publish.

Name: Lucas Browser Bridge

Single purpose: Connect a user-selected browser profile to the locally installed
Lucas Node so an authorized AI assistant can read and interact with websites at
the user's request.

Suggested description:

Lucas Browser Bridge connects your browser to Lucas running on your computer.
Use your existing browser sessions for tasks such as reading pages, entering
text, clicking controls, managing tabs and downloading files. Install Lucas Node,
open its Browser settings and pair this browser using the code in the extension
popup. Browser connections and authorizations are managed on your computer.

Permission explanations (reflecting the actual code):

| Permission | Purpose |
| --- | --- |
| tabs | Identify and operate tabs when Lucas requests a browser action. |
| scripting | Execute packaged browser interaction code for authorized commands. |
| storage | Store the local installation identity, profile labels and connection status. |
| downloads | Download files when the assistant requests a download. |
| host access | Read/interact with websites selected for browser tasks. The user may restrict extension site access in the browser. |

Data handling: The extension exchanges browser commands/results with the local
Node on 127.0.0.1:8766. Requested page text, tab information and action results may
be forwarded by Lucas to the user's AI service; execution metadata may be logged
by Lucas. It does not request cookie, browser history, webNavigation or debugger permissions.
Review and align the live privacy policy at https://lucasmcp.com/privacy with
these disclosures before submitting, and supply store screenshots, support
contact and any additional declarations required by the developer dashboard.
Do not claim that browser data never leaves the device.

Developer-account submission and store approval are separate from deploying
Lucas. No upload, publication or developer-account purchase is performed by the
packaging command.

## Local Settings IPC

The Settings process uses an authenticated loopback WebSocket at `/settings` on
the existing bridge port. A random per-start token is stored only in the local
Lucas configuration directory. Browser Origin headers are rejected on this path;
the path is not exposed as an MCP action. Pairing still requires the code from
the extension popup. Status never returns that code or the settings token.
