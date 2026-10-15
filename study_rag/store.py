"""服务端账号、会话、租户隔离和事务式调用预算。"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
import unicodedata
from uuid import uuid4
from .limits import MODEL_JOB_LEASE_SECONDS


class AccessError(ValueError):
    pass


class LimitError(ValueError):
    pass


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    encoded = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${encoded}"


def password_matches(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, encoded = stored.split("$")
        if scheme != "pbkdf2_sha256" or rounds != "600000":
            return False
        return hmac.compare_digest(password_hash(password, salt), stored)
    except ValueError:
        return False


class Store:
    def __init__(self, path: Path, *, user_daily_limit: int = 20,
                 global_daily_limit: int = 100, max_concurrent: int = 2):
        if not all(isinstance(value, int) and value > 0 for value in
                   (user_daily_limit, global_daily_limit, max_concurrent)):
            raise ValueError("预算配置必须是正整数。")
        self.path = path
        self.user_limit, self.global_limit, self.max_concurrent = user_daily_limit, global_daily_limit, max_concurrent
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.database() as database:
            database.execute("PRAGMA journal_mode=WAL")
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("用户数据库版本不支持。")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS chats_owner ON chats(user_id, created);
                CREATE TABLE IF NOT EXISTS exchanges (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    request_key TEXT NOT NULL, question TEXT NOT NULL, result TEXT NOT NULL,
                    created REAL NOT NULL, UNIQUE(user_id, request_key));
                CREATE INDEX IF NOT EXISTS exchanges_chat ON exchanges(chat_id, created);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    request_key TEXT NOT NULL, budget_day TEXT NOT NULL,
                    state TEXT NOT NULL, lease_until REAL NOT NULL, usage TEXT,
                    UNIQUE(user_id, request_key));
                CREATE INDEX IF NOT EXISTS jobs_budget ON jobs(budget_day, user_id, state);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    bucket TEXT NOT NULL, created REAL NOT NULL);
            """)
            # 增量升级，原有账号默认仍为 learner，不按用户名自动提权。
            columns = {row[1] for row in database.execute("PRAGMA table_info(users)")}
            if "role" not in columns:
                database.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'learner' "
                                 "CHECK(role IN ('learner','admin'))")
            database.execute("PRAGMA user_version=2")

    @contextmanager
    def database(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection

    def register(self, username: str, password: str) -> dict:
        return self._create_user(username, password, role="learner")

    def create_admin(self, username: str, password: str) -> dict:
        """仅供本机维护入口使用；不覆盖或提升同名现有账号。"""
        return self._create_user(username, password, role="admin")

    def _create_user(self, username: str, password: str, *, role: str) -> dict:
        username = unicodedata.normalize("NFKC", username).casefold().strip()
        if not 3 <= len(username) <= 32 or not all(char.isalnum() or char in "_-" for char in username):
            raise ValueError("用户名须为3～32个字母、数字、汉字、下划线或短横线。")
        if not 10 <= len(password) <= 128:
            raise ValueError("密码长度须为10～128个字符。")
        user = {"id": uuid4().hex, "username": username, "role": role}
        try:
            with self.database() as database:
                database.execute("INSERT INTO users(id,username,password_hash,created,role) VALUES (?,?,?,?,?)",
                                 (user["id"], username, password_hash(password), time.time(), role))
        except sqlite3.IntegrityError:
            raise ValueError("用户名已被使用。") from None
        return user

    def login(self, username: str, password: str, client: str) -> dict:
        username = unicodedata.normalize("NFKC", username).casefold().strip()
        bucket = token_hash(client)  # 同一来源不能换账号绕过本地登录尝试上限。
        now = time.time()
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute("DELETE FROM login_attempts WHERE created < ?", (now - 600,))
            count = database.execute("SELECT COUNT(*) FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()[0]
            if count >= 12:
                raise LimitError("登录尝试过多，请稍后再试。")
            database.execute("INSERT INTO login_attempts VALUES (?,?)", (bucket, now))
            row = database.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row is None or not password_matches(password, row["password_hash"]):
            raise AccessError("用户名或密码不正确。")
        return {"id": row["id"], "username": row["username"], "role": row["role"]}

    def create_session(self, user_id: str) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.database() as database:
            database.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            database.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                             (token_hash(token), user_id, csrf, time.time() + 7 * 86400))
        return token, csrf

    def authenticate(self, token: str | None) -> dict:
        if not token or len(token) > 128:
            raise AccessError("请先登录。")
        with self.database() as database:
            row = database.execute("""SELECT u.id,u.username,u.role,s.csrf FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?""",
                (token_hash(token), time.time())).fetchone()
        if row is None:
            raise AccessError("登录已失效，请重新登录。")
        return dict(row)

    def logout(self, token: str):
        with self.database() as database:
            database.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))

    def admin_overview(self, user_id: str) -> dict:
        """最小只读管理入口：统计，不暴露密码、令牌或别人的问答。"""
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        with self.database() as database:
            role = database.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            if role is None or role[0] != "admin":
                raise AccessError("需要管理员权限。")
            return {"users": database.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                    "chats": database.execute("SELECT COUNT(*) FROM chats").fetchone()[0],
                    "exchanges": database.execute("SELECT COUNT(*) FROM exchanges").fetchone()[0],
                    "today_reserved": database.execute("SELECT COUNT(*) FROM jobs WHERE budget_day=?", (day,)).fetchone()[0],
                    "global_daily_limit": self.global_limit,
                    "active_generations": database.execute(
                        "SELECT COUNT(*) FROM jobs WHERE state='active' AND lease_until>?", (time.time(),)).fetchone()[0],
                    "max_concurrent": self.max_concurrent, "reset_timezone": "Asia/Shanghai"}

    def create_chat(self, user_id: str, title: str) -> dict:
        chat = {"id": uuid4().hex, "title": title.strip()[:80] or "新的学习讨论", "created": time.time()}
        with self.database() as database:
            database.execute("INSERT INTO chats VALUES (?,?,?,?)", (chat["id"], user_id, chat["title"], chat["created"]))
        return chat

    def list_chats(self, user_id: str) -> list[dict]:
        with self.database() as database:
            return [dict(row) for row in database.execute(
                "SELECT id,title,created FROM chats WHERE user_id=? ORDER BY created DESC LIMIT 50", (user_id,))]

    def require_chat(self, user_id: str, chat_id: str):
        with self.database() as database:
            if database.execute("SELECT 1 FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone() is None:
                raise AccessError("讨论不存在。")

    def history(self, user_id: str, chat_id: str) -> list[dict]:
        self.require_chat(user_id, chat_id)
        with self.database() as database:
            return [{"id": row["id"], "question": row["question"], "result": json.loads(row["result"]),
                     "created": row["created"]} for row in database.execute(
                "SELECT * FROM exchanges WHERE chat_id=? AND user_id=? ORDER BY created,rowid", (chat_id, user_id))]

    def save_exchange(self, user_id: str, chat_id: str, request_key: str, question: str, result: dict):
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            if database.execute("SELECT 1 FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone() is None:
                raise AccessError("讨论不存在。")
            database.execute("INSERT INTO exchanges VALUES (?,?,?,?,?,?,?)",
                             (uuid4().hex, user_id, chat_id, request_key, question,
                              json.dumps(result, ensure_ascii=False), time.time()))

    def recent_exchanges(self, user_id: str, chat_id: str, limit: int = 12) -> list[dict]:
        """只读取本人当前讨论的有界尾部，避免整段历史进入生成请求。"""
        self.require_chat(user_id, chat_id)
        if not 1 <= limit <= 12:
            raise ValueError("上下文读取数量超出范围。")
        with self.database() as database:
            rows = database.execute(
                "SELECT question,result FROM exchanges WHERE chat_id=? AND user_id=? "
                "ORDER BY created DESC,rowid DESC LIMIT ?", (chat_id, user_id, limit)).fetchall()
        return [{"question": row["question"], "result": json.loads(row["result"])} for row in reversed(rows)]

    def previous_request(self, user_id: str, request_key: str) -> dict | None:
        with self.database() as database:
            row = database.execute("SELECT chat_id,question,result FROM exchanges WHERE user_id=? AND request_key=?",
                                   (user_id, request_key)).fetchone()
        return {"chat_id": row["chat_id"], "question": row["question"],
                "result": json.loads(row["result"])} if row else None

    def delete_chat(self, user_id: str, chat_id: str):
        with self.database() as database:
            count = database.execute("DELETE FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).rowcount
            if count != 1:
                raise AccessError("讨论不存在。")

    def reserve(self, user_id: str, request_key: str) -> str:
        now = time.time()
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        job_id = uuid4().hex
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            if database.execute("SELECT 1 FROM jobs WHERE user_id=? AND request_key=?", (user_id, request_key)).fetchone():
                raise LimitError("该生成请求已处理或正在处理，请查看讨论记录。")
            user_calls = database.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND budget_day=?", (user_id, day)).fetchone()[0]
            total_calls = database.execute("SELECT COUNT(*) FROM jobs WHERE budget_day=?", (day,)).fetchone()[0]
            if user_calls >= self.user_limit or total_calls >= self.global_limit:
                raise LimitError("今日讲解额度已用完，仍可使用原文检索。")
            active = database.execute("SELECT user_id FROM jobs WHERE state='active' AND lease_until>?", (now,)).fetchall()
            if len(active) >= self.max_concurrent or any(row[0] == user_id for row in active):
                raise LimitError("已有讲解正在生成，请稍后再试。")
            database.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,NULL)",
                             (job_id, user_id, request_key, day, "active", now + MODEL_JOB_LEASE_SECONDS))
        return job_id

    def finish(self, job_id: str, result: dict):
        with self.database() as database:
            database.execute("UPDATE jobs SET state='finished',usage=? WHERE id=?",
                             (json.dumps({"status": result.get("status"), "model_calls": result.get("model_calls", 0),
                                          "usage": result.get("usage")}, ensure_ascii=False), job_id))

    def quota(self, user_id: str) -> dict:
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        with self.database() as database:
            used = database.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND budget_day=?", (user_id, day)).fetchone()[0]
        return {"used": used, "limit": self.user_limit, "reset_timezone": "Asia/Shanghai"}
