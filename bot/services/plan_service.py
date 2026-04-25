import copy


LIFETIME_SENTINEL_DAYS = 365000


def _normalize_plan(raw_plan):
    if not isinstance(raw_plan, dict):
        return None

    raw_id = str(raw_plan.get("id") or "").strip()
    raw_title = str(raw_plan.get("title") or "").strip()
    if not raw_id or not raw_title:
        return None

    try:
        price_stars = int(raw_plan.get("priceStars"))
    except (TypeError, ValueError):
        return None
    if price_stars < 1:
        return None

    raw_duration = raw_plan.get("durationDays")
    is_lifetime = bool(raw_plan.get("isLifetime"))
    if raw_duration in (0, "0") or is_lifetime:
        is_lifetime = True
        duration_days = 0
    else:
        if raw_duration in (None, ""):
            return None
        try:
            duration_days = int(raw_duration)
        except (TypeError, ValueError):
            return None
        if duration_days < 1:
            return None

    return {
        "id": raw_id,
        "title": raw_title,
        "priceStars": price_stars,
        "durationDays": duration_days,
        "enabled": bool(raw_plan.get("enabled", True)),
        "isLifetime": is_lifetime,
    }


def _build_fallback_plan(settings):
    return {
        "id": "default",
        "title": str(settings.get("subscriptionName") or "Доступ").strip() or "Доступ",
        "priceStars": int(settings["subscriptionPriceStars"]),
        "durationDays": int(settings["subscriptionDurationDays"]),
        "enabled": True,
        "isLifetime": False,
        "isFallback": True,
    }


def get_all_plans(settings):
    raw_plans = settings.get("plans")
    if not raw_plans:
        return [_build_fallback_plan(settings)]

    plans = []
    for raw_plan in raw_plans:
        normalized = _normalize_plan(raw_plan)
        if normalized:
            plans.append(normalized)
    return plans


def get_enabled_plans(settings):
    return [plan for plan in get_all_plans(settings) if plan.get("enabled")]


def has_multiple_enabled_plans(settings):
    return len(get_enabled_plans(settings)) > 1


def get_default_plan(settings):
    plans = get_enabled_plans(settings)
    return copy.deepcopy(plans[0]) if plans else None


def get_plan(settings, plan_id, enabled_only=True):
    normalized_plan_id = str(plan_id or "").strip()
    if not normalized_plan_id:
        return get_default_plan(settings)

    plans = get_enabled_plans(settings) if enabled_only else get_all_plans(settings)
    for plan in plans:
        if plan["id"] == normalized_plan_id:
            return copy.deepcopy(plan)
    return None


def build_plan_payload(user_id, plan_id=None):
    normalized_user_id = int(user_id)
    normalized_plan_id = str(plan_id or "").strip()
    if not normalized_plan_id:
        return f"subscription:{normalized_user_id}"
    return f"subscription:{normalized_user_id}:{normalized_plan_id}"


def parse_plan_payload(payload):
    text = str(payload or "").strip()
    parts = text.split(":")
    if len(parts) not in (2, 3) or parts[0] != "subscription":
        return None

    try:
        user_id = int(parts[1])
    except (TypeError, ValueError):
        return None

    plan_id = None
    if len(parts) == 3:
        plan_id = parts[2].strip() or None
        if plan_id is None:
            return None

    return {"userId": user_id, "planId": plan_id}


def resolve_purchase_plan(settings, plan_id=None):
    normalized_plan_id = str(plan_id or "").strip()
    if not normalized_plan_id:
        return get_default_plan(settings)
    return get_plan(settings, normalized_plan_id, enabled_only=True)


def build_invoice_payload(settings, user_id, plan):
    if plan.get("isFallback"):
        return build_plan_payload(user_id)
    return build_plan_payload(user_id, plan["id"])


def apply_plan_to_settings(settings, plan):
    resolved = copy.deepcopy(settings)
    resolved["subscriptionPriceStars"] = plan["priceStars"]
    resolved["subscriptionDurationDays"] = plan["durationDays"] or LIFETIME_SENTINEL_DAYS
    resolved["isLifetimePlan"] = bool(plan.get("isLifetime"))
    resolved["selectedPlanId"] = plan["id"]
    resolved["selectedPlanTitle"] = plan["title"]
    return resolved


def format_plan_duration(plan):
    if plan.get("isLifetime"):
        return "Навсегда"

    duration_days = plan["durationDays"]
    if duration_days == 1:
        return "1 день"
    if duration_days % 10 == 1 and duration_days % 100 != 11:
        return f"{duration_days} день"
    if duration_days % 10 in (2, 3, 4) and duration_days % 100 not in (12, 13, 14):
        return f"{duration_days} дня"
    return f"{duration_days} дней"


def format_plan_label(plan):
    return f"{plan['title']} — {plan['priceStars']} Stars"
