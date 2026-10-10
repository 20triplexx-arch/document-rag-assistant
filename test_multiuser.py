"""多人隔离、预算、引用验证和网页接口测试；不调用 DeepSeek。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from study_rag.core import Source, build_index, prepare_corpus
from study_rag.rag import (
    ProviderError, answer_from_pack, build_messages, prose_mask, retrieve, validate_draft, visible_prose,
)
from study_rag.store import AccessError, LimitError, Store, password_matches
from study_rag.web import create_app

PROJECT = Path(__file__).resolve().parent
PASSWORD = "test-password-only-123"
SOURCES = [Source("book-a", "awesome-agentic-ai-zh", "测试", "example/a", "a" * 40, "a.md"),
           Source("book-b", "Hello-Agents", "测试", "example/b", "b" * 40, "b.md")]
TEXT = ("# 教材\n\n## RAG 与 Memory\n\nRAG 先检索外部资料，再根据证据生成回答。"
        "Memory 保存下次仍需使用的状态。\n\n```python\n# RAG Memory 日志\nprint('RAG Memory')\n```\n"
        "\n## 习题\n\n请分析 RAG 与 Memory 的关系。\n")


class FakeModel:
    model_name = "fake-offline-only"
    def __init__(self, *, invalid_quote=False, unavailable=False):
        self.calls = 0
        self.messages = []
        self.invalid_quote = invalid_quote
        self.unavailable = unavailable

    def generate(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.unavailable:
            raise ProviderError("MOCK_TIMEOUT")
        pack = json.loads(messages[1]["content"])
        evidence = pack["EVIDENCE"][0]
        quote = "不在这份原文里的虚构引文片段" if self.invalid_quote else "RAG 先检索外部资料，再根据证据生成回答。"
        return json.dumps({"status": "answered", "claims": [
            {"text": "RAG 先找资料，再依证据回答。", "evidence_id": evidence["evidence_id"], "quote": quote}],
            "missing_information": ""}, ensure_ascii=False), {"model": self.model_name, "attempts": 1,
                                                                 "prompt_tokens": 10, "output_tokens": 20}


class MultiuserTests(unittest.TestCase):
    def setUp(self):
        root = PROJECT / "output" / "multiuser_test_tmp"
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-", dir=root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "corpus"
        prepare_corpus(SOURCES, self.data, lambda source: TEXT.encode())
        self.index = self.data / "index.sqlite3"
        build_index(self.data, self.index)
        self.store = Store(self.root / "users.sqlite3", user_daily_limit=2, global_daily_limit=3, max_concurrent=2)
        self.model = FakeModel()
        self.app = create_app(data_dir=self.data, store=self.store, model=self.model)
        self.a, self.b = TestClient(self.app), TestClient(self.app)
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def register(self, client, username):
        response = client.post("/api/register", json={"username": username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        return response.json()

    def chat(self, client, title="讨论"):
        response = client.post("/api/chats", json={"title": title})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def ask(self, client, chat_id, *, explain=True, request_key=None, question="RAG 与 Memory 的区别"):
        return client.post("/api/ask", json={"chat_id": chat_id, "request_key": request_key or uuid4().hex,
                                            "question": question, "book": None, "explain": explain})

    def test_public_library_private_actions_require_login(self):
        self.assertEqual(self.a.get("/api/library").status_code, 200)
        self.assertEqual(self.a.get("/api/chats").status_code, 401)
        self.assertEqual(self.a.post("/api/chats", json={"title": "a"}).status_code, 401)
        self.assertEqual(self.model.calls, 0)

    def test_password_and_session_are_not_stored_as_plaintext(self):
        response = self.a.post("/api/register", json={"username": "learner-a", "password": PASSWORD})
        token = self.a.cookies.get("rag_session")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        with self.store.database() as database:
            hashed = database.execute("SELECT password_hash FROM users").fetchone()[0]
            stored_token = database.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertNotEqual(hashed, PASSWORD)
        self.assertTrue(password_matches(PASSWORD, hashed))
        self.assertNotEqual(stored_token, token)
        self.assertNotIn("password", response.json())

    def test_case_normalization_prevents_duplicate_accounts(self):
        self.register(self.a, "Learner-A")
        duplicate = self.b.post("/api/register", json={"username": "learner-a", "password": PASSWORD})
        self.assertEqual(duplicate.status_code, 409)

    def test_wrong_password_and_logout_revoke_access(self):
        self.register(self.a, "learner-a")
        wrong = self.b.post("/api/login", json={"username": "learner-a", "password": "wrong-password-123"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.a.post("/api/logout", json={}).status_code, 200)
        self.assertEqual(self.a.get("/api/me").status_code, 401)

    def test_two_users_cannot_read_delete_or_write_each_others_chats(self):
        self.register(self.a, "learner-a"); self.register(self.b, "learner-b")
        own = self.chat(self.a)
        self.assertEqual(self.ask(self.a, own, explain=False).status_code, 200)
        self.assertEqual(self.b.get(f"/api/chats/{own}").status_code, 404)
        self.assertEqual(self.b.delete(f"/api/chats/{own}").status_code, 404)
        self.assertEqual(self.ask(self.b, own).status_code, 404)
        self.assertEqual(self.b.get("/api/chats").json(), [])
        self.assertEqual(len(self.a.get(f"/api/chats/{own}").json()), 1)
        self.assertEqual(self.model.calls, 0)

    def test_database_reopen_keeps_accounts_sessions_and_history(self):
        self.register(self.a, "learner-a")
        chat = self.chat(self.a)
        self.ask(self.a, chat, explain=False)
        reopened = Store(self.store.path)
        user = reopened.authenticate(self.a.cookies.get("rag_session"))
        self.assertEqual(len(reopened.history(user["id"], chat)), 1)

    def test_missing_csrf_and_cross_origin_requests_rejected(self):
        self.register(self.a, "learner-a")
        csrf = self.a.headers.pop("X-CSRF-Token")
        self.assertEqual(self.a.post("/api/chats", json={"title": "a"}).status_code, 403)
        self.a.headers["X-CSRF-Token"] = csrf
        result = self.a.post("/api/chats", json={"title": "a"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(result.status_code, 403)

    def test_cannot_inject_owner_or_exceed_question_length(self):
        self.register(self.a, "learner-a")
        chat = self.chat(self.a)
        result = self.a.post("/api/chats", json={"title": "a", "user_id": "someone-else"})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.ask(self.a, chat, question="字" * 501).status_code, 422)
        result = self.a.post("/api/login", json={"username": "ab", "password": "my-secret"})
        self.assertNotIn("my-secret", result.text)
        self.assertEqual(self.model.calls, 0)

    def test_duplicate_request_reuses_answer_without_second_call(self):
        self.register(self.a, "learner-a")
        chat, key = self.chat(self.a), uuid4().hex
        first, second = self.ask(self.a, chat, request_key=key), self.ask(self.a, chat, request_key=key)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(second.json()["reused"])
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(len(self.a.get(f"/api/chats/{chat}").json()), 1)
        changed = self.ask(self.a, chat, request_key=key, question="什么是 Chunk")
        self.assertEqual(changed.status_code, 409)

    def test_user_quota_blocks_paid_calls_but_allows_retrieval(self):
        self.register(self.a, "learner-a")
        chat = self.chat(self.a)
        self.assertEqual(self.ask(self.a, chat).status_code, 200)
        self.assertEqual(self.ask(self.a, chat).status_code, 200)
        self.assertEqual(self.ask(self.a, chat).status_code, 429)
        self.assertEqual(self.ask(self.a, chat, explain=False).status_code, 200)
        self.assertEqual(self.model.calls, 2)

    def test_global_budget_shared_by_users(self):
        self.register(self.a, "learner-a"); self.register(self.b, "learner-b")
        ca, cb = self.chat(self.a), self.chat(self.b)
        self.ask(self.a, ca); self.ask(self.a, ca); self.ask(self.b, cb)
        self.assertEqual(self.ask(self.b, cb).status_code, 429)
        self.assertEqual(self.model.calls, 3)

    def test_parallel_reservations_are_atomic(self):
        user = self.store.register("learner-a", PASSWORD)
        def attempt(_):
            try:
                return self.store.reserve(user["id"], uuid4().hex)
            except LimitError:
                return None
        with ThreadPoolExecutor(max_workers=5) as executor:
            jobs = list(executor.map(attempt, range(5)))
        self.assertEqual(sum(job is not None for job in jobs), 1)

    def test_budget_is_shared_across_store_instances(self):
        user = self.store.register("learner-a", PASSWORD)
        second = Store(self.store.path, user_daily_limit=2, global_daily_limit=3, max_concurrent=2)
        job = self.store.reserve(user["id"], uuid4().hex)
        with self.assertRaises(LimitError):
            second.reserve(user["id"], uuid4().hex)
        self.store.finish(job, {"status": "MOCK_FAILED", "model_calls": 1})
        second.reserve(user["id"], uuid4().hex)

    def test_model_failure_does_not_leave_active_slot(self):
        self.register(self.a, "learner-a")
        chat = self.chat(self.a)
        self.model.unavailable = True
        self.assertEqual(self.ask(self.a, chat).json()["status"], "MODEL_FAILED")
        self.model.unavailable = False
        self.assertEqual(self.ask(self.a, chat).json()["status"], "CITED_DRAFT")

    def test_no_other_users_history_enters_model_prompt(self):
        self.register(self.a, "learner-a"); self.register(self.b, "learner-b")
        self.ask(self.a, self.chat(self.a), question="RAG SECRET_FROM_A")
        self.ask(self.b, self.chat(self.b), question="什么是 RAG")
        self.assertNotIn("SECRET_FROM_A", json.dumps(self.model.messages[-1]))

    def test_code_mask_has_same_positions_and_balanced_book_evidence(self):
        masked = prose_mask(TEXT)
        self.assertEqual(len(masked), len(TEXT))
        self.assertNotIn("print(", masked)
        pack = retrieve(self.data, self.index, "RAG 与 Memory")
        self.assertEqual({e["book"] for e in pack["evidence"]}, {"Hello-Agents", "awesome-agentic-ai-zh"})
        self.assertTrue(all("习题" not in e["section"] for e in pack["evidence"]))
        self.assertTrue(all("print(" not in e["context_text"] for e in pack["evidence"]))

    def test_unknown_citation_and_fabricated_quote_rejected(self):
        pack = retrieve(self.data, self.index, "RAG")
        result = answer_from_pack(pack, FakeModel(invalid_quote=True))
        self.assertEqual(result["status"], "CITATION_VALIDATION_FAILED")
        self.assertIsNone(result["answer"])
        with self.assertRaises(ValueError):
            validate_draft(json.dumps({"status": "answered", "claims": [{"text": "a", "evidence_id": "E6",
                "quote": "RAG 先检索外部资料，再根据证据生成回答。"}], "missing_information": ""}), pack["evidence"])

    def test_real_quote_does_not_mark_semantic_support_verified(self):
        pack = retrieve(self.data, self.index, "RAG")
        result = answer_from_pack(pack, FakeModel())
        self.assertTrue(result["quote_verified"])
        self.assertFalse(result["support_verified"])

    def test_visible_quote_can_cross_html_emphasis_without_rewriting(self):
        text = "首先是<strong>工作记忆 (Working Memory)</strong>，存储当前对话的上下文。"
        visible = visible_prose(text, prose_mask(text))
        evidence = [{"evidence_id": "E1", "text": text, "context_text": visible}]
        raw = json.dumps({"status": "answered", "claims": [{"text": "工作记忆存储当前对话。",
             "evidence_id": "E1", "quote": "工作记忆 (Working Memory)，存储当前对话的上下文。"}],
             "missing_information": ""}, ensure_ascii=False)
        self.assertEqual(validate_draft(raw, evidence).claims[0].evidence_id, "E1")
        with self.assertRaises(ValueError):
            validate_draft(raw.replace("当前对话的上下文。", "所有历史对话的上下文。"), evidence)

    def test_whitespace_quote_cannot_bypass_quote_check(self):
        pack = retrieve(self.data, self.index, "RAG")
        raw = json.dumps({"status": "answered", "claims": [{"text": "a", "evidence_id": "E1",
                          "quote": " " * 20}], "missing_information": ""})
        with self.assertRaises(ValueError):
            validate_draft(raw, pack["evidence"])

    def test_insufficient_shape_cannot_include_factual_claims(self):
        pack = retrieve(self.data, self.index, "RAG")
        raw = json.dumps({"status": "insufficient", "claims": [], "missing_information": "当前证据没有费用依据。"})
        self.assertEqual(validate_draft(raw, pack["evidence"]).status, "insufficient")
        with self.assertRaises(ValueError):
            validate_draft(raw.replace('"claims": []', '"claims": [{"text":"a","evidence_id":"E1","quote":"RAG 先检索外部资料"}]'), pack["evidence"])

    def test_retrieval_only_and_no_match_never_call_model(self):
        pack = retrieve(self.data, self.index, "RAG")
        self.assertEqual(answer_from_pack(pack, self.model, explain=False)["model_calls"], 0)
        empty = retrieve(self.data, self.index, "unobtainiumzz")
        self.assertEqual(answer_from_pack(empty, self.model)["model_calls"], 0)
        self.assertEqual(self.model.calls, 0)

    def test_web_assets_and_headers(self):
        response = self.a.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("学有据", response.text)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.a.get("/static/app.js").status_code, 200)
        self.assertNotIn("innerHTML", self.a.get("/static/app.js").text)

    def test_admin_overview_requires_authenticated_admin(self):
        self.assertEqual(self.a.get("/api/admin/overview").status_code, 401)
        self.register(self.a, "learner-a")
        self.assertEqual(self.a.get("/api/admin/overview").status_code, 403)

    def test_registration_cannot_assign_admin_role_even_named_admin(self):
        rejected = self.a.post("/api/register", json={"username": "evil-admin", "password": PASSWORD, "role": "admin"})
        self.assertEqual(rejected.status_code, 422)
        user = self.register(self.a, "admin")
        self.assertEqual(user["role"], "learner")
        self.assertEqual(self.a.get("/api/me").json()["role"], "learner")
        self.assertEqual(self.a.get("/api/admin/overview").status_code, 403)

    def test_admin_bootstrap_never_overwrites_existing_account(self):
        original = self.store.register("admin", PASSWORD)
        with self.assertRaises(ValueError):
            self.store.create_admin("admin", "a-different-password-123")
        self.assertEqual(self.store.login("admin", PASSWORD, "test-client")["role"], "learner")
        with self.store.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
        self.assertEqual(self.store.list_chats(original["id"]), [])

    def test_real_admin_can_view_counts_but_not_other_users_private_chats(self):
        self.store.create_admin("owner-admin", PASSWORD)
        response = self.a.post("/api/login", json={"username": "owner-admin", "password": PASSWORD})
        self.assertEqual(response.json()["role"], "admin")
        self.a.headers["X-CSRF-Token"] = response.json()["csrf"]
        self.register(self.b, "learner-b")
        other_chat = self.chat(self.b, "PRIVATE_DISCUSSION_TITLE")
        self.ask(self.b, other_chat, explain=False, question="RAG PRIVATE_QUESTION")
        overview = self.a.get("/api/admin/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["users"], 2)
        self.assertEqual(overview.json()["chats"], 1)
        self.assertEqual(overview.json()["exchanges"], 1)
        for secret in (PASSWORD, "csrf", "password_hash", "PRIVATE_QUESTION", "PRIVATE_DISCUSSION_TITLE"):
            self.assertNotIn(secret, overview.text)
        self.assertEqual(self.a.get(f"/api/chats/{other_chat}").status_code, 404)
        self.assertEqual(self.a.delete(f"/api/chats/{other_chat}").status_code, 404)
        own = self.chat(self.a)
        self.assertEqual(self.ask(self.a, own).status_code, 200)
        self.assertEqual(self.ask(self.a, own).status_code, 200)
        self.assertEqual(self.ask(self.a, own).status_code, 429)

    def test_v1_migration_preserves_user_password_session_and_chat(self):
        legacy = self.root / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as database:
            database.executescript("""
                CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE chats(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL,created REAL NOT NULL);
                PRAGMA user_version=1;
            """)
            from study_rag.store import password_hash, token_hash
            database.execute("INSERT INTO users VALUES(?,?,?,?)", ("legacy-user", "legacy", password_hash(PASSWORD), 1))
            database.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash("legacy-token"), "legacy-user", "csrf-only", 9_999_999_999))
            database.execute("INSERT INTO chats VALUES(?,?,?,?)", ("legacy-chat", "legacy-user", "旧讨论", 1))
            database.commit()
        upgraded = Store(legacy)
        self.assertEqual(upgraded.login("legacy", PASSWORD, "test-client")["role"], "learner")
        self.assertEqual(upgraded.authenticate("legacy-token")["role"], "learner")
        self.assertEqual(upgraded.list_chats("legacy-user")[0]["title"], "旧讨论")
        with upgraded.database() as database:
            self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
