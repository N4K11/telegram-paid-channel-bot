from bot.ui_admin import (
    get_admin_broadcast_menu,
    get_admin_main,
    get_admin_payment_anomalies,
    get_admin_payment_diagnostics,
    get_admin_settings,
    get_admin_template_editor,
    get_admin_templates_menu,
    get_admin_user_details,
    get_admin_users,
)
from bot.ui_user import get_main_menu, get_plan_picker, get_user_help


class UIProvider:
    get_main_menu = staticmethod(get_main_menu)
    get_plan_picker = staticmethod(get_plan_picker)
    get_user_help = staticmethod(get_user_help)
    get_admin_main = staticmethod(get_admin_main)
    get_admin_settings = staticmethod(get_admin_settings)
    get_admin_users = staticmethod(get_admin_users)
    get_admin_user_details = staticmethod(get_admin_user_details)
    get_admin_payment_diagnostics = staticmethod(get_admin_payment_diagnostics)
    get_admin_payment_anomalies = staticmethod(get_admin_payment_anomalies)
    get_admin_templates_menu = staticmethod(get_admin_templates_menu)
    get_admin_template_editor = staticmethod(get_admin_template_editor)
    get_admin_broadcast_menu = staticmethod(get_admin_broadcast_menu)


__all__ = [
    "UIProvider",
    "get_main_menu",
    "get_plan_picker",
    "get_user_help",
    "get_admin_main",
    "get_admin_settings",
    "get_admin_users",
    "get_admin_user_details",
    "get_admin_payment_diagnostics",
    "get_admin_payment_anomalies",
    "get_admin_templates_menu",
    "get_admin_template_editor",
    "get_admin_broadcast_menu",
]
