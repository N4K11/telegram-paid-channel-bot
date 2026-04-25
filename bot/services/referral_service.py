import re


REFERRAL_START_PREFIX = "ref_"
REFERRAL_REWARD_DAYS = 3
REFERRAL_CODE_RE = re.compile(r"^[A-Z0-9]{4,16}$")


def normalize_referral_code(code):
    normalized = str(code or "").strip().upper()
    if not normalized or not REFERRAL_CODE_RE.fullmatch(normalized):
        return None
    return normalized


def parse_start_referral_parameter(parameter):
    value = str(parameter or "").strip()
    if not value.lower().startswith(REFERRAL_START_PREFIX):
        return None
    return normalize_referral_code(value[len(REFERRAL_START_PREFIX):])


def apply_start_referral(app, user_id, parameter):
    raw_parameter = str(parameter or "").strip()
    if not raw_parameter.lower().startswith(REFERRAL_START_PREFIX):
        return {"status": "ignored", "user": app.store.get_user(user_id), "referrer": None}
    referral_code = parse_start_referral_parameter(raw_parameter)
    if not referral_code:
        return {"status": "invalid_code", "user": app.store.get_user(user_id), "referrer": None}
    return app.store.attach_referral(user_id, referral_code)


def format_start_referral_result(result):
    status = result.get("status")
    if status == "attached":
        return "Реферальный код принят. После первой успешной оплаты по нему будет выдан бонус +3 дн."
    if status == "self_referral":
        return "Нельзя использовать собственный реферальный код."
    if status == "already_set":
        return "Реферальный код уже был сохранён раньше."
    if status == "not_found":
        return "Реферальный код не найден."
    if status == "invalid_code":
        return "Некорректный формат реферального кода."
    return None
