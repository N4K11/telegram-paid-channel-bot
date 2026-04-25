from bot import logging_config
from bot.services import plan_service
from bot.services import promo_service


STALE_PROMO_STATUSES = {"not_found", "disabled", "already_used", "max_uses_reached", "invalid_type"}


def build_payment_payload(user_id):
    return f"subscription:{int(user_id)}"


def parse_payment_payload(payload):
    parsed = plan_service.parse_plan_payload(payload)
    if not parsed:
        return None
    return parsed["userId"]


def _clear_stale_pending_promo(app, user_id, promo_context):
    if promo_context.get("status") in STALE_PROMO_STATUSES and promo_context.get("pendingCode"):
        app.store.clear_user_pending_promo_code(user_id)


def _resolve_invoice_amount(app, user_id, plan, total_amount=None):
    promo_context = promo_service.get_pending_discount_context(
        app.store,
        user_id,
        plan,
        total_amount=total_amount,
    )
    _clear_stale_pending_promo(app, user_id, promo_context)
    if promo_context.get("status") == "applied":
        return promo_context.get("promo"), int(promo_context.get("finalAmount") or plan["priceStars"])
    return None, int(promo_context.get("finalAmount") or plan["priceStars"])


def handle_buy_access(app, user_id, chat_id=None, message_id=None, plan_id=None):
    settings = app.store.get_settings()
    plan = plan_service.resolve_purchase_plan(settings, plan_id=plan_id)
    if not plan:
        app.send_main_menu(user_id, notice="Сейчас нет доступных тарифов.")
        return None

    _, amount = _resolve_invoice_amount(app, user_id, plan)
    params = {
        "chat_id": user_id,
        "title": settings["subscriptionName"],
        "description": settings["subscriptionDescription"],
        "payload": plan_service.build_invoice_payload(settings, user_id, plan),
        "currency": "XTR",
        "prices": [{"label": plan["title"], "amount": amount}],
    }
    return app.get_telegram().send_invoice(params)


def handle_pre_checkout(app, pre_checkout_query):
    payload = pre_checkout_query.get("invoice_payload", "")
    parsed = plan_service.parse_plan_payload(payload)
    plan = None
    is_valid = False
    if parsed:
        plan = plan_service.resolve_purchase_plan(app.store.get_settings(), parsed.get("planId"))
    if parsed is not None and plan is not None:
        query_user_id = ((pre_checkout_query.get("from") or {}).get("id") or parsed["userId"])
        promo_context = promo_service.get_pending_discount_context(
            app.store,
            query_user_id,
            plan,
            total_amount=pre_checkout_query.get("total_amount"),
        )
        _clear_stale_pending_promo(app, query_user_id, promo_context)
        is_valid = promo_context.get("status") != "amount_mismatch"
    return app.get_telegram().answer_pre_checkout_query(
        pre_checkout_query["id"],
        is_valid,
        "Ошибка" if not is_valid else "",
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

    promo_context = promo_service.get_pending_discount_context(
        app.store,
        user_id,
        plan,
        total_amount=successful_payment["total_amount"],
    )
    _clear_stale_pending_promo(app, user_id, promo_context)
    promo_code = promo_context.get("pendingCode") if promo_context.get("status") == "applied" else None

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
        promo_code=promo_code,
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
    if result.get("rewardedReferrerId"):
        referrer = app.store.get_user(result["rewardedReferrerId"])
        if referrer and referrer.get("pendingJoinRequest"):
            app.approve_pending_request(result["rewardedReferrerId"])
    app.send_main_menu(user_id, notice="Оплата принята! Доступ открыт.")
    return result
