import tempfile
import unittest
from pathlib import Path

from storage.json_store import JsonStore
from storage.migrations import migrate_json_to_sqlite
from storage.sqlite_store import SQLiteStore


class StoreContractTests(unittest.TestCase):
    def _backend_cases(self):
        return [
            ('json', JsonStore, 'db.json'),
            ('sqlite', SQLiteStore, 'db.sqlite3'),
        ]

    def _make_store(self, backend_class, path):
        return backend_class(str(path))

    def _sample_user(self, user_id=101, username='user101'):
        return {
            'id': user_id,
            'username': username,
            'first_name': 'Test',
            'last_name': 'User',
            'language_code': 'ru',
        }

    def _sample_payment(self, user_id=101, charge_id='charge_101'):
        return {
            'userId': user_id,
            'telegramPaymentChargeId': charge_id,
            'providerPaymentChargeId': f'provider_{charge_id}',
            'invoicePayload': f'subscription:{user_id}',
            'currency': 'XTR',
            'totalAmount': 250,
            'paidAt': 1700000000000,
        }

    def test_backend_initializes_default_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    store = self._make_store(backend_class, tmp_path / filename)
                    state = store.get_state()
                    self.assertIn('meta', state)
                    self.assertIn('settings', state)
                    self.assertIn('users', state)
                    self.assertIn('payments', state)
                    self.assertIn('auditLog', state)

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    path = tmp_path / filename
                    store = self._make_store(backend_class, path)
                    updated = store.update_settings({
                        'subscriptionPriceStars': 333,
                        'warningDays': 5,
                    })
                    self.assertEqual(updated['subscriptionPriceStars'], 333)
                    self.assertEqual(updated['warningDays'], 5)

                    reopened = self._make_store(backend_class, path)
                    settings = reopened.get_settings()
                    self.assertEqual(settings['subscriptionPriceStars'], 333)
                    self.assertEqual(settings['warningDays'], 5)

    def test_ensure_user_is_idempotent_and_generates_referral_code(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    store = self._make_store(backend_class, tmp_path / filename)
                    first = store.ensure_user(self._sample_user())
                    second = store.ensure_user(self._sample_user())

                    users = store.list_users()
                    self.assertEqual(len(users), 1)
                    self.assertEqual(first['id'], second['id'])
                    self.assertTrue(first.get('referralCode'))
                    self.assertEqual(first['referralCode'], second['referralCode'])

    def test_update_user_fields_persists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    path = tmp_path / filename
                    store = self._make_store(backend_class, path)
                    store.ensure_user(self._sample_user())
                    store.update_user_fields(101, {
                        'balanceStars': 77,
                        'channelMemberStatus': 'member',
                    })

                    reopened = self._make_store(backend_class, path)
                    user = reopened.get_user(101)
                    self.assertEqual(user['balanceStars'], 77)
                    self.assertEqual(user['channelMemberStatus'], 'member')

    def test_record_payment_and_activate_subscription_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    path = tmp_path / filename
                    store = self._make_store(backend_class, path)
                    store.ensure_user(self._sample_user())
                    settings = store.get_settings()
                    payment = self._sample_payment()

                    first = store.record_payment_and_activate_subscription(101, payment, settings)
                    second = store.record_payment_and_activate_subscription(101, payment, settings)

                    self.assertEqual(first['status'], 'processed')
                    self.assertEqual(second['status'], 'duplicate')

                    reopened = self._make_store(backend_class, path)
                    user = reopened.get_user(101)
                    self.assertEqual(user['totalPaymentsCount'], 1)
                    self.assertEqual(user['totalSpentStars'], 250)
                    self.assertIsNotNone(user['subscriptionUntil'])
                    self.assertEqual(len(reopened.get_payments()), 1)

    def test_grant_subscription_days_persists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for label, backend_class, filename in self._backend_cases():
                with self.subTest(backend=label):
                    path = tmp_path / filename
                    store = self._make_store(backend_class, path)
                    store.ensure_user(self._sample_user())
                    granted = store.grant_subscription_days(101, 7, reason='contract_test')
                    self.assertIsNotNone(granted)
                    self.assertIsNotNone(granted['subscriptionUntil'])

                    reopened = self._make_store(backend_class, path)
                    user = reopened.get_user(101)
                    self.assertEqual(user['subscriptionUntil'], granted['subscriptionUntil'])

    def test_json_to_sqlite_migration_preserves_core_state_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_path = tmp_path / 'db.json'
            sqlite_path = tmp_path / 'db.sqlite3'
            backup_path = tmp_path / 'backups' / 'db.pre-sqlite-migration.json'

            json_store = JsonStore(str(json_path))
            json_store.update_settings({'subscriptionPriceStars': 444})
            json_store.ensure_user(self._sample_user())
            json_store.record_payment_and_activate_subscription(101, self._sample_payment(), json_store.get_settings())

            result = migrate_json_to_sqlite(str(json_path), str(sqlite_path), backup_path=str(backup_path))

            self.assertEqual(result['backupPath'], str(backup_path.resolve()))
            self.assertTrue(backup_path.exists())
            self.assertTrue(sqlite_path.exists())

            sqlite_store = SQLiteStore(str(sqlite_path))
            self.assertEqual(sqlite_store.get_settings()['subscriptionPriceStars'], 444)
            self.assertEqual(len(sqlite_store.list_users()), 1)
            self.assertEqual(len(sqlite_store.get_payments()), 1)
            self.assertEqual(sqlite_store.get_user(101)['totalPaymentsCount'], 1)


if __name__ == '__main__':
    unittest.main()