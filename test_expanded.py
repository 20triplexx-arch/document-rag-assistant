"""扩库契约、语言选择、MDX 原文位置和动态教材范围；只用离线模型替身。"""
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from expanded_import import NEW_BOOKS, select_lessons
from fulltext_import import git_blob
from starter import main
from study_rag.core import (CorpusError, Source, build_index, json_text,
                            prepare_corpus, read_source_manifest, search, split_document, verified_chunks)
from study_rag.mdx import mdx_mask
from study_rag.rag import prose_mask, retrieve, validate_draft, visible_prose
from study_rag.store import Store
from study_rag.web import create_app
from test_multiuser import FakeModel, PASSWORD, TEXT

PROJECT = Path(__file__).resolve().parent


class ExpandedSelectionTests(TestCase):
    def setUp(self):
        self.sources, self.catalog = read_source_manifest(PROJECT / "sources-expanded.json")

    def test_manifest_counts_commits_licenses_and_original_ids(self):
        self.assertEqual(Counter(s.book for s in self.sources), {
            "awesome-agentic-ai-zh": 71, "Hello-Agents": 54, "microsoft-ai-agents": 19, "huggingface-agents": 60})
        old, _ = read_source_manifest(PROJECT / "sources-full.json")
        self.assertEqual(self.sources[:125], old)
        self.assertEqual([b["license"] for b in self.catalog["books"]], ["MIT", "CC BY-NC-SA 4.0", "MIT", "Apache-2.0"])
        for book, _, _, commit, _, count in NEW_BOOKS:
            selected = [s for s in self.sources if s.book == book]
            self.assertEqual(len(selected), count)
            self.assertEqual({s.commit for s in selected}, {commit})
            self.assertEqual({self.catalog["chapters"][s.source_id]["language"] for s in selected}, {"zh-CN"})

    def selection_fixture(self, book):
        selected = [s for s in self.sources if s.book == book]
        chapters = [self.catalog["chapters"][s.source_id] for s in selected]
        paths = {s.path for s in selected} | {c["canonical_path"] for c in chapters}
        toc = "\n".join("  - local: " + c["canonical_path"].removeprefix("units/en/").removesuffix(".mdx") for c in chapters)
        return selected, paths, toc

    def test_microsoft_chinese_priority_and_one_english_fallback(self):
        selected, paths, _ = self.selection_fixture("microsoft-ai-agents")
        self.assertTrue(all(language == "zh-CN" for _, _, language in select_lessons("microsoft-ai-agents", paths)))
        paths.remove(selected[4].path)
        result = select_lessons("microsoft-ai-agents", paths)
        self.assertEqual(len(result), 19)
        self.assertEqual(result[4][0], result[4][1])
        self.assertEqual(result[4][2], "en")

    def test_hf_bonus_mapping_exclusions_and_language_dedup(self):
        selected, paths, toc = self.selection_fixture("huggingface-agents")
        paths.update({"units/en/unit1/quiz1.mdx", "units/en/unit0/discord101.mdx",
                      "units/en/unit4/get-your-certificate.mdx", "units/en/unit1/additional-readings.mdx",
                      "units/en/unit1/README.md"})
        result = select_lessons("huggingface-agents", paths, toc)
        self.assertEqual(len(result), 60)
        self.assertEqual(len({canonical for canonical, _, _ in result}), 60)
        bonuses = [(c, p, lang) for c, p, lang in result if "/bonus-unit2/" in c]
        self.assertEqual(len(bonuses), 3)
        self.assertTrue(all("/bonus_unit2/" in p and lang == "zh-CN" for _, p, lang in bonuses))
        paths.remove(selected[4].path)
        result = select_lessons("huggingface-agents", paths, toc)
        self.assertEqual(sum(lang == "en" for _, _, lang in result), 1)

    def test_incomplete_toc_is_rejected(self):
        _, paths, toc = self.selection_fixture("huggingface-agents")
        with self.assertRaises(CorpusError):
            select_lessons("huggingface-agents", paths, toc.split("\n", 1)[1])


class MdxTests(TestCase):
    def setUp(self):
        self.source = Source("mdx-test", "hf", "测试", "example/hf", "a" * 40, "units/en/test.mdx")
        self.text = ("import {\n  Banner\n} from './banner';\nexport const config = {\n  title: 'hidden'\n};\n"
                     "<CourseFloatingBanner\n chapter={2}\n callback={() => '>'}\n description={`\n## 组件伪标题\n`}\n/>\n"
                     "# 教学正文\n\n工具调用保留原文，引用必须定位原文件。\n"
                     "<details>\n<summary>教学说明</summary>\n保留组件内教学正文。\n</details>\n"
                     "| 工具 | 用途 |\n| --- | --- |\n| search | 检索 |\n"
                     "```python\n# 代码伪标题\nimport tools\nprint('<Banner />')\n```\n"
                     "<iframe\n src='video'>隐藏媒体内容</iframe>\n![图片](media.png)\n## 记忆\n记忆保存状态。\n")

    def test_position_preserving_multiline_mask_and_teaching_retention(self):
        masked = mdx_mask(self.text)
        self.assertEqual(len(masked), len(self.text))
        self.assertEqual([i for i, c in enumerate(masked) if c == "\n"], [i for i, c in enumerate(self.text) if c == "\n"])
        for hidden in ("CourseFloatingBanner", "组件伪标题", "hidden", "隐藏媒体内容", "media.png"):
            self.assertNotIn(hidden, masked)
        for body in ("教学正文", "组件内教学正文", "| search | 检索 |", "# 代码伪标题", "import tools", "print('<Banner />')"):
            self.assertIn(body, masked)
        prose = visible_prose(self.text, prose_mask(masked))
        self.assertIn("工具调用保留原文", prose)
        self.assertNotIn("代码伪标题", prose)

    def test_headings_raw_fragments_and_original_lines(self):
        chunks = split_document(self.source, self.text.encode(), max_chars=200, overlap=20)
        self.assertFalse(any("伪标题" in c.section for c in chunks))
        self.assertTrue(any(c.section == "教学正文 / 记忆" for c in chunks))
        lines = self.text.splitlines(keepends=True)
        for chunk in chunks:
            self.assertEqual(chunk.text, self.text[chunk.start_char:chunk.end_char])
            self.assertIn(chunk.text, "".join(lines[chunk.start_line - 1:chunk.end_line]))
        self.assertTrue(any("| search |" in c.text for c in chunks))

    def test_resource_list_is_available_raw_but_excluded_from_concept_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            raw = "# 教学正文\n工具执行动作并返回结果。\n\n## 额外资源\n[RAG memory guide](https://example.test)\n".encode()
            prepare_corpus([self.source], data, lambda _: raw)
            build_index(data, data / "index.sqlite3")
            self.assertTrue(search(data, data / "index.sqlite3", "RAG memory")["candidates"])
            self.assertFalse(retrieve(data, data / "index.sqlite3", "RAG memory")["evidence"])


class ExpandedIntegrationTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "corpus"
        actual, catalog = read_source_manifest(PROJECT / "sources-expanded.json")
        self.catalog = deepcopy(catalog)
        self.sources, self.content, chapters = [], {}, {}
        for book in catalog["books"]:
            prototype = next(s for s in actual if s.book == book["book"])
            for n in range(2):
                source = replace(prototype, source_id=f"fixture-{book['order']}-{n}",
                                 path=f"lesson{n}.mdx" if book["order"] == 3 else f"lesson{n}.md", chapter=f"章节 {n}")
                language = "en" if book["order"] == 3 else "zh-CN"
                raw = ("# Tools and memory\n\nTools perform actions. Memory stores context across steps. Planning chooses actions.\n"
                       if language == "en" else TEXT).encode()
                self.sources.append(source)
                self.content[source.source_id] = raw
                chapters[source.source_id] = {"language": language, "canonical_path": f"lesson{n}.md", "order": n,
                                              "git_blob": git_blob(raw), "bytes": len(raw)}
        self.catalog["chapters"] = chapters
        prepare_corpus(self.sources, self.data, lambda s: self.content[s.source_id], catalog=self.catalog)
        build_index(self.data, self.data / "index.sqlite3")
        self.store = Store(self.root / "users.sqlite3")
        self.model = FakeModel()
        self.client = TestClient(create_app(data_dir=self.data, store=self.store, model=self.model))
        self.addCleanup(self.client.close)
        registered = self.client.post("/api/register", json={"username": "fixture-user", "password": PASSWORD})
        self.client.headers["X-CSRF-Token"] = registered.json()["csrf"]
        self.chat = self.client.post("/api/chats", json={"title": "离线扩库测试"}).json()["id"]

    def ask(self, book=None, explain=False):
        return self.client.post("/api/ask", json={"chat_id": self.chat, "request_key": uuid4().hex,
                                                 "question": "RAG memory tools", "book": book, "explain": explain})

    def test_library_order_language_and_license(self):
        payload = self.client.get("/api/library").json()
        self.assertEqual([b["book"] for b in payload["books"]], [b["book"] for b in self.catalog["books"]])
        self.assertEqual(payload["books"][-1]["license"], "Apache-2.0")
        self.assertEqual(payload["books"][-1]["chapters"][0]["language"], "en")
        self.assertEqual([c["title"] for c in payload["books"][-1]["chapters"]], ["章节 0", "章节 1"])
        self.assertEqual(payload["books"][0]["display_name"], "Agentic AI 学习路线")
        self.assertIn("/3c469e773ec04e5f338b727ff20e3a6ea823ff81/LICENSE", payload["books"][-1]["license_url"])

    def test_all_four_filters_and_unknown_book_422_before_model_or_save(self):
        for book in self.catalog["books"]:
            response = self.ask(book["book"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual({e["book"] for e in response.json()["evidence"]}, {book["book"]})
        before = self.client.get(f"/api/chats/{self.chat}").json()
        for unknown in ("missing", "", "Hello-agents"):
            self.assertEqual(self.ask(unknown, explain=True).status_code, 422)
        self.assertEqual(before, self.client.get(f"/api/chats/{self.chat}").json())
        self.assertEqual(self.model.calls, 0)

    def test_cross_four_eight_evidence_and_one_mock_model_call(self):
        result = self.ask(explain=True).json()
        self.assertEqual(len(result["evidence"]), 8)
        self.assertEqual(Counter(e["book"] for e in result["evidence"]), {b["book"]: 2 for b in self.catalog["books"]})
        self.assertEqual(result["evidence"][-1]["evidence_id"], "E8")
        self.assertEqual(self.model.calls, 1)
        self.assertFalse(result["support_verified"])
        draft = json.dumps({"status": "answered", "claims": [{"text": "离线替身声明", "evidence_id": "E8",
                           "quote": "Tools perform actions."}], "missing_information": ""})
        validate_draft(draft, result["evidence"])

    def test_chinese_aliases_retrieve_english_gap(self):
        for query in ("工具", "记忆", "上下文", "规划"):
            pack = retrieve(self.data, self.data / "index.sqlite3", query, "huggingface-agents")
            self.assertTrue(pack["evidence"])
            self.assertTrue(all(e["language"] == "en" for e in pack["evidence"]))
            raw = search(self.data, self.data / "index.sqlite3", query, book="huggingface-agents")
            self.assertTrue(raw["candidates"])

    def test_cli_same_dynamic_scope_and_unknown_rejected(self):
        with redirect_stdout(io.StringIO()):
            result = main(["--data-dir", str(self.data), "--output-dir", str(self.root / "reports"),
                           "search", "记忆", "--book", "huggingface-agents"])
            self.assertEqual(result, 0)
            for operation in ("search", "ask"):
                with patch("starter.DeepSeekModel", return_value=self.model):
                    self.assertEqual(main(["--data-dir", str(self.data), "--output-dir", str(self.root / "reports"),
                                           operation, "memory", "--book", "unknown"]), 1)
        self.assertEqual(self.model.calls, 0)

    def test_offline_reimport_reuses_no_fetch(self):
        with patch("study_rag.core.fetch_source", side_effect=AssertionError("不应联网")):
            result = prepare_corpus(self.sources, self.data, lambda _: self.fail("不应读取网络"), catalog=self.catalog)
            self.assertEqual(result["network_requests"], 0)
            self.assertEqual(build_index(self.data, self.data / "index.sqlite3")["status"], "INDEX_REUSED")

    def test_catalog_tampering_rejected_and_new_order_changes_snapshot(self):
        path = self.data / "corpus.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["catalog"]["books"][3]["license"] = "MIT"
        path.write_text(json_text(manifest), encoding="utf-8")
        with self.assertRaises(CorpusError):
            verified_chunks(self.data, self.data / "index.sqlite3")
        updated = deepcopy(self.catalog)
        updated["books"][0]["order"], updated["books"][1]["order"] = 1, 0
        other = self.root / "other"
        result = prepare_corpus(self.sources, other, lambda s: self.content[s.source_id], catalog=updated)
        self.assertNotEqual(result["corpus_version"], manifest["corpus_version"])

    def test_duplicate_language_variant_or_invalid_blob_rejected(self):
        duplicate = deepcopy(self.catalog)
        duplicate["chapters"][self.sources[1].source_id]["canonical_path"] = "lesson0.md"
        with self.assertRaises(CorpusError):
            prepare_corpus(self.sources, self.root / "duplicate", lambda s: self.content[s.source_id], catalog=duplicate)
        broken = deepcopy(self.catalog)
        broken["chapters"][self.sources[0].source_id]["git_blob"] = "0" * 40
        with self.assertRaises(CorpusError):
            prepare_corpus(self.sources, self.root / "broken", lambda s: self.content[s.source_id], catalog=broken)
