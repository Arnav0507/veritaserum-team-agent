import json
import tempfile
import unittest
from pathlib import Path
from veritaserum.store import Store
from veritaserum.service import Service, Fault
from veritaserum.providers import ReferenceProvider

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'chat.sqlite')
        self.store.seed()
        self.service = Service(self.store)
    def tearDown(self):
        self.tmp.cleanup()
    def test_contributor_creates_team_chat_and_requests_private_contributions(self):
        room = self.service.create_room('maya', 'checkout', 'Team chat', 'Restore checkout', ['maya','eli','noor'])['id']
        result = self.service.team_chat(room, 'maya', 'Help us recover checkout')
        self.assertEqual(result['status'], 'needs_evidence')
        self.assertEqual({r['role'] for r in result['requests']}, {'support','engineering','operations'})
        self.service.private_chat(room, 'maya', 'FACT affected_segment=eu_wallet\nFAKE-PRIVATE-KEY')
        private = self.service.private_state(room, 'maya')
        self.assertEqual(len(private['messages']), 2)
        self.assertNotIn('FAKE-PRIVATE-KEY', json.dumps(self.service.snapshot(room, 'eli')))
        self.assertNotIn('FAKE-PRIVATE-KEY', json.dumps(self.service.private_state(room, 'eli')))
        self.assertEqual(self.service.snapshot(room, 'eli')['claims'], [])
        proposal = self.service.analyze(room, 'maya')['proposal_ids'][0]
        self.service.disclose(room, 'maya', proposal)
        self.assertEqual(len(self.service.snapshot(room, 'eli')['claims']), 1)
    def test_private_response_rechecks_membership(self):
        service = self.service
        class RevokingProvider(ReferenceProvider):
            def converse(self, context):
                service.revoke('checkout', 'noor', 'maya')
                return {'reply': 'PRIVATE-RESPONSE'}
        service.private_provider = RevokingProvider()
        with self.assertRaises(Fault) as caught:
            service.private_chat('checkout', 'maya', 'Private input')
        self.assertEqual(caught.exception.status, 403)
        with self.store.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM private_messages WHERE speaker='agent'").fetchone()[0], 0)
    def test_observer_cannot_send_private_or_team_chat(self):
        for method in (self.service.private_chat, self.service.team_chat):
            with self.assertRaises(Fault) as caught:
                method('checkout', 'alex', 'hello')
            self.assertEqual(caught.exception.status, 403)
