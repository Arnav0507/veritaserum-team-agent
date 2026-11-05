import json
import time
import secrets
import threading

from .policy import FACTS, RUNBOOK, ACTIONS, INITIAL_CONFIG, assess, statement, simulate, verify
from .providers import ReferenceProvider, ProviderError
from .store import check_password, password_hash, token_hash, identifier, event


class Fault(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def member(db, room, actor, roles=None):
    row = db.execute("SELECT * FROM members WHERE room=? AND user=? AND active=1", (room, actor)).fetchone()
    if not row:
        raise Fault(403, "Room access denied")
    if roles is not None and row["role"] not in roles:
        raise Fault(403, "Your role cannot perform this action")
    return dict(row)


def active_claims(db, room):
    return [dict(row) for row in db.execute(
        "SELECT id,owner,key,value,created FROM disclosures WHERE room=? AND active=1 ORDER BY created,id", (room,))]


class Service:
    def __init__(self, store, private_provider=None, shared_provider=None):
        self.store = store
        self.private_provider = private_provider or ReferenceProvider()
        self.shared_provider = shared_provider or ReferenceProvider()
        self.dummy_password = password_hash("nonexistent-account")
        self._inflight = set()
        self._inflight_lock = threading.Lock()

    def _infer(self, scope, fn, context):
        with self._inflight_lock:
            if scope in self._inflight:
                raise Fault(429, "An agent is already working on this request. Wait for it to finish before trying again.")
            self._inflight.add(scope)
        try:
            return fn(context)
        except ProviderError as exc:
            raise Fault(502, str(exc)) from None
        finally:
            with self._inflight_lock:
                self._inflight.discard(scope)

    def _conversation(self, db, room, actor, audience):
        """Server-side audience projection. Private turns never enter a team projection."""
        turns = []
        for row in db.execute("SELECT id,actor,kind,payload,created FROM events WHERE room=? ORDER BY revision DESC LIMIT 100", (room,)):
            payload = json.loads(row["payload"])
            if row["kind"] in {"message", "agent_message"}:
                turns.append({"id": "shared-" + str(row["id"]), "audience": "team",
                    "speaker": row["actor"] if row["kind"] == "message" else "agent",
                    "text": payload["text"], "created": row["created"]})
            elif row["kind"] == "disclosed":
                turns.append({"id": "shared-" + str(row["id"]), "audience": "team", "speaker": "agent",
                    "text": "Approved contribution from " + row["actor"] + ": " + payload["statement"], "created": row["created"]})
            elif row["kind"] == "delegated":
                turns.append({"id": "shared-" + str(row["id"]), "audience": "team", "speaker": "agent",
                    "text": "I need approved evidence for: " + ", ".join(r["label"] for r in payload["requests"]) + ". You can respond privately; I will ask before sharing a statement.", "created": row["created"]})
        if audience == "private":
            for row in db.execute("SELECT id,speaker,text,created FROM private_messages WHERE room=? AND owner=? ORDER BY id DESC LIMIT 40", (room, actor)):
                turns.append({"id": "private-" + str(row["id"]), "audience": "private",
                    "speaker": actor if row["speaker"] == "you" else "agent", "text": row["text"], "created": row["created"]})
        return sorted(turns, key=lambda t: (t["created"], t["id"]))

    def conversation(self, room, actor):
        with self.store.tx() as db:
            member(db, room, actor)
            return {"task_id": room, "agent": "Veritaserum", "turns": self._conversation(db, room, actor, "private")}

    def turn(self, room, actor, audience, text):
        if not isinstance(audience, str) or audience not in {"team", "private"}:
            raise Fault(400, "Choose team or private audience")
        if audience == "team":
            return self.team_chat(room, actor, text)
        self.private_chat(room, actor, text)
        return self.analyze(room, actor)

    def list_rooms(self, actor):
        with self.store.tx() as db:
            return {"rooms": [dict(r) for r in db.execute(
                "SELECT r.id,r.name,r.goal,m.role FROM rooms r JOIN members m ON m.room=r.id "
                "WHERE m.user=? AND m.active=1 ORDER BY r.rowid DESC", (actor,))]}

    def create_room(self, actor, source_room, name, goal, users):
        if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
                or not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 1000
                or not isinstance(users, list) or not 1 <= len(users) <= 30
                or not all(isinstance(u, str) for u in users)):
            raise Fault(400, "Provide a name, a goal, and 1–30 team members")
        with self.store.tx() as db:
            member(db, source_room, actor, FACTS_ROLES)
            selected = set(users) | {actor}
            people = [member(db, source_room, user) for user in selected]
            if not FACTS_ROLES.issubset({p["role"] for p in people}):
                raise Fault(400, "Include support, engineering, and operations to complete this workflow")
            room = identifier()
            db.execute("INSERT INTO rooms(id,name,goal,runbook,config) VALUES(?,?,?,?,?)",
                       (room, name.strip(), goal.strip(), RUNBOOK, json.dumps(INITIAL_CONFIG)))
            for p in people:
                db.execute("INSERT INTO members(room,user,role) VALUES(?,?,?)", (room, p["user"], p["role"]))
            event(db, room, actor, "opened", {"name": name.strip(), "goal": goal.strip()})
            return {"id": room}

    def add_document(self, room, actor, title, body):
        if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 120
                or not isinstance(body, str) or not 1 <= len(body.strip()) <= 16000):
            raise Fault(400, "Give the note a title (up to 120 characters) and text (up to 16000 characters)")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            count = db.execute("SELECT count(*) FROM documents WHERE room=? AND owner=?", (room, actor)).fetchone()[0]
            if count >= 20:
                raise Fault(400, "This workspace supports 20 private notes per person. Edit an existing note.")
            did = identifier()
            db.execute("INSERT INTO documents(id,room,owner,title,body) VALUES(?,?,?,?,?)",
                       (did, room, actor, title.strip(), body))
            return {"id": did}

    def update_knowledge(self, room, actor, runbook, revision):
        if not isinstance(runbook, str) or not 1 <= len(runbook.strip()) <= 12000 or type(revision) is not int:
            raise Fault(400, "Company knowledge must contain 1–12000 characters and a current revision")
        with self.store.tx() as db:
            member(db, room, actor, {"operations"})
            current = db.execute("SELECT revision FROM rooms WHERE id=?", (room,)).fetchone()[0]
            if current != revision:
                raise Fault(409, "The investigation changed. Review the latest state before saving company knowledge.")
            db.execute("UPDATE rooms SET runbook=? WHERE id=?", (runbook.strip(), room))
            event(db, room, actor, "knowledge_updated", {"runbook": runbook.strip()})
            return {"ok": True}

    def login(self, user, password):
        if not isinstance(user, str) or not isinstance(password, str) or len(password) > 256:
            raise Fault(401, "Invalid login")
        with self.store.tx() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user,)).fetchone()
            valid = check_password(password, row["password"] if row else self.dummy_password)
            if not row or not valid:
                raise Fault(401, "Invalid login")
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash(token), user, csrf, time.time() + 28800))
            return token, csrf

    def authenticate(self, token):
        with self.store.tx() as db:
            row = db.execute("SELECT s.user,s.csrf,u.name FROM sessions s JOIN users u ON u.id=s.user "
                             "WHERE token=? AND expires>?", (token_hash(token), time.time())).fetchone()
            if not row:
                raise Fault(401, "Please sign in")
            return dict(row)

    def logout(self, token):
        with self.store.tx() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token_hash(token),))

    def snapshot(self, room, actor):
        with self.store.tx() as db:
            membership = member(db, room, actor)
            state = dict(db.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone())
            claims = active_claims(db, room)
            for c in claims:
                c["statement"] = statement(c["key"], c["value"])
            plans = []
            for row in db.execute("SELECT * FROM plans WHERE room=? ORDER BY created DESC LIMIT 20", (room,)):
                p = dict(row)
                p["evidence"] = json.loads(p["evidence"])
                p["result"] = json.loads(p["result"]) if p["result"] else None
                p["stale"] = p["status"] == "proposed" and p["revision"] != state["revision"]
                plans.append(p)
            events = [dict(r) for r in db.execute("SELECT revision,actor,kind,payload,created FROM events "
                                                 "WHERE room=? ORDER BY revision DESC LIMIT 100", (room,))]
            for e in events:
                e["payload"] = json.loads(e["payload"])
            people = [dict(r) for r in db.execute("SELECT m.user,u.name,m.role FROM members m JOIN users u "
                                                 "ON m.user=u.id WHERE room=? AND active=1", (room,))]
            config = json.loads(state["config"])
            return {"id": room, "name": state["name"], "goal": state["goal"], "revision": state["revision"],
                    "role": membership["role"], "members": people, "claims": claims,
                    "plans": plans, "events": events, "assessment": assess(claims),
                    "runbook": state["runbook"], "config": config, "checks": verify(config),
                    "providers": {"private": self.private_provider.mode, "shared": self.shared_provider.mode}}

    def private_state(self, room, actor):
        with self.store.tx() as db:
            member(db, room, actor)
            docs = [dict(r) for r in db.execute("SELECT id,title,body,version FROM documents WHERE room=? AND owner=?",
                                               (room, actor))]
            proposals = [dict(r) for r in db.execute("SELECT p.*,d.id AS disclosure_id,d.active AS released "
                       "FROM proposals p LEFT JOIN disclosures d ON p.id=d.proposal "
                       "WHERE p.room=? AND p.owner=? ORDER BY p.created DESC LIMIT 40", (room, actor))]
            for p in proposals:
                p["statement"] = statement(p["key"], p["value"])
                source = next((d for d in docs if d["id"] == p["source_id"]), None)
                p["stale"] = not source or source["version"] != p["source_version"]
                p["source_title"] = source["title"] if source else "Unavailable source"
            messages = [dict(r) for r in db.execute(
                "SELECT speaker,text FROM private_messages WHERE room=? AND owner=? ORDER BY id DESC LIMIT 40", (room, actor))][::-1]
            return {"documents": docs, "proposals": proposals, "messages": messages}

    def private_chat(self, room, actor, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise Fault(400, "Write a private message of 1–2000 characters")
        # Messages become owned evidence, so approval references an actual versioned source.
        self.add_document(room, actor, "Private chat evidence", text.strip())
        with self.store.tx() as db:
            m = member(db, room, actor, FACTS_ROLES)
            db.execute("INSERT INTO private_messages(room,owner,speaker,text,created) VALUES(?,?,?,?,?)",
                       (room, actor, "you", text.strip(), time.time()))
            docs = [dict(r) for r in db.execute("SELECT id,title,body,version FROM documents WHERE room=? AND owner=?", (room, actor))]
            history = [dict(r) for r in db.execute("SELECT speaker,text FROM private_messages WHERE room=? AND owner=? ORDER BY id DESC LIMIT 12", (room, actor))][::-1]
            r = db.execute("SELECT goal,runbook FROM rooms WHERE id=?", (room,)).fetchone()
            context = {"role": m["role"], "team_goal": r["goal"], "messages": history,
                       "documents": docs, "requested_facts": [k for k, f in FACTS.items() if f["role"] == m["role"]]}
            context.update({"task_id": room, "agent_identity": "Veritaserum", "audience": "private",
                            "company_knowledge": r["runbook"],
                            "conversation": self._conversation(db, room, actor, "private"),
                            "approved_facts": active_claims(db, room)})
            context["team_messages"] = [json.loads(e["payload"])["text"] for e in db.execute(
                "SELECT payload FROM events WHERE room=? AND kind='message' ORDER BY revision DESC LIMIT 8", (room,))][::-1]
        result = self._infer(("private", room, actor), self.private_provider.converse, context)
        if not isinstance(result, dict) or set(result) != {"reply"} or not isinstance(result["reply"], str) or not 1 <= len(result["reply"]) <= 6000:
            raise Fault(502, "Private assistant returned an invalid reply. Your message is saved privately.")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            current = [dict(r) for r in db.execute("SELECT id,title,body,version FROM documents WHERE room=? AND owner=?", (room, actor))]
            if current != docs:
                raise Fault(409, "Your evidence changed during the reply. Your message is saved; try again after reviewing it.")
            db.execute("INSERT INTO private_messages(room,owner,speaker,text,created) VALUES(?,?,?,?,?)",
                       (room, actor, "agent", result["reply"], time.time()))
        return {"ok": True}

    def team_chat(self, room, actor, text):
        self.message(room, actor, text)
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            r = db.execute("SELECT goal,runbook,revision FROM rooms WHERE id=?", (room,)).fetchone()
            context = {"task_id": room, "agent_identity": "Veritaserum", "audience": "team",
                       "goal": r["goal"], "company_knowledge": r["runbook"],
                       "conversation": self._conversation(db, room, actor, "team"),
                       "approved_facts": active_claims(db, room), "assessment": assess(active_claims(db, room))}
        response = self._infer(("shared", room), self.shared_provider.converse, context)
        if not isinstance(response, dict) or set(response) != {"reply"} or not isinstance(response["reply"], str) or not 1 <= len(response["reply"]) <= 6000:
            raise Fault(502, "Agent returned an invalid reply. Your team message is saved.")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            if db.execute("SELECT revision FROM rooms WHERE id=?", (room,)).fetchone()[0] != r["revision"]:
                raise Fault(409, "Team context changed during the reply. Please send again.")
            event(db, room, actor, "agent_message", {"text": response["reply"], "shared_context": context})
        return self.coordinate(room, actor)

    def analyze(self, room, actor):
        with self.store.tx() as db:
            m = member(db, room, actor, FACTS_ROLES)
            docs = [dict(r) for r in db.execute("SELECT id,title,body,version FROM documents WHERE room=? AND owner=?",
                                               (room, actor))]
            allowed = {k: v for k, v in FACTS.items() if v["role"] == m["role"]}
            if not docs:
                raise Fault(400, "Add a private note before asking your agent to review it")
            context = {"task": "Find the requested incident facts for optional disclosure to this room.",
                       "allowed_facts": allowed, "documents": docs}
        output = self._infer(("private", room, actor), self.private_provider.private, context)
        sources = {d["id"]: d["version"] for d in docs}
        if (not isinstance(output, dict) or set(output) != {"proposals"}
                or not isinstance(output["proposals"], list) or len(output["proposals"]) > 8):
            raise Fault(502, "Private worker returned an invalid proposal schema")
        for p in output["proposals"]:
            if (not isinstance(p, dict) or set(p) != {"key", "value", "source_id"}
                    or not all(isinstance(v, str) for v in p.values())
                    or p["key"] not in allowed or p["value"] not in allowed[p["key"]]["values"]
                    or p["source_id"] not in sources):
                raise Fault(502, "Private worker output failed the disclosure boundary")
        with self.store.tx() as db:
            current = member(db, room, actor, FACTS_ROLES)
            if current["role"] != m["role"]:
                raise Fault(409, "Your role changed during analysis")
            current_sources = {r["id"]: r["version"] for r in db.execute(
                "SELECT id,version FROM documents WHERE room=? AND owner=?", (room, actor))}
            if current_sources != sources:
                raise Fault(409, "Private evidence changed; analyze again")
            ids = []
            for p in output["proposals"]:
                existing = db.execute("SELECT id FROM proposals WHERE room=? AND owner=? AND source_id=? "
                    "AND source_version=? AND key=? AND value=?", (room, actor, p["source_id"],
                        sources[p["source_id"]], p["key"], p["value"])).fetchone()
                pid = existing["id"] if existing else identifier()
                if not existing:
                    db.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?)",
                        (pid, room, actor, p["source_id"], sources[p["source_id"]], p["key"], p["value"], time.time()))
                ids.append(pid)
            return {"proposal_ids": ids}

    def disclose(self, room, actor, proposal_id):
        with self.store.tx() as db:
            m = member(db, room, actor, FACTS_ROLES)
            p = db.execute("SELECT * FROM proposals WHERE id=? AND room=? AND owner=?",
                           (proposal_id, room, actor)).fetchone()
            if not p:
                raise Fault(404, "Proposal not found")
            source = db.execute("SELECT version FROM documents WHERE id=? AND room=? AND owner=?",
                                (p["source_id"], room, actor)).fetchone()
            if not source or source["version"] != p["source_version"] or FACTS[p["key"]]["role"] != m["role"]:
                raise Fault(409, "Proposal is stale; analyze again")
            old = db.execute("SELECT id,active FROM disclosures WHERE proposal=?", (proposal_id,)).fetchone()
            if old:
                if not old["active"]:
                    db.execute("UPDATE disclosures SET active=1 WHERE id=?", (old["id"],))
                    event(db, room, actor, "disclosed", {"id": old["id"], "key": p["key"], "value": p["value"],
                                                       "statement": statement(p["key"], p["value"]), "reshared": True})
                return {"id": old["id"]}
            did = identifier()
            db.execute("INSERT INTO disclosures(id,room,owner,proposal,key,value,created) VALUES(?,?,?,?,?,?,?)",
                       (did, room, actor, proposal_id, p["key"], p["value"], time.time()))
            # No private source identifier or private title enters the public event.
            event(db, room, actor, "disclosed", {"id": did, "key": p["key"], "value": p["value"],
                                               "statement": statement(p["key"], p["value"])})
            return {"id": did}

    def withdraw(self, room, actor, disclosure_id):
        with self.store.tx() as db:
            member(db, room, actor)
            row = db.execute("SELECT * FROM disclosures WHERE id=? AND room=? AND owner=?",
                             (disclosure_id, room, actor)).fetchone()
            if not row:
                raise Fault(404, "Disclosure not found")
            if row["active"]:
                db.execute("UPDATE disclosures SET active=0 WHERE id=?", (disclosure_id,))
                event(db, room, actor, "withdrawn", {"id": disclosure_id})
            return {"ok": True}

    def coordinate(self, room, actor):
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            r = dict(db.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone())
            claims = active_claims(db, room)
            assessment = assess(claims)
            if assessment["missing"] or assessment["conflicts"]:
                requests = [{"key": key, "role": FACTS[key]["role"], "label": FACTS[key]["label"]}
                            for key in assessment["missing"]]
                event(db, room, actor, "delegated", {"requests": requests, "conflicts": assessment["conflicts"]})
                return {"status": "needs_evidence", "requests": requests, "conflicts": assessment["conflicts"]}
            context = {"company_knowledge": r["runbook"], "goal": r["goal"],
                       "disclosures": [{"id": c["id"], "key": c["key"], "value": c["value"]} for c in claims],
                       "simulator": json.loads(r["config"]),
                       "eligible_actions": assessment["eligible"]}
            context["team_messages"] = [json.loads(e["payload"])["text"] for e in db.execute(
                "SELECT payload FROM events WHERE room=? AND kind='message' ORDER BY revision DESC LIMIT 8", (room,))][::-1]
        # Preserve the application input before handing a separate object to the adapter.
        # This receipt contains only already-shared data, never headers or private inputs.
        context_receipt = json.loads(json.dumps(context))
        output = self._infer(("shared", room), self.shared_provider.shared, context)
        if (not isinstance(output, dict) or set(output) != {"action"}
                or (output["action"] is not None and output["action"] not in assessment["eligible"])):
            raise Fault(502, "Coordinator proposed an unauthorized action")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            current = db.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
            if current["revision"] != r["revision"]:
                raise Fault(409, "Team evidence changed during planning; coordinate again")
            if output["action"] is None:
                event(db, room, actor, "abstained", {})
                return {"status": "abstained"}
            pid = identifier()
            comparisons = [simulate(json.loads(r["config"]), action)[1] for action in ACTIONS]
            revision = event(db, room, actor, "planned", {"id": pid, "action": output["action"],
                                                         "shared_context": context_receipt,
                                                         "company_knowledge": r["runbook"], "goal": r["goal"],
                                                         "comparisons": comparisons,
                                                         "model": self.shared_provider.mode,
                                                         "evidence": [c["id"] for c in claims]})
            db.execute("INSERT INTO plans(id,room,revision,config_version,action,evidence,created) VALUES(?,?,?,?,?,?,?)",
                       (pid, room, revision, r["config_version"], output["action"],
                        json.dumps([c["id"] for c in claims]), time.time()))
            return {"status": "proposed", "plan_id": pid}

    def execute(self, room, actor, plan_id):
        with self.store.tx() as db:
            member(db, room, actor, {"operations"})
            p = db.execute("SELECT * FROM plans WHERE id=? AND room=?", (plan_id, room)).fetchone()
            if not p:
                raise Fault(404, "Plan not found")
            if p["result"]:
                return json.loads(p["result"])
            r = db.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
            claims = active_claims(db, room)
            if (p["revision"] != r["revision"] or p["config_version"] != r["config_version"]
                    or set(json.loads(p["evidence"])) != {c["id"] for c in claims}
                    or p["action"] not in assess(claims)["eligible"]):
                raise Fault(409, "Plan is stale; coordinate with current evidence before executing")
            config, result = simulate(json.loads(r["config"]), p["action"])
            result["plan_id"] = plan_id
            result["committed"] = result["passed"]
            if result["passed"]:
                db.execute("UPDATE rooms SET config=?,config_version=config_version+1 WHERE id=?",
                           (json.dumps(config), room))
            db.execute("UPDATE plans SET status=?,result=? WHERE id=?",
                       ("executed" if result["passed"] else "failed", json.dumps(result), plan_id))
            event(db, room, actor, "verified" if result["passed"] else "verification_failed", result)
            return result

    def message(self, room, actor, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise Fault(400, "Message must contain 1–2000 characters")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            event(db, room, actor, "message", {"text": text.strip()})
        return {"ok": True}

    def update_document(self, room, actor, doc_id, body, version):
        if not isinstance(body, str) or not body.strip() or len(body) > 16000 or type(version) is not int:
            raise Fault(400, "Invalid private document")
        with self.store.tx() as db:
            member(db, room, actor, FACTS_ROLES)
            doc = db.execute("SELECT * FROM documents WHERE id=? AND room=? AND owner=?", (doc_id, room, actor)).fetchone()
            if not doc:
                raise Fault(404, "Document not found")
            if doc["version"] != version:
                raise Fault(409, "Document changed; refresh before editing")
            db.execute("UPDATE documents SET body=?,version=version+1 WHERE id=?", (body, doc_id))
            # Updating a source invalidates all its current releases, without exposing its contents.
            disclosures = list(db.execute("SELECT d.id FROM disclosures d JOIN proposals p ON p.id=d.proposal "
                                          "WHERE p.source_id=? AND d.active=1", (doc_id,)))
            for d in disclosures:
                db.execute("UPDATE disclosures SET active=0 WHERE id=?", (d["id"],))
                event(db, room, actor, "withdrawn", {"id": d["id"]})
        return {"ok": True}

    def revoke(self, room, actor, target):
        with self.store.tx() as db:
            member(db, room, actor, {"operations"})
            if actor == target:
                raise Fault(400, "Self-revocation is not supported")
            member(db, room, target)
            db.execute("UPDATE members SET active=0 WHERE room=? AND user=?", (room, target))
            db.execute("UPDATE disclosures SET active=0 WHERE room=? AND owner=?", (room, target))
            event(db, room, actor, "member_revoked", {"user": target})
        return {"ok": True}


FACTS_ROLES = {schema["role"] for schema in FACTS.values()}
