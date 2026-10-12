"""Local retrieval strategies, source-preserving E5 windows and budget-free replay."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from typing import Protocol

from .core import corpus_catalog, index_contract
from .rag import (RETRIEVER_VERSION, expand_evidence, retrieve, requested_roles,
                  section_role, visible_prose)

E5_MODEL = "intfloat/multilingual-e5-small"
E5_REVISION = "5697a65b0a002a92fe8c4fc9d495303ffff9c7d2"
VECTOR_VERSION = "e5-window-480-overlap48-v1"


class RagAdapter(Protocol):
    def retrieve(self, question, config) -> dict: ...


class LocalRagAdapter:
    def __init__(self, data_dir, loaded, cache_dir, *, download=False):
        self.data_dir, self.loaded, self.cache_dir = data_dir, loaded, cache_dir
        self.download = download
        self.model = None
        self.matrix = self.windows = None
        self.manifest, self.chunks, self.sources, self.texts, self.masks = loaded[2:]
        self.by_chunk = {c.chunk_id: c for c in self.chunks}
        self.neighbors = defaultdict(list)
        for c in self.chunks:
            self.neighbors[(c.source_id, c.section)].append(c)

    def _model(self):
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ValueError("向量依赖未安装；执行 pip install -r requirements-vector.txt") from None
            self.model = SentenceTransformer(E5_MODEL, revision=E5_REVISION, device="cpu",
                cache_folder=str(self.cache_dir / "models"), local_files_only=not self.download,
                trust_remote_code=False)
        return self.model

    def vector_index(self):
        import numpy as np
        contract = {"corpus": self.manifest["corpus_version"], "index": index_contract(self.manifest),
                    "model": E5_MODEL, "revision": E5_REVISION, "version": VECTOR_VERSION,
                    "masked_text_sha256":hashlib.sha256(json.dumps(self.masks,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
        key = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        from filelock import FileLock
        with FileLock(str(self.cache_dir / f"{key}.lock"), timeout=600):
            return self._vector_index_locked(contract, key, np)

    def _vector_index_locked(self, contract, key, np):
        metadata = self.cache_dir / f"{key}.json"
        matrix_file = self.cache_dir / f"{key}.npy"
        if metadata.exists() and matrix_file.exists():
            meta = json.loads(metadata.read_text(encoding="utf-8"))
            if meta["contract"] != contract or hashlib.sha256(matrix_file.read_bytes()).hexdigest() != meta["sha256"]:
                raise ValueError("向量缓存契约或哈希不一致；请重新构建")
            self.windows = meta["windows"]
            self.matrix = np.load(matrix_file, allow_pickle=False)
            if self.matrix.ndim != 2 or self.matrix.shape != (len(self.windows), 384) or not np.isfinite(self.matrix).all():
                raise ValueError("向量缓存形状或数值无效")
            for w in self.windows:
                c = self.by_chunk.get(w["chunk_id"])
                if c is None or not c.start_char <= w["start_char"] < w["end_char"] <= c.end_char:
                    raise ValueError("向量窗口位置无效")
            return {"cache_hit": True, "windows": len(self.windows), "contract": contract}
        model = self._model()
        windows, inputs = [], []
        for chunk in self.chunks:
            body = self.masks[chunk.source_id][chunk.start_char:chunk.end_char]
            offsets = model.tokenizer(body, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
            for token_start in range(0, len(offsets), 432):
                part = offsets[token_start:token_start + 480]
                if not part:
                    continue
                start, end = part[0][0], part[-1][1]
                if start >= end or not body[start:end].strip():
                    continue
                windows.append({"chunk_id": chunk.chunk_id, "start_char": chunk.start_char + start,
                                "end_char": chunk.start_char + end})
                inputs.append("passage: " + body[start:end])
                if token_start + 480 >= len(offsets):
                    break
        if not windows:
            raise ValueError("没有可编码的正文窗口")
        matrix = model.encode(inputs, batch_size=16, normalize_embeddings=True,
                              show_progress_bar=True, convert_to_numpy=True).astype("float32")
        if matrix.shape != (len(windows), 384) or not np.isfinite(matrix).all():
            raise ValueError("Embedding 输出无效")
        temporary = matrix_file.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.save(stream, matrix, allow_pickle=False)
        temporary.replace(matrix_file)
        meta = {"contract": contract, "windows": windows,
                "sha256": hashlib.sha256(matrix_file.read_bytes()).hexdigest()}
        temporary_meta = metadata.with_suffix(".tmp")
        temporary_meta.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        temporary_meta.replace(metadata)
        self.matrix, self.windows = matrix, windows
        return {"cache_hit": False, "windows": len(windows), "contract": contract}

    def retrieve(self, question, config):
        started = time.perf_counter()
        lexical = retrieve(self.data_dir, self.data_dir / "index.sqlite3", question.question,
                           question.book, trace=True, expand=config.expand,
                           body_only=config.body_only, intent_filter=config.intent_filter)
        if config.strategy == "bm25":
            lexical["elapsed_seconds"] = time.perf_counter() - started
            return lexical
        if self.matrix is None:
            self.vector_index()
        import numpy as np
        model = self._model()
        # E5's window limit also applies to long queries; record the bounded query.
        query_tokens = model.tokenizer(question.question, add_special_tokens=False)["input_ids"]
        query = model.tokenizer.decode(query_tokens[:480], skip_special_tokens=True)
        vector = model.encode(["query: " + query], normalize_embeddings=True, convert_to_numpy=True)[0]
        scores = self.matrix @ vector
        best = {}
        for w, score in zip(self.windows, scores):
            if w["chunk_id"] not in best or score > best[w["chunk_id"]][0]:
                best[w["chunk_id"]] = (float(score), w)
        catalog = corpus_catalog(self.manifest)
        names = {b["book"]: b["display_name"] for b in catalog["books"]}
        books = [b["book"] for b in sorted(catalog["books"], key=lambda b: (b["order"], b["book"]))
                 if question.book is None or b["book"] == question.book]
        selected_by_book, traces = [], []
        for book in books:
            # Use BM25's actual eligible set, independently of keyword hits.
            roles = requested_roles(question.question)
            eligible = []
            import re
            for c in self.chunks:
                if self.sources[c.source_id].book != book or c.chunk_id not in best:
                    continue
                if config.intent_filter and section_role(c.section) not in roles:
                    continue
                if re.search(r"(?:^| / )(?:习题|练习|参考文献|额外资源|附加资源|参考资源|Additional Resources)(?:\s|$)", c.section, re.I):
                    continue
                body = self.masks[c.source_id][c.start_char:c.end_char]
                prose = re.sub(r"(?m)^ {0,3}#{1,6}\s+.*$", "", body)
                if re.search(r"[A-Za-z0-9\u3400-\u9fff]", prose):
                    eligible.append(c.chunk_id)
            ranked = sorted(eligible, key=lambda cid: (-best[cid][0], cid))
            dense_ranks = {cid: i + 1 for i, cid in enumerate(ranked)}
            sparse = next(b["candidates"] for b in lexical["trace"]["books"] if b["book"] == book)
            sparse_ranks = {c["chunk_id"]: i + 1 for i, c in enumerate(sparse)}
            if config.strategy == "hybrid":
                # Fuse a bounded 20-candidate pool from each method, with rank scores.
                pool = set(ranked[:20]) | set(sparse_ranks)
                fused = {cid: (1 / (60 + dense_ranks[cid]) if cid in ranked[:20] else 0) +
                              (1 / (60 + sparse_ranks[cid]) if cid in sparse_ranks else 0) for cid in pool}
                ranked = sorted(pool, key=lambda cid: (-fused[cid], cid))
            else:
                fused = {cid: best[cid][0] for cid in ranked}
            candidates, chosen = [], []
            for cid in ranked[:20]:
                c = self.by_chunk[cid]
                source = self.sources[c.source_id]
                item = (expand_evidence(c, self.neighbors[(c.source_id, c.section)], self.texts[c.source_id], self.masks[c.source_id])
                        if config.expand else {**asdict(c), "anchor_chunk_id": cid,
                            "context_text": visible_prose(c.text, self.masks[c.source_id][c.start_char:c.end_char])})
                item.update(book=book, display_name=names[book], chapter=source.chapter,
                    language=catalog["chapters"][source.source_id]["language"], score=fused[cid],
                    source_url=source.source_url,
                    line_url=f"{source.source_url}#L{item['start_line']}-L{item['end_line']}")
                candidates.append({"chunk_id": cid, "source_id": c.source_id, "section": c.section,
                    "score": fused[cid], "vector_score": best[cid][0], "embedding_window": best[cid][1],
                    "bm25_rank": sparse_ranks.get(cid), "vector_rank": dense_ranks[cid], "line_url": item["line_url"]})
                if any(c.source_id == p["source_id"] and
                       max(0, min(item["end_char"], p["end_char"]) - max(item["start_char"], p["start_char"])) /
                       min(item["end_char"] - item["start_char"], p["end_char"] - p["start_char"]) > .6 for p in chosen):
                    continue
                if len(chosen) < 2:
                    chosen.append(item)
            selected_by_book.append(chosen)
            traces.append({"book": book, "eligible_chunks": len(eligible), "candidates": candidates})
        evidence = [items[i] for i in range(2) for items in selected_by_book if i < len(items)][:8]
        for i, e in enumerate(evidence, 1):
            e["evidence_id"] = f"E{i}"
        return {**lexical, "evidence": evidence, "retriever": VECTOR_VERSION + ":" + config.strategy,
                "trace": {"strategy": config.strategy, "books": traces,
                          "query_tokens": len(query_tokens), "query_truncated": len(query_tokens) > 480,
                          "context_characters": sum(len(e["context_text"]) for e in evidence)},
                "elapsed_seconds": time.perf_counter() - started,
                "books_without_match": [book for book, selected in zip(books, selected_by_book) if not selected]}
