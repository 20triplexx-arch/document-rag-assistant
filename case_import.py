"""导入已审计 GitHub 案例 README；只读取公开文本，不执行案例或调用模型。"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath

from fulltext_import import git_blob, read_url
from study_rag.core import (CorpusError, Source, build_index, fetch_source, json_text, load_corpus,
                            prepare_corpus, read_source_manifest, validate_text, verified_chunks)

PROJECT = Path(__file__).resolve().parent
BASE = PROJECT / "data" / "courses-20261010-v1"
TARGET = PROJECT / "data" / "courses-cases-20261010-v1"
MANIFEST = PROJECT / "sources-cases.json"
INVENTORY = PROJECT / "data" / "cases-inventory.json"
REPOSITORY = "Shubhamsaboo/awesome-llm-apps"
COMMIT = "4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2"
BOOK = "awesome-llm-apps-cases"
ADK = "ai_agent_framework_crash_course/google_adk_crash_course/"
CASES = [
    ("自定义工具调用（Function Tools）", ["工具调用", "函数参数", "错误处理"],
     ADK + "4_tool_using_agent/4_2_function_tools/README.md", ["calculator_agent/agent.py", "calculator_agent/tools.py"]),
    ("持久会话与记忆（SQLite）", ["记忆", "会话", "持久化"],
     ADK + "5_memory_agent/5_2_persistent_conversation_agent/README.md", ["agent.py", "app.py"]),
    ("本地文档问答（Local RAG）", ["本地模型", "文档问答", "RAG"],
     "rag_tutorials/local_rag_agent/README.md", ["local_rag_agent.py"]),
    ("混合检索与重排（Hybrid RAG）", ["混合检索", "重排", "RAG"],
     "rag_tutorials/hybrid_search_rag/README.md", ["main.py"]),
    ("检索纠错（Corrective RAG）", ["检索纠错", "相关性评估", "查询改写"],
     "rag_tutorials/corrective_rag/README.md", ["corrective_rag.py"]),
    ("带推理的 Agentic RAG", ["Agentic RAG", "推理", "知识库"],
     "rag_tutorials/agentic_rag_with_reasoning/README.md", ["rag_reasoning_agent.py"]),
    ("知识图谱与可核对引用", ["知识图谱", "多跳检索", "引用"],
     "rag_tutorials/knowledge_graph_rag_citations/README.md", ["knowledge_graph_rag.py"]),
    ("RAG 故障诊断", ["RAG", "故障诊断", "调试"],
     "rag_tutorials/rag_failure_diagnostics_clinic/README.md", ["rag_failure_diagnostics_clinic.py"]),
    ("浏览器 MCP Agent", ["MCP", "浏览器", "工具调用"],
     "mcp_ai_agents/browser_mcp_agent/README.md", ["main.py"]),
    ("多 MCP 服务协作", ["MCP", "多服务", "工具协作"],
     "mcp_ai_agents/multi_mcp_agent/README.md", ["multi_mcp_agent.py"]),
    ("多 Agent 研究团队", ["多 Agent", "研究", "协作"],
     "advanced_ai_agents/multi_agent_apps/multi_agent_researcher/README.md", ["research_agent.py", "research_agent_llama3.py"]),
    ("多 Agent 旅行规划", ["多 Agent", "旅行规划", "任务分工"],
     "advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/README.md",
     ["backend/agents/team.py", "backend/agents/itinerary.py", "backend/travel_planning_team.py"]),
]


def select_language(path: str, paths: set[str]) -> tuple[str, str]:
    directory = str(PurePosixPath(path).parent)
    for name in ("README.zh-CN.md", "README.zh-Hans.md", "README.zh.md", "README_CN.md", "README_zh.md"):
        candidate = directory + "/" + name
        if candidate in paths:
            return candidate, "zh-CN"
    if path not in paths:
        raise CorpusError("案例 README 不存在于固定仓库树。")
    return path, "en"


def discover(tree: dict | None = None) -> dict:
    tree = tree or json.loads(read_url(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{COMMIT}?recursive=1"))
    if tree.get("truncated") or tree.get("sha") != COMMIT:
        raise CorpusError("案例 Git 树不完整或提交不同。")
    blobs = {e["path"]: e for e in tree["tree"] if e["type"] == "blob"}
    base_manifest, contents = load_corpus(BASE)
    if len(contents) != 204:
        raise CorpusError("基础四套课程不是已核对的 204 篇。")
    catalog = deepcopy(base_manifest["catalog"])
    sources = [asdict(s) for s, _ in contents]
    license_raw = read_url(f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/LICENSE")
    if git_blob(license_raw) != blobs["LICENSE"]["sha"] or b"Apache License" not in license_raw:
        raise CorpusError("案例固定版本许可不符。")
    catalog["books"].append({"book": BOOK, "display_name": "GitHub 实战案例 · awesome-llm-apps",
                             "order": max(b["order"] for b in catalog["books"]) + 1,
                             "kind": "case_collection", "repository": REPOSITORY, "commit": COMMIT,
                             "license": "Apache-2.0", "license_path": "LICENSE",
                             "license_text": license_raw.decode("utf-8"), "license_git_blob": git_blob(license_raw)})
    audit = []
    for order, (title, topics, canonical, code_paths) in enumerate(CASES):
        path, language = select_language(canonical, set(blobs))
        directory = str(PurePosixPath(canonical).parent)
        # 所选正文/实现文件的祖先目录有单独许可时停止，不能默认套用根许可。
        ancestors = {str(p) for p in PurePosixPath(canonical).parents if str(p) != "."}
        for entry in blobs:
            if (str(PurePosixPath(entry).parent) in ancestors
                    and PurePosixPath(entry).name.upper().startswith(("LICENSE", "COPYING"))):
                raise CorpusError("案例存在单独许可，需要重新审计。")
        implementations = []
        for name in code_paths:
            implementation = directory + "/" + name
            if implementation not in blobs or not implementation.endswith(".py"):
                raise CorpusError("案例实现入口不在固定仓库树。")
            entry = blobs[implementation]
            implementations.append({"path": implementation, "git_blob": entry["sha"], "bytes": entry["size"]})
        source_id = "llm-case-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
        source = Source(source_id, BOOK, title, REPOSITORY, COMMIT, path)
        sources.append(asdict(source))
        catalog["chapters"][source_id] = {"language": language, "canonical_path": canonical, "order": order,
                                           "kind": "case", "topics": topics, "implementation_files": implementations,
                                           "git_blob": blobs[path]["sha"], "bytes": blobs[path]["size"]}
        audit.append({"source_id": source_id, "title": title, "language": language, "path": path})
    payload = {"version": 2, "sources": sources, "catalog": catalog}
    # 先验证再发布清单；不覆盖已有完整快照。
    from study_rag.core import validate_catalog
    validate_catalog(catalog, [Source(**s) for s in sources])
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inventory = {"schema_version": 2, "verified_date": "2026-10-10", "repository": REPOSITORY,
                 "commit": COMMIT, "base_corpus_version": base_manifest["corpus_version"],
                 "scope": "12-selected-case-readmes-and-pinned-implementation-links", "cases": audit}
    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return inventory


def import_cases() -> dict:
    sources, catalog = read_source_manifest(MANIFEST)
    base_manifest, contents = load_corpus(BASE)
    baseline = {s.source_id: (s, raw) for s, raw in contents}
    if len(sources) != 216 or sources[:204] != [s for s, _ in contents]:
        raise CorpusError("案例来源声明与基础 204 篇不同。")
    if (TARGET / "corpus.json").exists():
        imported = prepare_corpus(sources, TARGET, catalog=catalog)
    else:
        def download(source):
            if source.source_id in baseline:
                return source.source_id, baseline[source.source_id][1], True
            expected = catalog["chapters"][source.source_id]
            # 复用本轮已经下载且 blob 相符的预览文件；不信任文件名对应关系。
            previews = PROJECT / "output" / "case-source-preview"
            raw = next((p.read_bytes() for p in previews.glob("*.md") if git_blob(p.read_bytes()) == expected["git_blob"]), None)
            reused = raw is not None
            raw = raw if reused else fetch_source(source)
            if git_blob(raw) != expected["git_blob"] or len(raw) != expected["bytes"]:
                raise CorpusError("案例原文与 Git blob 不符。")
            print(f"{'复用已核对预览' if reused else '下载'} {source.chapter}", flush=True)
            return source.source_id, raw, reused
        with ThreadPoolExecutor(max_workers=4) as pool:
            downloaded = list(pool.map(download, sources))
        raw_by_id = {sid: raw for sid, raw, _ in downloaded}
        imported = prepare_corpus(sources, TARGET, lambda s: raw_by_id[s.source_id], catalog=catalog)
        imported["network_requests"] = sum(not reused for _, _, reused in downloaded)
    index = build_index(TARGET, TARGET / "index.sqlite3")
    manifest, chunks, mapping = verified_chunks(TARGET, TARGET / "index.sqlite3")
    old_chunks = verified_chunks(BASE, BASE / "index.sqlite3")[1]
    if [asdict(c) for c in chunks if c.source_id in baseline] != [asdict(c) for c in old_chunks]:
        raise CorpusError("旧 4082 个片段发生变化。")
    for source, raw in load_corpus(TARGET)[1]:
        if source.source_id in baseline and (source, raw) != baseline[source.source_id]:
            raise CorpusError("旧来源或字节发生变化。")
        text, cursor = validate_text(raw), 0
        for start, end in sorted((c.start_char, c.end_char) for c in chunks if c.source_id == source.source_id):
            if text[cursor:start].strip():
                raise CorpusError("案例原文位置覆盖不全。")
            cursor = max(cursor, end)
        if text[cursor:].strip():
            raise CorpusError("案例原文末尾覆盖不全。")
    report = {"status": "CASES_VERIFIED", "verified_date": "2026-10-10", "import": imported, "index": index,
              "documents": len(sources), "case_documents": sum(s.book == BOOK for s in sources), "chunks": len(chunks),
              "documents_by_book": dict(Counter(s.book for s in sources)),
              "chunks_by_book": dict(Counter(mapping[c.source_id].book for c in chunks)),
              "case_languages": dict(Counter(catalog["chapters"][s.source_id]["language"] for s in sources if s.book == BOOK)),
              "old_documents_byte_identical": 204, "old_chunks_identical": len(old_chunks),
              "corpus_version": manifest["corpus_version"], "base_corpus_version": base_manifest["corpus_version"],
              "text_position_coverage": "all-nonwhitespace-characters", "model_calls": 0, "support_verified": False}
    (TARGET / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="核对固定 Git 树和许可后发布案例清单")
    args = parser.parse_args()
    if args.discover:
        discover()
    import_cases()
