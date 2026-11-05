import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from veritaserum.server import Server
from veritaserum.service import Service
from veritaserum.store import Store


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        store = Store(Path(cls.tmp.name) / "http.sqlite")
        store.seed()
        cls.server = Server(("127.0.0.1", 0), Service(store))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, data=None, cookie=None, csrf=None, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        headers.update(extra or {})
        conn.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        result = json.loads(raw) if response.getheader("Content-Type") == "application/json" else raw.decode()
        output = response.status, dict(response.getheaders()), result
        conn.close()
        return output

    def login(self, user):
        status, headers, result = self.request("/api/login", {"user": user, "password": f"{user}-demo"})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";")[0], result["csrf"]

    def test_unauthenticated_reads_denied(self):
        self.assertEqual(self.request("/api/rooms/checkout/private")[0], 401)
        self.assertEqual(self.request("/api/rooms/checkout/state")[0], 401)
        self.assertEqual(self.request("/api/rooms")[0], 401)

    def test_new_investigation_private_note_and_knowledge_http(self):
        cookie, csrf = self.login("noor")
        body = {"source_room": "checkout", "name": "HTTP investigation", "goal": "Restore checkout",
                "members": ["maya", "eli", "noor"]}
        self.assertEqual(self.request("/api/rooms", body, cookie)[0], 403)
        status, _, created = self.request("/api/rooms", body, cookie, csrf)
        self.assertEqual(status, 200)
        room = created["id"]
        base = f"/api/rooms/{room}"
        self.assertEqual(self.request(base + "/add-document", {"title": "Private title", "body": "Private contents"}, cookie, csrf)[0], 200)
        status, _, shared = self.request(base + "/state", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertNotIn("Private title", json.dumps(shared))
        self.assertEqual(self.request(base + "/knowledge", {"runbook": "Shared runbook", "revision": shared["revision"]}, cookie, csrf)[0], 200)
        viewer, _ = self.login("alex")
        self.assertEqual(self.request(base + "/state", cookie=viewer)[0], 403)
        self.assertNotIn(room, json.dumps(self.request("/api/rooms", cookie=viewer)[2]))
        member, _ = self.login("maya")
        self.assertEqual(self.request(base + "/private", cookie=member)[2]["documents"], [])

    def test_csrf_and_origin_required(self):
        cookie, csrf = self.login("maya")
        url = "/api/rooms/checkout/analyze"
        self.assertEqual(self.request(url, {}, cookie)[0], 403)
        self.assertEqual(self.request(url, {}, cookie, csrf, {"Origin": "https://evil.invalid"})[0], 403)
        self.assertEqual(self.request(url, {}, cookie, csrf)[0], 200)

    def test_actor_spoofing_does_not_grant_authority(self):
        cookie, csrf = self.login("maya")
        status, _, result = self.request("/api/rooms/checkout/execute", {"actor": "noor", "plan_id": "x"}, cookie, csrf)
        self.assertEqual(status, 403)

    def test_chat_routes_preserve_private_conversation(self):
        cookie, csrf = self.login("maya")
        status, _, result = self.request("/api/rooms", {"source_room": "checkout", "name": "Chat routes",
            "goal": "Restore checkout", "members": ["maya", "eli", "noor"]}, cookie, csrf)
        self.assertEqual(status, 200)
        base = "/api/rooms/" + result["id"]
        self.assertEqual(self.request(base + "/team-chat", {"text": "Please coordinate"}, cookie, csrf)[2]["status"], "needs_evidence")
        self.assertEqual(self.request(base + "/private-chat", {"text": "PRIVATE-CHAT-CANARY"}, cookie)[0], 403)
        self.assertEqual(self.request(base + "/private-chat", {"text": "PRIVATE-CHAT-CANARY"}, cookie, csrf)[0], 200)
        other, _ = self.login("eli")
        for route in ("/private", "/state"):
            self.assertNotIn("PRIVATE-CHAT-CANARY", json.dumps(self.request(base + route, cookie=other)[2]))

    def test_changed_browser_identity_is_not_mislabeled(self):
        cookie, csrf = self.login("eli")
        status, _, result = self.request("/api/rooms/checkout/private", cookie=cookie,
                                         extra={"X-Expected-User": "maya"})
        self.assertEqual(status, 401)
        self.assertNotIn("PRIVATE-SOURCE", json.dumps(result))

    def test_private_responses_are_scoped(self):
        cookie, csrf = self.login("eli")
        status, headers, result = self.request("/api/rooms/checkout/private", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("PRIVATE-SOURCE", json.dumps(result))
        self.assertNotIn("PRIVATE-CUSTOMER", json.dumps(result))
        self.assertNotIn("PRIVATE-OPS", json.dumps(result))

    def test_public_static_allowlist_and_csp(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("/../data/http.sqlite")[0], 404)
        self.assertEqual(self.request("/veritaserum/store.py")[0], 404)

    def test_host_rebinding_and_oversized_body(self):
        self.assertEqual(self.request("/", extra={"Host": "attacker.invalid"})[0], 403)
        self.assertEqual(self.request("/api/login", {"x": "a" * 25000})[0], 413)

    def test_session_logout_invalidates_cookie(self):
        cookie, csrf = self.login("alex")
        self.assertEqual(self.request("/api/logout", {}, cookie, csrf)[0], 200)
        self.assertEqual(self.request("/api/me", cookie=cookie)[0], 401)

    def test_full_http_workflow(self):
        sessions = {user: self.login(user) for user in ["maya", "eli", "noor"]}
        for user, (cookie, csrf) in sessions.items():
            status, _, body = self.request("/api/rooms/checkout/analyze", {}, cookie, csrf)
            self.assertEqual(status, 200)
            status, _, result = self.request("/api/rooms/checkout/disclose", {"proposal_id": body["proposal_ids"][0]}, cookie, csrf)
            self.assertEqual(status, 200)
        cookie, csrf = sessions["maya"]
        status, _, plan = self.request("/api/rooms/checkout/coordinate", {}, cookie, csrf)
        self.assertEqual(status, 200)
        cookie, csrf = sessions["noor"]
        status, _, result = self.request("/api/rooms/checkout/execute", {"plan_id": plan["plan_id"]}, cookie, csrf)
        self.assertEqual(status, 200)
        self.assertTrue(result["committed"])


if __name__ == "__main__":
    unittest.main()
