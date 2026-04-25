# Stage 1 Diagnostics

## Scope

This file records the current factual state of the project before any cleanup or refactor.

Constraints followed during this stage:

- No mass rewrites or deletions.
- `data/db.json` was not deleted.
- `.env` was not deleted.
- The goal was to identify the real runtime, compare it with tests and docs, and capture the results of the required checks.

## Required commands and results

### 1. Compile check

Command executed:

```powershell
& 'C:\Users\weew1\AppData\Local\Programs\Python\Python313\python.exe' -m compileall .
```

Result:

- Passed.
- Python sources in the current tree compile successfully.

### 2. Unit tests

Requested official command:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Observed in the current Codex shell:

- `python` is not available in `PATH` in this shell session, so the command does not start here as written.

Equivalent command executed with explicit interpreter path:

```powershell
& 'C:\Users\weew1\AppData\Local\Programs\Python\Python313\python.exe' -m unittest discover -s tests -p "test_*.py" -v
```

Result:

- Failed at test import stage.
- Root cause:

```text
ModuleNotFoundError: No module named 'app_py'
```

- Failing file: `tests/test_python_bot.py`
- The current tests target a legacy module that is no longer present in the workspace.

## Real runtime and entrypoint

The actual launch path is Python, not Node.

Current real entrypoint:

- `main.py`

Current active runtime object:

- `bot/app.py`
- class `SubscriptionBotApp`

Evidence:

- `main.py` imports `SubscriptionBotApp` from `bot.app`
- `main.py` loads config, validates it, creates the JSON store, then starts the bot

## Active files used by the current Python runtime

These files participate in the actual runtime started by `main.py`:

- `main.py`
- `config.py`
- `store_py.py`
- `telegram_client.py`
- `utils_py.py`
- `bot/app.py`
- `bot/fsm.py`
- `bot/ui.py`
- `bot/handlers/user.py`
- `bot/handlers/admin.py`

## Legacy and duplicate artifacts currently present

### Legacy Node stack still in the repository

These files remain present even though the active runtime is Python:

- `index.js`
- `app.js`
- `admin-server.js`
- `package.json`
- `src/`

Important mismatch:

- `package.json` still declares:
  - `"main": "index.js"`
  - `"start": "node index.js"`
  - `"check": "node -e \"require('./index.js'); console.log('syntax ok')\""`

This does not match the current Python runtime.

### Legacy Python artifacts still present

- `admin_server_py.py` is still present in the tree.
- `app_py.py` is not present anymore as a source file.
- `__pycache__/app_py.cpython-313.pyc` still exists.
- `__pycache__/admin_server_py.cpython-313.pyc` still exists.

This indicates an incomplete migration from earlier Python modules to the current `bot/` package layout.

## Functional routing map

### User entry and menu

- `/start` is handled in `bot/handlers/user.py`
- `bot/app.py` routes message commands to `UserHandler.handle_command`
- Main user panel rendering is done through:
  - `bot/app.py` -> `send_main_menu`
  - `bot/app.py` -> `render_panel`
  - `bot/ui.py` for markup generation

### Payment flow

- Invoice creation:
  - `bot/app.py` -> `send_invoice`
- Successful Telegram payment handling:
  - `bot/app.py` -> `handle_successful_payment`
- Subscription activation and persistence:
  - `store_py.py` -> `activate_subscription_from_payment`

### Invite link issuance

- Invite link creation/bootstrap:
  - `bot/app.py` -> `ensure_invite_link`
- Invite link delivery to the user:
  - `bot/app.py` -> `send_join_link`
- Stored fallback/effective invite link resolution:
  - `store_py.py` -> `get_effective_invite_link`

### Join request approval

- Telegram update polling includes `chat_join_request`
- Join request handler:
  - `bot/app.py` -> `handle_chat_join_request`
- Approval call:
  - `telegram_client.py` -> `approve_chat_join_request`

### Expiration and cleanup

- Background maintenance loop:
  - `bot/app.py` -> `run_maintenance_loop`
- Subscription checks, warnings, revocations:
  - `bot/app.py` -> `run_subscription_maintenance`
- Channel removal calls:
  - `telegram_client.py` -> `ban_chat_member`
  - `telegram_client.py` -> `unban_chat_member`

### Admin panel inside Telegram

- Admin command routing:
  - `bot/app.py` -> `handle_admin_command`
- Admin callback routing:
  - `bot/handlers/admin.py` -> `handle_callback`
- Admin FSM text input:
  - `bot/handlers/admin.py` -> `handle_text`
- Admin keyboard generation:
  - `bot/ui.py`

### Storage

- Persistent data store:
  - `store_py.py`
- Data includes:
  - settings
  - users
  - payments
  - audit log
  - bot metadata

## Callback and handler alignment

### User callback data generated in the active UI

Generated in `bot/ui.py`:

- `buy`
- `join`
- `user:help`
- `buy_balance`
- `panel:main`
- `admin:menu`

Handled in active runtime:

- `bot/handlers/user.py` handles:
  - `buy`
  - `join`
  - `user:help`
  - `buy_balance`
  - `panel:main`
- `bot/app.py` routes `admin:*` callbacks to the admin handler

### Admin callback data generated in the active UI

Generated in `bot/ui.py`:

- `admin:users:0`
- `admin:stats`
- `admin:settings`
- `admin:broadcast:menu`
- `admin:refresh_invite`
- `admin:input:price`
- `admin:input:days`
- `admin:input:warning`
- `admin:toggle:recurring`
- `admin:toggle:autoinvite`
- `admin:input:channel`
- `admin:input:support`
- `admin:templates:menu`
- `admin:filter:all`
- `admin:filter:active`
- `admin:filter:expired`
- `admin:user:{id}`
- `admin:users:{page}`
- `admin:input:search_user`
- `admin:input:grant:{id}`
- `admin:input:balance:{id}`
- `admin:approve:{id}`
- `admin:revoke:{id}`
- `admin:input:note:{id}`
- `admin:input:msg:{id}`
- `admin:templates:edit:{key}`
- `admin:input:broadcast:all`
- `admin:input:broadcast:active`
- `admin:input:broadcast:expired`

Handled in active runtime:

- `bot/handlers/admin.py` handles the above callback families through:
  - exact matches
  - `startswith(...)` branches
  - FSM text states for follow-up input

Conclusion:

- The active callback-driven admin UI is mostly aligned with the current `bot/` implementation.
- The larger mismatch is not callback routing. The larger mismatch is between documented slash commands and the active command router.

## README vs actual code mismatches

# Stage 14 Diagnostics

## Scope

Goal of this stage: add an admin-only workflow for diagnosing suspicious payment cases and manually restoring access without any automatic speculative recovery.

## Current admin surface relevant to payment recovery

- `/admin` opens the Telegram admin panel
- `/admin_user` is still not a direct slash-command in the current runtime
- direct admin grant/revoke actions exist mainly through inline admin flows and storage methods
- audit log helpers already exist in `store_py.py` and are used for admin-side actions
- the safest recovery UX is a read-only diagnostics command plus an explicit admin recovery command

## Stage 14 runtime additions

### Direct admin commands

- `/admin_payment_diag USER_ID`
  - admin-only
  - read-only diagnostics for a target user
  - does not modify state
- `/admin_recover_payment USER_ID DAYS REASON`
  - admin-only
  - explicit manual access recovery
  - writes audit type `manual_payment_recovery`
  - does not create fake payment records
  - does not change payment totals

### Diagnostics helper

Added read-only helper in `store_py.py`:

- `get_user_payment_diagnostics(user_id)`

It reports:

- `userId`
- `totalPaymentsCount`
- `totalSpentStars`
- `subscriptionUntil`
- `subscriptionActive`
- `lastPaymentAt`
- recent payment records
- suspicious indicators:
  - payment records exist but subscription is not active
  - totals mismatch against recorded payments
  - duplicate charge ids
  - missing charge ids
  - legacy-like payment records without expected fields

### Manual recovery helper

Added explicit admin recovery helper in `store_py.py`:

- `manual_payment_recovery(admin_id, user_id, days, reason)`

Current policy:

- access recovery is always manual
- no speculative auto-recovery for legacy/partial payment records
- recovery updates only subscription/access fields
- recovery writes audit with admin id, user id, days, reason, timestamp
- recovery does not alter `totalPaymentsCount` or `totalSpentStars`
- recovery does not synthesize a Telegram charge id

# Stage 15 Diagnostics

## Scope

Goal of this stage: add an admin-only, read-only обзор suspicious payment/users cases so anomalies can be reviewed as a list instead of only by one `USER_ID`.

## Read-only helper

Added in `store_py.py`:

- `list_payment_anomalies(limit=20)`

Current behavior:

- iterates through users
- reuses per-user payment diagnostics
- returns only users with warnings
- does not modify state
- does not write audit
- does not trigger any recovery action

Returned anomaly items include:

- `userId`
- `username`
- `displayName`
- `warnings`
- `totalPaymentsCount`
- `totalSpentStars`
- `subscriptionActive`
- `subscriptionUntil`
- `lastPaymentAt`

## Sorting policy

Sorting is deterministic and read-only:

- first by anomaly severity
  - duplicate charge ids
  - payment records exist but no active subscription
  - totals mismatch
  - missing charge ids
  - legacy incomplete payment records
- then by `lastPaymentAt` descending
- then by `userId`

## Admin access surface

Added:

- direct command `/admin_payment_anomalies [limit]`
- admin-only callback `admin:payment_anomalies`

Both paths:

- are read-only
- show suspicious users with warning summary
- point to `/admin_payment_diag USER_ID`
- do not recover anything automatically

## Policy confirmation

- automatic speculative recovery is still disabled
- manual recovery remains explicit through `/admin_recover_payment USER_ID DAYS REASON`
- manual recovery still does not create fake payments and does not change payment totals

# Stage 16 Diagnostics

## Scope

Goal of this stage: extract payment orchestration from `bot/app.py` into a dedicated service module without changing payloads, runtime behavior, duplicate policy, or recovery/anomaly policy.

## Payment flow before extraction

`bot/app.py` previously contained:

- invoice parameter building in `send_invoice`
- pre-checkout payload validation in `handle_pre_checkout_query`
- successful payment orchestration in `handle_successful_payment`
- atomic store call to `record_payment_and_activate_subscription(...)`
- duplicate payment early-return behavior
- pending join approval after processed payment

## Payment flow after extraction

Created:

- `bot/services/__init__.py`
- `bot/services/payment_service.py`

Exported functions:

- `build_payment_payload`
- `parse_payment_payload`
- `handle_buy_access`
- `handle_pre_checkout`
- `handle_successful_payment`

Current policy remains unchanged:

- payload stays `subscription:{user_id}`
- pre-checkout rejects invalid payload safely
- successful payment still uses `record_payment_and_activate_subscription(...)`
- duplicate payments do not send a second success confirmation
- pending join approval is still attempted only after a processed payment
- recovery/anomaly policy is unchanged

## bot/app.py compatibility

`bot/app.py` keeps public methods:

- `send_invoice`
- `handle_pre_checkout_query`
- `handle_successful_payment`

These are now thin wrappers that delegate into `bot/services/payment_service.py`.

# Stage 17 Diagnostics

## Scope

Goal of this stage: extract invite/join/access orchestration from `bot/app.py` into a dedicated service module without changing invite priority, join approval behavior, revoke behavior, payment flow, or recovery/anomaly policy.

## Access flow before extraction

`bot/app.py` previously contained:

- invite resolution/creation in `ensure_invite_link` and `refresh_invite_link`
- join request handling in `handle_chat_join_request`
- pending approval in `approve_pending_request`
- revoke orchestration in `revoke_user_subscription`
- user join-link rendering in `send_join_link`
- stale pending decline branch inside `_process_maintenance_user`

## Access flow after extraction

Created:

- `bot/services/access_service.py`

Exported functions:

- `get_join_link`
- `ensure_invite_link`
- `refresh_invite_link`
- `handle_chat_join_request`
- `approve_pending_request`
- `decline_pending_join_request`
- `prune_expired_pending_join_requests`
- `revoke_user_subscription`
- `send_join_link`

Current policy remains unchanged:

- manual `channelInviteLink` still has priority
- auto invite creation still uses join-request invite links
- join requests still persist `pendingJoinRequest`
- active subscribers are still auto-approved
- inactive subscribers still get the same notice path
- stale pending join requests are still declined from maintenance
- revoke still uses `ban_chat_member` + `unban_chat_member`
- payment payload, payment flow, recovery policy, and anomalies review are unchanged

## bot/app.py compatibility

`bot/app.py` keeps public methods:

- `handle_chat_join_request`
- `approve_pending_request`
- `ensure_invite_link`
- `refresh_invite_link`
- `revoke_user_subscription`
- `send_join_link`

These now delegate into `bot/services/access_service.py`.

### Admin commands documented in README but not implemented as direct slash commands in the active runtime

Documented in `README.md`:

- `/admin_user ID`
- `/admin_create_user ID`
- `/admin_grant ID [days]`
- `/admin_revoke ID`
- `/admin_balance ID amount`
- `/admin_approve ID`
- `/admin_message ID text`
- `/admin_note ID text`
- `/admin_set key value`
- `/admin_setup_channel @my_private_channel`

Declared in `bot/app.py` inside `ADMIN_COMMANDS`, but not implemented in `handle_admin_command`:

- `/admin_set`
- `/admin_user`
- `/admin_create_user`
- `/admin_grant`
- `/admin_revoke`
- `/admin_balance`
- `/admin_approve`
- `/admin_message`
- `/admin_note`
- `/admin_setup_channel`

Implemented as direct slash commands in `handle_admin_command`:

- `/admin_login`
- `/admin_logout`
- `/admin`
- `/admin_stats`
- `/admin_settings`
- `/admin_users`
- `/admin_help`
- `/admin_refresh_invite`
- `/admin_broadcast`

Conclusion:

- README currently overstates the available slash-command surface.
- The real admin workflow is now mainly callback/FSM-driven inside Telegram.

### Package metadata mismatch

README and recent project direction indicate Python runtime, but `package.json` still points to the old Node entrypoint.

## Test suite mismatch

Current test file:

- `tests/test_python_bot.py`

Problem:

- Imports `SubscriptionBotApp` from `app_py`
- `app_py.py` no longer exists in the repository
- The active runtime class now lives in `bot/app.py`

Conclusion:

- The current automated tests are stale and do not cover the actual runtime.
- Any green test result from the old target would not validate the current bot.

## Additional technical risks observed

### 1. Corrupted or inconsistent user-facing text

Some strings in the active `bot/` runtime appear garbled in terminal reads. This suggests encoding damage or mixed file encoding in at least part of the current user/admin message layer.

Risk:

- Telegram users may receive broken Russian text.

### 2. Leftover runtime/view-model code in `bot/app.py`

`bot/app.py` includes logic that appears unrelated to the current callback-only Telegram runtime, including admin view-model/editor style helpers from older iterations.

Risk:

- The file is harder to reason about.
- Dead or semi-dead logic can mislead future fixes.

### 3. Repository hygiene

Current `.gitignore` does not ignore common Python artifacts such as:

- `__pycache__/`
- `*.pyc`
- test caches

Risk:

- stale compiled files can mask source removal
- repository noise increases
- diagnostics become harder because old bytecode survives after source deletion

### 4. Official command portability not yet established

Target command from the staged plan:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Observed in this Codex shell:

- `python` is not available as a command alias here

Risk:

- The documented official command may not work consistently across environments until interpreter assumptions are made explicit.

## Stage 1 conclusion

Current project state is a partially migrated codebase:

- real runtime is Python
- active implementation is `main.py` + `bot/`
- tests still target removed legacy module `app_py`
- docs still describe a broader slash-command interface than the runtime actually exposes
- legacy Node and older Python artifacts remain in the tree

This means the project should not be cleaned up blindly. The next stage should be a controlled alignment pass:

1. choose the single supported runtime layout
2. align tests to the real runtime
3. align README to the real command/UI model
4. only then remove dead files and stale artifacts

## Stage 2 Stabilization Results

### Tests

`tests/test_python_bot.py` was rewritten to target the current runtime instead of the removed legacy module.

Current smoke coverage includes:

- `import main`
- `import bot.app`
- current entrypoint wiring inside `main.main()`
- config creation and validation with test env variables
- absence of legacy `app_py` imports in `tests/`
- syntax compile smoke for the active Python runtime files

### Package metadata

`package.json` no longer points to `index.js` as the effective runtime.

Current status:

- marked as legacy npm metadata
- clearly states that the primary runtime is Python via `main.py`
- `npm start` and `npm run check` now fail fast with an informational message instead of starting the old Node bot

### README alignment

`README.md` was aligned to the current codebase state.

Updated points:

- official launch is `python main.py`
- official checks are `python -m compileall .` and `python -m unittest discover -s tests -p "test_*.py" -v`
- only actually implemented slash commands remain in the supported command list
- previously documented but currently unsupported direct slash commands were moved into a non-implemented section
- the inline admin workflow is described as the primary admin interface

### Safe cleanup performed

Removed during stabilization:

- `__pycache__/`
- `*.pyc`
- `.pytest_cache/` if present

Note:

- final `compileall` recreated fresh `__pycache__` and `*.pyc` artifacts, which is expected

### Legacy files intentionally left in place

Still intentionally kept for later cleanup:

- `index.js`
- `app.js`
- `admin-server.js`
- `src/`
- `admin_server_py.py`

### Encoding follow-up candidates

Historical note: these candidates were identified at the end of stage 2 and then addressed in stage 3 text normalization.

- `bot/ui.py` -> fixed in stage 3
- `bot/handlers/user.py` -> fixed in stage 3
- `bot/handlers/admin.py` -> fixed in stage 3

### Verification result for stage 2

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 3 Text Normalization Results

### Files changed

- `bot/ui.py`
- `bot/handlers/user.py`
- `bot/handlers/admin.py`
- `bot/app.py`
- `config.py`
- `store_py.py`
- `tests/test_python_bot.py`
- `data/db.json`

### Strings that were actually damaged

Confirmed mojibake was present in active runtime user/admin texts, including:

- main user menu labels and notices in `bot/ui.py`
- help text in `bot/ui.py`
- admin menu, admin settings, admin user list, template editor and broadcast text in `bot/ui.py`
- payment and balance notices in `bot/handlers/user.py`
- admin callback notices and admin input prompts in `bot/handlers/admin.py`
- direct admin command responses, payment notices, join notices, subscription warning/expiration notices and join-link buttons in `bot/app.py`
- default subscription title/description/welcome text in `config.py`
- default persisted settings and message templates in `store_py.py`
- already saved damaged `settings` and `messageTemplates` values in `data/db.json`

### Safe migration applied to data/db.json

A targeted text-only migration was applied to the live JSON store:

- fixed `settings.subscriptionName`
- fixed `settings.subscriptionDescription`
- fixed `settings.welcomeText`
- fixed `settings.messageTemplates.*`

Intentionally not changed:

- user records
- payment records
- callback data
- storage field names
- schema structure

### Strings intentionally left unchanged

Left unchanged because they are not mojibake fixes for runtime UI text:

- user-provided names from Telegram profiles
- bot metadata fields returned by Telegram
- legacy Node files and other non-runtime files

### Mojibake test

Added a narrow runtime test in `tests/test_python_bot.py`:

- `test_runtime_user_texts_do_not_contain_mojibake_markers`

The test inspects string literals in active runtime Python files only and checks for common mojibake markers:

- `?`
- `N`
- `Рџ`
- `рџ`
- `вќ`
- `вњ`
- `вљ`
- replacement character `?`

### Verification result for stage 3

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

### Remaining follow-up

No mojibake markers remain in the active Python runtime files covered by the new test.

Possible future cleanup still outside this stage:

- normalize legacy files if they will be kept
- decide whether to clean old Node/Python legacy sources
- optionally audit remaining non-runtime text assets for consistency

## Stage 4 Legacy Cleanup Results

### Import map and decisions

Current active Python runtime import chain:

- `main.py` imports `config.py`, `store_py.py`, `bot.app`
- `bot/app.py` imports `telegram_client.py`, `bot/fsm.py`, `bot/ui.py`, `bot/handlers/admin.py`, `bot/handlers/user.py`, `utils_py.py`
- `tests/test_python_bot.py` imports `config.py` and `store_py.py`

Legacy candidates reviewed:

- `index.js`
  - active runtime usage: none
  - references found: legacy docs/history only
  - decision: moved to `legacy/`
- `app.js`
  - active runtime usage: none
  - references found: legacy docs/history only
  - decision: moved to `legacy/`
- `admin-server.js`
  - active runtime usage: none
  - references found: legacy docs/history only
  - decision: moved to `legacy/`
- `store.js`
  - active runtime usage: none
  - references found: legacy docs/history only
  - decision: moved to `legacy/`
- `src/`
  - active runtime usage: none
  - references found: only through moved legacy Node files
  - decision: moved to `legacy/`
- `admin_server_py.py`
  - active runtime usage: none
  - references found: legacy docs/history only
  - decision: moved to `legacy/`
- `store_py.py`
  - active runtime usage: yes
  - references found: `main.py`, `tests/test_python_bot.py`
  - decision: kept in root as active storage module
- `app_py`
  - active runtime usage: none
  - source file status: absent
  - decision: remains absent; protected by tests against reintroduction into runtime/tests

### Files moved to legacy/

Moved during stage 4:

- `legacy/index.js`
- `legacy/app.js`
- `legacy/admin-server.js`
- `legacy/store.js`
- `legacy/admin_server_py.py`
- `legacy/src/`

Documented in:

- `legacy/README_LEGACY.md`

### Files kept in active root

Kept intentionally:

- `main.py` -> official runtime entrypoint
- `bot/` -> active runtime package
- `store_py.py` -> active JSON store used by runtime and tests
- `package.json` -> harmless npm stub that no longer points to legacy Node entrypoints

### Documentation/package updates

- `README.md` now points to `legacy/README_LEGACY.md` instead of describing root Node files as still co-located runtime artifacts
- `package.json` now explicitly describes itself as a legacy npm stub and still does not launch any old Node bot
- `tests/test_python_bot.py` now also checks that README does not point to `app_py`, that `legacy/README_LEGACY.md` exists, and that `package.json` does not launch `index.js`

### Verification result for stage 4

Final verification status before post-check cache cleanup:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 5 Active Runtime Cleanup Results

### What `bot/app.py` looked like before this stage

`bot/app.py` was still the main active runtime file, but it mixed multiple responsibilities in one long module:

- runtime bootstrap and polling
- direct admin command routing
- callback/message dispatch
- UI panel rendering
- payment and join-request handling
- subscription maintenance
- legacy-compatible JSON/editor helpers

The file was working, but broad method bodies and repeated local patterns made it harder to read and safer-than-necessary changes harder to reason about.

### Safe internal cleanup performed

This stage kept the public interface and behavior intact while reducing local duplication and grouping related logic.

Changes made:

- added a runtime map in `RUNTIME_MAP.md`
- added section markers in `bot/app.py` to separate:
  - runtime setup
  - polling/update dispatch
  - incoming message/callback routing
  - admin commands
  - UI rendering helpers
  - payments/access control
  - user/admin side effects
  - subscription maintenance
  - legacy-compatible JSON/editor helpers
- extracted small internal helpers:
  - `_now_ms`
  - `_log_error`
  - `_ensure_user_context`
  - `_handle_admin_login`
  - `_handle_admin_logout`
  - `_dispatch_admin_command`
  - `_resolve_panel_message_id`
  - `_save_panel_message_state`
  - `_build_main_menu_context`
  - `_matches_broadcast_scope`
- replaced repeated inline values with class-level constants:
  - `ALLOWED_UPDATES`
  - `JOIN_REQUEST_TTL_MS`

### Duplicates reduced

Reduced without changing behavior:

- repeated `time.time() * 1000` calls now use `_now_ms()`
- repeated admin direct-command branching now goes through small dedicated helpers
- repeated user bootstrap/ensure logic now goes through `_ensure_user_context()`
- repeated panel message state updates now go through `_resolve_panel_message_id()` and `_save_panel_message_state()`
- repeated main-menu context assembly now goes through `_build_main_menu_context()`
- repeated broadcast-scope checks now go through `_matches_broadcast_scope()`
- repeated top-level Telegram error prints now go through `_log_error()`

### Deliberately not moved yet

Left in place on purpose because moving them now would be a higher-risk refactor:

- legacy-compatible JSON/editor helpers at the bottom of `bot/app.py`
- current handler split between `bot/app.py`, `bot/handlers/admin.py`, `bot/handlers/user.py`
- `store_py.py`
- callback data definitions and menu structure
- all business logic around payments, subscriptions, invite links and maintenance

### Regression tests added/updated

`tests/test_python_bot.py` now also covers:

- `test_bot_app_public_entrypoints_exist`
- `test_callback_data_constants_or_buttons_stable`
- `test_commands_still_documented_consistently`
- `test_legacy_not_imported_by_runtime`

These tests are intentionally narrow and aimed at catching accidental interface drift:

- missing public entrypoints needed by `main.py`
- callback data changes in the active UI
- docs drifting away from supported direct commands
- accidental runtime imports from `legacy/`, `app_py` or `admin_server_py`

### Stage 5 compatibility confirmation

Confirmed unchanged during this stage:

- official entrypoint remains `python main.py`
- callback data was not renamed
- slash commands were not changed
- payment payloads were not changed
- `data/db.json` schema was not changed
- user/admin interaction flow was not changed
- `store_py.py` remains active and used by runtime/tests

### Verification result for stage 5

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 6 Compatibility Helper Extraction Results

### Inventory of the extracted helper block

The lower helper block previously inside `bot/app.py` contained:

- `get_admin_view_model`
- `get_user_editor_view_model`
- `replace_state_from_json`
- `replace_settings_from_json`
- `replace_templates_from_json`
- `save_user_structured`
- `replace_user_json`
- `delete_user`
- `format_stats_text`
- `get_template_context`
- `render_message_template`
- `configure_channel`
- `get_dashboard_stats_extended`

Current usage after inventory:

- active runtime / handlers still use:
  - `get_template_context`
  - `render_message_template`
  - `configure_channel`
  - `get_dashboard_stats_extended`
- compatibility / legacy-facing surface kept for `bot.app`:
  - `get_admin_view_model`
  - `get_user_editor_view_model`
  - `replace_state_from_json`
  - `replace_settings_from_json`
  - `replace_templates_from_json`
  - `save_user_structured`
  - `replace_user_json`
  - `delete_user`
  - `format_stats_text`

### New module introduced

Created:

- `bot/compat_helpers.py`

This module now owns the compatibility/editor/JSON helper implementations and does not import `bot.app`.

### Compatibility preserved in `bot/app.py`

`bot/app.py` now keeps thin wrappers for the same helper methods, so external access through `SubscriptionBotApp` remains available without path changes.

Examples of preserved wrappers:

- `SubscriptionBotApp.get_template_context()`
- `SubscriptionBotApp.configure_channel()`
- `SubscriptionBotApp.get_dashboard_stats_extended()`
- all legacy/editor JSON helpers listed above

### Runtime/documentation updates

Updated during this stage:

- `RUNTIME_MAP.md`
- `tests/test_python_bot.py`

Added regression coverage for:

- direct import of `bot.compat_helpers`
- `bot.app` wrapper/re-export compatibility
- absence of `bot.app` import inside `bot.compat_helpers`
- continued absence of imports from `legacy/` in active runtime

### Stage 6 compatibility confirmation

Confirmed unchanged during this stage:

- official entrypoint remains `python main.py`
- callback data was not renamed
- slash commands were not changed
- payment payloads were not changed
- `data/db.json` schema was not changed
- user/admin interaction flow was not changed
- `store_py.py` remains active and unchanged

### Verification target for stage 6

Required final commands for this stage:

- `python -m compileall .`
- `python -m unittest discover -s tests -p "test_*.py" -v`

### Verification result for stage 6

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 7 compat_helpers Cleanup Results

### What changed internally

`bot/compat_helpers.py` was reorganized without changing its public function names or return shapes.

Added in-file sections:

- Imports
- Internal helpers
- View model helpers
- JSON replacement helpers
- User editor helpers
- Template helpers
- Channel/settings helpers
- Stats helpers

Added private helpers:

- `_now_ms`
- `_parse_json`
- `_format_json`
- `_user_search_haystack`
- `_is_active_subscription`
- `_matches_status_filter`
- `_build_pending_join_request`
- `_render_template_values`
- `_normalize_channel_id`

### Public API preserved

The following public functions remain available in `bot/compat_helpers.py` and via wrappers in `bot/app.py`:

- `get_admin_view_model`
- `get_user_editor_view_model`
- `replace_state_from_json`
- `replace_settings_from_json`
- `replace_templates_from_json`
- `save_user_structured`
- `replace_user_json`
- `delete_user`
- `format_stats_text`
- `get_template_context`
- `render_message_template`
- `configure_channel`
- `get_dashboard_stats_extended`

### Tests added

New focused test file:

- `tests/test_compat_helpers.py`

Covered checks:

- public compat helper API exists
- `bot.app` still reexports compat wrappers
- invalid JSON is rejected without touching the mocked store
- unknown template placeholders remain unchanged
- `configure_channel` works with a fake app and does not require real Telegram access

### Verification result for stage 7

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 8 Runtime Resilience Results

### try/except inventory found in `bot/app.py`

Current protected areas in the active runtime:

- invite bootstrap in `start()`
- per-poll outer loop in `poll_loop()`
- per-update handling in `_process_polled_update()`
- panel edit fallback in `render_panel()`
- join request approval in `approve_pending_request()`
- channel revoke calls in `revoke_user_subscription()`
- admin direct message send in `send_admin_message()`
- broadcast send loop in `broadcast_users()`
- generic user notification send in `notify_user()`
- outer maintenance loop in `run_maintenance_loop()`
- per-user maintenance iteration in `run_subscription_maintenance()`
- pending join request decline in `_process_maintenance_user()`

### Error handling changes

Adjusted without changing business logic:

- added per-update resilience through `_process_polled_update()` so one bad update no longer blocks later updates in the same poll batch
- `lastUpdateId` is now advanced per update in a `finally` path, preventing a permanently failing update from replaying forever
- added per-user resilience in subscription maintenance so one broken user record or side-effect no longer aborts maintenance for all users
- replaced silent `except` branches with `_log_error()` in:
  - `render_panel()` edit fallback
  - `revoke_user_subscription()`
  - `send_admin_message()`
  - `broadcast_users()`
  - `notify_user()`
  - pending join request decline path

### Fake Telegram test infrastructure

Added:

- `tests/fakes.py`

`FakeTelegramClient` records calls for:

- `send_message`
- `edit_message_text`
- `answer_callback_query`
- `answer_pre_checkout_query`
- `send_invoice`
- `create_chat_invite_link`
- `approve_chat_join_request`
- `decline_chat_join_request`
- `ban_chat_member`
- `unban_chat_member`
- `get_me`
- `delete_webhook`
- `get_updates`

No test in this stage performs real network calls.

### Isolated store strategy

Scenario tests use:

- `tempfile.TemporaryDirectory()`
- temporary `db.json` path per test case
- `create_store()` against that temporary path
- fake/test-safe `Config`

The real `data/db.json` is not used by these tests.

### Scenario tests added

Added:

- `tests/test_runtime_fake_telegram.py`

Covered scenarios:

- `/start` renders the main menu without network
- `/buy` sends an invoice with the expected payload/price
- `successful_payment` records payment and activates subscription
- duplicate successful payment does not create a second payment record
- active subscriber join request gets approved
- expired subscription revoke continues when one channel API call fails
- authorized admin can open the admin panel
- unauthorized user is denied admin access
- polling continues from a bad update to a good update in the same batch

### Coverage limits

Not directly covered in this stage:

- the infinite threaded `start()` runtime loop end-to-end, because tests intentionally avoid starting long-running threads/polling indefinitely
- real Telegram HTTP behaviour, by design
- multi-iteration retry behaviour in `telegram_client.py`, because stage scope was fake-client runtime coverage, not HTTP transport testing

### Verification result for stage 8

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 9 Telegram Transport Stabilization Results

### Methods found in `telegram_client.py`

Public client methods:

- `call`
- `get_me`
- `delete_webhook`
- `get_updates`
- `delete_message`
- `send_message`
- `edit_message_text`
- `answer_callback_query`
- `answer_pre_checkout_query`
- `send_invoice`
- `create_chat_invite_link`
- `approve_chat_join_request`
- `decline_chat_join_request`
- `ban_chat_member`
- `unban_chat_member`

All current Bot API calls still use POST with JSON payloads.

### Transport/error handling changes

Transport logic is now centralized through:

- `_build_url`
- `_build_request`
- `_read_response_body`
- `_parse_json_body`
- `_parse_ok_response`
- `_parse_http_error`
- `_is_terminal_error`
- `_request`

Current behavior:

- `ok: true` -> return `result`
- `ok: false` -> raise `RuntimeError` with a Telegram API error message
- HTTP error with JSON body -> raise `RuntimeError` with parsed Telegram description
- invalid JSON/encoding -> raise predictable `RuntimeError`
- network failures -> retry with the existing simple backoff, then raise predictable `RuntimeError`

### `message is not modified`

`edit_message_text()` now handles `message is not modified` as a safe non-fatal case and returns `None` instead of raising.

This keeps current `bot/app.py` behavior safe and avoids treating a no-op edit as a runtime failure.

### Fake HTTP transport tests

Added:

- `tests/test_telegram_client.py`

Fake transport strategy:

- inject a callable `transport` into `TelegramClient`
- fake transport records URL, HTTP method, payload and timeout
- fake responses can return:
  - `ok:true` JSON
  - `ok:false` HTTPError JSON
  - invalid JSON bytes
  - network exceptions

No test in this stage touches the real network.

### Payload validation covered by tests

Checked through transport tests:

- `send_message` payload fields
- `edit_message_text` request path and safe not-modified handling
- `send_invoice` Stars payload (`currency = XTR`, `prices`, `payload`)
- join request approve/decline payloads
- ban/unban payloads
- `get_updates` payload fields (`offset`, `timeout`, `allowed_updates`)

No runtime payment payload contract was changed.

### Verification result for stage 9

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 10 Store Stabilization Results

### Public methods and functions found in `store_py.py`

Module-level functions:

- `create_default_state`
- `merge_settings`
- `merge_state`
- `create_store`

`JsonStore` public methods:

- `get_state`
- `replace_state`
- `get_meta`
- `get_settings`
- `update_settings`
- `replace_settings`
- `add_audit_log`
- `get_audit_log`
- `ensure_user`
- `get_user`
- `list_users`
- `replace_user`
- `update_user_fields`
- `delete_user`
- `get_payments`
- `has_payment`
- `record_payment`
- `set_user_pending_join_request`
- `clear_user_pending_join_request`
- `set_user_channel_member_status`
- `set_user_notes`
- `set_bot_info`
- `set_last_update_id`
- `set_join_invite_link`
- `get_effective_invite_link`
- `is_subscription_active`
- `activate_subscription_from_payment`
- `grant_subscription_days`
- `revoke_subscription`
- `adjust_balance`
- `purchase_with_balance`
- `mark_warning_sent`
- `mark_access_revoked`
- `get_dashboard_stats`

### Persistence/error-handling changes

Stage 10 kept the public API intact and made only targeted persistence-layer fixes:

- `_load()` now raises predictable `RuntimeError` values for invalid JSON, unreadable files and invalid non-object JSON root values
- `_ensure_file()` and `_save_unlocked()` now use a shared JSON writer that flushes and fsyncs writes before replace
- `_save_unlocked()` now cleans up `*.tmp` on failure instead of leaving temp files behind
- `record_payment()` is now idempotent by `telegramPaymentChargeId` and no longer double-counts payment totals when the same charge is recorded twice

### Atomic save status

Atomic save is now present in the active store path.

Current write flow:

1. serialize JSON into `db.json.tmp`
2. flush and `os.fsync()` the temporary file
3. replace the target with `os.replace(tmp, db.json)`
4. clean up the temp file if replace fails

This protects the on-disk `db.json` from partial overwrite during a failed save.

### Storage tests added

Added new file:

- `tests/test_store_py.py`

Covered scenarios:

- missing db initialization
- corrupt db error path
- partial top-level state merge without dropping existing data
- settings persistence
- message template persistence
- idempotent `ensure_user`
- user field persistence
- idempotent payment recording
- subscription extension from active expiration
- subscription activation from expired state
- balance adjustment floor at zero
- pending join request lifecycle
- channel member status persistence
- dashboard stats counting
- audit log persistence and order
- atomic save failure leaving the existing on-disk db valid

All store tests use `tempfile.TemporaryDirectory()` and an explicit temporary `db.json` path.

### Problems found during stage 10

Confirmed and fixed:

- duplicate `record_payment()` calls previously re-applied totals for the same charge id
- invalid/corrupt JSON did not previously produce a clear store-specific runtime error

Known residual edge case intentionally left unchanged in this stage:

- if a save fails after in-memory mutation but before `os.replace()` succeeds, the in-memory store instance may be ahead of disk until the process reloads the store; on-disk data remains intact and this is now covered by tests

### Production data safety

`data/db.json` was not used by the new storage tests and was not modified during stage 10.

### Verification result for stage 10

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 11 In-Memory Rollback Results

### Mutating methods identified in `store_py.py`

Methods that mutate `self.state` and then save:

- `replace_state`
- `update_settings`
- `replace_settings`
- `add_audit_log`
- `ensure_user`
- `replace_user`
- `update_user_fields`
- `delete_user`
- `record_payment`
- `set_user_pending_join_request`
- `set_user_channel_member_status`
- `set_user_notes`
- `set_bot_info`
- `set_last_update_id`
- `set_join_invite_link`
- `activate_subscription_from_payment`
- `grant_subscription_days`
- `revoke_subscription`
- `adjust_balance`
- `purchase_with_balance`
- `mark_warning_sent`
- `mark_access_revoked`

Indirect mutating wrapper:

- `clear_user_pending_join_request` -> delegates to `set_user_pending_join_request`

### Rollback helper

Added private helper:

- `_mutate_and_save(mutator)`

Behavior:

1. deep-copy current `self.state`
2. apply the mutator
3. call `_save_unlocked()`
4. if save fails, restore `self.state` from the backup and re-raise the original exception

This keeps the in-memory store aligned with the on-disk file after failed save operations.

### Methods moved to rollback path

All mutating methods listed above now use `_mutate_and_save()` directly, except `clear_user_pending_join_request`, which stays a thin delegating wrapper.

### Rollback tests added

Added targeted rollback tests in `tests/test_store_py.py`:

- `test_failed_save_rolls_back_update_settings_in_memory`
- `test_failed_save_rolls_back_user_update_in_memory`
- `test_failed_save_rolls_back_record_payment_in_memory`
- `test_failed_save_rolls_back_audit_log_in_memory`
- `test_failed_save_keeps_disk_file_valid`

### Stage 11 verification result

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 12 Compound Store Atomicity Results

### Compound operations found in `store_py.py`

Reviewed compound paths:

- user mutation followed by separate audit save:
  - `replace_user`
  - `update_user_fields`
  - `delete_user`
  - `set_user_notes`
  - `grant_subscription_days`
  - `revoke_subscription`
  - `adjust_balance`
- chained mutating call:
  - `purchase_with_balance` previously did one save for balance debit and then a second save through `grant_subscription_days`
- already single-save and left unchanged:
  - `record_payment`
  - `activate_subscription_from_payment`
  - `clear_user_pending_join_request` via `set_user_pending_join_request`

### Stage 12 changes

Targeted changes applied:

- added internal helper usage `_append_audit_entry(state, entry)` so audit writes can participate in the same transaction as the main mutation
- moved audit creation for the user/admin mutation methods above into the same `_mutate_and_save()` call
- rewrote `purchase_with_balance` so balance debit, subscription extension, warning reset, access-grant timestamp and `grant_subscription` audit entry happen in one transaction and one save

### Partial-write risks closed

Closed inside `store_py.py`:

- user changed but audit missing after second save failure
- balance debited but subscription not granted in `purchase_with_balance`
- subscription granted by follow-up method after earlier balance change had already been saved
- in-memory and on-disk partial divergence for the compound methods above after failed save

### Remaining risks

No remaining multi-save compound operation was left inside `store_py.py`.

The payment-record + subscription-activation sequence in runtime flow remains orchestrated above the store layer and was not changed in this stage because it belongs to runtime behavior, not store internals.

### Stage 12 tests added

Added/updated tests in `tests/test_store_py.py`:

- `test_purchase_with_balance_is_single_transaction`
- `test_purchase_with_balance_can_repeat_when_balance_is_sufficient`
- `test_purchase_with_balance_rolls_back_all_changes_on_failed_save`
- `test_purchase_with_balance_insufficient_balance_no_partial_change`
- `test_activate_subscription_from_payment_single_transaction`
- `test_grant_subscription_days_rolls_back_on_failed_save`
- `test_revoke_subscription_rolls_back_on_failed_save`

### Stage 12 verification result

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## Stage 13 Payment Orchestration Results

### Where payment orchestration was

Runtime successful payment handling lives in `bot/app.py` inside `handle_successful_payment(message)`.

Before this stage, the flow was:

1. `store.has_payment(charge_id)`
2. `store.record_payment(payment)`
3. `store.activate_subscription_from_payment(user_id, payment, settings)`
4. `approve_pending_request(user_id)`
5. `send_main_menu(user_id, notice=...)`

Risk in that old sequence:

- payment could be persisted before subscription activation
- duplicate charge id would then block a second `record_payment()` call
- old partial state could leave a payment recorded without a completed activation

### Strategy chosen

Chosen strategy: add a new store-level atomic method and move runtime successful-payment orchestration onto it.

New store method:

- `record_payment_and_activate_subscription(user_id, payment, settings)`

The method performs, inside one `_mutate_and_save()` transaction:

- duplicate check by `telegramPaymentChargeId`
- payment insert
- totals update
- `lastPaymentAt` update
- subscription activation/extension
- `lastWarningAt` reset
- `lastAccessGrantedAt` update

### Schema policy

No schema change was added in stage 13.

Reason:

- new partial failures are removed by the atomic store method
- for historical duplicates without an activation marker, the safer policy is strict duplicate idempotency, not speculative re-activation

### Duplicate payment policy

Current duplicate policy:

- existing `telegramPaymentChargeId` => return `status = duplicate`
- totals do not increase again
- subscription is not extended again
- runtime does not send a second success acknowledgement

Legacy duplicate policy:

- if an old payment record already exists, it is treated as processed
- runtime does not try to reconstruct unknown historical partial state automatically
- this avoids accidental double extension for already-completed historical payments

### Partial payment risk closed

Closed for current runtime flow:

- `successful_payment` can no longer save a payment and then fail before subscription activation because both now happen in one store transaction
- failed save rolls back payment, totals and subscription changes together
- duplicate Telegram payment updates do not extend subscription twice

### Tests added/updated

Store tests in `tests/test_store_py.py`:

- `test_record_payment_and_activate_subscription_single_transaction_success`
- `test_record_payment_and_activate_subscription_duplicate_is_idempotent`
- `test_record_payment_and_activate_subscription_rolls_back_on_failed_save`
- `test_record_payment_and_activate_subscription_legacy_duplicate_policy`

Runtime fake Telegram tests in `tests/test_runtime_fake_telegram.py`:

- `test_successful_payment_uses_atomic_store_flow`
- `test_successful_payment_duplicate_does_not_extend_twice`
- `test_successful_payment_store_failure_does_not_ack_as_success_if_state_not_saved`
- `test_successful_payment_with_pending_join_request_approves_request`
- `test_successful_payment_keeps_subscription_when_pending_approve_fails`

### Pending join request behavior

Confirmed unchanged:

- after successful atomic activation, runtime still calls `approve_pending_request()`
- approve failure logs an error and does not roll back the paid subscription

### Stage 13 verification result

Final verification status:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

# Stage 18 Diagnostics

## Scope

Goal of this stage: extract maintenance warning / expire / revoke orchestration from `bot/app.py` into a dedicated service module without changing warning windows, revoke semantics, stale pending cleanup, payment flow, or access/recovery policy.

## Maintenance flow before extraction

`bot/app.py` previously contained:

- warning window checks inside `_process_maintenance_user`
- warning notification delivery through `notify_user(...)`
- `store.mark_warning_sent(...)` after warning delivery
- expired subscription revoke orchestration in `_process_maintenance_user`
- `store.mark_access_revoked(...)` after revoke
- stale pending join cleanup branch inside `_process_maintenance_user`
- per-user error isolation in `run_subscription_maintenance`
- daemon loop in `run_maintenance_loop`

## Maintenance flow after extraction

Created:

- `bot/services/maintenance_service.py`

Exported functions:

- `warning_window_ms`
- `should_revoke_access`
- `should_send_warning`
- `notify_subscription_warning`
- `notify_subscription_expired`
- `cleanup_stale_pending_requests`
- `process_maintenance_user`
- `run_subscription_maintenance`

Current policy remains unchanged:

- warning window still derives from `warningDays`
- repeated warning spam is still blocked by `lastWarningAt`
- warning delivery still calls `mark_warning_sent`
- expired subscriptions still revoke through the existing access flow
- `mark_access_revoked` still runs after revoke
- stale pending join requests are still declined through `access_service`
- one failing user still does not stop maintenance for remaining users
- payment flow, invite/join/revoke semantics, recovery policy, and anomaly review are unchanged

## bot/app.py compatibility

`bot/app.py` keeps public/runtime methods:

- `run_maintenance_loop`
- `run_subscription_maintenance`
- `_process_maintenance_user`

`run_maintenance_loop` remains the daemon loop in `bot/app.py`, while `run_subscription_maintenance` and `_process_maintenance_user` now delegate into `bot/services/maintenance_service.py`.

# Stage 19 Diagnostics

## Scope

Goal of this stage: extract command/callback/update routing from `bot/app.py` into a dedicated dispatch module without changing Telegram UI contracts, callback data, slash commands, payment payloads, or any existing user/admin flow.

## Dispatch flow before extraction

`bot/app.py` previously contained:

- raw update routing in `handle_update`
- message routing in `handle_message`
- callback query routing in `handle_callback_query`
- direct admin command parsing in `handle_admin_command`
- pre-checkout routing in `handle_pre_checkout_query`
- successful payment routing in `handle_successful_payment`
- join request routing in `handle_chat_join_request`

## Dispatch flow after extraction

Created:

- `bot/dispatcher.py`

Exported functions:

- `dispatch_update`
- `dispatch_message`
- `dispatch_callback_query`
- `dispatch_admin_command`
- `dispatch_user_command`
- `dispatch_pre_checkout`
- `dispatch_successful_payment`
- `dispatch_chat_join_request`

Current policy remains unchanged:

- update routing priority is still message -> callback -> pre-checkout -> join request
- `successful_payment` is still handled before generic text-command fallback
- admin command semantics and argument format are unchanged
- admin callbacks still route into `AdminHandler`
- user commands and callbacks still route into `UserHandler`
- payment/access/maintenance/recovery/anomaly policy is unchanged
- callback data, slash commands, and payload contract remain unchanged

## bot/app.py compatibility

`bot/app.py` keeps public/runtime methods:

- `handle_update`
- `handle_message`
- `handle_callback_query`
- `handle_admin_command`
- `handle_pre_checkout_query`
- `handle_successful_payment`
- `handle_chat_join_request`

These methods are now thin wrappers over `bot/dispatcher.py`, while `bot/app.py` remains the runtime shell for bootstrap, polling, wrappers, and dependency wiring.

# Stage 20 Diagnostics

## Scope

Goal of this stage: structure the admin handling layer without changing direct admin commands, admin callback data, admin panel UX, or recovery/anomaly behavior.

## Admin layer before cleanup

`bot/handlers/admin.py` previously mixed:

- admin callback routing
- admin FSM text handling
- input/broadcast/template triggers
- admin panel rendering helpers
- payment diagnostics rendering
- payment anomalies rendering

## Admin layer after cleanup

Kept public facade:

- `bot/handlers/admin.py`

Added internal modules:

- `bot/handlers/admin_actions.py`
- `bot/handlers/admin_render.py`

Current split:

- `bot/dispatcher.py` handles direct slash-command routing for admin commands
- `bot/handlers/admin_actions.py` handles admin callbacks and FSM text states
- `bot/handlers/admin_render.py` handles admin panel rendering helpers
- `bot/handlers/admin.py` keeps the same facade methods and delegates internally

## Preserved contracts

The following remain unchanged:

- direct admin commands and their argument format
- admin callback data
- admin auth and unauthorized behavior
- payment diagnostics flow
- manual payment recovery flow
- payment anomalies review flow
- payment/access/maintenance/recovery policy
- user-facing Telegram UI contracts

# Stage 21 Diagnostics

## Scope

Goal of this stage: structure the user handling layer without changing user commands, user callback data, user menu UX, payment path, join path, or help/support behavior.

## User layer before cleanup

`bot/handlers/user.py` previously mixed:

- user callback handling
- user slash-command handling
- buy/buy_balance/join/help action branching
- direct calls into render paths on the runtime shell

## User layer after cleanup

Kept public facade:

- `bot/handlers/user.py`

Added internal modules:

- `bot/handlers/user_actions.py`
- `bot/handlers/user_render.py`

Current split:

- `bot/handlers/user_actions.py` handles user commands and callbacks
- `bot/handlers/user_render.py` handles user render-path helpers and post-action notices
- `bot/handlers/user.py` keeps the same facade methods and delegates internally

## Preserved contracts

The following remain unchanged:

- user slash commands and their argument format
- user callback data
- buy path and payload contract
- join-link behavior for active/inactive users
- help path
- support path as a URL button in the main menu
- payment/access/maintenance/admin recovery/anomaly policy

# Stage 22 Diagnostics

## Scope

Goal of this stage: structure the UI builders layer without changing callback data, button texts, button order, or any user/admin Telegram-visible UI contract.

## UI layer before cleanup

`bot/ui.py` previously contained:

- user main menu builder
- user help builder
- admin main/settings/users/stats builders
- admin payment diagnostics/anomalies builders
- admin templates/broadcast builders

All of these lived inside one `UIProvider` class.

## UI layer after cleanup

Kept public facade:

- `bot/ui.py`

Added internal modules:

- `bot/ui_common.py`
- `bot/ui_user.py`
- `bot/ui_admin.py`

Current split:

- `bot/ui_common.py` contains small keyboard helpers
- `bot/ui_user.py` contains user UI builders
- `bot/ui_admin.py` contains admin UI builders
- `bot/ui.py` re-exports the old public API through `UIProvider` and module-level functions

## Preserved contracts

The following remain unchanged:

- callback data
- button texts
- button order
- reply markup structure
- user/admin visible message text
- payment/access/maintenance/recovery/anomaly policy

## Tests added

Added `tests/test_ui_contracts.py` to lock:

- `bot.ui` public API
- user main menu keyboard contract
- help/join-related keyboard contract
- admin main menu keyboard contract
- admin settings keyboard contract
- `admin:payment_anomalies` button contract
- accidental duplicate callback data inside the main keyboards

# Stage 23 Diagnostics

## Scope

Goal of this stage: keep `bot/app.py` as a thin runtime shell, verify active runtime portability for Ubuntu deployment, and add deployment notes without changing Telegram-visible behavior.

## bot/app.py after stage 23

Current shell responsibilities:

- dependency wiring for config, store, Telegram client, FSM and handler facades;
- runtime lifecycle and bootstrap;
- polling loop and top-level runtime error handling;
- public wrappers delegating into dispatcher/services/compat helpers;
- small shell-local helpers used by polling, rendering and admin auth.

Targeted cleanup performed:

- grouped constructor wiring into dependency/runtime/handler sections;
- centralized Telegram client construction via `_create_telegram_client(...)`;
- normalized `bot/app.py` section markers so the file reads as a runtime shell instead of a mixed domain module;
- kept all public wrappers and shell-local helpers that are still referenced by dispatcher, handlers, services or tests.

No domain behavior was moved in this stage.

## Ubuntu portability checks

Validated for the active runtime:

- no hard-coded `C:\` or `D:\` absolute paths in active runtime source files;
- no Node runtime dependency in the Python launch path;
- relative JSON store path remains `data/db.json` by default;
- `.env.example` remains Linux-safe and was normalized to readable UTF-8 values;
- `requirements.txt` exists;
- official runtime entrypoint remains `python main.py`.

## Deployment documentation

Created:

- `DEPLOY_UBUNTU.md`

Contents include:

- apt packages
- virtualenv setup
- `.env` setup
- official verification commands
- first launch command
- systemd unit example
- service management commands
- permissions guidance
- backup command
- update procedure
- production safety checklist

## Tests added

Created:

- `tests/test_runtime_shell.py`

Coverage added:

- shell public API preserved on `SubscriptionBotApp`
- forbidden `bot.app` imports remain absent from dispatcher/services/ui/handlers
- active runtime has no Windows absolute paths
- `DEPLOY_UBUNTU.md` exists and contains deployment essentials
- `requirements.txt` exists and is non-empty

# Stage 24 Diagnostics

## Scope

Goal of this stage: harden release operations for Ubuntu deployment, backups, rollback and manual smoke checks without changing runtime logic.

## .env.example review

Updated `.env.example` to make deploy expectations explicit:

- uses real config key names from `config.py`
- documents token/channel/admin id formats
- keeps `DATA_FILE_PATH=data/db.json` as the Linux-safe default
- keeps placeholder values only, without any real secrets

## requirements.txt review

`requirements.txt` remains intentionally minimal because the active runtime uses the Python standard library only.

It was kept non-empty and now explicitly documents that it exists for consistent deploy commands.

## Deployment docs

Expanded `DEPLOY_UBUNTU.md` to include:

- server prerequisites
- recommended project path under `/opt/private-channel-bot`
- dedicated Linux user creation
- venv setup
- `.env` setup
- data directory permissions
- official checks
- first manual run
- systemd unit and lifecycle commands
- journalctl usage
- backup procedure
- rollback procedure
- update procedure
- common production issues

## Release checklist

Created:

- `RELEASE_CHECKLIST.md`

It now covers:

- pre-deploy checks
- manual smoke after deploy
- rollback steps

## Optional ops scripts

Created POSIX-friendly helper scripts:

- `scripts/check.sh`
- `scripts/backup_db.sh`
- `scripts/run_local.sh`

These scripts do not require root, do not embed secrets, and do not reference Windows paths.

## Ops tests added

Created:

- `tests/test_ops_readiness.py`

Coverage includes:

- required Ubuntu deploy doc sections
- release checklist presence and content
- required `.env.example` keys
- script presence and POSIX-friendly content
- no absolute production path in backup script
- no real-looking Telegram token in release-facing docs/scripts

# Roadmap Stage 1 Diagnostics

## Scope

Goal of this roadmap stage: add an admin-only `/admin_channel_check` command so the current production issue around channel access can be diagnosed directly from Telegram without speculative recovery or side effects.

## Current problem being addressed

Observed on the Ubuntu server after deployment:

- `Telegram API error at createChatInviteLink: Forbidden: bot was kicked from the channel chat`

## New read-only diagnostics path

Added service:

- `bot/services/channel_diagnostics_service.py`

Exported functions:

- `run_channel_diagnostics(app)`
- `format_channel_diagnostics(result)`

Current behavior:

- reads effective `CHANNEL_ID` from runtime settings/config
- fetches bot identity via `getMe`
- checks bot membership and admin rights via `getChatMember`
- reports:
  - channel configured or not
  - bot access status
  - admin status
  - `can_invite_users`
  - `can_restrict_members`
  - manual invite configured vs auto-create invite enabled
- does not create invite links
- does not mutate store state
- redacts token-like strings and private invite links from error output

## Admin routing

Added direct admin command:

- `/admin_channel_check`

Routing path:

- `bot/dispatcher.py` -> `AdminHandler._render_channel_diagnostics(...)`
- `bot/handlers/admin_render.py` uses the diagnostics service and sends a read-only Telegram message

## Telegram transport addition

Added read-only client method:

- `telegram_client.py` -> `get_chat_member(chat_id, user_id)`

This is used only for diagnostics in this stage.

# Roadmap Stage 2 Diagnostics

## Scope

Goal of this roadmap stage: add an admin-only `/admin_health` command so the current bot/runtime state can be inspected directly from Telegram without changing store data or Telegram-visible behavior.

## New read-only health path

Added service:

- `bot/services/health_service.py`

Exported functions:

- `get_health_status(app)`
- `format_health_status(status)`

Current health output includes:

- uptime since `SubscriptionBotApp` start
- bot username / id if available
- channel configured yes/no
- store writable yes/no via a temporary file next to `db.json`
- `lastUpdateId`
- last maintenance run timestamp
- active / expired / pending user counts
- backup directory existence
- last logged runtime/API error

## Minimal runtime state additions

Added runtime-only fields on `SubscriptionBotApp`:

- `started_at_ms`
- `last_runtime_error`
- `last_maintenance_run_at`

These are in-memory only and do not change `db.json` schema.

## Admin routing

Added direct admin command:

- `/admin_health`

Routing path:

- `bot/dispatcher.py` -> `AdminHandler._render_health(...)`
- `bot/handlers/admin_render.py` -> `health_service`

## Safety notes

- healthcheck is read-only for store state
- writable probe creates and removes a temp file in the store directory
- formatted output redacts token-like strings and private invite links from runtime errors

# Roadmap Stage 3 Diagnostics

## Scope

Goal of this roadmap stage: replace ad-hoc runtime `print` error output with a centralized logging layer that stays readable in `journalctl` and redacts secrets.

## New logging layer

Added module:

- `bot/logging_config.py`

Exposed helpers:

- `sanitize_text`
- `configure_logging`
- `get_logger`
- `format_event`
- `log_event`
- `classify_error_event`

## Runtime wiring

`SubscriptionBotApp` now owns `self.logger` and exposes:

- `_log_error(context, error)`
- `log_event(event, **fields)`

`_log_error(...)` still preserves runtime behavior, but now emits structured log events instead of direct `print(...)`.

## Current event coverage

Added structured events in existing runtime paths:

- `payment_received`
- `payment_duplicate`
- `subscription_activated`
- `join_request_approved`
- `join_request_declined`
- `subscription_revoked`
- `maintenance_started`
- `maintenance_finished`
- `admin_recovery_used`
- `channel_diagnostics_failed`
- `health_check_failed`

Generic error classification currently maps to:

- `telegram_api_error`
- `store_save_error`
- fallback `runtime_error`

## Redaction policy

Structured logs redact:

- Telegram token-like strings
- private invite links of the form `https://t.me/+...`

This keeps `journalctl` production-safe without removing useful error context.

# Roadmap Stage 4 Diagnostics

## Scope

Goal of this roadmap stage: harden operational backup and restore procedures for `data/db.json` without touching runtime logic or store schema.

## New scripts

Added:

- `scripts/restore_db.sh`
- `scripts/verify_backup.sh`

Updated:

- `scripts/backup_db.sh`

## Operational guarantees

- backups are copied into `data/backups/`
- backup script validates copied JSON before reporting success
- restore requires explicit `--yes`
- restore creates a pre-restore safety backup of current `db.json`
- verify is read-only and checks both JSON validity and basic store structure

## Documentation

Updated:

- `DEPLOY_UBUNTU.md`
- `RELEASE_CHECKLIST.md`
- `RUNTIME_MAP.md`

# Roadmap Stage 5 Diagnostics

## Scope

Goal of this roadmap stage: add read-only admin analytics commands without changing payment, access, maintenance, recovery, or anomaly policies.

## New service

Added:

- `bot/services/analytics_service.py`

Current responsibilities:

- build analytics snapshot from store state
- calculate revenue for day/week/month using `appTimezone`
- calculate unique payers for day/week/month
- produce formatted admin reports for stats, revenue, and activity

## Admin routing

Added direct admin commands:

- `/admin_revenue`
- `/admin_activity`

Kept existing direct admin command:

- `/admin_stats`

Routing path:

- `bot/dispatcher.py` -> admin handler render methods
- `bot/handlers/admin_render.py` -> analytics service formatters

## Safety notes

- analytics is read-only
- no payment totals or user state are modified
- empty db case is handled
- duplicate payment policy is unchanged
- manual recovery and payment anomalies remain unchanged
# Roadmap Stage 6 Diagnostics

## Scope

Goal of this roadmap stage: add multi-plan tariffs without breaking legacy payment payloads, existing user commands, or the current payment/access/admin policies.

## New service

Added:

- `bot/services/plan_service.py`

Current responsibilities:

- normalize configured tariff entries from `settings["plans"]`
- preserve fallback behavior through legacy `subscriptionPriceStars` and `subscriptionDurationDays`
- parse both legacy and plan-aware payment payloads
- resolve enabled plans for invoice and balance purchase flows
- map plan-specific price/duration into store-compatible settings

## Payment and payload compatibility

Current policy:

- legacy payload still works: `subscription:{user_id}`
- plan-aware payload is now supported: `subscription:{user_id}:{plan_id}`
- duplicate `telegramPaymentChargeId` behavior is unchanged and remains idempotent
- processed payments still use `record_payment_and_activate_subscription(...)`
- disabled plans are rejected in pre-checkout and are not sellable through user UI

## User UI and routing

Updated paths:

- `bot/ui_user.py` now renders a tariff picker when more than one enabled plan is configured
- `bot/handlers/user_actions.py` routes `buy:plan:{id}` and `buy_balance:plan:{id}` callbacks
- `bot/services/payment_service.py` resolves plan price/duration before invoice and payment activation
- `bot/app.py.send_invoice(...)` remains a backward-compatible wrapper and now accepts an optional `plan_id`

Current behavior:

- single-plan/fallback UX remains the same
- multi-plan UX shows tariffs in settings order
- balance purchase path uses the selected plan price and duration
- lifetime plans are supported through the new plan normalization layer

## Store compatibility

Backward-compatible state changes:

- `settings` now includes optional `plans: []` by default
- legacy top-level settings remain the fallback source of truth when `plans` are absent
- no existing payment fields were renamed or removed
- no top-level `db.json` schema break was introduced

## Tests added

Added:

- `tests/test_plan_service.py`
- `tests/test_multi_plan_payment.py`

Coverage added:

- legacy payload parsing still works
- plan-aware payload parsing works
- disabled plans are not sold
- price/duration are taken from the selected plan
- duplicate plan payment does not extend subscription twice
- tariff picker preserves configured plan order
- balance purchase path uses the selected plan

# Roadmap Stage 7 Diagnostics

## Scope

Goal of this roadmap stage: add promo codes without breaking existing payment payloads, duplicate-payment safety, UI contracts, or the current manual recovery policy.

## New service

Added:

- `bot/services/promo_service.py`

Current responsibilities:

- validate admin promo create arguments
- normalize promo codes and promo types
- format admin stats and result messages
- apply user promo codes safely
- compute invoice discount context without mutating payment flow semantics

## Store compatibility

Backward-compatible state changes:

- added top-level `promoCodes: {}`
- added per-user optional `pendingPromoCode`
- no existing payment fields were renamed or removed
- no existing callback data or payload formats were changed

## Payment and promo policy

Current policy:

- legacy payload still works: `subscription:{user_id}`
- plan-aware payload still works: `subscription:{user_id}:{plan_id}`
- `free_days` promo grants days directly and writes audit without fake payments
- discount promos are stored as pending and applied only to the next invoice/payment
- duplicate `telegramPaymentChargeId` remains idempotent and does not re-activate subscription or re-consume promo usage
- invalid or stale pending discount promos are cleared safely before invoice or payment validation

## Routing and commands

Added direct admin commands:

- `/admin_promo_create <code> <type> <value> <limit>`
- `/admin_promo_disable <code>`
- `/admin_promo_stats <code>`

Added user command:

- `/promo <code>`

Current behavior:

- admin promo commands remain direct-command only
- user promo flow does not create fake payments
- existing user/admin callbacks remain unchanged

## Tests added

Added:

- `tests/test_promo_service.py`
- `tests/test_promo_runtime.py`

Coverage added:

- promo service imports without `bot.app` cycle
- invalid, disabled, reused and exhausted promo paths
- `free_days` promo grants subscription without payment record creation
- discount promo changes the next invoice amount
- successful payment consumes applied promo once
- duplicate payment does not consume promo twice
- admin promo commands require admin and preserve runtime behavior

# Roadmap Stage 8 Diagnostics

## Scope

Goal of this roadmap stage: add a minimal referral system without changing existing Telegram UI contracts, payment payloads, or duplicate-payment guarantees.

## New service

Added:

- `bot/services/referral_service.py`

Current responsibilities:

- parse `/start ref_<code>` payloads
- validate referral codes
- attach referral only once for a user
- format referral start notices

## Store compatibility

Backward-compatible user fields:

- `referralCode`
- `referredBy`
- `referralRewards`

No existing top-level store buckets, payment payloads, callback data or admin flows were removed.

## Referral policy

Current policy:

- each user gets a generated `referralCode`
- self-referral is forbidden
- `referredBy` is saved only once
- reward is granted only after the referred user's first successful payment
- reward type is `+3 days` to the referrer subscription
- duplicate `telegramPaymentChargeId` remains idempotent and does not issue the reward twice
- reward writes audit entries: `referral_attached` and `referral_reward_granted`

## Runtime integration

Updated paths:

- `bot/handlers/user_actions.py` handles `/start ref_<code>`
- `store_py.py.record_payment_and_activate_subscription(...)` applies referral reward atomically with payment activation
- `bot/services/payment_service.py` preserves existing successful payment flow and only optionally approves the referrer if they already have a pending join request

## Tests added

Added:

- `tests/test_referral_service.py`
- `tests/test_referral_runtime.py`

Coverage added:

- referral code generation
- self-referral rejection
- one-time referral attachment
- reward after first payment
- duplicate payment does not reward twice
- audit log entries are written


# Roadmap Stage 9 Diagnostics

## Scope

Goal of this roadmap stage: add minimal GitHub Actions CI so every push and pull request automatically runs the same compile and unittest checks already required locally.

## Added

- `.github/workflows/tests.yml`
- `tests/test_ci_config.py`

## Workflow contract

Current workflow:

- triggers on `push`
- triggers on `pull_request`
- uses `actions/checkout@v4`
- uses `actions/setup-python@v5`
- pins Python `3.11`
- runs `pip install -r requirements.txt`
- runs `python -m compileall .`
- runs `python -m unittest discover -s tests -p "test_*.py" -v`

## Safety

Current CI stage intentionally does not:

- deploy to Ubuntu
- restart services
- run backup/restore scripts
- use repository or Telegram secrets

## Tests added

Coverage added:

- workflow file exists
- compileall step exists
- unittest step exists
- no secrets are referenced in workflow
- no deploy automation is present in workflow
