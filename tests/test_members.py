import tempfile
import unittest
from pathlib import Path
from veritaserum.admin import provision
from veritaserum.store import Store
from veritaserum.service import Service, Fault


class MembershipTests(unittest.TestCase):
    def test_additional_contributor_conflict_and_separate_private_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'members.sqlite')
            store.seed()
            provision(store, 'checkout', 'fifth', 'Fifth Member', 'support', 'test-password-long',
                      'A separate private customer. FACT should not match inline.\nFACT affected_segment=us_card')
            s = Service(store)
            token, _ = s.login('fifth', 'test-password-long')
            self.assertEqual(s.authenticate(token)['user'], 'fifth')
            self.assertEqual(len(s.snapshot('checkout', 'fifth')['members']), 5)
            self.assertNotIn('Juniper', str(s.private_state('checkout', 'fifth')))
            for user in ['maya', 'eli', 'noor', 'fifth']:
                pid = s.analyze('checkout', user)['proposal_ids'][0]
                s.disclose('checkout', user, pid)
            result = s.coordinate('checkout', 'maya')
            self.assertEqual(result['status'], 'needs_evidence')
            self.assertEqual(result['conflicts'], ['affected_segment'])
            with self.assertRaises(ValueError):
                provision(store, 'checkout', 'fifth', 'Override', 'operations', 'test-password-long')
