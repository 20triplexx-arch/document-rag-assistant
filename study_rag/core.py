"""固定来源导入、保留位置的切分和持久关键词检索；不调用模型。"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Callable
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener
from .mdx import mdx_mask
from .limits import MAX_QUESTION_CHARS

SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 2_000_000
CHUNK_CHARS = 1400
OVERLAP_CHARS = 160
_SOURCE_IO = ThreadPoolExecutor(max_workers=8, thread_name_prefix='rag-source-io')


class CorpusError(ValueError):
    """语料或索引无法核对，必须停止。"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Source:
    source_id: str
    book: str
    chapter: str
    repository: str
    commit: str
    path: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.source_id):
            raise CorpusError("来源 ID 格式错误。")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise CorpusError("仓库名称格式错误。")
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit):
            raise CorpusError("来源必须固定到完整 Git 提交号。")
        path = PurePosixPath(self.path)
        if (not self.path or path.is_absolute() or ".." in path.parts
                or "\\" in self.path or path.suffix.lower() not in {".md", ".mdx", ".txt", ".py", ".ipynb", ".js", ".ts", ".mjs", ".cjs", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
                or any(ord(char) < 32 for char in self.path)):
            raise CorpusError("来源必须是仓库内 Markdown/MDX/TXT/Python 文件。")
        if not self.book.strip() or not self.chapter.strip():
            raise CorpusError("教材名和章节不能为空。")

    @property
    def raw_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repository}/{self.commit}/{quote(self.path)}"

    @property
    def source_url(self) -> str:
        return f"https://github.com/{self.repository}/blob/{self.commit}/{quote(self.path)}"


@lru_cache(maxsize=8192)
def _source_values(values):
    return Source(*values)


def _source_record(record):
    fields=('source_id','book','chapter','repository','commit','path')
    if set(record)!=set(fields):raise CorpusError('来源声明字段不同。')
    return _source_values(tuple(record[field] for field in fields))


def read_source_manifest(path: Path) -> tuple[list[Source], dict | None]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("version") not in {1, 2, 3, 4} or not payload.get("sources"):
        raise CorpusError("来源清单版本不支持或清单为空。")
    sources = [Source(**record) for record in payload["sources"]]
    if len({source.source_id for source in sources}) != len(sources):
        raise CorpusError("来源 ID 重复。")
    if payload["version"] < 3 and any(s.path.endswith(".py") for s in sources):
        raise CorpusError("Python 实现文件需要 v3 来源契约。")
    catalog = payload.get("catalog") if payload["version"] >= 2 else None
    if payload["version"] >= 2:
        if not isinstance(catalog,dict):raise CorpusError("来源目录缺失。")
        if payload["version"] >= 3 and catalog.get("version") != payload["version"]:
            raise CorpusError("v3 目录版本缺失。")
        validate_catalog(catalog, sources)
    return sources, catalog


def read_sources(path: Path) -> list[Source]:
    return read_source_manifest(path)[0]


def validate_catalog(catalog: dict, sources: list[Source]) -> None:
    if not isinstance(catalog, dict) or set(catalog) not in ({"books", "chapters"}, {"books", "chapters", "version"}):
        raise CorpusError("v2 教材目录缺失。")
    v4 = catalog.get("version") == 4
    v3 = catalog.get("version") in {3, 4}
    if "version" in catalog and not v3:
        raise CorpusError("目录契约版本不支持。")
    books = catalog["books"]
    if (not books or len({b["book"] for b in books}) != len(books)
            or {b["book"] for b in books} != {s.book for s in sources}
            or len({b["order"] for b in books}) != len(books)
            or set(catalog["chapters"]) != {s.source_id for s in sources}):
        raise CorpusError("教材目录与来源覆盖不同。")
    by_book = {b["book"]: b for b in books}
    for book in books:
        if (not isinstance(book["order"], int) or not book["display_name"].strip()
                or not book["license"].strip() or not book["license_text"].strip()
                or not re.fullmatch(r"[0-9a-f]{40}", book["license_git_blob"])):
            raise CorpusError("教材显示名、顺序或许可无效。")
        license_raw = book["license_text"].encode("utf-8")
        if hashlib.sha1(f"blob {len(license_raw)}\0".encode() + license_raw).hexdigest() != book["license_git_blob"]:
            raise CorpusError("许可原文与 Git blob 不一致。")
        path = PurePosixPath(book["license_path"])
        if path.is_absolute() or ".." in path.parts or "\\" in str(path):
            raise CorpusError("许可路径无效。")
    for source in sources:
        book = by_book[source.book]
        chapter = catalog["chapters"][source.source_id]
        canonical = PurePosixPath(chapter["canonical_path"])
        if (book["repository"] != source.repository or book["commit"] != source.commit
                or chapter["language"] not in {"zh-CN", "en"}
                or not isinstance(chapter["order"], int)
                or not chapter["canonical_path"] or canonical.is_absolute() or ".." in canonical.parts
                or "\\" in chapter["canonical_path"]
                or not re.fullmatch(r"[0-9a-f]{40}", chapter["git_blob"])
                or not isinstance(chapter["bytes"], int) or chapter["bytes"] <= 0):
            raise CorpusError("章节语言、版本或对应关系无效。")
        if chapter.get("kind") == "case":
            topics, implementations = chapter.get("topics"), chapter.get("implementation_files")
            if (book.get("kind") != "case_collection" or not isinstance(topics, list) or not 1 <= len(topics) <= 8
                    or any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 80 for t in topics)
                    or not isinstance(implementations, list) or not 1 <= len(implementations) <= 8):
                raise CorpusError("案例主题或实现入口无效。")
            for implementation in implementations:
                path = PurePosixPath(implementation["path"])
                if (path.is_absolute() or ".." in path.parts or "\\" in str(path) or path.suffix != ".py"
                        or any(ord(c) < 32 for c in str(path))
                        or not str(path).startswith(str(canonical.parent) + "/")
                        or not re.fullmatch(r"[0-9a-f]{40}", implementation["git_blob"])
                        or not isinstance(implementation["bytes"], int) or implementation["bytes"] <= 0):
                    raise CorpusError("案例实现入口不属于该章节或未固定到 Git blob。")
        if v3 and chapter.get("content_type") is not None:
            if chapter["content_type"] not in ({"prose", "code", "snippet", "configuration", "notebook"} if v4 else {"prose", "code", "snippet"}):
                raise CorpusError("正文类型无效。")
            versions = chapter.get("applicable_versions")
            if (not isinstance(versions, list) or not versions or len(versions) != len(set(versions))
                    or any(v not in {"unknown", "pinned-documentation", "2025-11-25", "2026-07-28"} for v in versions)):
                raise CorpusError("资料适用版本无效。")
            for field in ("parent_source_ids", "root_source_ids", "dependencies"):
                ids = chapter.get(field, [])
                if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(i not in catalog["chapters"] or i == source.source_id for i in ids if field != "root_source_ids"):
                    raise CorpusError("资料依赖关系无效。")
                if any(i not in catalog["chapters"] for i in ids):
                    raise CorpusError("资料关联来源不存在。")
        if source.path.endswith(".py") and not v4:
            if not v3 or chapter.get("content_type") != "code" or chapter.get("kind") != "implementation":
                raise CorpusError("实现代码缺少 v3 类型声明。")
            parents = chapter.get("parent_source_ids", [])
            registered = [f for p in parents for f in catalog["chapters"][p].get("implementation_files", [])]
            if not any(f["path"] == source.path and f["git_blob"] == chapter["git_blob"] and f["bytes"] == chapter["bytes"] for f in registered):
                raise CorpusError("实现代码未登记到父案例。")
    if v3:
        mapping = {s.source_id:s for s in sources}
        for sid, meta in catalog["chapters"].items():
            for dep in meta.get("dependencies", []):
                target = catalog["chapters"][dep]
                if (sid not in target.get("parent_source_ids", []) or mapping[sid].repository != mapping[dep].repository
                        or mapping[sid].commit != mapping[dep].commit):
                    raise CorpusError("MDX 依赖没有关联到实际同版本文件。")
    for book in books:
        chapters = [catalog["chapters"][s.source_id] for s in sources if s.book == book["book"]]
        if (len({c["canonical_path"] for c in chapters}) != len(chapters)
                or len({c["order"] for c in chapters}) != len(chapters)):
            raise CorpusError("章节语言镜像或顺序重复。")


def corpus_catalog(manifest: dict) -> dict:
    """v1 快照仍可读；已知旧教材的展示元数据集中兼容。"""
    if manifest["schema_version"] >= 2:
        return manifest["catalog"]
    sources = [Source(**record["source"]) for record in manifest["documents"]]
    legacy = {"awesome-agentic-ai-zh": (0, "Agentic AI 学习路线", "MIT", "LICENSE"),
              "Hello-Agents": (1, "Hello-Agents", "CC BY-NC-SA 4.0", "LICENSE.txt")}
    books = []
    for name in dict.fromkeys(s.book for s in sources):
        source = next(s for s in sources if s.book == name)
        order, display, license_name, license_path = legacy.get(name, (2, name, "未记录", "LICENSE"))
        books.append({"book": name, "order": order, "display_name": display, "license": license_name,
                      "license_path": license_path, "repository": source.repository, "commit": source.commit})
    return {"books": sorted(books, key=lambda b: (b["order"], b["book"])),
            "chapters": {s.source_id: {"language": "zh-CN"} for s in sources}}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CorpusError("教材下载出现重定向，未继续访问。")


def fetch_source(source: Source) -> bytes:
    """只访问固定 raw URL，限制大小/超时，不执行教材里的代码。"""
    request = Request(source.raw_url, headers={"User-Agent": "document-rag-learning-assistant"})
    with build_opener(HTTPSHandler(), NoRedirect()).open(request, timeout=25) as response:
        if response.status != 200:
            raise CorpusError("下载未返回成功状态。")
        raw = response.read(MAX_SOURCE_BYTES + 1)
    validate_text(raw)
    return raw


def validate_text(raw: bytes) -> str:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise CorpusError("文件为空或超过单文件 2MB 上限。")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip() or "\x00" in text:
        raise CorpusError("文件没有有效文本。")
    return text


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    section: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int
    text: str


def split_document(source: Source, raw: bytes, *, max_chars: int = CHUNK_CHARS,
                   overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    if max_chars < 40 or not 0 <= overlap < max_chars // 2:
        raise CorpusError("切分大小或重叠长度无效。")
    text = validate_text(raw)
    if source.path.endswith(".py"):
        from .code_index import python_chunks
        return python_chunks(source, raw, max_chars=max_chars, overlap=overlap)
    structural = mdx_mask(text) if source.path.endswith(".mdx") else text
    boundaries = [(0, "正文")]
    stack: list[tuple[int, str]] = []
    offset = 0
    fence_char, fence_length = "", 0
    for line in structural.splitlines(keepends=True):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            marker, suffix = fence.groups()
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length and not suffix.strip():
                fence_char, fence_length = "", 0
        elif not fence_char:
            heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if heading:
                level, title = len(heading[1]), heading[2]
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                section = " / ".join(item[1] for item in stack)
                if offset == 0:
                    boundaries[0] = (0, section)
                else:
                    boundaries.append((offset, section))
        offset += len(line)

    chunks: list[Chunk] = []
    raw_hash = digest(raw)
    for index, (section_start, section) in enumerate(boundaries):
        section_end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        start = section_start
        while start < section_end:
            end = min(start + max_chars, section_end)
            if end < section_end:
                # 优先保留整段，再保留整行；超长单行才按字符截断。
                half = start + max_chars // 2
                paragraph = text.rfind("\n\n", half, end)
                newline = text.rfind("\n", half, end)
                if paragraph >= half:
                    end = paragraph + 2
                elif newline >= half:
                    end = newline + 1
            fragment = text[start:end]
            if fragment.strip():
                identity = json_text([source.source_id, raw_hash, section, start, end])
                chunks.append(Chunk(
                    chunk_id=f"{source.source_id}-{digest(identity.encode())[:20]}",
                    source_id=source.source_id, section=section,
                    start_char=start, end_char=end,
                    start_line=text.count("\n", 0, start) + 1,
                    end_line=text.count("\n", 0, max(start, end - 1)) + 1,
                    text=fragment,
                ))
            if end == section_end:
                break
            start = max(start + 1, end - overlap)
    return chunks


def prepare_corpus(sources: list[Source], data_dir: Path,
                   fetch: Callable[[Source], bytes] = fetch_source, *, catalog: dict | None = None) -> dict:
    """下载阶段失败不会发布半套语料；同清单的完整快照无网络复用。"""
    if not sources or len({source.source_id for source in sources}) != len(sources):
        raise CorpusError("来源不能为空或重复。")
    declarations = [asdict(source) for source in sources]
    if catalog is not None:
        validate_catalog(catalog, sources)
    manifest_path = data_dir / "corpus.json"
    if manifest_path.exists():
        manifest = load_corpus(data_dir)[0]
        stored = [record["source"] for record in manifest["documents"]]
        if stored != declarations or manifest.get("catalog") != catalog:
            raise CorpusError("已有语料与清单不同。请指定新的 data 目录保存新版本。")
        return {"status": "CORPUS_REUSED", "corpus_version": manifest["corpus_version"],
                "documents": len(sources), "network_requests": 0}

    contents = [(source, fetch(source)) for source in sources]
    from .source_views import source_text
    for source, raw in contents:
        source_text(source, raw)
    if catalog is not None:
        for source, raw in contents:
            expected = catalog["chapters"][source.source_id]
            blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            if blob != expected["git_blob"] or len(raw) != expected["bytes"]:
                raise CorpusError("原文与目录声明的 Git blob 不一致。")
    records = [{"source": asdict(source), "sha256": digest(raw),
                "bytes": len(raw), "file": f"{source.source_id}.md"}
               for source, raw in contents]
    body = {"schema_version": SCHEMA_VERSION, "documents": records}
    if catalog is not None:
        body.update(schema_version=catalog.get("version",2), catalog=catalog)
    manifest = {**body, "corpus_version": digest(json_text(body).encode())}
    data_dir.mkdir(parents=True, exist_ok=True)
    # 未完成的旧下载也不静默覆盖，需使用新的独立目录。
    if any((data_dir / record["file"]).exists() for record in records):
        raise CorpusError("目录中已有未发布的原文，请指定新的 data 目录。")
    for (source, raw), record in zip(contents, records):
        with (data_dir / record["file"]).open("xb") as stream:
            stream.write(raw)
    with manifest_path.open("x", encoding="utf-8") as stream:
        stream.write(json_text(manifest))
    return {"status": "CORPUS_IMPORTED", "corpus_version": manifest["corpus_version"],
            "documents": len(sources), "network_requests": len(sources)}


@lru_cache(maxsize=8192)
def _raw_source_path(data_dir, filename):
    # Cache path parsing only. The file is opened and fully read every time.
    return data_dir / filename


@lru_cache(maxsize=4)
def _checked_manifest(raw_manifest):
    manifest = json.loads(raw_manifest.decode('utf-8'))
    body = {"schema_version": manifest["schema_version"], "documents": manifest["documents"]}
    if manifest["schema_version"] >= 2:
        body["catalog"] = manifest.get("catalog")
    encoded_body=json_text(body)
    if (manifest["schema_version"] not in {1, 2, 3, 4} or not manifest["documents"]
            or digest(encoded_body.encode()) != manifest["corpus_version"]):
        raise CorpusError("语料清单损坏或版本不匹配。")
    declarations=[]
    for record in manifest["documents"]:
        source = _source_record(record["source"])
        if record["file"] != f"{source.source_id}.md":
            raise CorpusError("来源文件名不匹配。")
        declarations.append((source,record))
    if len({s.source_id for s,_ in declarations})!=len(declarations):raise CorpusError('语料来源重复。')
    if manifest['schema_version']>=2:
        validate_catalog(manifest['catalog'],[s for s,_ in declarations])
    return manifest,tuple(declarations)


def load_corpus(data_dir: Path) -> tuple[dict, list[tuple[Source, bytes]]]:
    # The manifest, every raw source and the index are reread on every request.
    # Only deterministic parsing/proof of exactly equal bytes is cached.
    manifest, declarations = _checked_manifest((data_dir/'corpus.json').read_bytes())
    def read(record_pair):
        source,record=record_pair
        raw = _raw_source_path(data_dir,record['file']).read_bytes()
        if digest(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise CorpusError("原文变更或损坏，拒绝复用旧索引。")
        from .source_views import source_text
        source_text(source, raw)
        if manifest['schema_version']>=2:
            expected = manifest["catalog"]["chapters"][source.source_id]
            if (len(raw) != expected["bytes"]
                    or hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected["git_blob"]):
                raise CorpusError("原文与固定 Git blob 不符。")
        return source,raw
    if len(declarations)>32:
        # Eight long-lived workers, eight work items. Thousands of per-file
        # Futures added scheduling/GC spikes while all bytes still had to be read.
        batches=[declarations[i::8] for i in range(8)]
        def read_batch(batch):return [read(pair) for pair in batch]
        by_id={s.source_id:(s,raw) for batch in _SOURCE_IO.map(read_batch,batches) for s,raw in batch}
        contents=[by_id[s.source_id] for s,_ in declarations]
    else:contents=list(map(read,declarations))
    return deepcopy(manifest),contents


@lru_cache(maxsize=2)
def _checked_catalog(encoded_body):
    body=json.loads(encoded_body)
    validate_catalog(body['catalog'],[_source_record(row['source']) for row in body['documents']])
    return True


def index_contract(manifest: dict) -> dict:
    from .source_views import VERSION as view_version
    return {"schema_version": manifest["schema_version"], "corpus_version": manifest["corpus_version"],
            "chunker": view_version if manifest["schema_version"] == 4 else "heading-mdx-python-ast-v3.1" if manifest["schema_version"] == 3 else "heading-char-mdx-v2" if manifest["schema_version"] == 2 else "heading-char-v1", "max_chars": CHUNK_CHARS,
            "overlap": OVERLAP_CHARS, "retriever": "cjk-bigram-bm25-v1"}


@lru_cache(maxsize=2)
def _compiled_chunks(contents: tuple, version: int, max_chars: int, overlap: int) -> tuple:
    if version == 4:
        from .source_views import view_chunks
        return tuple(chunk for source, raw in contents for chunk in view_chunks(source,raw))
    chunks = [chunk for source, raw in contents for chunk in split_document(source, raw, max_chars=max_chars, overlap=overlap)]
    if version >= 3:
        from .code_index import markdown_code_chunks
        chunks.extend(chunk for source, raw in contents if not source.path.endswith(".py")
                      for chunk in markdown_code_chunks(source, raw))
    return tuple(chunks)


def all_chunks(contents: list[tuple[Source, bytes]], *, version: int = 2) -> list[Chunk]:
    # Cache deterministic parsing of exact verified bytes, never file/DB validity.
    # Sources and chunks are frozen; callers receive a fresh list.
    return list(_compiled_chunks(tuple(contents), version, CHUNK_CHARS, OVERLAP_CHARS))


@lru_cache(maxsize=2)
def _canonical_index_rows(contents, version):
    return tuple(json_text(asdict(chunk)) for chunk in _compiled_chunks(contents,version,CHUNK_CHARS,OVERLAP_CHARS))


@lru_cache(maxsize=2)
def _checked_index_bytes(contract, expected_rows, raw_index):
    """Reuse a semantic check only for exactly equal, fully reread database bytes."""
    try:
        with closing(sqlite3.connect(':memory:')) as database:
            database.deserialize(raw_index)
            database.execute('PRAGMA query_only=ON')
            database.execute('PRAGMA trusted_schema=OFF')
            row=database.execute("SELECT value FROM metadata WHERE key='contract'").fetchone()
            stored=tuple(row[0] for row in database.execute('SELECT payload FROM chunks ORDER BY position'))
        if row is None or json.loads(row[0])!=json.loads(contract) or stored!=expected_rows:
            raise CorpusError('索引契约或片段与已核对原文不同。')
    except (sqlite3.Error,ValueError) as error:
        if isinstance(error,CorpusError):raise
        raise CorpusError('索引数据库无法完整核对。') from None
    return True


def open_index(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CorpusError("索引不存在，请先导入教材。")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def verified_chunks(data_dir: Path, index_path: Path) -> tuple[dict, list[Chunk], dict[str, Source]]:
    manifest, chunks, sources, _ = verified_corpus(data_dir, index_path)
    return manifest, chunks, sources


def verified_corpus(data_dir: Path, index_path: Path) -> tuple[dict, list[Chunk], dict[str, Source], list]:
    """一次校验同时提供原文字节，调用者无需重新读取与哈希核对。"""
    manifest, contents = load_corpus(data_dir)
    expected = all_chunks(contents, version=manifest["schema_version"])
    if manifest['schema_version']==4:
        if not index_path.is_file():raise CorpusError('索引不存在，请先导入教材。')
        _checked_index_bytes(json_text(index_contract(manifest)),_canonical_index_rows(tuple(contents),4),index_path.read_bytes())
        return manifest,expected,{source.source_id:source for source,_ in contents},contents
    with closing(open_index(index_path)) as database:
        row = database.execute("SELECT value FROM metadata WHERE key='contract'").fetchone()
        stored = database.execute("SELECT payload FROM chunks ORDER BY position").fetchall()
    if row is None or json.loads(row[0]) != index_contract(manifest):
        raise CorpusError("索引契约不同，拒绝使用旧索引。")
    consistent = (tuple(row[0] for row in stored) == _canonical_index_rows(tuple(contents),manifest['schema_version'])
                  if manifest['schema_version'] == 4 else [json.loads(row[0]) for row in stored] == [asdict(chunk) for chunk in expected])
    if not consistent:
        raise CorpusError("索引片段与原文不一致。")
    return manifest, expected, {source.source_id: source for source, _ in contents}, contents


def build_index(data_dir: Path, index_path: Path) -> dict:
    manifest, contents = load_corpus(data_dir)
    if index_path.exists():
        chunks = verified_chunks(data_dir, index_path)[1]
        return {"status": "INDEX_REUSED", "chunks": len(chunks),
                "corpus_version": manifest["corpus_version"]}
    chunks = all_chunks(contents, version=manifest["schema_version"])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(index_path)) as database, database:
        database.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute("CREATE TABLE chunks (position INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        database.execute("INSERT INTO metadata VALUES ('contract', ?)",
                         (json_text(index_contract(manifest)),))
        database.executemany("INSERT INTO chunks VALUES (?, ?)",
                             [(i, json_text(asdict(chunk))) for i, chunk in enumerate(chunks)])
    return {"status": "INDEX_BUILT", "chunks": len(chunks),
            "corpus_version": manifest["corpus_version"]}


def tokenize(text: str) -> Counter:
    """英文单词与中文相邻双字；单字用于召回，降低其排名权重。"""
    terms = []
    for match in re.finditer(r"[a-z0-9_]+|[\u3400-\u9fff]+", text.casefold()):
        word = match[0]
        if re.fullmatch(r"[a-z0-9_]+", word):
            terms.append(word)
        else:
            terms.extend(word)
            terms.extend(word[i:i + 2] for i in range(len(word) - 1))
    return Counter(terms)


TERM_ALIASES = (
    ("rag", "检索增强"), ("memory", "memories", "记忆"),
    ("embedding", "embeddings", "嵌入"), ("chunk", "chunks", "切分"),
    ("tool", "tools", "工具"), ("planning", "plan", "计划", "规划"),
    ("context", "上下文"), ("observability", "可观测性"),
    ("hybrid", "混合检索"), ("reranking", "rerank", "重排"),
    ("corrective", "检索纠错", "纠错检索"), ("graph", "知识图谱"),
    ("diagnostics", "故障诊断"), ("browser", "浏览器"),
    ("research", "研究"), ("travel", "旅行规划"),
    ("install", "安装", "setup", "getting started", "启动", "dependencies", "依赖"),
)


def query_terms(question: str) -> tuple[set[str], set[str]]:
    terms, aspects = set(tokenize(question)), set()
    for group in TERM_ALIASES:
        if any(word in terms if word.isascii() else word in question for word in group):
            terms.update(term for word in group for term in tokenize(word))
            aspects.add(group[0])
    return terms, aspects


def search(data_dir: Path, index_path: Path, question: str, *, top_k: int = 5,
           book: str | None = None) -> dict:
    if not question.strip() or len(question) > MAX_QUESTION_CHARS or not 1 <= top_k <= 20:
        raise CorpusError(f"问题不能为空、须不超过 {MAX_QUESTION_CHARS} 字；top_k 范围是 1～20。")
    query = query_terms(question)[0]
    if not query:
        raise CorpusError("问题没有可检索文字。")
    manifest, chunks, sources, contents = verified_corpus(data_dir, index_path)
    catalog = corpus_catalog(manifest)
    display_names = {b["book"]: b["display_name"] for b in catalog["books"]}
    if book is not None:
        if book not in {source.book for source in sources.values()}:
            raise CorpusError("教材筛选值不存在。")
        chunks = [chunk for chunk in chunks if sources[chunk.source_id].book == book]
    masks = {s.source_id: mdx_mask(validate_text(raw)) for s, raw in contents if s.path.endswith(".mdx")}
    raw_sources={s.source_id:raw for s,raw in contents}
    vectors = [tokenize(sources[chunk.source_id].chapter + "\n" + chunk.section + "\n" + (masks[chunk.source_id][chunk.start_char:chunk.end_char]
                        if chunk.source_id in masks else chunk.text)) for chunk in chunks]
    average = sum(sum(vector.values()) for vector in vectors) / max(1, len(vectors))
    frequencies = Counter(term for vector in vectors for term in vector)
    ranked = []
    for chunk, vector in zip(chunks, vectors):
        length = sum(vector.values())
        score = 0.0
        for term in query:
            count = vector[term]
            if count:
                inverse = math.log(1 + (len(chunks) - frequencies[term] + 0.5)
                                   / (frequencies[term] + 0.5))
                weight = 0.15 if len(term) == 1 and not term.isascii() else 1.0
                score += weight * inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            source = sources[chunk.source_id]
            from .source_views import locator
            location=locator(source,raw_sources[source.source_id],chunk.start_char,chunk.end_char)
            ranked.append({**asdict(chunk), "book": source.book, "chapter": source.chapter,
                           "language": catalog["chapters"][source.source_id]["language"], "display_name": display_names[source.book],
                           "commit": source.commit, "source_url": source.source_url,
                           "line_url": source.source_url if location else f"{source.source_url}#L{chunk.start_line}-L{chunk.end_line}",
                           **({'source_locator':location} if location else {}),
                           "score": round(score, 6)})
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    return {"status": "CANDIDATES_FOUND" if ranked else "NO_KEYWORD_MATCH",
            "question": question, "book_filter": book, "corpus_version": manifest["corpus_version"],
            "source_verified": True, "model_calls": 0, "network_requests": 0,
            "support_verified": False, "candidates": ranked[:top_k]}


def read_evidence(data_dir: Path, index_path: Path, chunk_id: str) -> dict:
    manifest, chunks, sources, contents = verified_corpus(data_dir, index_path)
    chunk = next((item for item in chunks if item.chunk_id == chunk_id), None)
    if chunk is None:
        raise CorpusError("引用片段 ID 不存在于当前索引。")
    source = sources[chunk.source_id]
    from .source_views import locator
    location=locator(source,next(raw for s,raw in contents if s.source_id==source.source_id),chunk.start_char,chunk.end_char)
    catalog = corpus_catalog(manifest)
    return {**asdict(chunk), "book": source.book, "chapter": source.chapter,
            "language": catalog["chapters"][source.source_id]["language"],
            "display_name": next(b["display_name"] for b in catalog["books"] if b["book"] == source.book),
            "corpus_version": manifest["corpus_version"], "source_url": source.source_url,
            "line_url": source.source_url if location else f"{source.source_url}#L{chunk.start_line}-L{chunk.end_line}",
            **({'source_locator':location} if location else {}),
            "source_verified": True, "support_verified": False}
