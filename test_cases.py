"""案例来源与检索测试；临时语料和离线模型替身，不执行案例代码。"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from case_import import BOOK, COMMIT, select_language
from fulltext_import import git_blob
from study_rag.core import (CorpusError, build_index, load_corpus, prepare_corpus,
                            read_evidence, read_source_manifest, search, verified_chunks)
from study_rag.rag import retrieve
from study_rag.store import Store
from study_rag.web import create_app
from test_multiuser import FakeModel, PASSWORD, TEXT

PROJECT = Path(__file__).resolve().parent


class CaseManifestTests(TestCase):
    def test_selected_case_manifest_preserves_204_and_has_12_english_cases(self):
        sources, catalog = read_source_manifest(PROJECT / "sources-cases.json")
        old_sources, old_catalog = read_source_manifest(PROJECT / "sources-expanded.json")
        self.assertEqual(sources[:204], old_sources)
        self.assertEqual(catalog["books"][:4], old_catalog["books"])
        for source in old_sources:
            self.assertEqual(catalog["chapters"][source.source_id], old_catalog["chapters"][source.source_id])
        selected = sources[204:]
        self.assertEqual(len(selected), 12)
        self.assertEqual({s.book for s in selected}, {BOOK})
        self.assertEqual({s.commit for s in selected}, {COMMIT})
        self.assertEqual({catalog["chapters"][s.source_id]["language"] for s in selected}, {"en"})
        self.assertEqual(catalog["books"][-1]["license"], "Apache-2.0")
        self.assertEqual(catalog["books"][-1]["kind"], "case_collection")
        self.assertTrue(all(catalog["chapters"][s.source_id]["implementation_files"] for s in selected))
        self.assertEqual(len({s.path for s in selected}), 12)

    def test_language_priority_is_one_file_and_requires_canonical(self):
        path = "examples/README.md"
        self.assertEqual(select_language(path, {path}), (path, "en"))
        self.assertEqual(select_language(path, {path, "examples/README.zh-CN.md", "examples/README.zh.md"}),
                         ("examples/README.zh-CN.md", "zh-CN"))
        with self.assertRaises(CorpusError):
            select_language(path, {"README.md"})


class CaseIntegrationTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        sources, catalog = read_source_manifest(PROJECT / "sources-cases.json")
        self.sources = [next(s for s in sources if s.book == b["book"]) for b in catalog["books"][:4]]
        self.sources += [sources[204], sources[207]]
        self.catalog = deepcopy(catalog)
        self.catalog["chapters"] = {s.source_id: deepcopy(catalog["chapters"][s.source_id]) for s in self.sources}
        self.contents = {}
        for source in self.sources:
            if source.book == BOOK:
                raw = ("# Hybrid Search and Tools\n\nHybrid search combines semantic and keyword matching. "
                       "Reranking selects context. Tools perform actions. Memory persists state.\n\n"
                       "```python\nraise AssertionError('case code must never execute')\n```\n").encode()
            else:
                raw = (TEXT + "\n## 第二节 RAG Memory\n\nRAG 先检索外部资料，再根据证据生成回答。Memory 保存状态。\n").encode()
            self.contents[source.source_id] = raw
            self.catalog["chapters"][source.source_id].update(git_blob=git_blob(raw), bytes=len(raw))
        prepare_corpus(self.sources, self.data, lambda s: self.contents[s.source_id], catalog=self.catalog)
        self.index = self.data / "index.sqlite3"
        build_index(self.data, self.index)
        self.store = Store(self.root / "users.sqlite3")
        self.model = FakeModel()
        self.client = TestClient(create_app(data_dir=self.data, store=self.store, model=self.model))
        self.addCleanup(self.client.close)
        result = self.client.post("/api/register", json={"username": "case-reader", "password": PASSWORD})
        self.client.headers["X-CSRF-Token"] = result.json()["csrf"]
        self.chat = self.client.post("/api/chats", json={"title": "离线案例"}).json()["id"]

    def ask(self, book=None, explain=False):
        return self.client.post("/api/ask", json={"chat_id": self.chat, "request_key": uuid4().hex,
            "question": "RAG memory tools hybrid", "book": book, "explain": explain})

    def test_library_has_fifth_case_collection_topics_and_pinned_code_links(self):
        library = self.client.get("/api/library").json()
        self.assertEqual(len(library["books"]), 5)
        book = library["books"][-1]
        self.assertEqual(book["book"], BOOK)
        self.assertEqual(book["kind"], "case_collection")
        self.assertEqual(book["chapters"][0]["language"], "en")
        self.assertEqual(book["chapters"][0]["kind"], "case")
        self.assertIn("工具调用", book["chapters"][0]["topics"])
        for chapter in book["chapters"]:
            for code in chapter["implementation_links"]:
                self.assertIn("/blob/" + COMMIT + "/", code["url"])
                self.assertTrue(code["url"].endswith(".py"))
        self.assertEqual(self.model.calls, 0)

    def test_case_filter_and_unknown_collection_rejected(self):
        response = self.ask(BOOK)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({e["book"] for e in response.json()["evidence"]}, {BOOK})
        self.assertEqual(self.ask("unknown-cases", True).status_code, 422)
        self.assertEqual(self.model.calls, 0)

    def test_five_collections_total_eight_and_one_offline_model_call(self):
        result = self.ask(explain=True).json()
        self.assertEqual(len(result["evidence"]), 8)
        counts = Counter(e["book"] for e in result["evidence"])
        self.assertEqual(set(counts), {s.book for s in self.sources})
        self.assertLessEqual(max(counts.values()), 2)
        self.assertEqual(self.model.calls, 1)
        self.assertFalse(result["support_verified"])

    def test_chinese_case_query_matches_english_body_and_original_lines(self):
        for question in ("混合检索案例", "工具调用案例", "重排"):
            pack = retrieve(self.data, self.index, question, BOOK)
            self.assertTrue(pack["evidence"])
            for evidence in pack["evidence"]:
                self.assertEqual(evidence["language"], "en")
                original = read_evidence(self.data, self.index, evidence["chunk_id"])
                self.assertEqual(evidence["text"], original["text"])
                self.assertEqual(evidence["line_url"], original["line_url"])
            self.assertTrue(search(self.data, self.index, question, book=BOOK)["candidates"])

    def test_readme_code_is_preserved_without_execution_and_hidden_in_concepts(self):
        _, chunks, mapping = verified_chunks(self.data, self.index)
        code = [c for c in chunks if mapping[c.source_id].book == BOOK]
        self.assertTrue(any("raise AssertionError" in c.text for c in code))
        pack = retrieve(self.data, self.index, "hybrid", BOOK)
        self.assertTrue(all("raise AssertionError" not in e["context_text"] for e in pack["evidence"]))

    def test_case_metadata_tampering_fails_snapshot_integrity(self):
        path = self.data / "corpus.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["catalog"]["chapters"][self.sources[-1].source_id]["topics"].append("虚构主题")
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(CorpusError):
            load_corpus(self.data)

    def test_implementation_outside_case_or_moving_reference_is_rejected(self):
        for path in ("../secret.py", "other-case/agent.py", "https://example.test/agent.py"):
            catalog = deepcopy(self.catalog)
            catalog["chapters"][self.sources[-1].source_id]["implementation_files"][0]["path"] = path
            with self.assertRaises(CorpusError):
                prepare_corpus(self.sources, self.root / "invalid", lambda s: self.contents[s.source_id], catalog=catalog)

    def test_reimport_does_not_fetch_and_reuses_index(self):
        result = prepare_corpus(self.sources, self.data, lambda _: self.fail("不能重新下载"), catalog=self.catalog)
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(build_index(self.data, self.index)["status"], "INDEX_REUSED")

    def test_heading_only_and_masked_code_are_not_concept_evidence(self):
        data = self.root / "only-headings"
        raw = "# Tool\n\n## Memory\n\n```python\nMemory=True\n```\n\n## Definition\nTools perform actions.\n".encode()
        prepare_corpus([self.sources[0]], data, lambda _: raw)
        build_index(data, data / "index.sqlite3")
        self.assertFalse(retrieve(data, data / "index.sqlite3", "memory")["evidence"])
        pack = retrieve(data, data / "index.sqlite3", "tool")
        self.assertTrue(pack["evidence"])
        self.assertTrue(all("Tools perform actions." in e["context_text"] for e in pack["evidence"]))
