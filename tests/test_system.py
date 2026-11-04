import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path

from veritaserum.store import Store
from veritaserum.service import Service, Fault
from veritaserum.providers import ReferenceProvider, ProviderError
from veritaserum.policy import INITIAL_CONFIG, simulate, assess


class RecordingProvider(ReferenceProvider):
    def __init__(self):
        self.calls = []

    def private(self, context):
        self.calls.append(("private", context))
        return super().private(context)

    def shared(self, context):
        self.calls.append(("shared", context))
        return super().shared(context)


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite"
        self.store = Store(self.path)
        self.store.seed()
        self.provider = RecordingProvider()
        self.s = Service(self.store, self.provider, self.provider)

    def tearDown(self):
        self.tmp.cleanup()

    def fault(self, status, fn, *args):
        with self.assertRaises(Fault) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status, status)

    def release(self, actor):
        pid = self.s.analyze("checkout", actor)["proposal_ids"][0]
        return self.s.disclose("checkout", actor, pid)["id"]

    def ready(self):
        for actor in ["maya", "eli", "noor"]:
            self.release(actor)
        return self.s.coordinate("checkout", "maya")["plan_id"]

    def test_successful_joint_work_keeps_raw_private_context_out(self):
        self.assertEqual(self.s.coordinate("checkout", "maya")["status"], "needs_evidence")
        self.release("maya")
        self.release("eli")
        self.assertEqual(self.s.coordinate("checkout", "eli")["status"], "needs_evidence")
        self.release("noor")
        pid = self.s.coordinate("checkout", "maya")["plan_id"]
        result = self.s.execute("checkout", "noor", pid)
        self.assertTrue(result["committed"])
        self.assertFalse(result["before"][0]["passed"])
        self.assertTrue(all(c["passed"] for c in result["checks"]))
        shared = json.dumps(self.s.snapshot("checkout", "alex"))
        shared_calls = json.dumps([c for kind, c in self.provider.calls if kind == "shared"])
        for secret in ["PRIVATE-CUSTOMER", "PRIVATE-SOURCE", "PRIVATE-OPS", "Juniper", "dana@", "source_id", "support-note"]:
            self.assertNotIn(secret, shared)
            self.assertNotIn(secret, shared_calls)
        for kind, context in self.provider.calls:
            if kind == "private":
                self.assertEqual(len(context["documents"]), 1)

    def test_private_ownership_and_approval(self):
        pid = self.s.analyze("checkout", "maya")["proposal_ids"][0]
        self.fault(404, self.s.disclose, "checkout", "eli", pid)
        self.assertEqual(self.s.private_state("checkout", "eli")["proposals"], [])
        self.assertEqual(self.s.snapshot("checkout", "eli")["claims"], [])
        first = self.s.disclose("checkout", "maya", pid)
        self.assertEqual(first, self.s.disclose("checkout", "maya", pid))
        self.assertEqual(len(self.s.snapshot("checkout", "maya")["claims"]), 1)

    def test_cross_room_denial(self):
        for fn in [self.s.snapshot, self.s.private_state, self.s.analyze, self.s.coordinate]:
            self.fault(403, fn, "other", "maya")
        self.fault(403, self.s.disclose, "other", "maya", "arbitrary")

    def test_viewer_cannot_mutate_and_contributor_cannot_execute(self):
        self.fault(403, self.s.analyze, "checkout", "alex")
        self.fault(403, self.s.coordinate, "checkout", "alex")
        self.fault(403, self.s.message, "checkout", "alex", "hello")
        pid = self.ready()
        self.fault(403, self.s.execute, "checkout", "maya", pid)

    def test_withdrawal_stales_plan_and_does_not_erase_history(self):
        pid = self.ready()
        did = self.s.snapshot("checkout", "maya")["claims"][0]["id"]
        self.fault(404, self.s.withdraw, "checkout", "eli", did)
        self.s.withdraw("checkout", "maya", did)
        self.fault(409, self.s.execute, "checkout", "noor", pid)
        snap = self.s.snapshot("checkout", "maya")
        self.assertTrue(snap["plans"][0]["stale"])
        self.assertIn("disclosed", [e["kind"] for e in snap["events"]])

    def test_source_update_invalidates_release_and_old_proposal(self):
        self.release("maya")
        p = self.s.private_state("checkout", "maya")["proposals"][0]
        self.s.update_document("checkout", "maya", "support-note", "FACT affected_segment=us_card", 1)
        self.assertEqual(self.s.snapshot("checkout", "maya")["claims"], [])
        self.fault(409, self.s.disclose, "checkout", "maya", p["id"])
        self.fault(409, self.s.update_document, "checkout", "maya", "support-note", "new", 1)
        self.fault(404, self.s.update_document, "checkout", "eli", "support-note", "new", 2)

    def test_revoke_removes_access_and_stales_plan(self):
        pid = self.ready()
        self.s.revoke("checkout", "noor", "maya")
        self.fault(403, self.s.snapshot, "checkout", "maya")
        self.fault(403, self.s.private_state, "checkout", "maya")
        self.fault(409, self.s.execute, "checkout", "noor", pid)

    def test_concurrent_execute_has_one_effect(self):
        pid = self.ready()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.s.execute("checkout", "noor", pid), range(6)))
        self.assertTrue(all(r == results[0] for r in results))
        events = self.s.snapshot("checkout", "maya")["events"]
        self.assertEqual(sum(e["kind"] == "verified" for e in events), 1)

    def test_persistence_across_restart(self):
        pid = self.ready()
        result = self.s.execute("checkout", "noor", pid)
        second = Service(Store(self.path))
        second.store.seed()
        self.assertEqual(second.execute("checkout", "noor", pid), result)
        self.assertFalse(second.snapshot("checkout", "eli")["config"]["fast_checkout"])

    def test_hostile_private_model_cannot_publish_free_text_or_borrow_source(self):
        bad = [
            {"proposals": [{"key": "affected_segment", "value": "PRIVATE-CUSTOMER", "source_id": "support-note"}]},
            {"proposals": [{"key": "affected_segment", "value": "eu_wallet", "source_id": "operations-note"}]},
            {"proposals": [{"key": "rollback_safe", "value": "yes", "source_id": "support-note"}]},
            {"proposals": [], "summary": "secret"},
            {"proposals": [{"key": [], "value": "x", "source_id": "support-note"}]},
            {"proposals": [{"key": "affected_segment", "value": "eu_wallet", "source_id": "support-note", "tool": "shell"}]},
        ]
        for output in bad:
            self.provider.private = lambda context: output
            self.fault(502, self.s.analyze, "checkout", "maya")
        self.assertEqual(self.s.private_state("checkout", "maya")["proposals"], [])
        self.assertEqual(self.s.snapshot("checkout", "maya")["events"], [])

    def test_hostile_shared_model_cannot_execute(self):
        self.ready()
        self.provider.shared = lambda context: {"action": "cat /secrets"}
        self.fault(502, self.s.coordinate, "checkout", "maya")
        self.assertTrue(self.s.snapshot("checkout", "maya")["config"]["fast_checkout"])

    def test_revocation_while_private_inference_in_flight(self):
        original = self.provider.private
        def revoke(context):
            self.s.revoke("checkout", "noor", "maya")
            return original(context)
        self.provider.private = revoke
        self.fault(403, self.s.analyze, "checkout", "maya")
        with self.store.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM proposals").fetchone()[0], 0)

    def test_change_while_shared_inference_in_flight(self):
        self.ready()
        def change(context):
            self.s.message("checkout", "eli", "New instruction; reconsider")
            return {"action": "disable_fast_checkout"}
        self.provider.shared = change
        self.fault(409, self.s.coordinate, "checkout", "maya")

    def test_failed_simulation_does_not_commit(self):
        self.s.update_document("checkout", "eli", "engineering-note", "FACT repair=restart", 1)
        pid = self.ready()
        result = self.s.execute("checkout", "noor", pid)
        self.assertFalse(result["committed"])
        self.assertEqual(self.s.snapshot("checkout", "maya")["config"], INITIAL_CONFIG)

    def test_conflicting_claims_require_resolution(self):
        claims = [{"key": "repair", "value": "restart"}, {"key": "repair", "value": "disable_fast_checkout"}]
        self.assertEqual(assess(claims)["conflicts"], ["repair"])
        self.assertEqual(assess(claims)["eligible"], [])

    def test_simulator_finds_rollback_and_restart_failures(self):
        for action in ["rollback", "restart"]:
            self.assertFalse(simulate(INITIAL_CONFIG, action)[1]["passed"])
        self.assertTrue(simulate(INITIAL_CONFIG, "disable_fast_checkout")[1]["passed"])

    def test_authentication_expiry_and_logout(self):
        self.fault(401, self.s.login, "maya", "wrong")
        self.fault(401, self.s.login, "unknown", "wrong")
        token, csrf = self.s.login("maya", "maya-demo")
        self.assertEqual(self.s.authenticate(token)["csrf"], csrf)
        self.s.logout(token)
        self.fault(401, self.s.authenticate, token)

    def test_provider_failure_publishes_nothing(self):
        def fail(context):
            raise ProviderError("Provider unavailable")
        self.provider.private = fail
        self.fault(502, self.s.analyze, "checkout", "maya")
        self.assertEqual(self.s.private_state("checkout", "maya")["proposals"], [])


if __name__ == "__main__":
    unittest.main()
