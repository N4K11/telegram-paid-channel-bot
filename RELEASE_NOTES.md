# Release Notes

## Current status

This project is in release-candidate state for Ubuntu deployment.

Current guarantees:

- official runtime is Python via `main.py`
- `bot/app.py` is a runtime shell
- payment flow uses atomic store orchestration
- duplicate payments do not extend access twice
- manual payment recovery does not create fake payments
- payment anomalies review is read-only
- storage uses atomic save and rollback-aware mutation handling
- no active runtime dependency on legacy Node files

Latest verification result:

- `python -m compileall .` -> pass
- `python -m unittest discover -s tests -p "test_*.py" -v` -> pass

## How to run checks

Official checks:

```bash
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
```

POSIX helper script:

```bash
sh scripts/check.sh
```

## How to deploy on Ubuntu

Follow the full guide in `DEPLOY_UBUNTU.md`.

Short version:

1. Upload the project to `/opt/private-channel-bot`.
2. Create service user `botuser`.
3. Create and activate `.venv`.
4. Run `pip install -r requirements.txt`.
5. Copy `.env.example` to `.env` and fill required values.
6. Run the official checks.
7. Start once manually with `python main.py`.
8. Install and start the systemd unit.
9. Verify with `systemctl status` and `journalctl`.

## Required .env keys

Required or operationally important keys:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD` or `ADMIN_TELEGRAM_ID`
- `SUBSCRIPTION_PRICE_STARS`
- `SUBSCRIPTION_DURATION_DAYS`
- `WARNING_DAYS`
- `SUPPORT_USERNAME`
- `APP_TIMEZONE`
- `AUTO_CREATE_INVITE_LINK`
- `POLL_TIMEOUT_SECONDS`
- `SERVICE_CHECK_INTERVAL_MS`
- `DATA_FILE_PATH`

Default JSON store path remains:

- `data/db.json`

## Backup procedure

Manual backup:

```bash
cp data/db.json data/db.backup.$(date +%F-%H%M%S).json
```

POSIX helper script:

```bash
sh scripts/backup_db.sh
```

Backups should be created:

- before first production deploy
- before every update
- before any manual data intervention

## Manual smoke checklist

After deploy, verify:

- service is running cleanly in `systemctl status`
- `journalctl` shows no critical errors
- `/start` works
- `/admin` works
- admin stats opens
- invoice opens from buy flow
- a safe payment test is handled correctly
- successful payment activates subscription
- active user can obtain the join link
- join request approval works
- revoke path works for an expired test user
- `/admin_payment_anomalies` works
- `/admin_payment_diag <user_id>` works

## Known safe admin recovery commands

These commands are intended for safe manual diagnostics or recovery:

- `/admin_payment_diag <user_id>`
- `/admin_payment_anomalies [limit]`
- `/admin_recover_payment <user_id> <days> <reason>`

Current safety rules:

- diagnostics are read-only
- anomalies review is read-only
- manual recovery does not create fake payment records
- manual recovery does not change `totalPaymentsCount` or `totalSpentStars`

## What not to change before production launch

Do not change any of the following without a separate post-freeze stage:

- callback data
- slash commands
- payment payload `subscription:{user_id}`
- `db.json` schema
- payment/access/maintenance logic
- recovery/anomaly policy
- user/admin Telegram-visible UX
- runtime shell wiring in `bot/app.py`

Do not remove or bypass the current checks:

- storage rollback/atomic save tests
- transport tests
- runtime fake Telegram tests
- UI contract tests
- ops readiness tests

## Rollback summary

If deployment fails:

1. Stop the systemd service.
2. Restore the previous code version.
3. Restore the last known-good `data/db.json` backup if needed.
4. Activate the virtual environment.
5. Run the official checks again.
6. Start the service.
7. Inspect `systemctl status` and `journalctl` before reopening access.

Detailed operational steps remain in `DEPLOY_UBUNTU.md` and `RELEASE_CHECKLIST.md`.
