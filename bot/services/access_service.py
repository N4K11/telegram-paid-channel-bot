def get_join_link(app, user_id=None):
    return app.store.get_effective_invite_link(app.config.channel_invite_link)


def ensure_invite_link(app, force=False):
    settings = app.store.get_settings()
    if not force and (settings.get("channelInviteLink") or app.store.get_meta().get("joinInviteLink")):
        return app.store.get_effective_invite_link()

    system = app.get_effective_system_settings()
    if system["autoCreateInviteLink"]:
        response = app.get_telegram().create_chat_invite_link(system["channelId"], "Bot Link", True)
        link = response.get("invite_link", "")
        app.store.set_join_invite_link(link)
        return link
    return ""


def refresh_invite_link(app):
    return ensure_invite_link(app, force=True)


def handle_chat_join_request(app, request):
    user_id = request["from"]["id"]
    chat_id = request["chat"]["id"]
    app.store.set_user_pending_join_request(
        user_id,
        {"chatId": chat_id, "createdAt": int(app._now_ms())},
    )
    if app.store.is_subscription_active(user_id):
        app.approve_pending_request(user_id)
    else:
        app.send_main_menu(user_id, notice="\u0417\u0430\u044f\u0432\u043a\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0430. \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u0435 \u0434\u043e\u0441\u0442\u0443\u043f \u0434\u043b\u044f \u0432\u0445\u043e\u0434\u0430.")


def approve_pending_request(app, user_id, force=False):
    is_active = app.store.is_subscription_active(user_id)

    if is_active or force:
        channel_id = app.get_effective_system_settings()["channelId"]
        try:
            app.get_telegram().approve_chat_join_request(channel_id, user_id)
            app.store.clear_user_pending_join_request(user_id)
            app.store.set_user_channel_member_status(user_id, "member")
            return True
        except Exception as error:
            app._log_error(f"Approval failed for {user_id}", error)
    return False


def decline_pending_join_request(app, user_id):
    user = app.store.get_user(user_id)
    pending = user.get("pendingJoinRequest") if user else None
    if not pending:
        return False

    try:
        app.get_telegram().decline_chat_join_request(app.get_effective_system_settings()["channelId"], user_id)
        app.store.clear_user_pending_join_request(user_id)
        return True
    except Exception as error:
        app._log_error(f"Decline join request failed for {user_id}", error)
        return False


def prune_expired_pending_join_requests(app, now_ms=None, users=None):
    if now_ms is None:
        now_ms = app._now_ms()
    if users is None:
        users = app.store.list_users()

    declined = 0
    for user in users:
        pending = user.get("pendingJoinRequest")
        if not pending or not pending.get("createdAt"):
            continue
        if (now_ms - pending["createdAt"]) <= app.JOIN_REQUEST_TTL_MS:
            continue
        if decline_pending_join_request(app, user["id"]):
            declined += 1
    return declined


def revoke_user_subscription(app, user_id, reason):
    app.store.revoke_subscription(user_id, reason)
    try:
        channel_id = app.get_effective_system_settings()["channelId"]
        app.get_telegram().ban_chat_member(channel_id, user_id)
        app.get_telegram().unban_chat_member(channel_id, user_id)
    except Exception as error:
        app._log_error(f"Revoke channel access failed for {user_id}", error)


def send_join_link(app, user_id, callback_query=None):
    is_active = app.store.is_subscription_active(user_id)
    if not is_active:
        text = app.render_message_template("noSubscription", user_id)
        markup = {
            "inline_keyboard": [
                [{"text": "\U0001f4b3 \u041a\u0443\u043f\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f", "callback_data": "buy"}],
                [{"text": "\U0001f519 \u041d\u0430\u0437\u0430\u0434", "callback_data": "panel:main"}],
            ]
        }
        app.render_panel(user_id, text, markup, "user:join", callback_query=callback_query)
        return

    invite_link = get_join_link(app, user_id)
    if not invite_link:
        text = app.render_message_template("noInviteLink", user_id)
        markup = {"inline_keyboard": [[{"text": "\U0001f519 \u041d\u0430\u0437\u0430\u0434", "callback_data": "panel:main"}]]}
        app.render_panel(user_id, text, markup, "user:join", callback_query=callback_query)
        return

    text = app.render_message_template("joinInstructions", user_id)
    markup = {
        "inline_keyboard": [
            [{"text": "\U0001f517 \u0412\u0441\u0442\u0443\u043f\u0438\u0442\u044c \u0432 \u043a\u0430\u043d\u0430\u043b", "url": invite_link}],
            [{"text": "\U0001f519 \u041d\u0430\u0437\u0430\u0434", "callback_data": "panel:main"}],
        ]
    }
    app.render_panel(user_id, text, markup, "user:join", callback_query=callback_query)
