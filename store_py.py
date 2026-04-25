import copy
import json
import os
import random
import threading
import time

from utils_py import add_days, now_iso


def create_default_state():
    timestamp = now_iso()
    return {
        "meta": {
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "lastUpdateId": 0,
            "botInfo": None,
            "joinInviteLink": "",
            "joinInviteLinkCreatedAt": None
        },
        "settings": {
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
            "warningDays": 3,
            "recurringPaymentsEnabled": False,
            "subscriptionName": "Доступ в приватный канал",
            "subscriptionDescription": "Оплата доступа к приватному Telegram-каналу",
            "supportUsername": "",
            "welcomeText": "Оформите подписку, и бот выдаст доступ в приватный канал.",
            "channelInviteLink": "",
            "botTokenOverride": "",
            "channelId": "",
            "appTimezone": "",
            "adminUsername": "",
            "adminPassword": "",
            "autoCreateInviteLink": None,
            "pollTimeoutSeconds": 25,
            "serviceCheckIntervalMs": 60000,
            "messageTemplates": {
                "paymentReceived": "Оплата получена. Подписка активна до <b>{{subscriptionUntil}}</b>.",
                "joinApproved": "Запрос на вступление в канал одобрен.",
                "joinPending": "Запрос на вступление получен. Как только оплата будет подтверждена, я одобрю его автоматически.",
                "subscriptionExpiring": "Подписка скоро закончится: <b>{{subscriptionUntil}}</b>. Продлите доступ заранее.",
                "subscriptionExpired": "Срок подписки истёк. Доступ к приватному каналу отключён.",
                "noSubscription": "Сначала нужно оформить или продлить подписку.",
                "noInviteLink": "Ссылка на канал пока не настроена. Напишите администратору.",
                "adminGrant": "Администратор выдал вам подписку до <b>{{subscriptionUntil}}</b>.",
                "adminRevoke": "Доступ к приватному каналу был отключён администратором.",
                "support": "По вопросам оплаты напишите {{supportMention}}.",
                "joinInstructions": "Ваша подписка активна. Вступайте в канал по ссылке:\n{{inviteLink}}\n\nПосле отправки заявки бот одобрит её автоматически."
            }
        },
        "users": {},
        "payments": {},
        "auditLog": []
    }


def merge_settings(settings=None):
    defaults = create_default_state()["settings"]
    incoming = settings or {}
    merged = copy.deepcopy(defaults)
    merged.update(incoming)
    merged["messageTemplates"] = {
        **defaults["messageTemplates"],
        **incoming.get("messageTemplates", {})
    }
    return merged


def merge_state(state=None):
    defaults = create_default_state()
    incoming = state or {}
    merged = copy.deepcopy(defaults)
    merged.update(incoming)
    merged["meta"] = {**defaults["meta"], **incoming.get("meta", {})}
    merged["settings"] = merge_settings(incoming.get("settings"))
    merged["users"] = incoming.get("users", {}) or {}
    merged["payments"] = incoming.get("payments", {}) or {}
    merged["auditLog"] = incoming.get("auditLog", []) or []
    return merged


class JsonStore:
    def __init__(self, file_path):
        self.file_path = file_path
        self.temp_file_path = f"{file_path}.tmp"
        self.lock = threading.RLock()
        self._ensure_file()
        self.state = self._load()

    def _write_json_file(self, file_path, payload):
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())

    def _cleanup_temp_file(self):
        try:
            if os.path.exists(self.temp_file_path):
                os.remove(self.temp_file_path)
        except OSError:
            pass

    def _ensure_file(self):
        directory = os.path.dirname(self.file_path) or "."
        os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.file_path):
            self._write_json_file(self.file_path, create_default_state())

    def _load(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid JSON in store file {self.file_path}: {error}") from error
        except OSError as error:
            raise RuntimeError(f"Failed to read store file {self.file_path}: {error}") from error

        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid store root in {self.file_path}: expected JSON object")

        return merge_state(payload)

    def _save_unlocked(self):
        self.state["meta"]["updatedAt"] = now_iso()
        try:
            self._write_json_file(self.temp_file_path, self.state)
            os.replace(self.temp_file_path, self.file_path)
        except Exception:
            self._cleanup_temp_file()
            raise

    def _mutate_and_save(self, mutator):
        # A full deepcopy rollback is acceptable for the current small JSON store.
        # If the state grows substantially, move to a finer transaction model or SQLite.
        backup_state = copy.deepcopy(self.state)
        try:
            result = mutator(self.state)
            self._save_unlocked()
            return result
        except Exception:
            self.state = backup_state
            raise

    def _clone_user(self, user):
        return copy.deepcopy(user) if user else None

    @staticmethod
    def _user_display_name(user):
        if not user:
            return "ID -"

        parts = [user.get("firstName"), user.get("lastName")]
        parts = [part for part in parts if part]
        if parts:
            return " ".join(parts)

        username = user.get("username")
        if username:
            return f"@{username}"

        return f"ID {user.get('id', '-')}"

    def _audit_entry(self, entry):
        return {
            "id": f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
            "createdAt": now_iso(),
            **entry
        }

    def _append_audit_entry(self, state, entry):
        state["auditLog"].insert(0, self._audit_entry(entry))
        state["auditLog"] = state["auditLog"][:500]

    def _apply_record_payment_to_user(self, user, payment):
        user["totalSpentStars"] = (user.get("totalSpentStars") or 0) + payment["totalAmount"]
        user["totalPaymentsCount"] = (user.get("totalPaymentsCount") or 0) + 1
        user["lastPaymentAt"] = payment["paidAt"]
        user["updatedAt"] = now_iso()

    def _apply_subscription_activation(self, user, payment, settings, current_time_ms):
        if settings.get("recurringPaymentsEnabled") and payment.get("subscriptionExpirationDate"):
            next_expiration = max(
                payment["subscriptionExpirationDate"],
                user.get("subscriptionUntil") or 0,
                current_time_ms
            )
        else:
            base_time = (
                user.get("subscriptionUntil")
                if user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms
                else current_time_ms
            )
            next_expiration = add_days(base_time, settings["subscriptionDurationDays"])

        user["subscriptionUntil"] = next_expiration
        user["lastWarningAt"] = None
        user["lastAccessGrantedAt"] = current_time_ms
        user["updatedAt"] = now_iso()

    def _default_user(self, user_id):
        return {
            "id": int(user_id),
            "username": "",
            "firstName": "",
            "lastName": "",
            "languageCode": "",
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
            "balanceStars": 0,
            "subscriptionUntil": None,
            "totalSpentStars": 0,
            "totalPaymentsCount": 0,
            "lastPaymentAt": None,
            "lastWarningAt": None,
            "lastAccessGrantedAt": None,
            "lastAccessRevokedAt": None,
            "pendingJoinRequest": None,
            "channelMemberStatus": "unknown",
            "notes": "",
            "panelMessageId": None,
            "panelMode": "user:home"
        }

    def get_state(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def replace_state(self, next_state):
        with self.lock:
            def mutate(state):
                replacement = merge_state(next_state)
                state.clear()
                state.update(replacement)

            self._mutate_and_save(mutate)
            return copy.deepcopy(self.state)

    def get_meta(self):
        with self.lock:
            return copy.deepcopy(self.state["meta"])

    def get_settings(self):
        with self.lock:
            return copy.deepcopy(self.state["settings"])

    def update_settings(self, partial_settings):
        with self.lock:
            def mutate(state):
                current = copy.deepcopy(state["settings"])
                current.update(partial_settings)
                current["messageTemplates"] = {
                    **state["settings"].get("messageTemplates", {}),
                    **partial_settings.get("messageTemplates", {})
                }
                state["settings"] = merge_settings(current)

            self._mutate_and_save(mutate)
            return copy.deepcopy(self.state["settings"])

    def replace_settings(self, settings):
        with self.lock:
            self._mutate_and_save(lambda state: state.__setitem__("settings", merge_settings(settings)))
            return copy.deepcopy(self.state["settings"])

    def add_audit_log(self, entry):
        with self.lock:
            self._mutate_and_save(lambda state: self._append_audit_entry(state, entry))

    def get_audit_log(self, limit=30):
        with self.lock:
            return copy.deepcopy(self.state["auditLog"][:limit])

    def ensure_user(self, telegram_user):
        with self.lock:
            user_id = str(telegram_user["id"])

            def mutate(state):
                current = copy.deepcopy(state["users"].get(user_id, self._default_user(user_id)))
                current["username"] = telegram_user.get("username") or current.get("username") or ""
                current["firstName"] = telegram_user.get("first_name") or telegram_user.get("firstName") or current.get("firstName") or ""
                current["lastName"] = telegram_user.get("last_name") or telegram_user.get("lastName") or current.get("lastName") or ""
                current["languageCode"] = telegram_user.get("language_code") or telegram_user.get("languageCode") or current.get("languageCode") or ""
                current["updatedAt"] = now_iso()
                state["users"][user_id] = current

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][user_id])

    def get_user(self, user_id):
        with self.lock:
            return self._clone_user(self.state["users"].get(str(user_id)))

    def list_users(self):
        with self.lock:
            users = [copy.deepcopy(user) for user in self.state["users"].values()]
        return sorted(
            users,
            key=lambda item: ((item.get("subscriptionUntil") or 0), item.get("id") or 0),
            reverse=True
        )

    def replace_user(self, user_id, raw_user):
        normalized_id = str(user_id or raw_user.get("id") or "")
        if not normalized_id:
            raise RuntimeError("User id is required")

        with self.lock:
            def mutate(state):
                previous = copy.deepcopy(state["users"].get(normalized_id, self._default_user(normalized_id)))
                created_at = raw_user.get("createdAt") or previous.get("createdAt") or now_iso()
                state["users"][normalized_id] = {
                    **previous,
                    **raw_user,
                    "id": int(normalized_id),
                    "createdAt": created_at,
                    "updatedAt": now_iso()
                }
                self._append_audit_entry(state, {
                    "type": "replace_user",
                    "userId": int(normalized_id)
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def update_user_fields(self, user_id, fields):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                current = state["users"][normalized_id]
                state["users"][normalized_id] = {
                    **current,
                    **fields,
                    "id": int(normalized_id),
                    "updatedAt": now_iso()
                }
                self._append_audit_entry(state, {
                    "type": "update_user_fields",
                    "userId": int(normalized_id)
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def delete_user(self, user_id):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return False

            def mutate(state):
                state["users"].pop(normalized_id, None)
                self._append_audit_entry(state, {
                    "type": "delete_user",
                    "userId": int(normalized_id)
                })

            self._mutate_and_save(mutate)
        return True

    def get_payments(self):
        with self.lock:
            payments = [copy.deepcopy(item) for item in self.state["payments"].values()]
        return sorted(payments, key=lambda item: item.get("paidAt", 0), reverse=True)

    def has_payment(self, charge_id):
        with self.lock:
            return bool(self.state["payments"].get(charge_id))

    def record_payment(self, payment):
        with self.lock:
            payment_id = payment["telegramPaymentChargeId"]
            existing = self.state["payments"].get(payment_id)
            if existing:
                return copy.deepcopy(existing)

            def mutate(state):
                state["payments"][payment_id] = payment
                user = state["users"].get(str(payment["userId"]))
                if user:
                    self._apply_record_payment_to_user(user, payment)

            self._mutate_and_save(mutate)
            return copy.deepcopy(self.state["payments"][payment_id])

    def record_payment_and_activate_subscription(self, user_id, payment, settings):
        normalized_id = str(user_id)
        with self.lock:
            user = self.state["users"].get(normalized_id)
            if not user:
                return {"status": "user_not_found", "payment": None, "user": None}

            payment_id = payment["telegramPaymentChargeId"]
            existing = self.state["payments"].get(payment_id)
            if existing:
                return {
                    "status": "duplicate",
                    "payment": copy.deepcopy(existing),
                    "user": self._clone_user(user),
                }

            def mutate(state):
                current_user = state["users"][normalized_id]
                state["payments"][payment_id] = payment
                self._apply_record_payment_to_user(current_user, payment)
                self._apply_subscription_activation(
                    current_user,
                    payment,
                    settings,
                    int(time.time() * 1000),
                )

            self._mutate_and_save(mutate)
            return {
                "status": "processed",
                "payment": copy.deepcopy(self.state["payments"][payment_id]),
                "user": self._clone_user(self.state["users"][normalized_id]),
            }

    def get_user_payment_diagnostics(self, user_id, current_time_ms=None):
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)

        with self.lock:
            user = self._clone_user(self.state["users"].get(str(user_id)))
            if not user:
                return None

            payments = [
                copy.deepcopy(payment)
                for payment in self.state["payments"].values()
                if str(payment.get("userId")) == str(user_id)
            ]

        payments.sort(key=lambda item: item.get("paidAt", 0), reverse=True)
        total_amount = sum(payment.get("totalAmount", 0) or 0 for payment in payments)
        charge_ids = {}
        duplicate_charge_ids = []
        legacy_records = []
        missing_charge_ids = 0

        for payment in payments:
            charge_id = payment.get("telegramPaymentChargeId")
            if not charge_id:
                missing_charge_ids += 1
            else:
                charge_ids[charge_id] = charge_ids.get(charge_id, 0) + 1

            if "invoicePayload" not in payment or "currency" not in payment:
                legacy_records.append(charge_id or "<missing>")

        duplicate_charge_ids = sorted(
            charge_id for charge_id, count in charge_ids.items() if count > 1
        )
        subscription_active = bool(
            user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms
        )

        warnings = []
        if payments and not subscription_active:
            warnings.append("Есть платежи, но активной подписки сейчас нет.")
        if (user.get("totalPaymentsCount") or 0) != len(payments):
            warnings.append("totalPaymentsCount не совпадает с числом платежей пользователя.")
        if (user.get("totalSpentStars") or 0) != total_amount:
            warnings.append("totalSpentStars не совпадает с суммой платежей пользователя.")
        if duplicate_charge_ids:
            warnings.append(
                "Обнаружены повторяющиеся telegramPaymentChargeId: "
                + ", ".join(duplicate_charge_ids)
            )
        if missing_charge_ids:
            warnings.append(f"Найдено платежей без telegramPaymentChargeId: {missing_charge_ids}.")
        if legacy_records:
            warnings.append(
                "Есть legacy payment records без полного набора полей: "
                + ", ".join(legacy_records[:5])
            )

        return {
            "userId": user["id"],
            "totalPaymentsCount": user.get("totalPaymentsCount") or 0,
            "totalSpentStars": user.get("totalSpentStars") or 0,
            "subscriptionUntil": user.get("subscriptionUntil"),
            "subscriptionActive": subscription_active,
            "lastPaymentAt": user.get("lastPaymentAt"),
            "recentPayments": payments[:5],
            "paymentCountByRecords": len(payments),
            "paymentAmountByRecords": total_amount,
            "duplicateChargeIds": duplicate_charge_ids,
            "missingChargeIdCount": missing_charge_ids,
            "legacyPaymentRecords": legacy_records,
            "warnings": warnings,
        }

    @staticmethod
    def _payment_anomaly_priority(diagnostics):
        priority = 0
        if diagnostics.get("duplicateChargeIds"):
            priority += 100
        if diagnostics.get("paymentCountByRecords") and not diagnostics.get("subscriptionActive"):
            priority += 90
        if diagnostics.get("totalPaymentsCount") != diagnostics.get("paymentCountByRecords"):
            priority += 80
        if diagnostics.get("totalSpentStars") != diagnostics.get("paymentAmountByRecords"):
            priority += 80
        if diagnostics.get("missingChargeIdCount"):
            priority += 70
        if diagnostics.get("legacyPaymentRecords"):
            priority += 60
        priority += len(diagnostics.get("warnings") or [])
        return priority

    def list_payment_anomalies(self, limit=20, current_time_ms=None):
        normalized_limit = max(1, min(int(limit or 20), 100))

        with self.lock:
            user_ids = list(self.state["users"].keys())

        anomalies = []
        for user_id in user_ids:
            diagnostics = self.get_user_payment_diagnostics(user_id, current_time_ms=current_time_ms)
            if not diagnostics or not diagnostics.get("warnings"):
                continue

            user = self.get_user(user_id)
            anomalies.append({
                "userId": diagnostics["userId"],
                "username": user.get("username") or "",
                "displayName": self._user_display_name(user),
                "warnings": copy.deepcopy(diagnostics.get("warnings") or []),
                "totalPaymentsCount": diagnostics["totalPaymentsCount"],
                "totalSpentStars": diagnostics["totalSpentStars"],
                "subscriptionActive": diagnostics["subscriptionActive"],
                "subscriptionUntil": diagnostics["subscriptionUntil"],
                "lastPaymentAt": diagnostics["lastPaymentAt"],
                "severity": self._payment_anomaly_priority(diagnostics),
            })

        anomalies.sort(
            key=lambda item: (
                -item["severity"],
                -(item.get("lastPaymentAt") or 0),
                item["userId"],
            )
        )

        result = []
        for item in anomalies[:normalized_limit]:
            clean_item = copy.deepcopy(item)
            clean_item.pop("severity", None)
            result.append(clean_item)
        return result

    def manual_payment_recovery(self, admin_id, user_id, days, reason):
        normalized_id = str(user_id)
        clean_reason = str(reason or "").strip()
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                current_time_ms = int(time.time() * 1000)
                base_time = (
                    user.get("subscriptionUntil")
                    if user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms
                    else current_time_ms
                )
                user["subscriptionUntil"] = add_days(base_time, days)
                user["lastWarningAt"] = None
                user["lastAccessGrantedAt"] = current_time_ms
                user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "manual_payment_recovery",
                    "adminId": int(admin_id),
                    "userId": int(normalized_id),
                    "days": days,
                    "reason": clean_reason,
                })

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def set_user_pending_join_request(self, user_id, pending_join_request):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["pendingJoinRequest"] = pending_join_request
                user["updatedAt"] = now_iso()

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def clear_user_pending_join_request(self, user_id):
        return self.set_user_pending_join_request(user_id, None)

    def set_user_channel_member_status(self, user_id, status):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["channelMemberStatus"] = status
                user["updatedAt"] = now_iso()

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def set_user_notes(self, user_id, notes, reason="admin_note"):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["notes"] = str(notes or "").strip()
                user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "update_notes",
                    "userId": int(normalized_id),
                    "reason": reason
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def set_bot_info(self, bot_info):
        with self.lock:
            self._mutate_and_save(lambda state: state["meta"].__setitem__("botInfo", bot_info))

    def set_last_update_id(self, last_update_id):
        with self.lock:
            self._mutate_and_save(lambda state: state["meta"].__setitem__("lastUpdateId", last_update_id))

    def set_join_invite_link(self, invite_link):
        with self.lock:
            def mutate(state):
                state["meta"]["joinInviteLink"] = invite_link
                state["meta"]["joinInviteLinkCreatedAt"] = now_iso()

            self._mutate_and_save(mutate)

    def get_effective_invite_link(self, fallback_invite_link=""):
        with self.lock:
            return (
                self.state["settings"].get("channelInviteLink")
                or self.state["meta"].get("joinInviteLink")
                or fallback_invite_link
                or ""
            )

    def is_subscription_active(self, user_id, current_time_ms=None):
        current_time_ms = current_time_ms or int(time.time() * 1000)
        with self.lock:
            user = self.state["users"].get(str(user_id))
            return bool(user and user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms)

    def activate_subscription_from_payment(self, user_id, payment, settings):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                self._apply_subscription_activation(
                    user,
                    payment,
                    settings,
                    int(time.time() * 1000),
                )

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def grant_subscription_days(self, user_id, days, reason="admin_grant"):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                current_time_ms = int(time.time() * 1000)
                base_time = (
                    user.get("subscriptionUntil")
                    if user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms
                    else current_time_ms
                )
                user["subscriptionUntil"] = add_days(base_time, days)
                user["lastWarningAt"] = None
                user["lastAccessGrantedAt"] = current_time_ms
                user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "grant_subscription",
                    "userId": int(normalized_id),
                    "days": days,
                    "reason": reason
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def revoke_subscription(self, user_id, reason="admin_revoke"):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["subscriptionUntil"] = int(time.time() * 1000) - 1
                user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "revoke_subscription",
                    "userId": int(normalized_id),
                    "reason": reason
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def adjust_balance(self, user_id, amount, reason="admin_balance"):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["balanceStars"] = max(0, (user.get("balanceStars") or 0) + amount)
                user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "balance_adjustment",
                    "userId": int(normalized_id),
                    "amount": amount,
                    "reason": reason
                })

            self._mutate_and_save(mutate)
        return self.get_user(normalized_id)

    def purchase_with_balance(self, user_id, settings):
        normalized_id = str(user_id)
        with self.lock:
            user = self.state["users"].get(normalized_id)
            if not user:
                return {"ok": False, "reason": "user_not_found"}
            if (user.get("balanceStars") or 0) < settings["subscriptionPriceStars"]:
                return {"ok": False, "reason": "not_enough_balance"}

            def mutate(state):
                balance_user = state["users"][normalized_id]
                current_time_ms = int(time.time() * 1000)
                base_time = (
                    balance_user.get("subscriptionUntil")
                    if balance_user.get("subscriptionUntil") and balance_user["subscriptionUntil"] > current_time_ms
                    else current_time_ms
                )
                balance_user["balanceStars"] -= settings["subscriptionPriceStars"]
                balance_user["subscriptionUntil"] = add_days(base_time, settings["subscriptionDurationDays"])
                balance_user["lastWarningAt"] = None
                balance_user["lastAccessGrantedAt"] = current_time_ms
                balance_user["updatedAt"] = now_iso()
                self._append_audit_entry(state, {
                    "type": "grant_subscription",
                    "userId": int(normalized_id),
                    "days": settings["subscriptionDurationDays"],
                    "reason": "balance_purchase"
                })

            updated_user = self._mutate_and_save(mutate)
            return {"ok": True, "user": self._clone_user(self.state["users"][normalized_id])}

    def mark_warning_sent(self, user_id):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["lastWarningAt"] = int(time.time() * 1000)
                user["updatedAt"] = now_iso()

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def mark_access_revoked(self, user_id):
        normalized_id = str(user_id)
        with self.lock:
            if normalized_id not in self.state["users"]:
                return None

            def mutate(state):
                user = state["users"][normalized_id]
                user["lastAccessRevokedAt"] = int(time.time() * 1000)
                user["updatedAt"] = now_iso()

            self._mutate_and_save(mutate)
            return self._clone_user(self.state["users"][normalized_id])

    def get_dashboard_stats(self, current_time_ms=None):
        current_time_ms = current_time_ms or int(time.time() * 1000)
        users = self.list_users()
        settings = self.get_settings()

        active_users = [
            user for user in users
            if user.get("subscriptionUntil") and user["subscriptionUntil"] > current_time_ms
        ]
        expired_users = [
            user for user in users
            if user.get("subscriptionUntil") and user["subscriptionUntil"] <= current_time_ms
        ]
        pending_join_requests = len([user for user in users if user.get("pendingJoinRequest")])
        warning_threshold = current_time_ms + settings["warningDays"] * 24 * 60 * 60 * 1000
        expiring_soon = [
            user for user in users
            if user.get("subscriptionUntil") and current_time_ms < user["subscriptionUntil"] <= warning_threshold
        ]
        revenue_stars = sum(payment.get("totalAmount", 0) for payment in self.get_payments())
        total_balance_stars = sum(user.get("balanceStars", 0) for user in users)
        channel_members = len([user for user in users if user.get("channelMemberStatus") == "member"])

        return {
            "totalUsers": len(users),
            "activeSubscriptions": len(active_users),
            "expiredSubscriptions": len(expired_users),
            "expiringSoon": len(expiring_soon),
            "pendingJoinRequests": pending_join_requests,
            "revenueStars": revenue_stars,
            "totalBalanceStars": total_balance_stars,
            "channelMembers": channel_members,
            "recurringEnabled": bool(settings.get("recurringPaymentsEnabled"))
        }


def create_store(file_path):
    return JsonStore(file_path)
