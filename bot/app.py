import logging
import threading
import time
from telegram_client import TelegramClient
from bot import compat_helpers
from bot import dispatcher
from bot import logging_config
from bot.fsm import FSM
from bot.services import access_service
from bot.services import maintenance_service
from bot.services import payment_service
from bot.ui import UIProvider
from bot.handlers.admin import AdminHandler
from bot.handlers.user import UserHandler

class SubscriptionBotApp:
    ADMIN_COMMANDS = {
        '/admin', '/admin_help', '/admin_login', '/admin_logout', 
        '/admin_stats', '/admin_settings', '/admin_set', '/admin_users', 
        '/admin_user', '/admin_create_user', '/admin_grant', '/admin_revoke', 
        '/admin_balance', '/admin_approve', '/admin_message', '/admin_note', 
        '/admin_broadcast', '/admin_refresh_invite', '/admin_setup_channel',
        '/admin_payment_diag', '/admin_recover_payment', '/admin_payment_anomalies',
        '/admin_channel_check', '/admin_health'
    }
    ALLOWED_UPDATES = ["message", "callback_query", "pre_checkout_query", "chat_join_request", "chat_member"]
    JOIN_REQUEST_TTL_MS = 7 * 24 * 3600 * 1000

    def __init__(self, config, store):
        # --- Dependencies ---
        self.config = config
        self.store = store
        self.telegram = self._create_telegram_client(config.bot_token, config.telegram_api_base_url)
        self.current_bot_token = config.bot_token
        self.current_api_base_url = config.telegram_api_base_url
        self.logger = logging_config.get_logger("runtime")

        # --- Runtime state ---
        self.is_stopping = False
        self.authorized_admin_user_ids = set()
        self.fsm = FSM()
        self.started_at_ms = int(self._now_ms())
        self.last_runtime_error = None
        self.last_maintenance_run_at = None

        # --- Handler facades ---
        self.admin_handler = AdminHandler(self)
        self.user_handler = UserHandler(self)

    # --- Dependencies and runtime state helpers ---

    @staticmethod
    def _create_telegram_client(bot_token, api_base_url):
        return TelegramClient(bot_token, api_base_url)

    def get_telegram(self):
        bot_token = self.get_effective_system_settings()["botToken"]
        api_base_url = self.config.telegram_api_base_url
        if bot_token != self.current_bot_token or api_base_url != self.current_api_base_url:
            self.telegram = self._create_telegram_client(bot_token, api_base_url)
            self.current_bot_token = bot_token
            self.current_api_base_url = api_base_url
        return self.telegram

    def get_effective_system_settings(self):
        settings = self.store.get_settings()
        return {
            "botToken": settings.get("botTokenOverride") or self.config.bot_token,
            "channelId": settings.get("channelId") or self.config.channel_id,
            "appTimezone": settings.get("appTimezone") or self.config.app_timezone,
            "adminUsername": settings.get("adminUsername") or self.config.admin_username,
            "adminPassword": settings.get("adminPassword") or self.config.admin_password,
            "adminTelegramId": settings.get("adminTelegramId") or getattr(self.config, "admin_telegram_id", ""),
            "autoCreateInviteLink": settings.get("autoCreateInviteLink") if isinstance(settings.get("autoCreateInviteLink"), bool) else self.config.auto_create_invite_link,
            "pollTimeoutSeconds": settings.get("pollTimeoutSeconds") or self.config.poll_timeout_seconds,
            "serviceCheckIntervalMs": settings.get("serviceCheckIntervalMs") or self.config.service_check_interval_ms,
        }

    def get_effective_admin_credentials(self):
        system = self.get_effective_system_settings()
        return {
            "username": system["adminUsername"],
            "password": system["adminPassword"],
            "telegram_id": str(system.get("adminTelegramId") or "")
        }

    @staticmethod
    def _now_ms():
        return time.time() * 1000

    def _log_error(self, context, error):
        self.last_runtime_error = {
            "context": str(context or "").strip(),
            "error": str(error or "").strip(),
            "loggedAt": int(self._now_ms()),
        }
        logging_config.log_event(
            self.logger,
            logging_config.classify_error_event(context, error),
            level=logging.ERROR,
            context=context,
            error=error,
        )

    def log_event(self, event, level=logging.INFO, **fields):
        logging_config.log_event(self.logger, event, level=level, **fields)

    def _ensure_user_context(self, user_info):
        if not user_info:
            return None
        self.store.ensure_user(user_info)
        return user_info["id"]

    def _process_polled_update(self, update):
        try:
            self.handle_update(update)
        except Exception as error:
            self._log_error(f"Update handling error for {update.get('update_id', 'unknown')}", error)
        finally:
            if "update_id" in update:
                self.store.set_last_update_id(update["update_id"])

    # --- Runtime lifecycle ---

    def start(self):
        self._bootstrap()
        self.get_telegram().delete_webhook(False)
        self.store.set_bot_info(self.get_telegram().get_me())
        
        try:
            self.ensure_invite_link()
        except Exception as error:
            self._log_error("Invite bootstrap error", error)

        threading.Thread(target=self.run_maintenance_loop, daemon=True).start()
        self.poll_loop()

    def stop(self):
        self.is_stopping = True

    def _bootstrap(self):
        # Initial settings setup from config
        settings = self.store.get_settings()
        bootstrap = {
            "subscriptionPriceStars": self.config.subscription_price_stars,
            "subscriptionDurationDays": self.config.subscription_duration_days,
            "warningDays": self.config.warning_days,
            "recurringPaymentsEnabled": self.config.recurring_payments_enabled,
            "subscriptionName": self.config.subscription_name,
            "subscriptionDescription": self.config.subscription_description,
            "supportUsername": self.config.support_username,
            "welcomeText": self.config.welcome_text,
            "channelInviteLink": self.config.channel_invite_link,
            "channelId": self.config.channel_id,
            "appTimezone": self.config.app_timezone,
            "adminUsername": self.config.admin_username,
            "adminPassword": self.config.admin_password,
            "adminTelegramId": self.config.admin_telegram_id,
            "autoCreateInviteLink": self.config.auto_create_invite_link,
            "pollTimeoutSeconds": self.config.poll_timeout_seconds,
            "serviceCheckIntervalMs": self.config.service_check_interval_ms,
        }
        partial = {k: v for k, v in bootstrap.items() if not settings.get(k)}
        if partial:
            self.store.update_settings(partial)

    # --- Polling ---

    def poll_loop(self):
        while not self.is_stopping:
            try:
                offset = (self.store.get_meta().get("lastUpdateId") or 0) + 1
                poll_timeout = self.get_effective_system_settings()["pollTimeoutSeconds"]
                updates = self.get_telegram().get_updates(offset, poll_timeout, self.ALLOWED_UPDATES)
                for update in updates:
                    self._process_polled_update(update)
            except Exception as error:
                self._log_error("Polling error", error)
                time.sleep(3)

    def handle_update(self, update):
        return dispatcher.dispatch_update(self, update)

    # --- Public dispatch wrappers ---

    def handle_message(self, message):
        return dispatcher.dispatch_message(self, message)

    def handle_callback_query(self, callback_query):
        return dispatcher.dispatch_callback_query(self, callback_query)

    # --- Admin auth and direct commands ---

    def _handle_admin_login(self, user, chat_id, args):
        creds = self.get_effective_admin_credentials()
        parts = args.split(None, 1)
        user_in = parts[0] if len(parts) == 2 else creds["username"]
        pass_in = parts[1] if len(parts) == 2 else (parts[0] if len(parts) == 1 else "")

        if (creds["telegram_id"] == str(user['id'])) or (user_in == creds["username"] and pass_in == creds["password"]):
            self.authorized_admin_user_ids.add(user['id'])
            self.admin_handler._render_main(chat_id, notice="Р вЂ™РЎвЂ¦Р С•Р Т‘ Р Р†РЎвЂ№Р С—Р С•Р В»Р Р…Р ВµР Р…", force_new=True)
        else:
            self.get_telegram().send_message(chat_id, "РІСњРЉ Р СњР ВµР Р†Р ВµРЎР‚Р Р…РЎвЂ№Р Вµ РЎС“РЎвЂЎР ВµРЎвЂљР Р…РЎвЂ№Р Вµ Р Т‘Р В°Р Р…Р Р…РЎвЂ№Р Вµ")

    def _handle_admin_logout(self, user, chat_id):
        self.authorized_admin_user_ids.discard(user['id'])
        self.send_main_menu(chat_id, notice="Р вЂ™РЎвЂ№ Р Р†РЎвЂ№РЎв‚¬Р В»Р С‘ Р С‘Р В· Р В°Р Т‘Р СР С‘Р Р…Р С”Р С‘")

    def _dispatch_admin_command(self, chat_id, command):
        actions = {
            "/admin": lambda: self.admin_handler._render_main(chat_id, force_new=True),
            "/admin_stats": lambda: self.admin_handler._render_stats(chat_id),
            "/admin_settings": lambda: self.admin_handler._render_settings(chat_id),
            "/admin_users": lambda: self.admin_handler._render_users(chat_id, 0),
            "/admin_help": lambda: self.admin_handler._render_main(
                chat_id, notice="Р ВРЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р в„–РЎвЂљР Вµ Р СР ВµР Р…РЎР‹ Р Т‘Р В»РЎРЏ РЎС“Р С—РЎР‚Р В°Р Р†Р В»Р ВµР Р…Р С‘РЎРЏ Р В±Р С•РЎвЂљР С•Р С.", force_new=True
            ),
            "/admin_refresh_invite": lambda: self.admin_handler._render_main(
                chat_id, notice=f"Р РЋРЎРѓРЎвЂ№Р В»Р С”Р В° Р С•Р В±Р Р…Р С•Р Р†Р В»Р ВµР Р…Р В°: {self.refresh_invite_link()}"
            ),
            "/admin_broadcast": lambda: self.admin_handler._handle_broadcast_trigger(chat_id, "admin:broadcast:menu"),
        }
        action = actions.get(command)
        if action:
            action()

    def handle_admin_command(self, message, command, args):
        return dispatcher.dispatch_admin_command(self, message, command, args)

    def is_authorized_admin(self, user):
        tid = self.get_effective_admin_credentials()["telegram_id"]
        if tid and str(user['id']) == tid:
            return True
        return user['id'] in self.authorized_admin_user_ids

    # --- User/admin panel rendering ---

    def _resolve_panel_message_id(self, user_id, callback_query, force_new):
        if force_new:
            return None
        if callback_query:
            return callback_query['message']['message_id']
        user = self.store.get_user(user_id)
        return user.get("panelMessageId") if user else None

    def _save_panel_message_state(self, user_id, message_id, panel_mode):
        self.store.update_user_fields(user_id, {"panelMessageId": message_id, "panelMode": panel_mode})

    def _build_main_menu_context(self, user_id, notice):
        settings = self.store.get_settings()
        return {
            "settings": settings,
            "user": self.store.get_user(user_id),
            "is_active": self.store.is_subscription_active(user_id),
            "effective_invite_link": self.store.get_effective_invite_link(self.config.channel_invite_link),
            "system": self.get_effective_system_settings(),
            "notice": notice,
            "is_admin": self.is_authorized_admin({"id": user_id}),
        }

    def render_panel(self, user_id, text, markup=None, panel_mode="home", callback_query=None, force_new=False):
        msg_id = self._resolve_panel_message_id(user_id, callback_query, force_new)
        extra = {"reply_markup": markup} if markup else {}
        
        try:
            if msg_id:
                self.get_telegram().edit_message_text(user_id, msg_id, text, extra)
                self._save_panel_message_state(user_id, msg_id, panel_mode)
                return
        except Exception as error:
            if "message is not modified" not in str(error).lower():
                self._log_error(f"Render panel edit failed for {user_id}", error)

        res = self.get_telegram().send_message(user_id, text, extra)
        if res:
            self._save_panel_message_state(user_id, res['message_id'], panel_mode)

    def send_main_menu(self, user_id, notice=None, callback_query=None, force_new=False):
        context = self._build_main_menu_context(user_id, notice)
        text, markup = UIProvider.get_main_menu(context)
        self.render_panel(user_id, text, markup, "user:home", callback_query=callback_query, force_new=force_new)

    # --- Domain-service wrappers ---

    def send_invoice(self, user_id):
        return payment_service.handle_buy_access(self, user_id)

    def handle_pre_checkout_query(self, pq):
        return dispatcher.dispatch_pre_checkout(self, pq)

    def handle_successful_payment(self, message):
        return dispatcher.dispatch_successful_payment(self, message)

    def handle_chat_join_request(self, request):
        return dispatcher.dispatch_chat_join_request(self, request)

    def approve_pending_request(self, user_id, force=False):
        return access_service.approve_pending_request(self, user_id, force=force)

    def ensure_invite_link(self, force=False):
        return access_service.ensure_invite_link(self, force=force)

    def refresh_invite_link(self):
        return access_service.refresh_invite_link(self)

    def update_settings(self, partial):
        return self.store.update_settings(partial)

    # --- Runtime side effects ---

    def grant_user_subscription(self, user_id, days):
        self.store.grant_subscription_days(user_id, days)
        self.notify_user(user_id, f"СЂСџР‹Рѓ Р вЂ™Р В°Р С Р Р†РЎвЂ№Р Т‘Р В°Р Р… Р Т‘Р С•РЎРѓРЎвЂљРЎС“Р С— Р Р…Р В° {days} Р Т‘Р Р….")
        self.approve_pending_request(user_id)

    def manual_recover_payment_access(self, admin_id, user_id, days, reason):
        user = self.store.manual_payment_recovery(admin_id, user_id, days, reason)
        if not user:
            return None
        self.log_event(
            "admin_recovery_used",
            admin_id=admin_id,
            user_id=user_id,
            days=days,
            reason=reason,
        )
        self.notify_user(user_id, f"СЂСџР‹Рѓ Р вЂќР С•РЎРѓРЎвЂљРЎС“Р С— Р Р†Р С•РЎРѓРЎРѓРЎвЂљР В°Р Р…Р С•Р Р†Р В»Р ВµР Р… Р Р†РЎР‚РЎС“РЎвЂЎР Р…РЎС“РЎР‹ Р Р…Р В° {days} Р Т‘Р Р….")
        self.approve_pending_request(user_id)
        return user

    def revoke_user_subscription(self, user_id, reason):
        return access_service.revoke_user_subscription(self, user_id, reason)

    def adjust_user_balance(self, user_id, amount):
        self.store.adjust_balance(user_id, amount)
        self.notify_user(user_id, f"СЂСџвЂ™В° Р вЂ™Р В°РЎв‚¬ Р В±Р В°Р В»Р В°Р Р…РЎРѓ Р С‘Р В·Р СР ВµР Р…Р ВµР Р… Р Р…Р В° {amount} Stars.")

    def set_user_notes(self, user_id, notes):
        self.store.set_user_notes(user_id, notes)

    def send_admin_message(self, user_id, text):
        try:
            self.get_telegram().send_message(user_id, f"РІСљвЂ°РїС‘РЏ <b>Р РЋР С•Р С•Р В±РЎвЂ°Р ВµР Р…Р С‘Р Вµ Р С•РЎвЂљ Р В°Р Т‘Р СР С‘Р Р…Р С‘РЎРѓРЎвЂљРЎР‚Р В°РЎвЂљР С•РЎР‚Р В°:</b>\n\n{text}")
            return True
        except Exception as error:
            self._log_error(f"Admin message failed for {user_id}", error)
            return False

    def _matches_broadcast_scope(self, user, scope, now):
        if scope == 'all':
            return True
        if scope == 'active':
            return (user.get('subscriptionUntil') or 0) > now
        if scope == 'expired':
            return (user.get('subscriptionUntil') or 0) <= now
        return False

    def broadcast_users(self, scope, text):
        users = self.store.list_users()
        count = 0
        now = self._now_ms()
        for u in users:
            if self._matches_broadcast_scope(u, scope, now):
                try:
                    self.get_telegram().send_message(u['id'], text)
                    count += 1
                except Exception as error:
                    self._log_error(f"Broadcast failed for {u['id']}", error)
        return count

    def notify_user(self, user_id, text):
        try:
            self.get_telegram().send_message(user_id, text)
        except Exception as error:
            self._log_error(f"Notify failed for {user_id}", error)

    # --- Maintenance wrappers ---

    def run_maintenance_loop(self):
        while not self.is_stopping:
            try:
                self.run_subscription_maintenance()
            except Exception as error:
                self._log_error("Maintenance error", error)

            interval = self.get_effective_system_settings()["serviceCheckIntervalMs"]
            time.sleep(max(10, interval / 1000))

    def _process_maintenance_user(self, user, now, warning_ms):
        settings = self.store.get_settings()
        return maintenance_service.process_maintenance_user(
            self,
            user,
            settings,
            now_ms=now,
            warning_ms=warning_ms,
        )

    def run_subscription_maintenance(self):
        result = maintenance_service.run_subscription_maintenance(self)
        self.last_maintenance_run_at = int(self._now_ms())
        return result

    # --- Compatibility wrappers ---

    def get_admin_view_model(self, filters=None):
        return compat_helpers.get_admin_view_model(self, filters)

    def get_user_editor_view_model(self, user_id):
        return compat_helpers.get_user_editor_view_model(self, user_id)

    def replace_state_from_json(self, js):
        return compat_helpers.replace_state_from_json(self, js)

    def replace_settings_from_json(self, js):
        return compat_helpers.replace_settings_from_json(self, js)

    def replace_templates_from_json(self, js):
        return compat_helpers.replace_templates_from_json(self, js)

    def save_user_structured(self, uid, form):
        return compat_helpers.save_user_structured(self, uid, form)

    def replace_user_json(self, uid, js):
        return compat_helpers.replace_user_json(self, uid, js)

    def delete_user(self, uid):
        return compat_helpers.delete_user(self, uid)

    def format_stats_text(self):
        return compat_helpers.format_stats_text(self)

    def get_template_context(self, user_id):
        return compat_helpers.get_template_context(self, user_id)

    def render_message_template(self, name, user_id):
        return compat_helpers.render_message_template(self, name, user_id)

    def send_join_link(self, user_id, callback_query=None):
        return access_service.send_join_link(self, user_id, callback_query=callback_query)

    def configure_channel(self, channel_id):
        return compat_helpers.configure_channel(self, channel_id)

    def send_user_help(self, user_id, callback_query=None, force_new=False):
        settings = self.store.get_settings()
        text, markup = UIProvider.get_user_help(settings.get("supportUsername", ""))
        self.render_panel(user_id, text, markup, "user:help", callback_query=callback_query, force_new=force_new)

    def get_dashboard_stats_extended(self):
        return compat_helpers.get_dashboard_stats_extended(self)
