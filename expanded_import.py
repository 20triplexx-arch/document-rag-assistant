"""首批扩库：审计固定 Git 树、中文优先、隔离快照；不运行教材代码或模型。"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from fulltext_import import git_blob, read_url
from study_rag.core import (CorpusError, Source, build_index, fetch_source, json_text,
                            load_corpus, prepare_corpus, read_source_manifest,
                            validate_text, verified_chunks)
from study_rag.web import chapter_order

PROJECT = Path(__file__).resolve().parent
TARGET = PROJECT / "data" / "courses-20261010-v1"
MANIFEST = PROJECT / "sources-expanded.json"
INVENTORY = PROJECT / "data" / "expanded-inventory.json"
OLD = PROJECT / "data" / "fulltext-20261009-v2"
NEW_BOOKS = [
    ("microsoft-ai-agents", "Microsoft · AI Agents for Beginners", "microsoft/ai-agents-for-beginners",
     "ff2ba665e088bf51d9959126c5893e089b50da30", "MIT", 19),
    ("huggingface-agents", "Hugging Face · Agents Course", "huggingface/agents-course",
     "3c469e773ec04e5f338b727ff20e3a6ea823ff81", "Apache-2.0", 60),
]


def select_lessons(book: str, paths: set[str], toc: str = "") -> list[tuple[str, str, str]]:
    """返回 (主线章节路径, 实际文件路径, 语言)，同一章节只收一个版本。"""
    if book == "microsoft-ai-agents":
        canonical = sorted(p for p in paths if re.fullmatch(r"(?:0\d|1[0-8])-[^/]+/README\.md", p))
        if {int(p[:2]) for p in canonical} != set(range(19)) or len(canonical) != 19:
            raise CorpusError("Microsoft 00～18 主线覆盖不全或重复。")
        chinese = lambda p: "translations/zh-CN/" + p
    elif book == "huggingface-agents":
        selected = {p for p in paths if re.fullmatch(r"units/en/(?:unit[0-4]|bonus-unit[1-3])/.*\.mdx", p)
                    and not re.search(r"quiz|discord101|get-your-certificate|additional-readings", p)}
        canonical = ["units/en/" + p + ".mdx" for p in re.findall(r"(?m)^\s*-?\s*local:\s*(\S+)", toc)
                     if "units/en/" + p + ".mdx" in selected]
        if len(canonical) != len(set(canonical)) or set(canonical) != selected or len(canonical) != 60:
            raise CorpusError("Hugging Face 教学正文或目录覆盖不符（目标 60 篇）。")
        chinese = lambda p: p.replace("units/en/", "units/zh-CN/", 1).replace("/bonus-unit2/", "/bonus_unit2/")
    else:
        raise CorpusError("未声明的扩库教材。")
    return [(p, chinese(p), "zh-CN") if chinese(p) in paths else (p, p, "en") for p in canonical]


def discover() -> dict:
    old_manifest, old_contents = load_corpus(OLD)
    old_inventory = json.loads((PROJECT / "data" / "fulltext-inventory.json").read_text(encoding="utf-8"))
    sources = [asdict(s) for s, _ in old_contents]
    chapters, books, audits = {}, [], []
    for order, (book, display, license_name) in enumerate([
        ("awesome-agentic-ai-zh", "Agentic AI 学习路线", "MIT"),
        ("Hello-Agents", "Hello-Agents", "CC BY-NC-SA 4.0"),
    ]):
        license_record = next(r for r in old_inventory["repositories"] if r["book"] == book)
        license_text = license_record["license_text"]
        books.append({"book": book, "display_name": display, "order": order,
                      "repository": license_record["repository"], "commit": license_record["commit"],
                      "license": license_name, "license_path": license_record["license_path"],
                      "license_text": license_text, "license_git_blob": git_blob(license_text.encode("utf-8"))})
        for index, (source, raw) in enumerate(sorted(((s, r) for s, r in old_contents if s.book == book),
                                                   key=lambda pair: chapter_order(pair[0]))):
            chapters[source.source_id] = {"language": "zh-CN", "canonical_path": source.path,
                                          "order": index, "git_blob": git_blob(raw), "bytes": len(raw)}
    for order, (book, display, repo, commit, license_name, expected) in enumerate(NEW_BOOKS, start=2):
        tree = json.loads(read_url(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"))
        if tree.get("truncated") or tree.get("sha") != commit:
            raise CorpusError("固定仓库树不完整。")
        blobs = {e["path"]: e for e in tree["tree"] if e["type"] == "blob"}
        toc = ""
        if book == "huggingface-agents":
            toc_raw = read_url(f"https://raw.githubusercontent.com/{repo}/{commit}/units/en/_toctree.yml")
            if git_blob(toc_raw) != blobs["units/en/_toctree.yml"]["sha"]:
                raise CorpusError("课程目录 Git blob 不符。")
            toc = toc_raw.decode("utf-8-sig")
        selected = select_lessons(book, set(blobs), toc)
        if len(selected) != expected:
            raise CorpusError("课程篇数不符。")
        for index, (canonical, path, language) in enumerate(selected):
            source_id = book + "-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
            chapter = canonical.split("/")[0] if book == "microsoft-ai-agents" else canonical.removeprefix("units/en/").removesuffix(".mdx")
            source = Source(source_id, book, chapter, repo, commit, path)
            sources.append(asdict(source))
            chapters[source_id] = {"language": language, "canonical_path": canonical, "order": index,
                                   "git_blob": blobs[path]["sha"], "bytes": blobs[path]["size"]}
        license_raw = read_url(f"https://raw.githubusercontent.com/{repo}/{commit}/LICENSE")
        if git_blob(license_raw) != blobs["LICENSE"]["sha"]:
            raise CorpusError("许可 Git blob 不符。")
        books.append({"book": book, "display_name": display, "order": order, "repository": repo,
                      "commit": commit, "license": license_name, "license_path": "LICENSE",
                      "license_text": license_raw.decode("utf-8"), "license_git_blob": git_blob(license_raw)})
        audits.append({"book": book, "canonical_paths": [p for p, _, _ in selected],
                       "languages": dict(Counter(language for _, _, language in selected)),
                       "excluded_teaching_candidates": sorted(p for p in blobs if p.startswith("units/en/")
                                                              and p.endswith(".mdx") and p not in {c for c, _, _ in selected})})
        print(f"目录核对：{book}，{len(selected)} 篇", flush=True)
    payload = {"version": 2, "sources": sources, "catalog": {"books": books, "chapters": chapters}}
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 写后用同一来源契约验证，旧声明与字节另在导入验证阶段逐篇检查。
    read_source_manifest(MANIFEST)
    inventory = {"schema_version": 2, "old_corpus_version": old_manifest["corpus_version"], "courses": audits}
    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return inventory


def import_expanded() -> dict:
    sources, catalog = read_source_manifest(MANIFEST)
    old_manifest, old_contents = load_corpus(OLD)
    old = {s.source_id: (s, raw) for s, raw in old_contents}
    if len(old) != 125 or len(sources) != 204 or sources[:125] != [s for s, _ in old_contents]:
        raise CorpusError("旧 125 篇声明或新增目标不符。")
    network = 0
    if (TARGET / "corpus.json").exists():
        imported = prepare_corpus(sources, TARGET, catalog=catalog)
    else:
        def download(source):
            raw = old[source.source_id][1] if source.source_id in old else fetch_source(source)
            expected = catalog["chapters"][source.source_id]
            if git_blob(raw) != expected["git_blob"] or len(raw) != expected["bytes"]:
                raise CorpusError(f"原文 blob 不符：{source.source_id}")
            print(f"{'复用' if source.source_id in old else '下载'} {source.chapter}", flush=True)
            return source.source_id, raw
        with ThreadPoolExecutor(max_workers=4) as pool:
            content = dict(pool.map(download, sources))
        network = sum(s.source_id not in old for s in sources)
        imported = prepare_corpus(sources, TARGET, lambda s: content[s.source_id], catalog=catalog)
        imported["network_requests"] = network
    index = build_index(TARGET, TARGET / "index.sqlite3")
    manifest, chunks, mapping = verified_chunks(TARGET, TARGET / "index.sqlite3")
    for source, raw in load_corpus(TARGET)[1]:
        if source.source_id in old and (source, raw) != old[source.source_id]:
            raise CorpusError("原有来源声明或字节发生变化。")
        text = validate_text(raw)
        cursor = 0
        for start, end in sorted((c.start_char, c.end_char) for c in chunks if c.source_id == source.source_id):
            if text[cursor:start].strip():
                raise CorpusError("正文切分位置覆盖不全。")
            cursor = max(cursor, end)
        if text[cursor:].strip():
            raise CorpusError("正文末尾覆盖不全。")
    report = {"status": "EXPANDED_VERIFIED", "verified_date": "2026-10-10", "import": imported,
              "index": index, "documents": len(sources), "chunks": len(chunks),
              "documents_by_book": dict(Counter(s.book for s in sources)),
              "chunks_by_book": dict(Counter(mapping[c.source_id].book for c in chunks)),
              "languages": dict(Counter(c["language"] for c in catalog["chapters"].values())),
              "english_gaps": [s.path for s in sources if catalog["chapters"][s.source_id]["language"] == "en"],
              "corpus_version": manifest["corpus_version"], "old_corpus_version": old_manifest["corpus_version"],
              "old_documents_byte_identical": 125, "text_position_coverage": "all-nonwhitespace-characters",
              "model_calls": 0, "support_verified": False}
    (TARGET / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    args = parser.parse_args()
    if args.discover:
        discover()
    import_expanded()
