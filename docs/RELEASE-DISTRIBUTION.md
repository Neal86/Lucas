# Review-distribution contract

This candidate is a source-only review build based on PR4 commit
`8787b1fabf219780af215e4d9aebb79e3ae4dac1`. It does not release a new Node
version, merge the divergent branches, deploy a service or run an installer.

## Channels and update safety

- `update_distribution.UPDATE_CHANNEL` is committed as `review`. Unknown
  channels also fail closed. There is no environment-variable override.
- Review builds show a localized warning and disable automatic checks and
  in-app update actions. Direct calls to the version reader and update worker
  are guarded before network requests, settings snapshots or installer launch.
- The existing stable contract is still the exact Neal86/Lucas main version
  metadata, main installer and main.zip. The stable channel is **not activated**
  by this change. A future release must deliberately reconcile its source,
  versions, package assets, update behavior and approvals before changing the
  channel marker. Different version/installer URLs are rejected.
- Do not use the production main installer as a way to install this review
  build. It installs different source. A reviewed matching package/source
  distribution and explicitly authorized disposable test device are required.
- Node metadata remains 1.7.55, the extension remains 2.1.0, and the legacy
  module `__version__` remains 1.2.0. That known identity mismatch is a release
  gate, not a new published version. Main reports package 1.7.69; PR2 reports
  1.8.0. Updating between these branches is not a defined review channel.

## Preserved runtime contracts

- Both Compose definitions regain main's loopback HTTP healthcheck. The final
  image includes curl. The staging volume remains `lucas-staging-data`, scoped
  to its Compose project; mounts, routing, credentials and isolation are not
  changed. Container health does not replace all-route smoke acceptance.
- The single-file PowerShell installer reads/restores JSON as UTF-8. Before a
  failed parse can be repaired, it copies original bytes to a unique `.corrupt-`
  backup. Only one unterminated, single-line `rules_text` immediately before
  `show_rule_summary` is repairable, with no quote/object/array boundary in the
  damaged span. The validated match is spliced exactly once. Strict decoding
  rejects invalid UTF-8, and repair preserves the original BOM state.
  Duplicate/ambiguous fields and unrelated parse failures abort without altering
  the original. This is narrower than main's legacy matcher.
  All bytes outside the corrected span survive; identities, tokens, roots,
  permissions and unknown fields are not guessed or reset.
- Settings uses a dedicated, pointer-sized Windows mutex. Duplicate or failed
  acquisitions stop before local configuration processing. An updater-created
  Settings process waits at most five seconds for the prior process to exit;
  ordinary launches do not wait. The installer itself never starts a second
  Settings window during an app update. Tray/shortcut reopening remains possible.
- Existing extension ZIP contents and wheel force-inclusion remain unchanged,
  including grant_lifecycle.js and page_actions.js. The current account/tab
  grants and canceled Eva/Profile policy are preserved.

## Verification and limits

Focused regressions cover blocked review/unknown-channel effects, mismatched
source URLs, stable parser compatibility, English/Chinese warning text,
metadata and ZIP byte parity, Compose/image healthcheck source parity,
isolated mutex acquisition/duplicate/handover/failure and installer fixtures.
The PowerShell tests execute **only the extracted reader function** against
temporary synthetic files, never the installer entrypoint. Windows CI also
checks the real kernel mutex with a unique disposable test name. Linux without
PowerShell skips the twelve PowerShell fixtures and native Windows mutex test.

The stacked PR targets `fix/history-response-ownership-20261016`; CI includes
that exact base branch and retains the Linux 3.11/3.12, Windows 3.11 and Chromium
matrix. The initial focused architecture-budget failure was corrected by
moving Settings argument/startup orchestration into its dedicated module;
the size limit was not raised.

This is not proof of a distributable wheel, actual Windows Settings/installer,
SMTP/provider, user-device, deployment or production acceptance. The canceled
wheel operation is not retried. Desktop/plugin/browser reconciliation,
referral reward policy, known paused Node/files findings, approved staging
image verification and existing subscription handling remain separate gates.
