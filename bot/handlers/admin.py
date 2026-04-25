from bot.handlers import admin_actions
from bot.handlers import admin_render
from bot.ui import UIProvider


class AdminHandler:
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store
        self.fsm = bot.fsm
        self.ui = UIProvider

    def get_context(self, chat_id):
        if not self.bot.is_authorized_admin({"id": chat_id}):
            return None
        return True

    def handle_callback(self, callback_query):
        return admin_actions.handle_callback(self, callback_query)

    def handle_text(self, message):
        return admin_actions.handle_text(self, message)

    def _handle_input_trigger(self, user_id, data):
        return admin_actions.handle_input_trigger(self, user_id, data)

    def _handle_broadcast_trigger(self, user_id, data):
        return admin_actions.handle_broadcast_trigger(self, user_id, data)

    def _handle_template_edit_trigger(self, user_id, key):
        return admin_actions.handle_template_edit_trigger(self, user_id, key)

    def _render_main(self, user_id, notice=None, force_new=False):
        return admin_render.render_main(self, user_id, notice=notice, force_new=force_new)

    def _render_settings(self, user_id, notice=None):
        return admin_render.render_settings(self, user_id, notice=notice)

    def _render_templates_menu(self, user_id, notice=None):
        return admin_render.render_templates_menu(self, user_id, notice=notice)

    def _render_users(self, user_id, page, notice=None):
        return admin_render.render_users(self, user_id, page, notice=notice)

    def _render_user_details(self, user_id, target_id, notice=None):
        return admin_render.render_user_details(self, user_id, target_id, notice=notice)

    def _render_stats(self, user_id):
        return admin_render.render_stats(self, user_id)

    def _render_payment_diagnostics(self, user_id, target_id, notice=None):
        return admin_render.render_payment_diagnostics(self, user_id, target_id, notice=notice)

    def _render_payment_anomalies(self, user_id, limit=20, notice=None):
        return admin_render.render_payment_anomalies(self, user_id, limit=limit, notice=notice)

    def _render_input_request(self, user_id, text):
        return admin_render.render_input_request(self, user_id, text)
