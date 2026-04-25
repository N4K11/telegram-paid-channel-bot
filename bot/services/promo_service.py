import math
import re


FREE_DAYS_PROMO_TYPE = "free_days"
DISCOUNT_PERCENT_PROMO_TYPE = "discount_percent"
DISCOUNT_STARS_PROMO_TYPE = "discount_stars"
FIXED_PRICE_PROMO_TYPE = "fixed_price"
DISCOUNT_PROMO_TYPES = {
    DISCOUNT_PERCENT_PROMO_TYPE,
    DISCOUNT_STARS_PROMO_TYPE,
    FIXED_PRICE_PROMO_TYPE,
}
ALLOWED_PROMO_TYPES = DISCOUNT_PROMO_TYPES | {FREE_DAYS_PROMO_TYPE}
PROMO_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


def normalize_promo_code(code):
    normalized = str(code or "").strip().upper()
    if not normalized or not PROMO_CODE_RE.fullmatch(normalized):
        return None
    return normalized


def normalize_promo_type(promo_type):
    normalized = str(promo_type or "").strip().lower()
    if normalized not in ALLOWED_PROMO_TYPES:
        return None
    return normalized


def validate_promo_value(promo_type, value):
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return None

    if promo_type == FREE_DAYS_PROMO_TYPE:
        return numeric_value if numeric_value >= 1 else None
    if promo_type == DISCOUNT_PERCENT_PROMO_TYPE:
        return numeric_value if 1 <= numeric_value <= 99 else None
    if promo_type in (DISCOUNT_STARS_PROMO_TYPE, FIXED_PRICE_PROMO_TYPE):
        return numeric_value if numeric_value >= 1 else None
    return None


def validate_promo_limit(limit):
    try:
        numeric_limit = int(limit)
    except (TypeError, ValueError):
        return None
    return numeric_limit if numeric_limit >= 1 else None


def parse_admin_create_args(args):
    parts = str(args or "").split(None, 3)
    if len(parts) != 4:
        return None

    code = normalize_promo_code(parts[0])
    promo_type = normalize_promo_type(parts[1])
    if not code or not promo_type:
        return None

    value = validate_promo_value(promo_type, parts[2])
    limit = validate_promo_limit(parts[3])
    if value is None or limit is None:
        return None

    return code, promo_type, value, limit


def describe_promo(promo):
    if not promo:
        return "-"

    promo_type = promo.get("type")
    value = int(promo.get("value") or 0)
    if promo_type == FREE_DAYS_PROMO_TYPE:
        return f"+{value} days"
    if promo_type == DISCOUNT_PERCENT_PROMO_TYPE:
        return f"-{value}%"
    if promo_type == DISCOUNT_STARS_PROMO_TYPE:
        return f"-{value} Stars"
    if promo_type == FIXED_PRICE_PROMO_TYPE:
        return f"fixed {value} Stars"
    return str(value)


def _sorted_used_by(used_by):
    def sort_key(raw_user_id):
        try:
            return (0, int(raw_user_id))
        except (TypeError, ValueError):
            return (1, str(raw_user_id))

    return sorted((str(user_id) for user_id in used_by.keys()), key=sort_key)


def get_promo_stats(store, code):
    normalized_code = normalize_promo_code(code)
    if not normalized_code:
        return {"status": "invalid_code", "promo": None}

    promo = store.get_promo_code(normalized_code)
    if not promo:
        return {"status": "not_found", "promo": None}

    used_by = promo.get("usedBy") or {}
    sorted_used_by = _sorted_used_by(used_by)
    return {
        "status": "ok",
        "promo": promo,
        "usedCount": len(used_by),
        "remainingUses": max(0, int(promo.get("maxUses") or 0) - len(used_by)),
        "usedBy": sorted_used_by,
    }


def format_promo_stats(result):
    status = result.get("status")
    if status == "invalid_code":
        return "Промокод должен содержать только A-Z, 0-9, _ или -."
    if status == "not_found":
        return "Промокод не найден."

    promo = result["promo"]
    state_text = "enabled" if promo.get("enabled", True) else "disabled"
    used_by = result.get("usedBy") or []
    used_preview = ", ".join(used_by[:10]) or "-"
    return (
        f"Promo code: <b>{promo['code']}</b>\n"
        f"Type: <b>{promo['type']}</b>\n"
        f"Value: <b>{describe_promo(promo)}</b>\n"
        f"State: <b>{state_text}</b>\n"
        f"Max uses: <b>{promo.get('maxUses', 0)}</b>\n"
        f"Used: <b>{result.get('usedCount', 0)}</b>\n"
        f"Remaining: <b>{result.get('remainingUses', 0)}</b>\n"
        f"Used by: <code>{used_preview}</code>"
    )


def format_admin_create_result(result):
    status = result.get("status")
    promo = result.get("promo")
    if status == "created":
        return (
            f"Промокод <b>{promo['code']}</b> создан.\n"
            f"Type: <b>{promo['type']}</b>\n"
            f"Value: <b>{describe_promo(promo)}</b>\n"
            f"Limit: <b>{promo['maxUses']}</b>"
        )
    if status == "exists":
        return f"Промокод <b>{promo['code']}</b> уже существует."
    return "Не удалось создать промокод."


def format_admin_disable_result(result, code):
    status = result.get("status")
    promo = result.get("promo")
    if status == "disabled":
        return f"Промокод <b>{promo['code']}</b> отключён."
    if status == "already_disabled":
        return f"Промокод <b>{promo['code']}</b> уже отключён."
    if status == "not_found":
        return f"Промокод <b>{code}</b> не найден."
    return "Не удалось отключить промокод."


def is_discount_promo(promo):
    return bool(promo and promo.get("type") in DISCOUNT_PROMO_TYPES)


def calculate_discounted_amount(base_amount, promo):
    base_amount = int(base_amount)
    if not is_discount_promo(promo):
        return base_amount

    promo_type = promo.get("type")
    value = int(promo.get("value") or 0)
    if promo_type == DISCOUNT_PERCENT_PROMO_TYPE:
        discounted = base_amount - math.floor(base_amount * value / 100)
        return max(1, discounted)
    if promo_type == DISCOUNT_STARS_PROMO_TYPE:
        return max(1, base_amount - value)
    if promo_type == FIXED_PRICE_PROMO_TYPE:
        return max(1, value)
    return base_amount


def get_pending_discount_context(store, user_id, plan, total_amount=None):
    base_amount = int(plan["priceStars"])
    user = store.get_user(user_id) or {}
    pending_code = normalize_promo_code(user.get("pendingPromoCode"))
    if not pending_code:
        return {
            "status": "none",
            "promo": None,
            "pendingCode": None,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }

    promo = store.get_promo_code(pending_code)
    if not promo:
        return {
            "status": "not_found",
            "promo": None,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }
    if not promo.get("enabled", True):
        return {
            "status": "disabled",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }
    if not is_discount_promo(promo):
        return {
            "status": "invalid_type",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }

    used_by = promo.get("usedBy") or {}
    if str(user_id) in used_by:
        return {
            "status": "already_used",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }

    max_uses = int(promo.get("maxUses") or 0)
    if len(used_by) >= max_uses:
        return {
            "status": "max_uses_reached",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }

    discounted_amount = calculate_discounted_amount(base_amount, promo)
    if total_amount is None:
        return {
            "status": "applied",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": discounted_amount,
        }

    numeric_total = int(total_amount)
    if numeric_total == discounted_amount:
        return {
            "status": "applied",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": discounted_amount,
        }
    if numeric_total == base_amount:
        return {
            "status": "ignored",
            "promo": promo,
            "pendingCode": pending_code,
            "baseAmount": base_amount,
            "finalAmount": base_amount,
        }
    return {
        "status": "amount_mismatch",
        "promo": promo,
        "pendingCode": pending_code,
        "baseAmount": base_amount,
        "finalAmount": discounted_amount,
    }


def apply_user_promo(app, user_id, code):
    normalized_code = normalize_promo_code(code)
    if not normalized_code:
        return {"status": "invalid_code", "promo": None}

    promo = app.store.get_promo_code(normalized_code)
    if not promo:
        return {"status": "not_found", "promo": None}
    if not promo.get("enabled", True):
        return {"status": "disabled", "promo": promo}

    used_by = promo.get("usedBy") or {}
    if str(user_id) in used_by:
        return {"status": "already_used", "promo": promo}

    max_uses = int(promo.get("maxUses") or 0)
    if len(used_by) >= max_uses:
        return {"status": "max_uses_reached", "promo": promo}

    if promo.get("type") == FREE_DAYS_PROMO_TYPE:
        result = app.store.redeem_free_days_promo(user_id, normalized_code)
        if result.get("status") == "processed":
            app.approve_pending_request(user_id)
        return result

    app.store.set_user_pending_promo_code(user_id, normalized_code)
    return {"status": "pending_invoice", "promo": promo}


def format_user_promo_result(result):
    status = result.get("status")
    promo = result.get("promo")

    if status == "processed":
        return (
            f"Промокод <b>{promo['code']}</b> применён. "
            f"Подписка продлена на <b>{promo['value']}</b> дн."
        )
    if status == "pending_invoice":
        return (
            f"Промокод <b>{promo['code']}</b> принят. "
            "Он будет применён к следующему счёту."
        )
    if status == "invalid_code":
        return "Промокод должен содержать только A-Z, 0-9, _ или -."
    if status == "not_found":
        return "Промокод не найден."
    if status == "disabled":
        return "Этот промокод отключён."
    if status == "already_used":
        return "Этот промокод уже использован вами."
    if status == "max_uses_reached":
        return "Лимит использований этого промокода исчерпан."
    if status == "invalid_type":
        return "Этот промокод нельзя применить этой командой."
    return "Не удалось применить промокод."
