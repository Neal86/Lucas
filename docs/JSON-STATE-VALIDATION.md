# Remaining JSON inputs and one-time OAuth state

Scope: LUC-B03/B04, against PR #8 head `d240afd` on 2026-10-18. Prior admin-query and localization fixes are preserved separately.

- Three email auth handlers now reuse the existing JSON-object reader, preserving their ValueError-to-400 policy, rate/verification behavior and configuration gates.
- Node access-request validates the JSON-object shape after its unchanged authentication check, before any downstream Node/capacity/rate/authorization operation. Malformed and nonobject input returns 400; valid empty objects still reach the existing missing-node validation.
- Google OAuth state's existing digest lookup/delete is now serialized by BEGIN IMMEDIATE in a single transaction. Expired/missing states retain PermissionError semantics. The owned connection closes after commit/rollback. No external Google call or code/token policy changed.

## Evidence

`python -m unittest discover -s tests -v`

Seven tests pass. Against the unchanged baseline, 21 invalid JSON request subcases returned 500 rather than 400 and the eight-thread state test accepted the same state more than once (22 failing assertions). After the patch all 24 invalid-body subcases and empty-object/configuration/auth-order controls pass. State concurrency yields exactly one accepted callback and seven rejected; sequential replay, expired removal and unrelated-state preservation pass.

The HTTP checks execute actual extracted handler/helper AST through real Starlette/HTTPX ASGI, with explicitly synthetic authentication, rate-limit and email-verification fixtures. They never invoke a Node or mail/provider service and are not full authenticated-route acceptance. State tests execute the actual consume method with disposable real SQLite WAL, an explicit connection factory fixture and eight concurrent threads, without real Google or account/token services. Existing complete hosted regression/browser tests remain required at the final published head. No production deployment or complete PRD acceptance is claimed.

## Confirmed-defect ledger

- LUC-B01: code corrected to timestamp/id ordering; isolated production-handler SQLite regressions and complete hosted `d240afd` regression passed. Live deployment is not verified.
- LUC-B02: code filters effective legacy-aware status before counting the limit; same isolated and hosted evidence passed. Production-scale sparse-filter latency remains unverified.
- LUC-B03: four remaining object-body boundaries corrected; the seven-test batch includes all 24 invalid-body request subcases and configuration/auth-order/object controls. Final candidate complete hosted integration remains pending; isolated fixtures are not real mail/Node acceptance.
- LUC-B04: one-time state consumption is transactionally serialized; eight concurrent consumers accept exactly once. Independent fault injection additionally verified DELETE failure rolls back, closes the connection and leaves state retryable. Final candidate hosted integration remains pending; no real Google OAuth provider exchange was performed.

These entries distinguish code fixes from deployment and external-service acceptance. They do not close the remaining PRD/device/provider/release gaps.
