"""Exercise a running local server with synthetic demo accounts. Never print sessions or source notes."""
import argparse
import http.client
import json
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--coordinate-only', action='store_true', help='Reuse already-approved synthetic evidence')
    args = parser.parse_args()
    sessions = {}

    def request(path, body=None, user=None):
        connection = http.client.HTTPConnection('127.0.0.1', args.port, timeout=150)
        headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{args.port}'}
        if user:
            headers['Cookie'], headers['X-CSRF-Token'] = sessions[user]
        connection.request('GET' if body is None else 'POST', path,
                           None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        cookie = response.getheader('Set-Cookie')
        connection.close()
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}: {result.get("error", "request failed")}')
        return result, cookie

    base = '/api/rooms/checkout/'
    for user in ['maya', 'eli', 'noor']:
        result, cookie = request('/api/login', {'user': user, 'password': f'{user}-demo'})
        sessions[user] = (cookie.split(';')[0], result['csrf'])
    state, _ = request(base + 'state', user='maya')
    print(json.dumps({'providers': state['providers'], 'initial_revision': state['revision']}), flush=True)
    if not all(mode.startswith('live') for mode in state['providers'].values()):
        raise RuntimeError('Both roles must use live providers for this check')
    for user in ([] if args.coordinate_only else ['maya', 'eli', 'noor']):
        started = time.monotonic()
        result, _ = request(base + 'analyze', {}, user)
        if not result['proposal_ids']:
            raise RuntimeError(f'{user}: model returned no supported facts')
        # Release only known synthetic fixture facts, not arbitrary model proposals.
        private, _ = request(base + 'private', user=user)
        expected = {'maya': ('affected_segment', 'eu_wallet'),
                    'eli': ('repair', 'disable_fast_checkout'), 'noor': ('rollback_safe', 'no')}[user]
        candidates = [p for p in private['proposals'] if p['id'] in result['proposal_ids']
                      and (p['key'], p['value']) == expected]
        if len(candidates) != 1:
            raise RuntimeError(f'{user}: expected synthetic fixture fact not uniquely extracted')
        request(base + 'disclose', {'proposal_id': candidates[0]['id']}, user)
        print(json.dumps({'participant': user, 'approved_fact': expected[0],
                          'seconds': round(time.monotonic() - started, 2)}), flush=True)
    started = time.monotonic()
    plan, _ = request(base + 'coordinate', {}, 'noor')
    if plan.get('status') != 'proposed':
        raise RuntimeError('Coordinator did not propose a repair')
    print(json.dumps({'coordinator': 'proposed', 'seconds': round(time.monotonic() - started, 2)}), flush=True)
    result, _ = request(base + 'execute', {'plan_id': plan['plan_id']}, 'noor')
    if not result['committed']:
        raise RuntimeError('Repair did not pass verification')
    state, _ = request(base + 'state', user='maya')
    shared = json.dumps(state)
    for marker in ['PRIVATE-CUSTOMER', 'PRIVATE-SOURCE', 'PRIVATE-OPS', 'Juniper', 'dana@', 'source_id']:
        if marker in shared:
            raise RuntimeError('Private fixture marker appeared in shared state')
    print(json.dumps({'result': 'PASS', 'checks': result['checks'],
                      'final_revision': state['revision'], 'private_markers_in_shared_state': False}), flush=True)


if __name__ == '__main__':
    main()
