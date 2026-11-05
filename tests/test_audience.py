"""One task/agent identity, server-enforced context projections across audiences."""
import json
import tempfile
import unittest
from pathlib import Path
from veritaserum.store import Store
from veritaserum.service import Service, Fault
from veritaserum.providers import ReferenceProvider

class RecordingAgent(ReferenceProvider):
    def __init__(self):
        self.contexts = []
    def converse(self, context):
        self.contexts.append(json.loads(json.dumps(context)))
        return {'reply': 'Private response FAKE_PRIVATE_REPLY' if context['audience'] == 'private' else 'Team response'}

class AudienceTests(unittest.TestCase):
    def test_same_agent_continues_without_private_to_team_context_contamination(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'audience.sqlite'); store.seed()
            agent = RecordingAgent(); service = Service(store, agent, agent)
            service.turn('checkout', 'maya', 'team', 'Help us restore checkout')
            result = service.turn('checkout', 'maya', 'private', 'FACT affected_segment=eu_wallet\nFAKE_PRIVATE_SECRET')
            service.turn('checkout', 'eli', 'team', 'What do we know so far?')
            contexts = agent.contexts
            self.assertEqual({c['task_id'] for c in contexts}, {'checkout'})
            self.assertEqual({c['agent_identity'] for c in contexts}, {'Veritaserum'})
            self.assertIn('Help us restore checkout', json.dumps(contexts[1]))
            self.assertIn('FAKE_PRIVATE_SECRET', json.dumps(contexts[1]))
            for context in (contexts[0], contexts[2]):
                self.assertNotIn('FAKE_PRIVATE', json.dumps(context))
                self.assertNotIn('documents', context)
            own = service.conversation('checkout', 'maya')
            self.assertIn('FAKE_PRIVATE_SECRET', json.dumps(own))
            self.assertIn('FAKE_PRIVATE_REPLY', json.dumps(own))
            for user in ('eli', 'noor', 'alex'):
                self.assertNotIn('FAKE_PRIVATE', json.dumps(service.conversation('checkout', user)))
            self.assertNotIn('FAKE_PRIVATE', json.dumps(service.snapshot('checkout', 'maya')))
            self.assertEqual(service.snapshot('checkout', 'eli')['claims'], [])
            service.disclose('checkout', 'maya', result['proposal_ids'][0])
            self.assertIn('Affected checkout segment', json.dumps(service.conversation('checkout', 'eli')))
            self.assertNotIn('FAKE_PRIVATE', json.dumps(service.conversation('checkout', 'eli')))
            for audience in ('everyone', 'eli', {}, None):
                with self.assertRaises(Fault) as caught:
                    service.turn('checkout', 'maya', audience, 'text')
                self.assertEqual(caught.exception.status, 400)
            service.revoke('checkout', 'noor', 'maya')
            with self.assertRaises(Fault):
                service.conversation('checkout', 'maya')
