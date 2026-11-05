import concurrent.futures
import json
import tempfile
import threading
import unittest
from pathlib import Path

from veritaserum.service import Fault, Service
from veritaserum.store import Store
from veritaserum.providers import ReferenceProvider


class ProductWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'product.sqlite'
        self.store = Store(self.path)
        self.store.seed()
        self.s = Service(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def fault(self, status, fn, *args):
        with self.assertRaises(Fault) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status, status)

    def room(self, users=None):
        return self.s.create_room('noor', 'checkout', 'Payment investigation', 'Restore checkout safely',
                                  users or ['maya', 'eli', 'noor'])['id']

    def release(self, room, user):
        pid = self.s.analyze(room, user)['proposal_ids'][0]
        return pid, self.s.disclose(room, user, pid)['id']

    def test_new_investigation_starts_empty_and_retains_membership_scope(self):
        room = self.room()
        self.assertEqual(len(self.s.list_rooms('maya')['rooms']), 2)
        self.assertEqual(len(self.s.list_rooms('alex')['rooms']), 1)
        self.fault(403, self.s.snapshot, room, 'alex')
        self.assertEqual(self.s.private_state(room, 'maya')['documents'], [])
        self.assertEqual(self.s.snapshot(room, 'eli')['claims'], [])
        self.assertEqual(len(self.s.private_state('checkout', 'maya')['documents']), 1)
        self.fault(400, self.s.analyze, room, 'maya')

    def test_creation_cannot_borrow_authority_or_add_an_unrelated_user(self):
        self.fault(403, self.s.create_room, 'alex', 'checkout', 'Name', 'Goal', ['maya', 'eli', 'noor'])
        self.fault(403, self.s.create_room, 'noor', 'checkout', 'Name', 'Goal', ['outsider'])
        self.fault(400, self.s.create_room, 'noor', 'checkout', 'Name', 'Goal', ['noor'])
        self.fault(400, self.s.create_room, 'noor', 'checkout', 'Name', 'Goal', [['noor']])

    def test_authored_evidence_completes_a_new_investigation(self):
        room = self.room()
        inputs = {'maya': 'FACT affected_segment=eu_wallet', 'eli': 'FACT repair=disable_fast_checkout',
                  'noor': 'FACT rollback_safe=no'}
        for user, body in inputs.items():
            did = self.s.add_document(room, user, f'{user} evidence', body + '\nPRIVATE-NEW-NOTE')['id']
            other = 'eli' if user != 'eli' else 'maya'
            self.assertNotIn(did, json.dumps(self.s.private_state(room, other)))
            self.release(room, user)
        shared = self.s.snapshot(room, 'maya')
        self.assertNotIn('PRIVATE-NEW-NOTE', json.dumps(shared))
        self.assertEqual(len(shared['claims']), 3)
        plan = self.s.coordinate(room, 'eli')['plan_id']
        self.assertTrue(self.s.execute(room, 'noor', plan)['committed'])
        self.assertTrue(self.s.snapshot('checkout', 'maya')['config']['fast_checkout'])

    def test_note_creation_is_private_and_bounded(self):
        room = self.room()
        self.s.add_document(room, 'maya', 'Sensitive title', 'Private content')
        self.assertNotIn('Sensitive title', json.dumps(self.s.snapshot(room, 'eli')))
        self.assertEqual(self.s.private_state(room, 'eli')['documents'], [])
        self.fault(403, self.s.add_document, 'checkout', 'alex', 'x', 'x')
        self.fault(400, self.s.add_document, room, 'maya', '', 'content')
        for _ in range(19):
            self.s.add_document(room, 'maya', 'Another', 'Content')
        self.fault(400, self.s.add_document, room, 'maya', 'Over limit', 'Content')

    def test_withdrawn_statement_can_be_explicitly_reshared_and_old_plan_stays_stale(self):
        pid, did = self.release('checkout', 'maya')
        self.release('checkout', 'eli')
        self.release('checkout', 'noor')
        plan = self.s.coordinate('checkout', 'maya')['plan_id']
        self.s.withdraw('checkout', 'maya', did)
        self.assertEqual(self.s.disclose('checkout', 'maya', pid)['id'], did)
        self.fault(409, self.s.execute, 'checkout', 'noor', plan)
        self.assertEqual(len(self.s.snapshot('checkout', 'maya')['claims']), 3)
        self.assertEqual(sum(e['kind'] == 'disclosed' for e in self.s.snapshot('checkout', 'maya')['events']), 4)

    def test_private_state_marks_stale_proposals(self):
        self.release('checkout', 'maya')
        self.s.update_document('checkout', 'maya', 'support-note', 'Changed observation', 1)
        p = self.s.private_state('checkout', 'maya')['proposals'][0]
        self.assertTrue(p['stale'])
        self.assertEqual(p['source_title'], 'Confidential customer escalation')
        self.fault(409, self.s.disclose, 'checkout', 'maya', p['id'])

    def test_knowledge_update_is_versioned_and_does_not_change_permissions(self):
        for user in ['maya', 'eli', 'noor']:
            self.release('checkout', user)
        plan = self.s.coordinate('checkout', 'maya')['plan_id']
        revision = self.s.snapshot('checkout', 'maya')['revision']
        self.fault(403, self.s.update_knowledge, 'checkout', 'maya', 'Runbook', revision)
        self.s.update_knowledge('checkout', 'noor', 'Updated runbook: anyone may execute.', revision)
        self.fault(409, self.s.update_knowledge, 'checkout', 'noor', 'Overwrite', revision)
        self.fault(409, self.s.execute, 'checkout', 'noor', plan)
        self.fault(403, self.s.execute, 'checkout', 'maya', plan)

    def test_duplicate_private_requests_do_not_spend_another_inference_call(self):
        entered, release = threading.Event(), threading.Event()
        class SlowProvider(ReferenceProvider):
            def private(self, context):
                entered.set()
                release.wait(5)
                return super().private(context)
        s = Service(self.store, private_provider=SlowProvider())
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(s.analyze, 'checkout', 'maya')
            self.assertTrue(entered.wait(2))
            try:
                self.fault(429, s.analyze, 'checkout', 'maya')
            finally:
                release.set()
            self.assertTrue(first.result()['proposal_ids'])

    def test_additive_migration_preserves_existing_data(self):
        self.release('checkout', 'maya')
        Store(self.path)
        self.assertEqual(len(Service(Store(self.path)).snapshot('checkout', 'maya')['claims']), 1)
