"""模型选择、请求隔离和调用预算；使用离线模型，不发生成请求。"""
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import test_multiuser as fixtures
from study_rag.rag import DeepSeekModel
from study_rag.web import create_app


class ModelSelectionTests(TestCase):
    register = fixtures.MultiuserTests.register
    chat = fixtures.MultiuserTests.chat

    def setUp(self):
        fixtures.MultiuserTests.setUp(self)
        self.a.close(); self.b.close()
        self.flash = self.model
        self.flash.model_name = "deepseek-flash"
        self.pro = fixtures.FakeModel()
        self.pro.model_name = "deepseek-v4-pro"
        self.app = create_app(data_dir=self.data, store=self.store, model=self.flash,
            model_options={self.flash.model_name:self.flash, self.pro.model_name:self.pro})
        self.a, self.b = TestClient(self.app), TestClient(self.app)
        self.addCleanup(self.a.close); self.addCleanup(self.b.close)

    def post(self, chat, **options):
        return self.a.post("/api/ask", json={"chat_id":chat, "request_key":uuid4().hex,
            "question":"RAG 与 Memory 的区别", **options})

    def test_catalog_preserves_old_model_field_and_exposes_choices_without_calls(self):
        catalog = self.a.get("/api/library").json()
        self.assertEqual(catalog["model"], "deepseek-flash")
        self.assertEqual(catalog["default_model"], "deepseek-flash")
        self.assertEqual([m["id"] for m in catalog["models"]], ["deepseek-flash", "deepseek-v4-pro"])
        self.assertTrue(catalog["models"][0]["is_default"])
        self.assertIn("高", catalog["models"][1]["description"])
        self.assertEqual(self.flash.calls + self.pro.calls, 0)

    def test_each_request_uses_selected_model_without_mutating_default(self):
        self.register(self.a, "model-choice-user")
        chat = self.chat(self.a)
        pro = self.post(chat, model="deepseek-v4-pro").json()
        flash = self.post(chat).json()
        self.assertEqual(pro["selected_model"], "deepseek-v4-pro")
        self.assertEqual(pro["usage"]["model"], "deepseek-v4-pro")
        self.assertEqual(flash["selected_model"], "deepseek-flash")
        self.assertEqual((self.pro.calls, self.flash.calls), (1,1))
        self.assertEqual(self.flash.model_name, "deepseek-flash")
        self.assertEqual(self.a.get(f"/api/chats/{chat}").json()[0]["result"]["selected_model"], "deepseek-v4-pro")
        self.assertEqual(self.post(chat, model="deepseek-v4-pro").status_code, 429)
        self.assertEqual((self.pro.calls, self.flash.calls), (1,1))

    def test_unknown_model_is_rejected_before_quota_or_provider_call(self):
        self.register(self.a, "model-validation-user")
        chat = self.chat(self.a)
        for name in ("other-provider", "https://example.test", "", "deepseek-v4-pro "):
            self.assertEqual(self.post(chat, model=name).status_code, 422)
        self.assertEqual(self.a.get("/api/me").json()["quota"]["used"], 0)
        self.assertEqual(self.flash.calls + self.pro.calls, 0)

    def test_idempotency_reuses_selected_model_and_rejects_changed_selection(self):
        self.register(self.a, "model-reuse-user")
        chat = self.chat(self.a)
        key = uuid4().hex
        first = self.post(chat, model="deepseek-v4-pro", request_key=key)
        reused = self.post(chat, model="deepseek-v4-pro", request_key=key)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(reused.json()["reused"])
        self.assertEqual(self.post(chat, model="deepseek-flash", request_key=key).status_code, 409)
        self.assertEqual(self.post(chat, request_key=key).status_code, 409)
        self.assertEqual(self.pro.calls, 1)
        self.assertEqual(self.a.get("/api/me").json()["quota"]["used"], 1)

    def test_old_record_without_model_metadata_still_reuses(self):
        self.register(self.a, "model-legacy-user")
        chat = self.chat(self.a)
        key = uuid4().hex
        self.post(chat, request_key=key)
        with self.store.database() as db:
            result=json.loads(db.execute("SELECT result FROM exchanges WHERE request_key=?", (key,)).fetchone()[0])
            result.pop("selected_model"); result.pop("requested_model")
            db.execute("UPDATE exchanges SET result=? WHERE request_key=?", (json.dumps(result),key))
        reused = self.post(chat, request_key=key)
        self.assertTrue(reused.json()["reused"])
        self.assertEqual(self.flash.calls, 1)

    def test_pro_failure_has_no_flash_fallback_or_retry(self):
        self.register(self.a, "model-failure-user")
        self.pro.unavailable=True
        result=self.post(self.chat(self.a), model="deepseek-v4-pro").json()
        self.assertEqual(result["status"], "MODEL_FAILED")
        self.assertEqual(result["selected_model"], "deepseek-v4-pro")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual((self.pro.calls,self.flash.calls), (1,0))

    def test_retrieval_and_missing_topic_do_not_call_selected_pro(self):
        self.register(self.a, "model-raw-user")
        chat=self.chat(self.a)
        raw=self.post(chat, model="deepseek-v4-pro", explain=False).json()
        missing=self.post(chat, model="deepseek-v4-pro", question="继续讲",use_history=False).json()
        self.assertEqual(raw["status"], "RETRIEVAL_ONLY")
        self.assertEqual(missing["status"], "CONTEXT_REQUIRED")
        self.assertEqual(self.flash.calls+self.pro.calls, 0)


class SelectedSdkTests(TestCase):
    def test_flash_name_reaches_sdk_with_same_single_call_limits(self):
        response=SimpleNamespace(model="deepseek-flash",usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason='stop')])
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY":"offline-placeholder"}), patch("study_rag.rag.OpenAI") as factory:
            client=factory.return_value
            client.chat.completions.create.return_value=response
            _,usage=DeepSeekModel("deepseek-flash").generate([{"role":"user","content":"json"}])
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "deepseek-flash")
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertEqual(factory.call_args.kwargs["base_url"], "https://api.deepseek.com")
        self.assertEqual(usage["model"], "deepseek-flash")
        client.chat.completions.create.assert_called_once()

    def test_empty_environment_uses_flash_and_explicit_choice_overrides_pro_default(self):
        with patch.dict("os.environ", {"DEEPSEEK_MODEL":" "}):
            self.assertEqual(DeepSeekModel().model_name, "deepseek-flash")
        with patch.dict("os.environ", {"DEEPSEEK_MODEL":"deepseek-v4-pro"}):
            self.assertEqual(DeepSeekModel().model_name, "deepseek-v4-pro")
            self.assertEqual(DeepSeekModel("deepseek-flash").model_name, "deepseek-flash")
