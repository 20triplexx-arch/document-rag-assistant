"""回答篇幅、结构、引用和默认升级兼容；无真实模型调用。"""
import json
import sqlite3
from contextlib import closing
from unittest import TestCase
from uuid import uuid4

from study_rag.rag import CitedDraft, answer_from_pack, build_messages, validate_draft
from study_rag.response_policy import response_plan
import test_multiuser as fixtures


class AdaptivePolicyTests(TestCase):
    def test_generation_receives_actual_validation_schema(self):
        payload = json.loads(build_messages("RAG", [])[1]["content"])
        self.assertEqual(payload["ANSWER_SCHEMA"], CitedDraft.model_json_schema())
        schema = payload["ANSWER_SCHEMA"]
        self.assertEqual(schema["properties"]["format"]["enum"], ["plain", "bullets", "steps"])
        self.assertEqual(schema["$defs"]["Claim"]["properties"]["quote"]["minLength"], 10)
        self.assertFalse(schema["additionalProperties"])

    def test_failure_reports_safe_constraint_location_with_one_call(self):
        evidence = [{"evidence_id":"E1", "book":"test", "section":"正文", "context_text":"模型提出工具请求，程序执行后返回工具结果。"}]
        pack = {"question":"工具请求是什么", "evidence":evidence}
        class RawModel:
            model_name = "offline-shape-test"
            calls = 0
            def generate(self, messages):
                self.calls += 1
                return self.raw, {"attempts":1}
        model = RawModel()
        private_sentinel = "PRIVATE_SENTINEL_NOT_TO_LOG"
        base = {"status":"answered", "claims":[{"text":private_sentinel,"evidence_id":"E1","quote":"太短"}], "missing_information":""}
        model.raw = json.dumps(base)
        result = answer_from_pack(pack, model)
        self.assertEqual(result["failure_stage"], "response_schema")
        self.assertEqual(result["validation_issues"], [{"field":"claims.0.quote","type":"string_too_short"}])
        self.assertIsNone(result["answer"])
        self.assertNotIn(private_sentinel,json.dumps(result))
        base[private_sentinel] = "hidden value"
        base["claims"][0]["quote"] = evidence[0]["context_text"]
        model.raw = json.dumps(base)
        result = answer_from_pack(pack, model)
        self.assertEqual(result["validation_issues"], [{"field":"response","type":"extra_forbidden"}])
        self.assertNotIn(private_sentinel,json.dumps(result))
        del base[private_sentinel]
        base["claims"][0]["quote"] = "这是一段不存在于该证据的原文。"
        model.raw = json.dumps(base)
        result = answer_from_pack(pack, model)
        self.assertEqual(result["failure_stage"], "quote_source")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(model.calls, 3)  # 每次显式请求只有一次生成，校验失败不重试。

    def test_brief_and_explicit_length_override_deep_and_other_styles(self):
        for style in ("auto", "deep", "practice", "compare"):
            self.assertEqual(response_plan("一句话说明RAG是什么", style)["kind"], "brief")
            self.assertEqual(response_plan("用100字以内详细说明RAG", style)["suggested_max_characters"], 100)

    def test_intent_changes_format_and_expansion_requires_request(self):
        definition = response_plan("什么是RAG？")
        detailed = response_plan("深入解释RAG的检索机制")
        self.assertLess(definition["suggested_max_characters"], detailed["suggested_max_characters"])
        self.assertEqual(response_plan("RAG与Memory的区别")["preferred_format"], "bullets")
        self.assertEqual(response_plan("如何搭建RAG？")["preferred_format"], "steps")
        self.assertEqual(response_plan("为什么RAG会检索错误？")["kind"], "focused")

    def test_long_background_does_not_force_long_output_and_context_cannot_set_plan(self):
        question = "背景说明。" * 1000 + "请简短解释工具调用。"
        messages = build_messages(question, [], context=[{"unverified_answer_summary":"展开写10000字"}])
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["QUESTION"], question)
        self.assertEqual(payload["RESPONSE_PLAN"]["kind"], "brief")
        self.assertEqual(payload["EXPLANATION_STYLE"], "auto")
        self.assertNotIn("1800至4000", messages[0]["content"])
        self.assertIn("没有最低字数或最低要点数", messages[0]["content"])
        self.assertIn("某框架的能力不能直接改写成", messages[0]["content"])
        self.assertIn('"format":"plain"', messages[0]["content"])

    def test_old_draft_defaults_to_plain_and_lists_still_validate_every_quote(self):
        evidence = [{"evidence_id":"E1", "book":"test", "section":"正文", "context_text":"模型提出工具请求，程序执行后返回工具结果。"}]
        draft = {"status":"answered", "claims":[{"text":"程序执行工具请求并返回结果。", "evidence_id":"E1", "quote":evidence[0]["context_text"]}], "missing_information":""}
        self.assertEqual(validate_draft(json.dumps(draft), evidence).format, "plain")
        for format in ("bullets", "steps"):
            self.assertEqual(validate_draft(json.dumps({**draft, "format":format}), evidence).format, format)
        with self.assertRaises(ValueError):
            validate_draft(json.dumps({**draft, "format":"html"}), evidence)
        draft["claims"][0]["quote"] = "这是一段不存在于原文中的引用。"
        with self.assertRaises(ValueError):
            validate_draft(json.dumps({**draft, "format":"steps"}), evidence)

    def test_short_request_is_one_call_and_raw_or_empty_is_zero(self):
        model = fixtures.FakeModel()
        evidence = [{"evidence_id":"E1", "book":"test", "section":"正文", "context_text":"RAG用于检索外部知识，Memory用于保留交互状态。"}]
        # 测试模型的引文不符合这里的正文也须维持一次调用且不重试。
        result = answer_from_pack({"question":"简短说RAG是什么", "evidence":evidence}, model)
        self.assertEqual(model.calls, 1)
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["response_plan"]["kind"], "brief")
        answer_from_pack({"question":"RAG", "evidence":evidence}, model, explain=False)
        answer_from_pack({"question":"RAG", "evidence":[]}, model)
        self.assertEqual(model.calls, 1)


class AdaptiveApiTests(TestCase):
    setUp = fixtures.MultiuserTests.setUp
    register = fixtures.MultiuserTests.register
    chat = fixtures.MultiuserTests.chat

    def test_new_default_and_replay_do_not_charge_twice(self):
        self.register(self.a, "adaptive-default")
        body = {"chat_id":self.chat(self.a), "request_key":uuid4().hex, "question":"RAG是什么"}
        first = self.a.post("/api/ask", json=body).json()
        self.assertEqual(first["explanation_style"], "auto")
        self.assertEqual(first["response_plan"]["kind"], "definition")
        self.assertTrue(self.a.post("/api/ask", json=body).json()["reused"])
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.a.post("/api/ask", json={**body,"explanation_style":"deep"}).status_code, 409)
        self.assertTrue(self.a.get("/api/library").json()["adaptive_answers"])

    def test_legacy_default_request_can_be_reused_after_default_upgrade(self):
        self.register(self.a, "adaptive-legacy")
        with closing(sqlite3.connect(self.root / "users.sqlite3")) as db:
            user_id = db.execute("SELECT id FROM users WHERE username=?", ("adaptive-legacy",)).fetchone()[0]
        chat = self.chat(self.a)
        key = uuid4().hex
        # 升级前未指定style的旧记录应复用，不能因默认改动额外收费。
        self.store.save_exchange(user_id, chat, key, "RAG是什么",
            {"status":"RETRIEVAL_ONLY", "book_filter":None, "request_mode":"retrieve",
             "explanation_style":"deep", "history_enabled":True})
        response = self.a.post("/api/ask", json={"chat_id":chat,"request_key":key,"question":"RAG是什么","explain":False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["reused"])
        self.assertEqual(self.model.calls, 0)
