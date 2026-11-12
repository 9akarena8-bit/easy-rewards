import unittest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from external_orders import DemoOrderLedger


class ExternalOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = DemoOrderLedger(Path(self.tmp.name) / 'external_orders.sqlite3')

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_and_sbp_are_only_nonpayable_drafts(self):
        for method in ('card', 'sbp', 'qr', 'bank_transfer'):
            order = self.ledger.create(plan='week', method=method)
            self.assertTrue(order['demo'])
            self.assertFalse(order['payment_verified'])
            self.assertFalse(order['licence_granted'])
            self.assertIsNone(order['payment_url'])
            self.assertEqual(self.ledger.status(order['order_id']), order)

    def test_skin_basket_is_untrusted_and_cs2_needs_finality(self):
        order = self.ledger.create(plan='day', method='steam_items', game='cs2',
                basket=[{'name': 'Test skin', 'estimate_kopeks': 12345}])
        self.assertEqual(order['reversible_days'], 7)
        self.assertFalse(order['basket'][0]['verified'])
        self.assertIsNone(order['trade_offer_url'])
        reviewed = self.ledger.review(order['order_id'], 'Mock review only')
        self.assertEqual(reviewed['status'], 'demo_reviewed')
        self.assertFalse(reviewed['licence_granted'])

    def test_no_forged_approval_api(self):
        self.assertFalse(hasattr(self.ledger, 'approve_payment'))
        self.assertFalse(hasattr(self.ledger, 'grant'))
        self.assertFalse(hasattr(self.ledger, 'mark_paid'))
        self.assertFalse(hasattr(self.ledger, 'confirm_trade'))

    def test_bad_items_rejected(self):
        for basket in ([{'name': 'x', 'estimate_kopeks': True}],
                       [{'name': '', 'estimate_kopeks': 100}],
                       [{'name': 'x', 'estimate_kopeks': 100}] * 17):
            with self.assertRaises(ValueError):
                self.ledger.create(plan='day', method='steam_items', game='rust', basket=basket)
        with self.assertRaises(ValueError):
            self.ledger.create(plan='month', method='bank_transfer', basket=[{'name':'x','estimate_kopeks':100}])
        with self.assertRaises(ValueError):
            self.ledger.create(plan='month', method='steam_items', game='madeup')

    def test_persists_without_creating_licence(self):
        order = self.ledger.create(plan='three_days', method='bank_transfer')
        other = DemoOrderLedger(self.ledger.path)
        self.assertEqual(other.status(order['order_id']), order)
        self.assertEqual(len(other.recent()), 1)

if __name__ == '__main__':
    unittest.main()