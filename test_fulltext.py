"""全文来源覆盖和多章节图书汇总测试，不访问网络或模型。"""
from dataclasses import replace
from pathlib import Path
import re
from unittest import TestCase

from fastapi.testclient import TestClient

from fulltext_import import selected_path
from study_rag.core import prepare_corpus, build_index, read_sources
from study_rag.settings import DEFAULT_DATA
from study_rag.web import chapter_order, create_app
import test_multiuser as fixtures
from test_multiuser import SOURCES, TEXT


class FulltextManifestTests(TestCase):
    def test_manifest_covers_all_main_chapters_and_fixed_versions(self):
        project = Path(__file__).resolve().parent
        sources = read_sources(project / "sources-full.json")
        hello = [s for s in sources if s.book == "Hello-Agents"]
        awesome = [s for s in sources if s.book == "awesome-agentic-ai-zh"]
        main = {int(re.match(r"docs/chapter(\d+)/", s.path)[1]) for s in hello if s.path.startswith("docs/chapter")}
        self.assertEqual(main, set(range(1, 17)))
        stages = {re.match(r"stages/([0-9.]+)-", s.path)[1] for s in awesome if re.match(r"stages/[0-9]", s.path)}
        self.assertEqual(stages, {"00", "01", "02", "03", "04", "05", "06", "07", "07.5", "08"})
        self.assertEqual(len({(s.repository, s.commit, s.path) for s in sources}), len(sources))
        self.assertEqual({s.commit for s in hello}, {"6acdf9527f9c229b173f26d66bee2f6831d6c93a"})
        self.assertEqual({s.commit for s in awesome}, {"50fc26d5decc1f3ee8a9e67b9f2c807e179e01d6"})
        self.assertEqual({s.source_id for s in sources if s.source_id in {"hello-chapter8", "awesome-stage6"}},
                         {"hello-chapter8", "awesome-stage6"})

    def test_english_mirrors_and_maintenance_assets_not_selected(self):
        paths = {"stages/01-llm-basics.md", "stages/01-llm-basics.en.md", "stages/01-llm-basics.zh-Hans.md"}
        self.assertTrue(selected_path("awesome-agentic-ai-zh", "stages/01-llm-basics.zh-Hans.md", paths))
        for path in ("stages/01-llm-basics.md", "stages/01-llm-basics.en.md", "stages/DESIGN.md", "docs/plans/plan.md", "resources/diagrams/prompts.md"):
            self.assertFalse(selected_path("awesome-agentic-ai-zh", path, paths))
        for path in ("docs/chapter1/Chapter1-English.md", "Co-creation-projects/demo/README.md",
                     "code/chapter10/a2a_document_20251009_024100.md", "code/chapter10/weather-mcp-server/PUBLISH_CHECKLIST.md",
                     "code/chapter12/data_generation/evaluation_results/report.md", "docs/images/image.png"):
            self.assertFalse(selected_path("Hello-Agents", path, set()))
        self.assertTrue(selected_path("Hello-Agents", "docs/chapter16/第十六章 毕业设计.md", set()))
        self.assertTrue(selected_path("Hello-Agents", "Extra-Chapter/Extra01-参考答案.md", set()))

    def test_default_does_not_overwrite_original_corpus_or_user_database(self):
        self.assertEqual(DEFAULT_DATA.name, "fulltext-20261009-v2")
        self.assertEqual(DEFAULT_DATA.parent.name, "data")
        self.assertNotEqual(DEFAULT_DATA, Path(__file__).resolve().parent / "output")

    def test_catalog_orders_main_chapters_numerically_before_supplements(self):
        sources = [replace(SOURCES[1], path=path) for path in [
            "Extra-Chapter/Extra01-练习.md", "docs/chapter10/第十章.md",
            "docs/chapter2/第二章.md", "docs/前言.md", "docs/chapter1/第一章.md"]]
        ordered = sorted(sources, key=chapter_order)
        self.assertEqual([s.path for s in ordered], ["docs/前言.md", "docs/chapter1/第一章.md",
                         "docs/chapter2/第二章.md", "docs/chapter10/第十章.md", "Extra-Chapter/Extra01-练习.md"])


# 复用测试初始化但不继承整套测试方法，避免重复执行所有账号测试。
class LibraryAggregationTests(TestCase):
    setUp = fixtures.MultiuserTests.setUp

    def test_book_counts_aggregate_all_sources_and_list_chapter_urls(self):
        extra = replace(SOURCES[1], source_id="book-b2", chapter="另一个章节", path="chapter2.md")
        data = self.root / "multiple-chapters"
        prepare_corpus([*SOURCES, extra], data, lambda _: TEXT.encode())
        build_index(data, data / "index.sqlite3")
        with TestClient(create_app(data_dir=data, store=self.store, model=self.model)) as client:
            response = client.get("/api/library")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["books"]), 2)
        self.assertEqual(sum(book["chunks"] for book in payload["books"]), payload["chunks"])
        hello = next(book for book in payload["books"] if book["book"] == "Hello-Agents")
        self.assertEqual(hello["documents"], 2)
        self.assertEqual(len(hello["chapters"]), 2)
        self.assertTrue(all(chapter["chunks"] > 0 and "/blob/" in chapter["source_url"] for chapter in hello["chapters"]))
        self.assertEqual(self.model.calls, 0)
