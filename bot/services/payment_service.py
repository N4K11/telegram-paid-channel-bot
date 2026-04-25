from bot import logging_config
from bot.services import plan_service

def build_payment_payload(user_id):
    return f"subscription:{int(user_id)}"


def parse_payment_payload(payload):
    parsed = plan_service.parse_plan_payload(payload)
    if not parsed:
        return None
    return parsed["userId"]


def handle_buy_access(app, user_id, chat_id=None, message_id=None, plan_id=None):
    settings = app.store.get_settings()
    plan = plan_service.resolve_purchase_plan(settings, plan_id=plan_id)
    if not plan:
        app.send_main_menu(user_id, notice="Сейчас нет доступных тарифов.")
        return None

    params = {
        "chat_id": user_id,
        "title": settings["subscriptionName"],
        "description": settings["subscriptionDescription"],
        "payload": plan_service.build_invoice_payload(settings, user_id, plan),
        "currency": "XTR",
        "prices": [{"label": plan["title"], "amount": plan["priceStars"]}],
    }
    return app.get_telegram().send_invoice(params)


def handle_pre_checkout(app, pre_checkout_query):
    payload = pre_checkout_query.get("invoice_payload", "")
    parsed = plan_service.parse_plan_payload(payload)
    plan = None
    if parsed:
        plan = plan_service.resolve_purchase_plan(app.store.get_settings(), parsed.get("planId"))
    is_valid = parsed is not None and plan is not None
    return app.get_telegram().answer_pre_checkout_query(
        pre_checkout_query["id"],
        is_valid,
        "\u041e\u0448\u0438\u0431\u043a\u0430" if not is_valid else "",
    )


def handle_successful_payment(app, message):
    successful_payment = message["successful_payment"]
    user_id = message["from"]["id"]
    parsed = plan_service.parse_plan_payload(successful_payment["invoice_payload"])
    if not parsed:
        return {"status": "invalid_payload", "payment": None, "user": None}

    settings = app.store.get_settings()
    plan = plan_service.resolve_purchase_plan(settings, parsed.get("planId"))
    if not plan:
        return {"status": "plan_not_found", "payment": None, "user": None}

    payment = {
        "userId": user_id,
        "paidAt": int(app._now_ms()),
        "currency": successful_payment["currency"],
        "totalAmount": successful_payment["total_amount"],
        "telegramPaymentChargeId": successful_payment["telegram_payment_charge_id"],
        "invoicePayload": successful_payment["invoice_payload"],
    }
    result = app.store.record_payment_and_activate_subscription(
        user_id,
        payment,
        plan_service.apply_plan_to_settings(settings, plan),
    )
    if result["status"] == "duplicate":
        logging_config.log_app_event(
            app,
            "payment_duplicate",
            user_id=user_id,
            charge_id=payment["telegramPaymentChargeId"],
            amount=payment["totalAmount"],
        )
        return result
    if result["status"] != "processed":
        return result

    logging_config.log_app_event(
        app,
        "payment_received",
        user_id=user_id,
        charge_id=payment["telegramPaymentChargeId"],
        amount=payment["totalAmount"],
        currency=payment["currency"],
    )
    logging_config.log_app_event(
        app,
        "subscription_activated",
        user_id=user_id,
        subscription_until=result["user"].get("subscriptionUntil"),
        charge_id=payment["telegramPaymentChargeId"],
    )
    app.approve_pending_request(user_id)
    app.send_main_menu(user_id, notice="\u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u0440\u0438\u043d\u044f\u0442\u0430! \u0414\u043e\u0441\u0442\u0443\u043f \u043e\u0442\u043a\u0440\u044b\u0442.")
    return result

