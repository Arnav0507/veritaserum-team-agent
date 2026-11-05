"""Loopback HTTP adapter. Production hosting/SSO is intentionally outside this milestone."""
import argparse
import getpass
import hmac
import json
import mimetypes
import os
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .providers import ChatProvider, ToolPlanningProvider, from_environment
from .service import Service, Fault
from .store import Store

STATIC = Path(__file__).parent.parent / "web"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service):
        super().__init__(address, Handler)
        self.service = service
        self.login_attempts = {}
        self.rate_lock = threading.Lock()

    def throttle_login(self, ip):
        with self.rate_lock:
            now = time.monotonic()
            recent = [t for t in self.login_attempts.get(ip, []) if t > now - 60]
            if len(recent) >= 20:
                raise Fault(429, "Too many login attempts; wait one minute")
            self.login_attempts[ip] = recent + [now]


class Handler(BaseHTTPRequestHandler):
    server_version = "Veritaserum"

    def setup(self):
        super().setup()
        self.connection.settimeout(50)

    def log_message(self, format, *args):
        # Access log intentionally excludes URL, headers and payloads.
        pass

    def reply(self, status, value, cookie=None, content_type="application/json"):
        body = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["vt_session"].value if "vt_session" in cookie else ""
        except Exception:
            return ""

    def check_host(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed:
            raise Fault(403, "Unrecognized host")

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, mutation):
        try:
            self.check_host()
            path = urlparse(self.path).path
            if mutation:
                if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
                    raise Fault(403, "Origin check failed")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise Fault(415, "JSON required")
                if self.headers.get("Transfer-Encoding"):
                    raise Fault(400, "Transfer encoding unsupported")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise Fault(400, "Invalid content length") from None
                if length < 0 or length > 24000:
                    raise Fault(413, "Request too large")
                try:
                    body = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeDecodeError):
                    raise Fault(400, "Invalid JSON") from None
                if not isinstance(body, dict):
                    raise Fault(400, "Expected an object")
            else:
                body = {}
            s = self.server.service
            if path == "/api/login" and mutation:
                self.server.throttle_login(self.client_address[0])
                token, csrf = s.login(body.get("user"), body.get("password"))
                self.reply(200, {"csrf": csrf}, cookie=f"vt_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800")
                return
            if not path.startswith("/api/") and not mutation:
                file = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(path)
                if not file:
                    raise Fault(404, "Not found")
                self.reply(200, (STATIC / file).read_bytes(), content_type=mimetypes.guess_type(file)[0] or "text/plain")
                return
            auth = s.authenticate(self.token())
            expected_user = self.headers.get("X-Expected-User")
            if expected_user is not None and expected_user != auth["user"]:
                raise Fault(401, "The browser identity changed; sign in again")
            if mutation and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), auth["csrf"]):
                raise Fault(403, "CSRF check failed")
            if path == "/api/me" and not mutation:
                self.reply(200, auth)
                return
            if path == "/api/logout" and mutation:
                s.logout(self.token())
                self.reply(200, {"ok": True}, cookie="vt_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
                return
            if path == "/api/rooms":
                result = s.create_room(auth["user"], required_string(body, "source_room"), body.get("name"),
                                       body.get("goal"), body.get("members")) if mutation else s.list_rooms(auth["user"])
                self.reply(200, result)
                return
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "rooms"]:
                raise Fault(404, "Not found")
            room, operation = parts[2:]
            actor = auth["user"]
            reads = {"state": s.snapshot, "private": s.private_state, "conversation": s.conversation}
            if not mutation and operation in reads:
                result = reads[operation](room, actor)
            elif mutation:
                # No client supplied actor, role, action or execution arguments are trusted.
                routes = {
                    "turn": lambda: s.turn(room, actor, body.get("audience"), body.get("text")),
                    "analyze": lambda: s.analyze(room, actor),
                    "disclose": lambda: s.disclose(room, actor, required_string(body, "proposal_id")),
                    "withdraw": lambda: s.withdraw(room, actor, required_string(body, "disclosure_id")),
                    "coordinate": lambda: s.coordinate(room, actor),
                    "execute": lambda: s.execute(room, actor, required_string(body, "plan_id")),
                    "message": lambda: s.message(room, actor, body.get("text")),
                    "team-chat": lambda: s.team_chat(room, actor, body.get("text")),
                    "private-chat": lambda: s.private_chat(room, actor, body.get("text")),
                    "document": lambda: s.update_document(room, actor, required_string(body, "document_id"),
                                                           body.get("body"), body.get("version")),
                    "add-document": lambda: s.add_document(room, actor, body.get("title"), body.get("body")),
                    "knowledge": lambda: s.update_knowledge(room, actor, body.get("runbook"), body.get("revision")),
                    "revoke": lambda: s.revoke(room, actor, required_string(body, "user")),
                }
                if operation not in routes:
                    raise Fault(404, "Not found")
                result = routes[operation]()
            else:
                raise Fault(404, "Not found")
            # Reauthenticate after slow inference so an expired/logged-out session receives no data.
            s.authenticate(self.token())
            self.reply(200, result)
        except Fault as exc:
            self.reply(exc.status, {"error": exc.message})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception:
            self.reply(500, {"error": "Internal error; no private details are included"})


def required_string(body, key):
    value = body.get(key)
    if not isinstance(value, str) or not value or len(value) > 128:
        raise Fault(400, f"Invalid {key}")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default="data/veritaserum.sqlite")
    parser.add_argument("--provider", choices=["environment", "fireworks", "meta"], default="environment")
    parser.add_argument("--model", help="Fireworks model ID; alternatively set FIREWORKS_MODEL")
    parser.add_argument("--private-model", default="muse-spark-1.3", help="Meta private-worker model")
    parser.add_argument("--shared-model", default="muse-wonder-1.0", help="Meta shared-coordinator model")
    parser.add_argument("--prompt-key", action="store_true", help="Read provider key without echo from your terminal")
    args = parser.parse_args()
    if args.provider == "meta":
        key = getpass.getpass("Meta Model API key (hidden): ") if args.prompt_key else os.environ.get("MODEL_API_KEY", "")
        if not key:
            parser.error("Meta requires MODEL_API_KEY or --prompt-key")
        if args.model:
            parser.error("For Meta use --private-model and --shared-model")
        endpoint = "https://api.meta.ai/v1/chat/completions"
        private = ChatProvider(endpoint, args.private_model, key)
        shared = ToolPlanningProvider(endpoint, args.shared_model, key)
    elif args.provider == "fireworks":
        model = args.model or os.environ.get("FIREWORKS_MODEL", "")
        key = getpass.getpass("Fireworks API key (hidden): ") if args.prompt_key else os.environ.get("FIREWORKS_API_KEY", "")
        if not model or not key:
            parser.error("Fireworks requires --model (or FIREWORKS_MODEL) and FIREWORKS_API_KEY (or --prompt-key)")
        endpoint = "https://api.fireworks.ai/inference/v1/chat/completions"
        private, shared = ChatProvider(endpoint, model, key), ChatProvider(endpoint, model, key)
    else:
        if args.model or args.prompt_key:
            parser.error("--model and --prompt-key require a selected live provider")
        private, shared = from_environment("PRIVATE"), from_environment("SHARED")
    store = Store(args.db)
    store.seed(natural=private.mode.startswith("live"))
    service = Service(store, private, shared)
    server = Server(("127.0.0.1", args.port), service)
    print(f"Veritaserum local synthetic demo: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Private: {service.private_provider.mode}; Shared: {service.shared_provider.mode}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
