# Release Checklist

## Before deploy

- [ ] Tests pass.
- [ ] `.env` is filled for the target server.
- [ ] Bot token is valid.
- [ ] Channel id is valid.
- [ ] Bot is admin in the channel.
- [ ] Bot has `invite users` permission.
- [ ] Bot has `restrict members` permission.
- [ ] Join requests are enabled if approve flow is required.
- [ ] Admin Telegram id is configured, or admin password is intentionally configured.
- [ ] Backup exists.
- [ ] Backup is verified with ./scripts/verify_backup.sh.
- [ ] `data/db.json` is writable by the runtime user.

## Manual smoke after deploy

- [ ] `systemctl status` is healthy.
- [ ] `journalctl` shows no critical errors.
- [ ] `/start` works.
- [ ] `/admin` works.
- [ ] `/admin_channel_check` reports channel access and bot rights clearly.
- [ ] `/admin_health` reports bot/runtime health clearly.
- [ ] Admin stats opens.
- [ ] Buy invoice opens.
- [ ] Pre-checkout works if tested.
- [ ] Successful payment activates subscription.
- [ ] Active user receives or can request the invite link.
- [ ] Join request approve works.
- [ ] Expired test user can be revoked.
- [ ] Payment anomalies command works.
- [ ] Backup command or backup procedure is tested.
- [ ] Restore procedure is reviewed or tested on a non-production copy.

## Rollback

- [ ] Stop the service.
- [ ] Restore the previous code release.
- [ ] Restore the db backup if needed.
- [ ] Run tests.
- [ ] Start the service again.
- [ ] Check logs after restart.

