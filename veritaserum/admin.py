"""Local administrator provisioning. Does not expose account creation over HTTP."""
import argparse
import getpass
import re
import time
from pathlib import Path

from .store import Store, password_hash, identifier, event


def provision(store, room, user, name, role, password, document="No evidence supplied yet."):
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", user) or not name.strip() or len(name) > 80:
        raise ValueError("Use a lowercase username and a display name of 1–80 characters")
    if role not in {"support", "engineering", "operations", "viewer"} or len(password) < 12:
        raise ValueError("A valid role and password of at least 12 characters are required")
    if len(document) > 16000:
        raise ValueError("Private evidence must be at most 16000 characters")
    with store.tx() as db:
        if not db.execute("SELECT 1 FROM rooms WHERE id=?", (room,)).fetchone():
            raise ValueError("Room does not exist")
        if db.execute("SELECT 1 FROM users WHERE id=?", (user,)).fetchone():
            raise ValueError("User already exists; provisioning does not overwrite accounts")
        db.execute("INSERT INTO users VALUES(?,?,?)", (user, name.strip(), password_hash(password)))
        db.execute("INSERT INTO members(room,user,role) VALUES(?,?,?)", (room, user, role))
        if role != "viewer":
            db.execute("INSERT INTO documents(id,room,owner,title,body) VALUES(?,?,?,?,?)",
                       (identifier(), room, user, "Private incident evidence", document))
        # New audience membership changes invalidate pending plans.
        event(db, room, "local-admin", "member_added", {"user": user, "role": role})


def main():
    parser = argparse.ArgumentParser(description="Provision a local prototype participant")
    parser.add_argument("--db", default="data/veritaserum.sqlite")
    parser.add_argument("--room", default="checkout")
    parser.add_argument("--user", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True, choices=["support", "engineering", "operations", "viewer"])
    parser.add_argument("--document", help="Optional UTF-8 private evidence file")
    args = parser.parse_args()
    password = getpass.getpass("New local account password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match")
    document = Path(args.document).read_text() if args.document else "No evidence supplied yet."
    try:
        provision(Store(args.db), args.room, args.user, args.name, args.role, password, document)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Participant provisioned. Existing room disclosures are visible to the new member.")


if __name__ == "__main__":
    main()
