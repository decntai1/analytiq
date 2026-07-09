"""
Accounts — users, sessions, plan credits, and saved conversations.

Complements core/tenancy.py: a Tenant is the ISOLATION unit (data, indexes,
dedicated model endpoint); a User is a PERSON who logs in and belongs to exactly
one tenant. Individuals get an auto-created personal tenant on registration;
company employees join an existing tenant via its invite code, giving every
company a dedicated workspace its whole team shares.

Storage is a single SQLite file (stdlib sqlite3, WAL). Same swap-for-a-real-DB
contract as TenantStore: the interface is the API, the storage is a detail.

Security notes:
- Passwords: scrypt (stdlib hashlib) with per-user salt; no plaintext anywhere.
- Sessions: random 32-byte tokens, server-side expiry, delivered as HttpOnly
  cookies by the API layer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass

import config

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
SESSION_TTL_S = 14 * 24 * 3600  # 14 days


@dataclass
class User:
    user_id: str
    email: str
    tenant_id: str
    role: str = "member"      # member | owner
    plan: str = ""            # empty = inherit tenant plan
    created: float = 0.0


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


class AccountStore:
    """Thread-safe SQLite-backed store for users/sessions/usage/conversations."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.settings.accounts_db
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            c = self._db
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
              pw_hash BLOB NOT NULL, salt BLOB NOT NULL,
              tenant_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
              plan TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
              token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS usage(
              user_id TEXT NOT NULL, period TEXT NOT NULL, credits INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (user_id, period));
            CREATE TABLE IF NOT EXISTS conversations(
              conv_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT 'New chat', created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
              msg_id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL,
              role TEXT NOT NULL, content TEXT NOT NULL,
              charts TEXT NOT NULL DEFAULT '[]', created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_msgs_conv ON messages(conv_id, msg_id);
            CREATE INDEX IF NOT EXISTS idx_convs_user ON conversations(user_id, created);
            """)
            c.commit()

    # --- users / auth ------------------------------------------------------
    def create_user(self, email: str, password: str, tenant_id: str,
                    role: str = "member", plan: str = "") -> User:
        email = email.strip().lower()
        salt = secrets.token_bytes(16)
        uid = "u_" + secrets.token_hex(8)
        with self._lock:
            self._db.execute(
                "INSERT INTO users(user_id,email,pw_hash,salt,tenant_id,role,plan,created)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (uid, email, _hash_pw(password, salt), salt, tenant_id, role, plan, time.time()))
            self._db.commit()
        return User(uid, email, tenant_id, role, plan, time.time())

    def verify(self, email: str, password: str) -> User | None:
        email = email.strip().lower()
        with self._lock:
            row = self._db.execute(
                "SELECT user_id,email,pw_hash,salt,tenant_id,role,plan,created"
                " FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            return None
        if not secrets.compare_digest(row[2], _hash_pw(password, row[3])):
            return None
        return User(row[0], row[1], row[4], row[5], row[6], row[7])

    def by_email(self, email: str) -> User | None:
        with self._lock:
            row = self._db.execute(
                "SELECT user_id,email,tenant_id,role,plan,created FROM users WHERE email=?",
                (email.strip().lower(),)).fetchone()
        return User(row[0], row[1], row[2], row[3], row[4], row[5]) if row else None

    # --- sessions ----------------------------------------------------------
    def change_password(self, user_id: str, current: str, new: str) -> bool:
        """Verify the current password, then set the new one (fresh salt)."""
        with self._lock:
            row = self._db.execute("SELECT email, pw_hash, salt FROM users WHERE user_id=?",
                                   (user_id,)).fetchone()
        if not row:
            return False
        if not hmac.compare_digest(_hash_pw(current, row[2]), row[1]):
            return False
        salt = os.urandom(16)
        with self._lock:
            self._db.execute("UPDATE users SET pw_hash=?, salt=? WHERE user_id=?",
                             (_hash_pw(new, salt), salt, user_id))
            self._db.commit()
        return True

    def open_session(self, user_id: str) -> str:
        token = "s_" + secrets.token_urlsafe(32)
        with self._lock:
            self._db.execute("INSERT INTO sessions(token,user_id,expires) VALUES(?,?,?)",
                             (token, user_id, time.time() + SESSION_TTL_S))
            self._db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            self._db.commit()
        return token

    def user_by_session(self, token: str) -> User | None:
        if not token:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT u.user_id,u.email,u.tenant_id,u.role,u.plan,u.created"
                " FROM sessions s JOIN users u ON u.user_id=s.user_id"
                " WHERE s.token=? AND s.expires>?", (token, time.time())).fetchone()
        return User(row[0], row[1], row[2], row[3], row[4], row[5]) if row else None

    def close_session(self, token: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE token=?", (token,))
            self._db.commit()

    # --- plan credits (monthly, lazily reset by period key) -----------------
    @staticmethod
    def _period() -> str:
        return time.strftime("%Y-%m")

    def credits_used(self, user_id: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT credits FROM usage WHERE user_id=? AND period=?",
                                   (user_id, self._period())).fetchone()
        return row[0] if row else 0

    def spend_credits(self, user_id: str, amount: int, limit: int) -> tuple[bool, int]:
        """Atomically spend `amount` if it stays within `limit`.
        Returns (ok, remaining_after)."""
        p = self._period()
        with self._lock:
            row = self._db.execute("SELECT credits FROM usage WHERE user_id=? AND period=?",
                                   (user_id, p)).fetchone()
            used = row[0] if row else 0
            if used + amount > limit:
                return False, max(limit - used, 0)
            self._db.execute(
                "INSERT INTO usage(user_id,period,credits) VALUES(?,?,?)"
                " ON CONFLICT(user_id,period) DO UPDATE SET credits=credits+?",
                (user_id, p, amount, amount))
            self._db.commit()
            return True, limit - used - amount

    # --- conversations (saved chat windows) ---------------------------------
    def create_conversation(self, tenant_id: str, user_id: str, title: str = "New chat") -> str:
        cid = "c_" + secrets.token_hex(8)
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations(conv_id,tenant_id,user_id,title,created)"
                " VALUES(?,?,?,?,?)", (cid, tenant_id, user_id, title[:120], time.time()))
            self._db.commit()
        return cid

    def list_conversations(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT conv_id,title,created FROM conversations WHERE user_id=?"
                " ORDER BY created DESC LIMIT ?", (user_id, limit)).fetchall()
        return [{"conv_id": r[0], "title": r[1], "created": r[2]} for r in rows]

    def conversation_owner(self, conv_id: str) -> tuple[str, str] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT tenant_id,user_id FROM conversations WHERE conv_id=?",
                (conv_id,)).fetchone()
        return (row[0], row[1]) if row else None

    def append_message(self, conv_id: str, role: str, content: str,
                       charts: list | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO messages(conv_id,role,content,charts,created) VALUES(?,?,?,?,?)",
                (conv_id, role, content, json.dumps(charts or []), time.time()))
            # first user message becomes the title
            self._db.execute(
                "UPDATE conversations SET title=? WHERE conv_id=? AND title='New chat' AND ?='user'",
                (content[:80], conv_id, role))
            self._db.commit()

    def get_messages(self, conv_id: str, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT role,content,charts,created FROM messages WHERE conv_id=?"
                " ORDER BY msg_id ASC LIMIT ?", (conv_id, limit)).fetchall()
        return [{"role": r[0], "content": r[1], "charts": json.loads(r[2]), "created": r[3]}
                for r in rows]

    def history_for_model(self, conv_id: str, max_messages: int = 8,
                          max_chars: int = 6000) -> list[dict]:
        """Last N user/assistant turns, char-capped, oldest-first — ready to inject."""
        msgs = [m for m in self.get_messages(conv_id) if m["role"] in ("user", "assistant")]
        msgs = msgs[-max_messages:]
        out, total = [], 0
        for m in reversed(msgs):
            c = m["content"][:2000]
            if total + len(c) > max_chars:
                break
            out.append({"role": m["role"], "content": c})
            total += len(c)
        return list(reversed(out))
