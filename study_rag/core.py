"""固定来源导入、保留位置的切分和持久关键词检索；不调用模型。"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Callable
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 2_000_000
CHUNK_CHARS = 1400
OVERLAP_CHARS = 160


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
                or "\\" in self.path or path.suffix.lower() not in {".md", ".txt"}
                or any(ord(char) < 32 for char in self.path)):
            raise CorpusError("来源必须是仓库内 Markdown/TXT 文件。")
        if not self.book.strip() or not self.chapter.strip():
            raise CorpusError("教材名和章节不能为空。")

    @property
    def raw_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repository}/{self.commit}/{quote(self.path)}"

    @property
    def source_url(self) -> str:
        return f"https://github.com/{self.repository}/blob/{self.commit}/{quote(self.path)}"


def read_sources(path: Path) -> list[Source]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("version") != 1 or not payload.get("sources"):
        raise CorpusError("来源清单版本不支持或清单为空。")
    sources = [Source(**record) for record in payload["sources"]]
    if len({source.source_id for source in sources}) != len(sources):
        raise CorpusError("来源 ID 重复。")
    return sources


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
    boundaries = [(0, "正文")]
    stack: list[tuple[int, str]] = []
    offset = 0
    fence_char, fence_length = "", 0
    for line in text.splitlines(keepends=True):
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
                   fetch: Callable[[Source], bytes] = fetch_source) -> dict:
    """下载阶段失败不会发布半套语料；同清单的完整快照无网络复用。"""
    if not sources or len({source.source_id for source in sources}) != len(sources):
        raise CorpusError("来源不能为空或重复。")
    declarations = [asdict(source) for source in sources]
    manifest_path = data_dir / "corpus.json"
    if manifest_path.exists():
        manifest = load_corpus(data_dir)[0]
        stored = [record["source"] for record in manifest["documents"]]
        if stored != declarations:
            raise CorpusError("已有语料与清单不同。请指定新的 data 目录保存新版本。")
        return {"status": "CORPUS_REUSED", "corpus_version": manifest["corpus_version"],
                "documents": len(sources), "network_requests": 0}

    contents = [(source, fetch(source)) for source in sources]
    for _, raw in contents:
        validate_text(raw)
    records = [{"source": asdict(source), "sha256": digest(raw),
                "bytes": len(raw), "file": f"{source.source_id}.md"}
               for source, raw in contents]
    body = {"schema_version": SCHEMA_VERSION, "documents": records}
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


def load_corpus(data_dir: Path) -> tuple[dict, list[tuple[Source, bytes]]]:
    manifest = json.loads((data_dir / "corpus.json").read_text(encoding="utf-8"))
    body = {"schema_version": manifest["schema_version"], "documents": manifest["documents"]}
    if (manifest["schema_version"] != SCHEMA_VERSION or not manifest["documents"]
            or digest(json_text(body).encode()) != manifest["corpus_version"]):
        raise CorpusError("语料清单损坏或版本不匹配。")
    contents = []
    for record in manifest["documents"]:
        source = Source(**record["source"])
        if record["file"] != f"{source.source_id}.md":
            raise CorpusError("来源文件名不匹配。")
        raw = (data_dir / record["file"]).read_bytes()
        if digest(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise CorpusError("原文变更或损坏，拒绝复用旧索引。")
        validate_text(raw)
        contents.append((source, raw))
    if len({source.source_id for source, _ in contents}) != len(contents):
        raise CorpusError("语料来源重复。")
    return manifest, contents


def index_contract(manifest: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "corpus_version": manifest["corpus_version"],
            "chunker": "heading-char-v1", "max_chars": CHUNK_CHARS,
            "overlap": OVERLAP_CHARS, "retriever": "cjk-bigram-bm25-v1"}


def all_chunks(contents: list[tuple[Source, bytes]]) -> list[Chunk]:
    return [chunk for source, raw in contents for chunk in split_document(source, raw)]


def open_index(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CorpusError("索引不存在，请先导入教材。")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def verified_chunks(data_dir: Path, index_path: Path) -> tuple[dict, list[Chunk], dict[str, Source]]:
    manifest, contents = load_corpus(data_dir)
    expected = all_chunks(contents)
    with closing(open_index(index_path)) as database:
        row = database.execute("SELECT value FROM metadata WHERE key='contract'").fetchone()
        stored = database.execute("SELECT payload FROM chunks ORDER BY position").fetchall()
    if row is None or json.loads(row[0]) != index_contract(manifest):
        raise CorpusError("索引契约不同，拒绝使用旧索引。")
    if [json.loads(row[0]) for row in stored] != [asdict(chunk) for chunk in expected]:
        raise CorpusError("索引片段与原文不一致。")
    return manifest, expected, {source.source_id: source for source, _ in contents}


def build_index(data_dir: Path, index_path: Path) -> dict:
    manifest, contents = load_corpus(data_dir)
    if index_path.exists():
        chunks = verified_chunks(data_dir, index_path)[1]
        return {"status": "INDEX_REUSED", "chunks": len(chunks),
                "corpus_version": manifest["corpus_version"]}
    chunks = all_chunks(contents)
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


def search(data_dir: Path, index_path: Path, question: str, *, top_k: int = 5,
           book: str | None = None) -> dict:
    if not question.strip() or len(question) > 500 or not 1 <= top_k <= 20:
        raise CorpusError("问题不能为空、须不超过 500 字；top_k 范围是 1～20。")
    query = tokenize(question)
    if not query:
        raise CorpusError("问题没有可检索文字。")
    manifest, chunks, sources = verified_chunks(data_dir, index_path)
    if book is not None:
        if book not in {source.book for source in sources.values()}:
            raise CorpusError("教材筛选值不存在。")
        chunks = [chunk for chunk in chunks if sources[chunk.source_id].book == book]
    vectors = [tokenize(chunk.section + "\n" + chunk.text) for chunk in chunks]
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
            ranked.append({**asdict(chunk), "book": source.book, "chapter": source.chapter,
                           "commit": source.commit, "source_url": source.source_url,
                           "line_url": f"{source.source_url}#L{chunk.start_line}-L{chunk.end_line}",
                           "score": round(score, 6)})
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    return {"status": "CANDIDATES_FOUND" if ranked else "NO_KEYWORD_MATCH",
            "question": question, "book_filter": book, "corpus_version": manifest["corpus_version"],
            "source_verified": True, "model_calls": 0, "network_requests": 0,
            "support_verified": False, "candidates": ranked[:top_k]}


def read_evidence(data_dir: Path, index_path: Path, chunk_id: str) -> dict:
    manifest, chunks, sources = verified_chunks(data_dir, index_path)
    chunk = next((item for item in chunks if item.chunk_id == chunk_id), None)
    if chunk is None:
        raise CorpusError("引用片段 ID 不存在于当前索引。")
    source = sources[chunk.source_id]
    return {**asdict(chunk), "book": source.book, "chapter": source.chapter,
            "corpus_version": manifest["corpus_version"], "source_url": source.source_url,
            "line_url": f"{source.source_url}#L{chunk.start_line}-L{chunk.end_line}",
            "source_verified": True, "support_verified": False}
