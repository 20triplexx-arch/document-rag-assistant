"""固定仓库版本的中文全教材目录审计与导入，不执行下载内容或调用模型。"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.request import HTTPSHandler, Request, build_opener

from study_rag.core import (
    CorpusError, NoRedirect, Source, build_index, fetch_source, json_text,
    load_corpus, prepare_corpus, read_sources, verified_chunks,
)

PROJECT = Path(__file__).resolve().parent
TARGET = PROJECT / "data" / "fulltext-20261009-v2"
INVENTORY = PROJECT / "data" / "fulltext-inventory.json"
MANIFEST = PROJECT / "sources-full.json"
REPOSITORIES = [
    ("awesome-agentic-ai-zh", "WenyuChiou/awesome-agentic-ai-zh", "50fc26d5decc1f3ee8a9e67b9f2c807e179e01d6", "LICENSE"),
    ("Hello-Agents", "datawhalechina/hello-agents", "6acdf9527f9c229b173f26d66bee2f6831d6c93a", "LICENSE.txt"),
]


def selected_path(book: str, path: str, paths: set[str]) -> bool:
    """中文课程正文和官方配套说明，排除英译、镜像、设计/运行产物。"""
    if not path.endswith(".md"):
        return False
    if book == "awesome-agentic-ai-zh":
        if path.startswith((".github/", "docs/", "scripts/", "resources/diagrams/")):
            return False
        if "/translations/" in path or PurePosixPath(path).name == "DESIGN.md":
            return False
        if "/" not in path and path.split(".")[0] not in {"README", "CAPSTONE", "RESOURCES", "ROADMAP", "PROGRESS", "index"}:
            return False
        if "/" in path and not path.startswith(("stages/", "tracks/", "branches/", "walkthroughs/", "resources/", "examples/")):
            return False
        if path.endswith(".en.md"):
            return False
        return path.endswith(".zh-Hans.md") or path[:-3] + ".zh-Hans.md" not in paths
    if book == "Hello-Agents":
        if path in {"README.md", "docs/README.md", "docs/前言.md", "docs/_sidebar.md"}:
            return True
        if re.fullmatch(r"docs/chapter\d+/第[^/]+\.md", path):
            return True
        if path.startswith(("Extra-Chapter/", "Additional-Chapter/")):
            return True
        if path.startswith("code/"):
            if any(part in {"evaluation_results", "evaluation_reports", "generated_data", "template_output"}
                   for part in PurePosixPath(path).parts):
                return False
            name = PurePosixPath(path).name
            return name not in {"report.md", "my_README.md", "PUBLISH_CHECKLIST.md"} and not name.startswith("a2a_document_")
    return False


def read_url(url: str, limit: int = 4_000_000) -> bytes:
    request = Request(url, headers={"User-Agent": "document-rag-learning-assistant"})
    with build_opener(HTTPSHandler(), NoRedirect()).open(request, timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise CorpusError("目录/许可超过下载上限。")
    return raw


def discover() -> dict:
    previous = {(s.repository, s.commit, s.path): s.source_id for s in read_sources(PROJECT / "sources.json")}
    documents, repositories = [], []
    for book, repo, commit, license_path in REPOSITORIES:
        tree = json.loads(read_url(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"))
        if tree.get("truncated") or tree.get("sha") != commit:
            raise CorpusError("仓库目录不完整或版本不一致，未发布清单。")
        blobs = [entry for entry in tree["tree"] if entry["type"] == "blob"]
        paths = {entry["path"] for entry in blobs}
        selected = [entry for entry in blobs if selected_path(book, entry["path"], paths)]
        # 核对章节覆盖，不能仅因下载成功就叫全教材。
        if book == "Hello-Agents":
            chapters = {int(re.match(r"docs/chapter(\d+)/", e["path"])[1]) for e in selected if e["path"].startswith("docs/chapter")}
            if chapters != set(range(1, 17)):
                raise CorpusError("Hello 中文 1～16 章覆盖不全。")
        elif len([e for e in selected if re.match(r"stages/\d", e["path"])]) != 10:
            raise CorpusError("awesome 全部阶段（含 7.5）覆盖不全。")
        prefix = "hello" if book == "Hello-Agents" else "awesome"
        for entry in sorted(selected, key=lambda e: e["path"]):
            path = entry["path"]
            source_id = previous.get((repo, commit, path), prefix + "-" + hashlib.sha256(path.encode()).hexdigest()[:16])
            source = Source(source_id, book, PurePosixPath(path).stem.removesuffix(".zh-Hans"), repo, commit, path)
            documents.append({"source": asdict(source), "git_blob": entry["sha"], "bytes": entry["size"]})
        license_raw = read_url(f"https://raw.githubusercontent.com/{repo}/{commit}/{license_path}")
        license_entry = next(entry for entry in blobs if entry["path"] == license_path)
        if git_blob(license_raw) != license_entry["sha"]:
            raise CorpusError("许可文件不匹配固定版本。")
        repositories.append({"book": book, "repository": repo, "commit": commit,
                             "license_path": license_path, "license_text": license_raw.decode("utf-8-sig"),
                             "selected_documents": len(selected),
                             "excluded": [{"path": e["path"], "bytes": e["size"]} for e in blobs if e not in selected]})
        print(f"目录已核对：{book}，{len(selected)} 篇中文教材/配套文档", flush=True)
    inventory = {"schema_version": 1, "scope": "fixed-version-chinese-course-and-official-companions",
                 "documents": documents, "repositories": repositories}
    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY.write_text(json_text(inventory), encoding="utf-8")
    MANIFEST.write_text(json.dumps({"version": 1, "sources": [d["source"] for d in documents]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return inventory


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def import_fulltext(inventory: dict) -> dict:
    sources = read_sources(MANIFEST)
    declarations = [d["source"] for d in inventory["documents"]]
    if declarations != [asdict(s) for s in sources]:
        raise CorpusError("来源清单与目录审计不一致。")
    expected = {d["source"]["source_id"]: d for d in inventory["documents"]}
    if (TARGET / "corpus.json").exists():
        imported = prepare_corpus(sources, TARGET)
    else:
        # 并行读取公开文本；仅原章节且 blob 完全相符时复用已有快照。
        old = {}
        if (PROJECT / "data" / "corpus.json").exists():
            old.update({source.source_id: raw for source, raw in load_corpus(PROJECT / "data")[1]})
        staging = PROJECT / "data" / "fulltext-20261009"
        if (staging / "corpus.json").exists():
            old.update({source.source_id: raw for source, raw in load_corpus(staging)[1]})
        def download(source):
            raw = old.get(source.source_id)
            reused = raw is not None and git_blob(raw) == expected[source.source_id]["git_blob"]
            if not reused:
                raw = fetch_source(source)
            record = expected[source.source_id]
            if len(raw) != record["bytes"] or git_blob(raw) != record["git_blob"]:
                raise CorpusError(f"固定版本的原文完整性失败：{source.source_id}")
            print(f"{'复用' if reused else '下载'} {source.book} / {source.chapter}", flush=True)
            return source.source_id, raw, reused
        with ThreadPoolExecutor(max_workers=4) as pool:
            downloaded = list(pool.map(download, sources))
        content = {key: raw for key, raw, _ in downloaded}
        imported = prepare_corpus(sources, TARGET, lambda s: content[s.source_id])
        imported["network_requests"] = sum(not reused for _, _, reused in downloaded)
    index = build_index(TARGET, TARGET / "index.sqlite3")
    manifest, chunks, mapping = verified_chunks(TARGET, TARGET / "index.sqlite3")
    count = Counter(mapping[c.source_id].book for c in chunks)
    # 分块位置并集必须覆盖每篇正文的全部非空白字符，包括代码与表格。
    for source, raw in load_corpus(TARGET)[1]:
        if git_blob(raw) != expected[source.source_id]["git_blob"] or len(raw) != expected[source.source_id]["bytes"]:
            raise CorpusError(f"复用原文不匹配固定 Git blob：{source.source_id}")
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        spans = sorted((c.start_char, c.end_char) for c in chunks if c.source_id == source.source_id)
        cursor = 0
        for start, end in spans:
            if text[cursor:start].strip():
                raise CorpusError(f"正文存在未索引位置：{source.source_id}")
            cursor = max(cursor, end)
        if text[cursor:].strip():
            raise CorpusError(f"正文末尾存在未索引位置：{source.source_id}")
    report = {"status": "FULLTEXT_VERIFIED", "import": imported, "index": index,
              "corpus_version": manifest["corpus_version"], "documents": len(sources),
              "chunks": len(chunks), "chunks_by_book": dict(count),
              "bytes": sum(d["bytes"] for d in manifest["documents"]), "model_calls": 0,
              "text_position_coverage": "all-nonwhitespace-characters",
              "limitations": ["图片/附件/视频仅保留正文中的引用，未进行 OCR、PDF 或视频转录",
                              "仅固定版本中文正文与官方配套说明，不包含外链网页正文、英译副本或社区项目源码"]}
    (TARGET / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="从固定 Git 树生成课程来源清单")
    args = parser.parse_args()
    inventory = discover() if args.discover else json.loads(INVENTORY.read_text(encoding="utf-8"))
    import_fulltext(inventory)
