# Lucas architecture boundaries

This repository intentionally keeps high-risk responsibilities isolated so a change in one area does not require editing unrelated code.

## Stable boundaries

- `webapp.py`: HTTP composition and route wiring only. Large HTML/CSS/JS payloads live in `web_assets.py`.
- `gateway.py`: gateway orchestration only. Persistence lives in `gateway_stores.py`; browser event fan-out lives in `gateway_events.py`.
- `node.py`: node lifecycle, protocol and dispatch. Local access-request UI lives in `node_approval.py`.
- `settings_ui.py`: settings window composition. Shared constants and presets live in `settings_constants.py`. New settings pages should be added as separate modules instead of growing this file.
- `tray.py`: tray orchestration. New Windows integration helpers should be added in dedicated modules rather than embedded into the tray class.

## Change rule

A feature change should touch only its owning module plus tests. Cross-boundary changes must be explicit and covered by regression tests. Do not move authentication, authorization, device identity, credential persistence, reconnect policy, UI rendering and installer behavior into the same module.

## Non-regression areas

The following behavior is treated as protected: Node ID persistence; device credential persistence; local permission authority; allowed-folder enforcement; account-to-node authorization; OAuth/API contracts; WebSocket protocol; tray/node lifecycle; installer configuration preservation; dashboard node/AI metadata editing.
