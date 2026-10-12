"""离线契约测试；使用合成资料，不下载教材、不请求模型。"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from study_rag.core import (
    CorpusError, Source, build_index, load_corpus, prepare_corpus,
    read_evidence, read_sources, search, split_document, validate_text, verified_chunks,
)

PROJECT = Path(__file__).resolve().parent
SOURCES = [
    Source("awesome-stage6", "awesome-agentic-ai-zh", "合成测试章节", "example/book-a", "a" * 40, "rag.md"),
    Source("hello-chapter8", "Hello-Agents", "合成测试章节", "example/book-b", "b" * 40, "memory.md"),
]
FIXTURES = {
    "awesome-stage6": "# 测试资料\n\n## RAG\n\nRAG 先检索相关片段，再根据原文生成回答。\n\n## 引用\n\n引用存在不等于结论被支持。\n".encode(),
    "hello-chapter8": "# 测试资料\n\n## 长期记忆\n\n长期记忆存储学习偏好，教材知识库保存教材原文。\n\n## RAG\n\nRAG 检索的候选需要检查相关性。\n".encode(),
}


class CorpusTests(unittest.TestCase):
    def setUp(self):
        test_root = PROJECT / "output" / "test_tmp"
        test_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="study-rag-test-", dir=test_root)
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "data"
        self.index = self.data / "index.sqlite3"

    def prepare(self):
        prepare_corpus(SOURCES, self.data, lambda source: FIXTURES[source.source_id])
        build_index(self.data, self.index)

    def test_manifest_pins_both_books(self):
        sources = read_sources(PROJECT / "sources.json")
        self.assertEqual({item.book for item in sources}, {"awesome-agentic-ai-zh", "Hello-Agents"})
        self.assertTrue(all(len(item.commit) == 40 for item in sources))

    def test_source_rejects_traversal_and_moving_branch(self):
        for field, value in [("path", "../secret.md"), ("path", "C:\\secret.md"),
                             ("commit", "main"), ("repository", "evil/a/../../b")]:
            with self.subTest(field=field, value=value), self.assertRaises(CorpusError):
                replace(SOURCES[0], **{field: value})

    def test_pinned_url_encodes_chinese_and_spaces(self):
        source = replace(SOURCES[0], path="docs/第八章 记忆.md")
        self.assertIn("/" + "a" * 40 + "/docs/", source.raw_url)
        self.assertNotIn(" ", source.raw_url)
        self.assertNotIn("第", source.raw_url)

    def test_empty_and_binary_text_are_rejected(self):
        for raw in [b"", b"\n \t", b"hello\x00world"]:
            with self.subTest(raw=raw), self.assertRaises(CorpusError):
                validate_text(raw)

    def test_heading_in_fenced_code_is_not_a_section(self):
        raw = b"# Real\n\n```python\n# fake heading\n```\n\n## Child\n\ncontent\n"
        chunks = split_document(SOURCES[0], raw)
        self.assertEqual([chunk.section for chunk in chunks], ["Real", "Real / Child"])
        self.assertIn("# fake heading", chunks[0].text)

    def test_character_spans_cover_long_lines_and_roundtrip(self):
        text = "# 文档\n\n" + "长行资料" * 120 + "\n\n## 第二节\n\n结束\n"
        chunks = split_document(SOURCES[0], text.encode(), max_chars=80, overlap=10)
        covered = set()
        for chunk in chunks:
            self.assertEqual(chunk.text, text[chunk.start_char:chunk.end_char])
            self.assertLessEqual(len(chunk.text), 80)
            self.assertEqual(chunk.start_line, text[:chunk.start_char].count("\n") + 1)
            self.assertEqual(chunk.end_line, text[:chunk.end_char - 1].count("\n") + 1)
            covered.update(range(chunk.start_char, chunk.end_char))
        self.assertTrue(all(i in covered for i, char in enumerate(text) if not char.isspace()))

    def test_chunk_ids_are_stable_and_version_sensitive(self):
        raw = FIXTURES[SOURCES[0].source_id]
        first = split_document(SOURCES[0], raw)
        self.assertEqual(first, split_document(SOURCES[0], raw))
        self.assertNotEqual(first[0].chunk_id, split_document(SOURCES[0], raw + b"\n")[0].chunk_id)

    def test_reimport_and_reindex_do_not_fetch_or_overwrite(self):
        self.prepare()
        before = self.index.read_bytes()
        def forbidden_fetch(source):
            self.fail("完整语料复用时不能访问网络。")
        report = prepare_corpus(SOURCES, self.data, forbidden_fetch)
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(build_index(self.data, self.index)["status"], "INDEX_REUSED")
        self.assertEqual(before, self.index.read_bytes())

    def test_failed_download_does_not_publish_partial_corpus(self):
        def failing_fetch(source):
            if source == SOURCES[1]:
                raise OSError("mock download failure")
            return FIXTURES[source.source_id]
        with self.assertRaises(OSError):
            prepare_corpus(SOURCES, self.data, failing_fetch)
        self.assertFalse(self.data.exists())

    def test_duplicate_source_is_rejected(self):
        with self.assertRaises(CorpusError):
            prepare_corpus([SOURCES[0], SOURCES[0]], self.data, lambda _: b"text")

    def test_changed_manifest_requires_new_directory(self):
        self.prepare()
        changed = [replace(SOURCES[0], commit="c" * 40), SOURCES[1]]
        with self.assertRaises(CorpusError):
            prepare_corpus(changed, self.data, lambda _: b"text")

    def test_changed_source_blocks_search(self):
        self.prepare()
        path = self.data / "awesome-stage6.md"
        with path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(CorpusError):
            search(self.data, self.index, "RAG")

    def test_changed_index_text_blocks_search(self):
        self.prepare()
        with closing(sqlite3.connect(self.index)) as database, database:
            row = database.execute("SELECT payload FROM chunks WHERE position=0").fetchone()
            payload = json.loads(row[0])
            payload["text"] = "forged evidence"
            database.execute("UPDATE chunks SET payload=? WHERE position=0", (json.dumps(payload),))
        with self.assertRaises(CorpusError):
            search(self.data, self.index, "RAG")

    def test_contract_mismatch_blocks_search(self):
        self.prepare()
        with closing(sqlite3.connect(self.index)) as database, database:
            database.execute("UPDATE metadata SET value='{}' WHERE key='contract'")
        with self.assertRaises(CorpusError):
            search(self.data, self.index, "RAG")

    def test_search_can_filter_each_book_and_read_original(self):
        self.prepare()
        for source in SOURCES:
            result = search(self.data, self.index, "RAG", book=source.book)
            self.assertTrue(result["candidates"])
            self.assertTrue(all(item["book"] == source.book for item in result["candidates"]))
            for item in result["candidates"]:
                evidence = read_evidence(self.data, self.index, item["chunk_id"])
                self.assertEqual(evidence["text"], item["text"])
                self.assertTrue(evidence["source_verified"])
                self.assertFalse(evidence["support_verified"])

    def test_unknown_query_is_not_an_answer_or_semantic_refusal(self):
        self.prepare()
        result = search(self.data, self.index, "unobtainiumzz")
        self.assertEqual(result["status"], "NO_KEYWORD_MATCH")
        self.assertEqual(result["candidates"], [])
        self.assertNotIn("answer", result)
        self.assertEqual(result["model_calls"], 0)

    def test_missing_index_unknown_book_and_unknown_evidence_fail(self):
        prepare_corpus(SOURCES, self.data, lambda source: FIXTURES[source.source_id])
        with self.assertRaises(CorpusError):
            search(self.data, self.index, "RAG")
        build_index(self.data, self.index)
        with self.assertRaises(CorpusError):
            search(self.data, self.index, "RAG", book="Unknown")
        with self.assertRaises(CorpusError):
            read_evidence(self.data, self.index, "not-a-real-id")

    def test_empty_punctuation_and_invalid_limit_fail(self):
        self.prepare()
        for question, limit in [("", 5), ("!!!", 5), ("RAG", 0), ("RAG", 21), ("a" * 10001, 5)]:
            with self.subTest(question=question, limit=limit), self.assertRaises(CorpusError):
                search(self.data, self.index, question, top_k=limit)

    def test_new_process_reopens_index_without_network(self):
        self.prepare()
        output = Path(self.temporary.name) / "reports"
        result = subprocess.run(
            [sys.executable, str(PROJECT / "starter.py"), "--data-dir", str(self.data),
             "--output-dir", str(output), "search", "RAG", "--top-k", "2"],
            capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list(output.glob("search_*.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(report["model_calls"], 0)
        self.assertFalse(report["answer_generated"])
        self.assertFalse(report["support_verified"])
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(verified_chunks(self.data, self.index)[0], load_corpus(self.data)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
