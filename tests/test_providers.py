import io
import json
import unittest
import contextlib
import urllib.error
from unittest.mock import patch
from veritaserum.providers import ChatProvider, NoRedirect, ProviderError, from_environment


class ProviderTests(unittest.TestCase):
    def provider(self):
        return ChatProvider('https://provider.example/v1/chat/completions', 'test-model', 'fake-test-key')

    def test_transport_serializes_only_supplied_context(self):
        body = json.dumps({'choices': [{'message': {'content': '{"action":"restart"}'}}]}).encode()
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(body)
            self.assertEqual(self.provider().shared({'eligible_actions': ['restart']}), {'action': 'restart'})
            request = opener.return_value.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload['model'], 'test-model')
            self.assertEqual(json.loads(payload['messages'][1]['content']), {'eligible_actions': ['restart']})
            self.assertNotIn('fake-test-key', request.data.decode())
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 40)

    def test_bad_responses_fail_closed_without_echo(self):
        for body in [b'PRIVATE-SECRET', b'{}', b'x' * 131073,
                     json.dumps({'choices':[{'message':{'content':'PRIVATE-SECRET'}}]}).encode()]:
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(body)
                with self.assertRaises(ProviderError) as caught:
                    self.provider().shared({})
                self.assertNotIn('PRIVATE-SECRET', str(caught.exception))

    def test_endpoint_validation_and_redirect_denial(self):
        for url in ['http://provider.example', 'https://user:pass@provider.example', '', 'file:///tmp/x']:
            with self.assertRaises(ValueError):
                ChatProvider(url, 'model', 'key')
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_provider_http_error_reports_safe_diagnostics_without_body(self):
        body = io.BytesIO(json.dumps({'error': {'code': 'model_not_found', 'param': 'model',
                                                'message': 'PRIVATE-SECRET'}}).encode())
        error = urllib.error.HTTPError('https://provider.example', 404, 'PRIVATE-SECRET', {}, body)
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(ProviderError) as caught:
                self.provider().shared({})
            self.assertIn('HTTP 404', str(caught.exception))
            self.assertIn('model_not_found', str(caught.exception))
            self.assertNotIn('PRIVATE-SECRET', str(caught.exception))

    def test_live_configuration_does_not_silently_fallback(self):
        with patch.dict('os.environ', {'TEST_MODE': 'live'}, clear=True):
            with self.assertRaises(ValueError):
                from_environment('TEST')

    def test_fireworks_launch_requires_credentials_before_opening_database(self):
        from veritaserum.server import main
        with patch.dict('os.environ', {}, clear=True), patch('sys.argv', ['server', '--provider', 'fireworks']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)
        with patch.dict('os.environ', {'TEST_MODE': 'typo'}, clear=True):
            with self.assertRaises(ValueError):
                from_environment('TEST')
