# Ubuntu Deployment

## 1. Server prerequisites

- Ubuntu server with network access to Telegram Bot API
- Python 3 with `venv` and `pip`
- a dedicated Linux user for the bot process
- writable project directory, including `data/` and `data/db.json`

Install system packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

## 2. Project upload path

Recommended target path:

- `/opt/private-channel-bot`

Example:

```bash
sudo mkdir -p /opt/private-channel-bot
sudo chown -R "$USER":"$USER" /opt/private-channel-bot
```

## 3. Create Linux user

```bash
sudo adduser --system --group --home /opt/private-channel-bot botuser
```

If the project files were uploaded by another user, fix ownership before enabling the service:

```bash
sudo chown -R botuser:botuser /opt/private-channel-bot
```

## 4. Python venv setup

```bash
cd /opt/private-channel-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` is intentionally minimal for the current runtime. Keep the install step anyway so the release process stays consistent.

## 5. .env setup

```bash
cp .env.example .env
nano .env
```

Minimum required values:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `ADMIN_PASSWORD` or `ADMIN_TELEGRAM_ID`
- `DATA_FILE_PATH`
- `APP_TIMEZONE`
- `SUBSCRIPTION_PRICE_STARS`
- `SUBSCRIPTION_DURATION_DAYS`
- `WARNING_DAYS`
- `AUTO_CREATE_INVITE_LINK`
- `POLL_TIMEOUT_SECONDS`
- `SERVICE_CHECK_INTERVAL_MS`
- `SUPPORT_USERNAME`

Linux-safe default store path:

- `DATA_FILE_PATH=data/db.json`

## 6. Data directory permissions

```bash
mkdir -p data
sudo chown -R botuser:botuser /opt/private-channel-bot
chmod 600 .env
```

Verify that `botuser` can write to:

- `data/`
- `data/db.json`

The JSON store writes only inside the project directory and does not require root privileges.

## 7. Official checks

```bash
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
```

If you prefer the venv interpreter explicitly:

```bash
/opt/private-channel-bot/.venv/bin/python -m compileall .
/opt/private-channel-bot/.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
```

## 8. First manual run

```bash
source .venv/bin/activate
python main.py
```

Official runtime entrypoint stays the same on Ubuntu:

- `python main.py`

## 9. systemd service unit

Path:

- `/etc/systemd/system/private-channel-bot.service`

Example unit:

```ini
[Unit]
Description=Private Channel Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/private-channel-bot
ExecStart=/opt/private-channel-bot/.venv/bin/python /opt/private-channel-bot/main.py
Restart=always
RestartSec=5
EnvironmentFile=/opt/private-channel-bot/.env
User=botuser
Group=botuser

[Install]
WantedBy=multi-user.target
```

## 10. Start/stop/restart/status commands

```bash
sudo systemctl daemon-reload
sudo systemctl enable private-channel-bot
sudo systemctl start private-channel-bot
sudo systemctl stop private-channel-bot
sudo systemctl restart private-channel-bot
sudo systemctl status private-channel-bot
```

## 11. journalctl logs

```bash
journalctl -u private-channel-bot -f
journalctl -u private-channel-bot -n 100 --no-pager
```

## 12. Backup db.json

Manual backup command:

```bash
cp data/db.json data/db.backup.$(date +%F-%H%M%S).json
```

If you use the helper script from this repository:

```bash
sh scripts/backup_db.sh
```

## 13. Rollback procedure

1. Stop the service.
2. Restore the previous code revision or previous release archive.
3. Restore `data/db.json` from backup if the release changed persistent state unexpectedly.
4. Activate the virtual environment.
5. Run the official checks again.
6. Start the service.
7. Inspect `systemctl status` and `journalctl` before reopening access.

Example:

```bash
sudo systemctl stop private-channel-bot
cp data/db.backup.YYYYmmdd-HHMMSS.json data/db.json
source .venv/bin/activate
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
sudo systemctl start private-channel-bot
sudo systemctl status private-channel-bot
journalctl -u private-channel-bot -n 100 --no-pager
```

## 14. Update procedure

1. Stop the service.
2. Back up `data/db.json`.
3. Pull or copy the new project files.
4. Activate the virtual environment.
5. Run `pip install -r requirements.txt`.
6. Run the official checks.
7. Start the service again.

Example:

```bash
sudo systemctl stop private-channel-bot
cp data/db.json data/db.backup.$(date +%F-%H%M%S).json
source .venv/bin/activate
pip install -r requirements.txt
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
sudo systemctl start private-channel-bot
```

## 15. Common issues

### bot does not start

- Check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, and admin credentials in `.env`.
- Run `python main.py` manually inside the virtual environment to see the immediate error.
- Check `journalctl -u private-channel-bot -n 100 --no-pager`.

### missing env variable

- `validate_config()` will fail startup if required variables are missing.
- Compare `.env` with `.env.example` and verify there are no empty required values.

### bot cannot approve join request

- Confirm the bot is an admin in the target channel.
- Confirm join requests are enabled if approve flow is required.
- Confirm the bot can invite users and manage join requests.

### bot cannot kick/revoke user

- Confirm the bot has permission to restrict or remove members.
- Check that the configured channel id is correct.
- Inspect logs for Telegram API permission errors.

### Stars payment not arriving

- Confirm the payment was opened from the current bot instance.
- Confirm the bot token and payment flow match the production bot.
- Inspect logs to see whether `pre_checkout_query` and `successful_payment` updates are arriving.

### permission denied on data/db.json

- Verify `botuser` owns `/opt/private-channel-bot`.
- Verify `data/` and `data/db.json` are writable by the service user.
- Do not run the service as root unless you have a separate operational reason.

### systemd service restart loop

- Check `sudo systemctl status private-channel-bot`.
- Check `journalctl -u private-channel-bot -n 100 --no-pager`.
- Run the bot manually with the same `.env` to confirm the startup error before restarting the unit repeatedly.

## 16. Production safety checklist

Before going live, verify all of the following:

1. `TELEGRAM_BOT_TOKEN` is set.
2. `TELEGRAM_CHANNEL_ID` is set.
3. The bot is an admin of the target channel.
4. The bot has invite and restrict permissions.
5. Join requests are enabled if approve flow is required.
6. `ADMIN_TELEGRAM_ID` is set, or `ADMIN_PASSWORD` is configured intentionally.
7. Price and duration settings are correct.
8. A backup of `data/db.json` exists.
9. Tests pass on the target server.
10. The systemd service starts cleanly.
11. `journalctl` does not show runtime errors.
12. `/start` works.
13. `/admin` works.
14. A test Stars payment is verified in a safe environment.
15. Maintenance loop runs without repeated errors.
