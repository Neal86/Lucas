# Remote execution reliability repair — 2026-10-24

The Gateway no longer injects Set-PSDebug into submitted commands. Operation accounting uses the existing static command parser; dynamic loop iterations are not measured by runtime tracing.

Node and Gateway return execution errors with stable codes (RPC_TIMEOUT, APPROVAL_TIMEOUT, PERMISSION_DENIED, NODE_DISCONNECTED, NODE_EXECUTION_FAILED). Tool runtime failures are returned as structured results rather than escaping into connector INVALID_ARGUMENT wrappers.

Local approval dialogs expire after 45 seconds; queued approvals wait at most 50 seconds before display. Duplicates share the decision and do not use the transport request ID as identity. Necessary dangerous-operation gates and explicit local blocks remain in force. Deploying the Gateway does not upgrade already-running Windows Nodes: they must also receive the matching Node source update and restart.

Durable jobs persist worker launch failures and interrupted outcomes, and never replay an unknown side effect. Shell timeouts terminate descendant processes. Approval happens before job creation, so an approval wait cannot be diagnosed solely through the jobs directory.

Validation: Linux suite 275 passed, 5 platform skips. Windows and deployment evidence is recorded after runtime verification.
