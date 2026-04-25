# Runtime Map

## Official entrypoint

- `main.py`
- launch path: `python main.py`

## External call chain

`main.py` uses only:

- `config.load_dotenv`
- `config.get_config`
- `config.validate_config`
- `store_py.create_store`
- `bot.app.SubscriptionBotApp`
- `SubscriptionBotApp.start()`

## bot/app.py logical map

### 1. Configuration and identity helpers

- `get_telegram`
- `get_effective_system_settings`
- `get_effective_admin_credentials`
- `is_authorized_admin`
- internal helpers:
  - `_now_ms`
  - `_log_error`
  - `_ensure_user_context`

### 2. Runtime setup / bootstrap

- `start`
- `stop`
- `_bootstrap`

### 3. Polling and top-level dispatch wrappers

- `poll_loop`
- `handle_update`
- `handle_message`
- `handle_callback_query`
- `handle_pre_checkout_query`
- `handle_successful_payment`
- `handle_chat_join_request`

These runtime-facing methods remain available on `SubscriptionBotApp`, but now delegate routing into `bot/dispatcher.py`.

### 4. Admin direct command layer

- `handle_admin_command`
- internal helpers:
  - `_handle_admin_login`
  - `_handle_admin_logout`
  - `_dispatch_admin_command`

`handle_admin_command` remains part of the public runtime surface, but now delegates command parsing/routing into `bot/dispatcher.py`.

Current direct admin commands handled by `handle_admin_command`:

- `/admin`
- `/admin_login`
- `/admin_logout`
- `/admin_channel_check`
- `/admin_stats`
- `/admin_settings`
- `/admin_users`
- `/admin_help`
- `/admin_refresh_invite`
- `/admin_broadcast`
- `/admin_payment_diag`
- `/admin_recover_payment`
- `/admin_payment_anomalies`

### 5. UI rendering layer

- `render_panel`
- `send_main_menu`
- `send_user_help`
- `send_join_link`
- internal helpers:
  - `_resolve_panel_message_id`
  - `_save_panel_message_state`
  - `_build_main_menu_context`

### 6. Payments and access control

- `send_invoice`
- `handle_pre_checkout_query`
- `handle_successful_payment`
- `handle_chat_join_request`
- `approve_pending_request`
- `ensure_invite_link`
- `refresh_invite_link`
- `send_join_link`

The three payment-facing methods above are thin wrappers in `bot/app.py` and now delegate into `bot/services/payment_service.py`.

The invite/join/access-facing methods above are thin wrappers in `bot/app.py` and now delegate into `bot/services/access_service.py`.

Payment orchestration notes:

- invoice creation lives in `bot/services/payment_service.py` through `handle_buy_access(...)`
- payment payload contract is still `subscription:{user_id}`
- `handle_pre_checkout_query` validates payload through `parse_payment_payload(...)`
- `handle_successful_payment` delegates into `bot/services/payment_service.py`
- `bot/services/payment_service.py` uses `store_py.JsonStore.record_payment_and_activate_subscription(...)`
- payment persistence and subscription activation are applied in one store transaction
- duplicate `telegramPaymentChargeId` values are treated as idempotent duplicates and do not extend access twice
- after a processed payment, runtime still calls `approve_pending_request(user_id)`
- automatic speculative recovery for legacy/partial payment records is intentionally disabled
- спорные historical payment cases are handled only through admin diagnostics plus explicit manual recovery
- admin-only anomaly review is read-only and surfaces suspicious users as a list without applying any fix

## bot/dispatcher.py map

This module contains update/message/callback routing for the active runtime and does not import `bot.app`.

### Exported functions

- `dispatch_update`
- `dispatch_message`
- `dispatch_callback_query`
- `dispatch_admin_command`
- `dispatch_user_command`
- `dispatch_pre_checkout`
- `dispatch_successful_payment`
- `dispatch_chat_join_request`

### Contract notes

- raw update routing priority is unchanged: message -> callback -> pre-checkout -> join request
- `successful_payment` message handling still has priority before generic text command routing
- admin command parsing and argument format are unchanged
- user commands still flow into `bot/handlers/user.py`
- admin callbacks still flow into `bot/handlers/admin.py`
- user callbacks still flow into `bot/handlers/user.py`
- payment/access domain logic still lives in services, not in the dispatcher

## bot/handlers/admin.py facade map

This module remains the public admin handler facade used by the runtime shell and does not import `bot.app`.

### Public handler surface

- `get_context`
- `handle_callback`
- `handle_text`
- `_handle_input_trigger`
- `_handle_broadcast_trigger`
- `_handle_template_edit_trigger`
- `_render_main`
- `_render_settings`
- `_render_templates_menu`
- `_render_users`
- `_render_user_details`
- `_render_stats`
- `_render_payment_diagnostics`
- `_render_payment_anomalies`
- `_render_input_request`

### Internal split

- `bot/handlers/admin_actions.py` contains admin callback handling and FSM text handling
- `bot/handlers/admin_render.py` contains admin panel rendering helpers
- `bot/dispatcher.py` keeps direct slash-command routing for admin commands

### Contract notes

- direct admin commands are unchanged
- admin callback data are unchanged
- payment diagnostics, anomalies review, and manual recovery paths are unchanged
- admin auth checks remain enforced at the same runtime boundaries

## bot/handlers/user.py facade map

This module remains the public user handler facade used by the runtime shell and does not import `bot.app`.

### Public handler surface

- `handle_callback`
- `handle_command`

### Internal split

- `bot/handlers/user_actions.py` contains user command/callback handling
- `bot/handlers/user_render.py` contains user render-path helpers that delegate to runtime wrappers

### Contract notes

- user slash commands are unchanged: `/start`, `/buy`, `/buy_balance`, `/status`, `/help`
- user callback data are unchanged: `buy`, `join`, `user:help`, `buy_balance`, `panel:main`
- help path remains callback-driven, while support remains a URL button in the main menu
- buy path still delegates into the payment flow
- join path still delegates into the access flow

## bot/ui.py facade map

This module remains the public UI builder facade used by the runtime shell, handlers, and tests.

### Public UI surface

- `UIProvider.get_main_menu`
- `UIProvider.get_user_help`
- `UIProvider.get_admin_main`
- `UIProvider.get_admin_settings`
- `UIProvider.get_admin_users`
- `UIProvider.get_admin_user_details`
- `UIProvider.get_admin_payment_diagnostics`
- `UIProvider.get_admin_payment_anomalies`
- `UIProvider.get_admin_templates_menu`
- `UIProvider.get_admin_template_editor`
- `UIProvider.get_admin_broadcast_menu`

The same function names are also re-exported at module level from `bot.ui`.

### Internal split

- `bot/ui_common.py` contains small keyboard helpers
- `bot/ui_user.py` contains user UI builders
- `bot/ui_admin.py` contains admin UI builders
- `bot/ui.py` re-exports the old public API through `UIProvider`

### Contract notes

- callback data are unchanged
- button texts are unchanged
- button order is unchanged
- message text is unchanged
- UI contract stability is now covered by `tests/test_ui_contracts.py`

## bot/services/payment_service.py map

This module contains the extracted payment orchestration for the active runtime and does not import `bot.app`.

### Exported functions

- `build_payment_payload`
- `parse_payment_payload`
- `handle_buy_access`
- `handle_pre_checkout`
- `handle_successful_payment`

### Contract notes

- payload remains `subscription:{user_id}`
- invalid payloads are rejected safely in pre-checkout
- duplicate successful payments return without a second success UI
- successful payments still use the atomic store method

## bot/services/access_service.py map

This module contains the extracted invite/join/revoke orchestration for the active runtime and does not import `bot.app`.

### Exported functions

- `get_join_link`
- `ensure_invite_link`
- `refresh_invite_link`
- `handle_chat_join_request`
- `approve_pending_request`
- `decline_pending_join_request`
- `prune_expired_pending_join_requests`
- `revoke_user_subscription`
- `send_join_link`

### Contract notes

- manual `channelInviteLink` still has priority over auto-generated invite links
- auto invite creation still uses `create_chat_invite_link(..., creates_join_request=True)`
- `handle_chat_join_request` still stores `pendingJoinRequest`
- active subscribers are still auto-approved
- inactive subscribers still receive the same pay/menu notice path
- `approve_pending_request` still clears pending requests and marks `channelMemberStatus = "member"` on success
- stale pending join requests are still declined from the maintenance path
- revoke flow still calls `ban_chat_member` + `unban_chat_member` and does not change payment/recovery/anomaly policy

### 7. Subscription/user side effects

- `update_settings`
- `grant_user_subscription`
- `revoke_user_subscription`
- `adjust_user_balance`
- `set_user_notes`
- `send_admin_message`
- `broadcast_users`
- `notify_user`
- internal helper:
  - `_matches_broadcast_scope`

### 8. Subscription maintenance

- `run_maintenance_loop`
- `run_subscription_maintenance`

`run_maintenance_loop` remains in `bot/app.py` as the daemon loop, while maintenance-specific orchestration now delegates into `bot/services/maintenance_service.py`.

## bot/services/maintenance_service.py map

This module contains the extracted maintenance orchestration for the active runtime and does not import `bot.app`.

### Exported functions

- `warning_window_ms`
- `should_revoke_access`
- `should_send_warning`
- `notify_subscription_warning`
- `notify_subscription_expired`
- `cleanup_stale_pending_requests`
- `process_maintenance_user`
- `run_subscription_maintenance`

### Contract notes

- warning window still derives from `settings["warningDays"]`
- warning notices are still suppressed after `lastWarningAt` is set
- warning delivery still calls `store.mark_warning_sent(...)`
- expired subscriptions still revoke access through `revoke_user_subscription(...)`
- expired revoke flow still marks `lastAccessRevokedAt` through `store.mark_access_revoked(...)`
- stale pending join requests are still cleaned through `bot/services/access_service.py`
- one failing user still does not stop maintenance for the remaining users

### 9. Compatibility/editor wrappers kept in `bot/app.py`

These methods remain available on `SubscriptionBotApp`, but now delegate into `bot/compat_helpers.py`:

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

## telegram_client.py transport layer

`telegram_client.py` is the Telegram Bot API transport layer used by the active runtime.

### Public methods

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

### Internal transport helpers

- `_build_url`
- `_build_request`
- `_read_response_body`
- `_parse_json_body`
- `_parse_ok_response`
- `_parse_http_error`
- `_is_terminal_error`
- `_request`

### Transport notes

- all Bot API calls are sent through one centralized POST transport path
- `edit_message_text()` treats `message is not modified` as a safe non-fatal result
- transport-level tests live in `tests/test_telegram_client.py`
- those tests use fake HTTP responses and do not touch the real network

## bot/compat_helpers.py map

The file is now split into in-file sections:

- Imports
- Internal helpers
- View model helpers
- JSON replacement helpers
- User editor helpers
- Template helpers
- Channel/settings helpers
- Stats helpers

### Exported helpers

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

### Internal helpers

- `_now_ms`
- `_parse_json`
- `_format_json`
- `_user_search_haystack`
- `_is_active_subscription`
- `_matches_status_filter`
- `_build_pending_join_request`
- `_render_template_values`
- `_normalize_channel_id`

## Compatibility/editor helper inventory and current usage

### Legacy/editor-only helpers

These remain part of the public `bot.app` surface for compatibility, but active Telegram runtime flow does not call them directly:

- `get_admin_view_model`
- `get_user_editor_view_model`
- `replace_state_from_json`
- `replace_settings_from_json`
- `replace_templates_from_json`
- `save_user_structured`
- `replace_user_json`
- `delete_user`
- `format_stats_text`

These are grouped inside `bot/compat_helpers.py` mainly under:

- View model helpers
- JSON replacement helpers
- User editor helpers
- Stats helpers

Historical consumer left in `legacy/`:

- `legacy/admin_server_py.py`

### Helpers still used by active runtime or handlers

- `get_template_context`
  - used by `bot/handlers/user.py`
  - used indirectly by `send_join_link` through `render_message_template`
- `render_message_template`
  - used by `bot/app.py` in `send_join_link`
- `configure_channel`
  - used by `bot/handlers/admin.py`
- `get_dashboard_stats_extended`
  - used by `bot/handlers/admin.py`

These are grouped inside `bot/compat_helpers.py` mainly under:

- Template helpers
- Channel/settings helpers
- Stats helpers

## What tests rely on directly

Current tests rely on:

- importing `main`
- importing `bot.app.SubscriptionBotApp`
- importing `bot.compat_helpers`
- importing `store_py.create_store`
- public methods still existing on `SubscriptionBotApp`:
  - `start`
  - `stop`
  - `handle_message`
  - `handle_callback_query`
  - `handle_pre_checkout_query`
  - `handle_chat_join_request`
  - `run_subscription_maintenance`
  - `render_panel`
  - `send_main_menu`
  - `send_join_link`
  - compatibility wrappers such as `get_template_context`, `configure_channel`, `get_dashboard_stats_extended`
- callback_data stability from `bot/ui.py`
- absence of imports from `legacy/` and `app_py`

## store_py.py persistence map

`store_py.py` remains the active persistence layer for the runtime started by `main.py`.

### Payment and recovery methods relevant to the active runtime

- `record_payment`
- `activate_subscription_from_payment`
- `record_payment_and_activate_subscription`
- `get_user_payment_diagnostics`
- `list_payment_anomalies`
- `manual_payment_recovery`

### Payment diagnostics and recovery policy

- `get_user_payment_diagnostics(user_id)` is read-only and does not change state
- `list_payment_anomalies(limit)` is read-only and returns only users with suspicious payment diagnostics
- it reports totals, subscription status, recent payments, and suspicious signals:
  - payment records exist but the subscription is not active
  - totals do not match stored payment records
  - duplicate charge ids
  - missing charge ids
  - legacy records without current expected payment fields
- anomaly list sorting is severity-first and then most recent payment first
- `manual_payment_recovery(admin_id, user_id, days, reason)` is an explicit admin-only action
- manual recovery writes audit type `manual_payment_recovery`
- manual recovery does not create fake Telegram payment records
- manual recovery does not change `totalPaymentsCount` or `totalSpentStars`

### Admin review UI

- direct command: `/admin_payment_anomalies [limit]`
- inline callback from admin menu: `admin:payment_anomalies`
- both paths are read-only and point admins to `/admin_payment_diag USER_ID` for per-user review

### Tests

- runtime fake Telegram coverage: `tests/test_runtime_fake_telegram.py`
- storage coverage: `tests/test_store_py.py`

## Notes for future cleanup

Safe next candidates for a later stage, if tests stay green:

- decide whether legacy-only editor/view-model helpers should eventually move behind a narrower compatibility facade;
- simplify some remaining broad `except: pass` branches with targeted logging;
- if needed, separate active admin-facing helpers from web-admin compatibility helpers inside `bot/compat_helpers.py` without changing the `bot.app` surface.

## store_py.py persistence layer

`store_py.py` is the active JSON persistence layer used by `main.py`, `bot/app.py` and the fake runtime tests.

### Current top-level db.json schema

- `meta`
  - runtime metadata such as `createdAt`, `updatedAt`, `lastUpdateId`, `botInfo`, invite link cache
- `settings`
  - subscription settings, channel/admin/runtime options and nested `messageTemplates`
- `users`
  - per-user records keyed by Telegram user id as string
- `payments`
  - payment records keyed by `telegramPaymentChargeId`
- `auditLog`
  - newest-first admin/system audit entries

### Public persistence API groups

- state and settings
  - `get_state`
  - `replace_state`
  - `get_meta`
  - `get_settings`
  - `update_settings`
  - `replace_settings`
- users and profile fields
  - `ensure_user`
  - `get_user`
  - `list_users`
  - `replace_user`
  - `update_user_fields`
  - `delete_user`
  - `set_user_notes`
  - `set_user_pending_join_request`
  - `clear_user_pending_join_request`
  - `set_user_channel_member_status`
- payments, subscriptions and balance
  - `get_payments`
  - `has_payment`
  - `record_payment`
  - `is_subscription_active`
  - `activate_subscription_from_payment`
  - `grant_subscription_days`
  - `revoke_subscription`
  - `adjust_balance`
  - `purchase_with_balance`
  - `mark_warning_sent`
  - `mark_access_revoked`
- runtime metadata and admin stats
  - `set_bot_info`
  - `set_last_update_id`
  - `set_join_invite_link`
  - `get_effective_invite_link`
  - `get_dashboard_stats`
  - `add_audit_log`
  - `get_audit_log`

### Persistence behavior notes

- missing db file is initialized with defaults
- partial top-level state is merged with defaults through `merge_state()`
- invalid JSON now raises a predictable `RuntimeError`
- saves write to `db.json.tmp`, flush and fsync, then replace the target via `os.replace`
- duplicate payments are ignored at store level when `telegramPaymentChargeId` already exists

### Store regression tests

- tests live in `tests/test_store_py.py`
- every store test uses `tempfile.TemporaryDirectory()`
- tests write only to a temporary `db.json` path and do not touch production `data/db.json`

### Store rollback note

Mutating store methods now use `_mutate_and_save()` for transaction-like in-memory rollback.

Current mutating methods covered by that path:

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

If `_save_unlocked()` fails, the on-disk file remains protected by atomic replace and `self.state` is restored from a deepcopy backup.

### Compound store operations note

Compound operations reviewed in `store_py.py`:

- previously multi-save due to main mutation + separate audit write:
  - `replace_user`
  - `update_user_fields`
  - `delete_user`
  - `set_user_notes`
  - `grant_subscription_days`
  - `revoke_subscription`
  - `adjust_balance`
- previously multi-save due to chained mutating call:
  - `purchase_with_balance` -> balance debit + `grant_subscription_days`
- already single-mutation operations and left as-is:
  - `record_payment`
  - `activate_subscription_from_payment`
  - `clear_user_pending_join_request` delegates to one mutating method

Current state:

- the user+audit operations above now append audit entries inside the same `_mutate_and_save()` transaction
- `purchase_with_balance` now applies balance debit, subscription extension and the `grant_subscription` audit trail inside one `_mutate_and_save()` call
- no compound store operation in `store_py.py` currently performs multiple persisted saves for one public call

### Payment orchestration note

`handle_successful_payment()` in `bot/app.py` now uses store-level atomic orchestration instead of the older runtime sequence `record_payment()` -> `activate_subscription_from_payment()`.

Current policy:

- store entrypoint: `record_payment_and_activate_subscription(user_id, payment, settings)`
- duplicate policy: strict idempotency by `telegramPaymentChargeId`
  - existing payment => status `duplicate`
  - no second totals increment
  - no second subscription extension
- legacy duplicate policy:
  - historical payment records without any extra activation marker are treated as already processed duplicates
  - store does not auto-recover unknown historical partials to avoid accidental double extension
- no schema change was needed for this stage

Covered by tests:

- `tests/test_store_py.py`
- `tests/test_runtime_fake_telegram.py`

## Stage 23 runtime shell and Ubuntu readiness

### What remains in `bot/app.py`

`bot/app.py` is now intentionally limited to:

- dependency wiring for `config`, `store`, `TelegramClient`, `FSM`, handler facades;
- runtime lifecycle (`start`, `stop`, `_bootstrap`);
- polling loop and top-level error handling;
- public dispatch wrappers that delegate into `bot/dispatcher.py`;
- public service wrappers for payment/access/maintenance flows;
- runtime side-effect wrappers (`notify_user`, `broadcast_users`, admin/user notifications);
- compatibility wrappers for `bot/compat_helpers.py`.

### Local helpers intentionally kept in `bot/app.py`

These helpers still belong to the runtime shell and were not removed:

- `_create_telegram_client`
- `_now_ms`
- `_log_error`
- `_ensure_user_context`
- `_process_polled_update`
- `_resolve_panel_message_id`
- `_save_panel_message_state`
- `_build_main_menu_context`
- `_matches_broadcast_scope`
- `_handle_admin_login`
- `_handle_admin_logout`
- `_dispatch_admin_command`

They remain because dispatcher, handlers, polling, panel rendering, or tests still rely on them.

### Ubuntu compatibility notes

Active runtime readiness checked in stage 23:

- active runtime files do not contain hard-coded `C:\` or `D:\` paths;
- `config.py` still resolves `DATA_FILE_PATH` through env or a relative project path;
- `requirements.txt` exists and remains usable for `pip install -r requirements.txt`;
- Ubuntu deployment instructions now live in `DEPLOY_UBUNTU.md`;
- official entrypoint remains `python main.py`.

### Stage 23 tests

Added `tests/test_runtime_shell.py` to cover:

- shell public API on `SubscriptionBotApp`;
- forbidden `bot.app` imports in dispatcher/services/ui/handlers;
- absence of Windows absolute paths in active runtime files;
- existence and content of `DEPLOY_UBUNTU.md`;
- existence of non-empty `requirements.txt`.

## Stage 24 ops readiness map

### Release-facing files

- `.env.example`
  - contains Linux-safe placeholder values and comments for required config keys
- `requirements.txt`
  - remains intentionally minimal because the runtime uses the standard library only
- `DEPLOY_UBUNTU.md`
  - primary Ubuntu deploy and rollback guide
- `RELEASE_CHECKLIST.md`
  - manual pre-deploy, post-deploy and rollback checklist
- `scripts/check.sh`
  - official local verification helper
- `scripts/backup_db.sh`
  - JSON store backup helper
- `scripts/run_local.sh`
  - local runtime launcher for POSIX shells

### Ops policy notes

- no runtime logic was changed for stage 24;
- backup and rollback remain operational procedures, not automatic runtime behavior;
- release docs avoid production tokens and Windows-only path assumptions.

## Channel diagnostics map

### bot/services/channel_diagnostics_service.py

This module is read-only and does not import `bot.app`.

Exported functions:

- `run_channel_diagnostics`
- `format_channel_diagnostics`

Current direct admin entrypoint:

- `/admin_channel_check`

Current diagnostics checks:

- `CHANNEL_ID` configured and readable from effective settings
- bot identity available through `getMe`
- bot membership/access status in the configured channel through `getChatMember`
- admin status
- `can_invite_users` for invite-link and join-request approval flow
- `can_restrict_members` for revoke flow
- manual invite configured vs auto-create invite enabled

Safety notes:

- diagnostics do not create or rotate invite links
- diagnostics do not modify `db.json`
- formatted output redacts token-like strings and private invite links from error text

## Healthcheck map

### bot/services/health_service.py

This module is read-only and does not import `bot.app`.

Exported functions:

- `get_health_status`
- `format_health_status`

Current direct admin entrypoint:

- `/admin_health`

Current healthcheck fields:

- uptime from runtime start
- bot username / id from stored `meta.botInfo` or `getMe`
- channel configured flag
- store writable check through a temp file next to `db.json`
- `meta.lastUpdateId`
- last maintenance run from runtime state
- active / expired / pending user counts from store stats
- backup directory existence
- last logged runtime/API error from runtime state

Safety notes:

- healthcheck does not mutate store state
- writable probe uses a temporary file and removes it immediately
- formatted output redacts token-like strings and private invite links from error text

## Logging map

### bot/logging_config.py

Centralized runtime logging layer for the active bot runtime.

Exported helpers:

- `sanitize_text`
- `configure_logging`
- `get_logger`
- `format_event`
- `log_event`
- `classify_error_event`

Current runtime wiring:

- `SubscriptionBotApp` owns `self.logger`
- `_log_error(...)` writes structured error events instead of raw `print`
- services emit domain events through `app.log_event(...)`

Current event names in active runtime:

- `payment_received`
- `payment_duplicate`
- `subscription_activated`
- `join_request_approved`
- `join_request_declined`
- `subscription_revoked`
- `maintenance_started`
- `maintenance_finished`
- `admin_recovery_used`
- `telegram_api_error`
- `store_save_error`
- `channel_diagnostics_failed`
- `health_check_failed`

Safety notes:

- Telegram token patterns are redacted
- private `t.me/+...` invite links are redacted
- logging remains stdout/stderr-friendly for `systemd` + `journalctl`
