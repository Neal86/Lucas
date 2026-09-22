# Lucas Project Rules

These rules are mandatory for all development, fixes, refactors, deployments, and AI-assisted changes in this repository.

## 1. Change plan before editing — MUST

Before modifying code, configuration, schemas, infrastructure, or deployment behavior, provide a concise change plan to the user first.

The plan must include:

- What will change and why.
- Existing files that are expected to be modified.
- New files that are expected to be created.
- Whether the change affects APIs, database/schema, permissions/security, deployment, or persistent data.
- Existing functionality that could be affected.
- How the change will be verified.

Do not begin editing first and explain the file changes afterward.

If the user has already explicitly said to execute/continue, the plan may be followed immediately by execution without asking for another routine confirmation. Destructive, system-wide, permission-sensitive, DNS/network, data-loss, or other high-risk changes still require the appropriate explicit confirmation before execution.

If the implementation scope changes while working, update the plan before making additional out-of-scope edits.

## 2. New feature = new module/file by default — MUST

When a new feature can reasonably be isolated, create a new file/module/component/service/route/directory for it instead of adding more unrelated code to an existing file.

Prefer:

- New UI feature -> new component/module and dedicated styles when appropriate.
- New backend feature -> new service/module/route.
- New integration -> its own integration/provider module.
- New security or permission behavior -> isolated policy/service module.
- New background/browser/tool behavior -> isolated tool/router/service module.
- New feature-specific tests -> dedicated test file.

Existing large files should increasingly become composition/orchestration entry points, not dumping grounds for new behavior.

Only add substantial new logic to an existing file when the behavior is genuinely inseparable from that file's responsibility.

## 3. Avoid code pollution — MUST

- Do not mix unrelated features in the same file for convenience.
- Do not introduce unrelated global state.
- Do not duplicate business rules, UI rules, CSS rules, translations, or permission rules across multiple sources.
- One behavior should have one authoritative source whenever practical.
- Shared logic belongs in clear shared/common/utils modules only when it is truly shared.
- Do not create a generic shared helper prematurely for logic used by only one feature.

### Public landing visual source of truth — MUST

- Public Landing branding constants belong in `web_landing_brand.py`.
- Landing header markup belongs in `web_landing_header.py`; Landing header/menu CSS belongs in `web_landing_header_styles.py`.
- `server.py` must never patch `.landing-*` CSS, Landing logo markup, Landing menu colors, or Landing layout at runtime.
- Shared Landing logo artwork must be referenced through the Landing brand constant, not duplicated as hard-coded asset URLs across modules.
- Any intentional Landing logo or navigation visual change must update the dedicated Landing brand regression contract in the same change.

## 4. Refactor large files instead of stacking patches

When a file has accumulated multiple unrelated responsibilities, prefer extracting modules before adding another large patch.

For UI code, separate at least where useful:

- markup/components
- styles
- behavior/runtime
- translations/i18n
- data/API access

For backend code, separate at least where useful:

- routes/controllers
- services/domain logic
- persistence/data access
- integrations/providers
- policy/security
- shared utilities

A bug fix must not knowingly make an oversized mixed-responsibility file worse when a safe extraction is practical.

## 5. Preserve existing behavior

Before changing an existing feature:

- Identify the current behavior that must remain.
- Check nearby functionality that could regress.
- Prefer targeted changes over broad rewrites unless a refactor is explicitly part of the plan.
- Do not replace whole production files from another branch when a precise patch can preserve unrelated production changes.

## 6. Tests and regression protection — MUST

Every meaningful new feature or bug fix should include suitable unit, integration, contract, or regression tests when practical.

For a regression:

- Add a test that would have caught the bug.
- Verify the fix against the real affected path, not only syntax/compile checks.
- Do not call a deployment successful until the relevant runtime behavior is verified.

For UI changes, protect important contracts such as visibility, routing, responsive behavior, localization, and single-source styling when those were involved in the bug.

## 7. Real data over mock data

Production-facing functionality must use real data sources and real state unless mock/demo data is explicitly requested.

Do not silently ship placeholder or mock values as if they were real application state.

## 8. Documentation and PRD stay synchronized

When a feature changes product behavior, architecture, permissions, setup flow, billing behavior, or user-visible workflow:

- Update the relevant documentation and/or PRD in the same change.
- Keep implementation and documented behavior aligned.

## 9. Deployment discipline

- Validate the target branch/application before deployment.
- Prefer staging verification before production for meaningful changes.
- Before every Production web release, run `scripts/smoke_web_pages.py <staging-base-url>` against the deployed Staging build.
- Every route in `web_smoke_routes.py` must pass. Any 5xx, failed required status, or unreachable route blocks Production deployment.
- After Production deployment, run the same smoke gate against Production and treat any failure as a release incident requiring immediate repair or rollback.
- Verify the actual deployed commit/container, not merely that a deploy command was accepted.
- Verify the real runtime endpoint/behavior after deployment.
- Do not treat queued, timed-out, or in-progress deployment calls as success.
- Do not change DNS, host-wide Docker/network settings, persistent mounts, or other shared infrastructure to fix an app-local problem unless the broader impact has been evaluated and explicitly approved.

## 10. Security and destructive operations

Security decisions must remain explicit and locally enforceable where Lucas is designed to enforce them.

Before destructive or broad-impact operations, identify the scope and obtain the required explicit confirmation.

Examples include:

- deleting large amounts of data/files
- destructive database/schema operations
- system registry/service changes
- installing/uninstalling software
- changing account or OS-level permissions
- formatting/storage operations
- host-wide network/DNS/Docker changes
- production security-policy changes

## 11. Commit quality

Use clear commit messages with conventional prefixes where appropriate:

- `feat:`
- `fix:`
- `refactor:`
- `docs:`
- `test:`
- `chore:`

Keep unrelated changes out of the same commit whenever practical.

## 12. Rule precedence for future work

For every future code change in Lucas:

1. Read this file before editing.
2. Present the change plan and file list.
3. Prefer new isolated files for new features.
4. Make the smallest coherent change.
5. Add regression protection.
6. Verify before deployment.
7. Verify again after deployment.

If a requested implementation conflicts with these rules, call out the conflict in the change plan before editing.
