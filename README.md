# Telegram Paid Channel Bot

Python-бот для продажи доступа в приватный Telegram-канал.

## Текущий статус проекта

- основной runtime: Python;
- основной entrypoint: `main.py`;
- админка работает внутри Telegram через inline-кнопки и текстовый ввод в чате с ботом;
- исторические Node/Python legacy-файлы вынесены в `legacy/` и не участвуют в текущем запуске.

## Официальный запуск

```powershell
python main.py
```

Если в вашей системе нет алиаса `python`, используйте ваш установленный интерпретатор, например:

```powershell
py main.py
```

## Официальные проверки

```powershell
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
```

## Настройка

1. Скопируйте `.env.example` в `.env`.
2. Заполните минимум:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHANNEL_ID`
   - `ADMIN_PASSWORD` или `ADMIN_TELEGRAM_ID`
3. Добавьте бота администратором в приватный канал.
4. Выдайте права:
   - `can_invite_users`
   - `can_restrict_members`
5. Запустите `python main.py`.

## Пользовательские команды

Поддерживаются текущим runtime:

- `/start`
- `/buy`
- `/buy_balance`
- `/status`
- `/help`

## Команды администратора

Поддерживаются как прямые slash-команды:

- `/admin`
- `/admin_login <username> <password>`
- `/admin_logout`
- `/admin_stats`
- `/admin_settings`
- `/admin_users`
- `/admin_help`
- `/admin_refresh_invite`
- `/admin_broadcast`
- `/admin_channel_check`
- `/admin_payment_diag <user_id>`
- `/admin_recover_payment <user_id> <days> <reason>`
- `/admin_payment_anomalies`

Дополнительно:

- `/admin_payment_anomalies <limit>` поддерживается с безопасным максимумом и показывает read-only список подозрительных payment-cases.

## Что доступно через inline-админку

После входа через `/admin` или `/admin_login` основные действия выполняются через кнопки и последующий ввод текста в том же чате:

- просмотр общей статистики;
- просмотр списка пользователей;
- фильтрация пользователей;
- открытие карточки пользователя;
- выдача дней подписки;
- изменение баланса;
- одобрение заявки на вступление;
- отзыв доступа;
- заметки по пользователю;
- сообщение пользователю;
- рассылка;
- изменение цены, срока и warning days;
- переключение recurring и auto-invite;
- изменение канала и username поддержки;
- редактирование текстовых шаблонов.
- диагностика спорных payment-cases по пользователю;
- список пользователей с подозрительными payment-cases;
- ручное восстановление доступа без создания fake payment records и без изменения totals оплаты.

## Команды, которые были задокументированы раньше, но сейчас не реализованы как прямые slash-команды

Эти действия сейчас не поддерживаются как отдельные slash-команды через `handle_admin_command`, даже если похожая логика есть в inline-админке:

- `/admin_set`
- `/admin_user`
- `/admin_create_user`
- `/admin_grant`
- `/admin_revoke`
- `/admin_balance`
- `/admin_approve`
- `/admin_message`
- `/admin_note`
- `/admin_setup_channel`

Если эти команды понадобятся именно как slash-команды, это отдельный следующий этап, а не текущая гарантия runtime.

## Что умеет бот

- принимает оплату через Telegram Stars;
- активирует подписку после `successful_payment`;
- выдаёт или обновляет invite-ссылку;
- одобряет `chat_join_request` для активной подписки;
- предупреждает о скором окончании доступа;
- исключает пользователя после истечения подписки;
- хранит состояние в JSON.

## Legacy-файлы

Исторические артефакты вынесены в [legacy/README_LEGACY.md](/D:/awd/legacy/README_LEGACY.md).

Они не участвуют в текущем runtime и не должны использоваться для запуска бота. Официальный запуск остаётся только через `python main.py`.
