import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from veritaserum.policy import INITIAL_CONFIG
from veritaserum.providers import ToolPlanningProvider, ProviderError
from veritaserum.store import Store


class ToolPlanningTests(unittest.TestCase):
    def provider(self):
        return ToolPlanningProvider('https://api.meta.ai/v1/chat/completions', 'muse-wonder-1.0', 'synthetic-key')

    def call(self, name='compare_repairs', arguments='{}'):
        return {'tool_calls': [{'id': 'call_test', 'type': 'function',
                                'function': {'name': name, 'arguments': arguments}}]}

    def test_model_observes_actual_simulation_before_final_decision(self):
        p = self.provider()
        context = {'simulator': INITIAL_CONFIG, 'eligible_actions': ['disable_fast_checkout']}
        with patch.object(p, '_request', side_effect=[self.call(), {'content': '{"action":"disable_fast_checkout"}'}]) as request:
            self.assertEqual(p.shared(context), {'action': 'disable_fast_checkout'})
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args_list[0].args[0]['tool_choice'], 'auto')
            self.assertFalse(request.call_args_list[0].args[0]['parallel_tool_calls'])
            tool_results = json.loads(request.call_args.args[0]['messages'][-1]['content'])
            outcomes = {r['action']: r['passed'] for r in tool_results}
            self.assertEqual(outcomes, {'disable_fast_checkout': True, 'rollback': False, 'restart': False})
            self.assertTrue(INITIAL_CONFIG['fast_checkout'])

    def test_model_cannot_expand_tool_or_supply_execution_arguments(self):
        for call in [self.call('read_private'), self.call(arguments='{"path":"/secret"}')]:
            p = self.provider()
            with patch.object(p, '_request', return_value=call) as request:
                with self.assertRaises(ProviderError):
                    p.shared({'simulator': INITIAL_CONFIG})
                self.assertEqual(request.call_count, 1)

    def test_no_tool_call_abstains_without_an_action(self):
        p = self.provider()
        with patch.object(p, '_request', return_value={'content': 'I cannot decide.'}):
            self.assertEqual(p.shared({'simulator': INITIAL_CONFIG}), {'action': None})

    def test_live_seed_contains_prose_without_reference_fact_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'natural.sqlite')
            store.seed(natural=True)
            with store.tx() as db:
                docs = list(db.execute('SELECT body FROM documents'))
                self.assertEqual(len(docs), 3)
                self.assertTrue(all('FACT ' not in d['body'] for d in docs))

    def test_meta_missing_key_fails_before_server_start(self):
        import contextlib
        import io
        from veritaserum.server import main
        with patch.dict('os.environ', {}, clear=True), patch('sys.argv', ['server', '--provider', 'meta']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)
