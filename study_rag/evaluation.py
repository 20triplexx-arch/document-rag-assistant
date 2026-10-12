"""固定原文位置的离线检索评测；不生成答案，不访问账号库。"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .core import index_contract, load_corpus, validate_text, verified_chunks
from .mdx import mdx_mask
from .rag import RETRIEVER_VERSION, normalize_quote, prose_mask, retrieve, visible_prose

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "evals" / "agent-learning-v1.json"
EVALUATOR_VERSION = "source-span-context-v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Span(Contract):
    source_id: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class Point(Contract):
    id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    supports: list[Span] = Field(min_length=1)


class ReviewScope(Contract):
    source_ids: list[str] = Field(min_length=1)
    checked_content: str = Field(min_length=1)
    absence_basis: str = Field(min_length=1)


class Question(Contract):
    id: str = Field(pattern=r"^[SCRG][0-9]{2}$")
    group: str = Field(min_length=1)
    split: Literal["dev", "holdout"]
    category: Literal["single", "cross", "paraphrase", "gap"]
    question: str = Field(min_length=1, max_length=500)
    book: str | None
    required_books: list[str] = Field(min_length=1)
    answerability: Literal["answerable", "partial", "insufficient"]
    points: list[Point]
    distractors: list[Span]
    missing_information: list[str]
    review_scope: ReviewScope | None


class Dataset(Contract):
    schema_version: Literal[1]
    dataset_version: str = Field(pattern=r"^agent-learning-v[1-9][0-9]*(?:\.[0-9]+)?$")
    annotated_on: str
    annotation_method: str
    corpus_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    documents: int = Field(gt=0)
    baseline_chunks: int = Field(gt=0)
    questions: list[Question]


class EvaluationQuestion(Question):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    split: Literal["dev", "calibration", "holdout"]
    question: str = Field(min_length=1, max_length=10000)
    review_status: Literal["pending", "approved"] = "pending"
    review_note: str = Field(default="", max_length=2000)


class EvaluationDataset(Contract):
    schema_version: Literal[2]
    dataset_version: str = Field(min_length=1, max_length=100)
    annotated_on: str
    annotation_method: str
    corpus_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    documents: int = Field(gt=0)
    baseline_chunks: int = Field(gt=0)
    questions: list[EvaluationQuestion] = Field(min_length=1, max_length=10000)


def _visible_quote(span: Span, texts: dict[str, str], masks: dict[str, str]) -> str:
    return normalize_quote(visible_prose(
        texts[span.source_id][span.start_char:span.end_char],
        masks[span.source_id][span.start_char:span.end_char]))


def validate_dataset(dataset: Dataset, manifest: dict, texts: dict[str, str],
                     sources: dict, masks: dict[str, str]) -> None:
    """静态原文校验不执行 retrieve；原始语料版本必须一致。"""
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    require(dataset.corpus_version == manifest["corpus_version"], "题集与语料版本不匹配")
    require(dataset.documents == len(sources), "题集与原文篇数不匹配")
    questions = dataset.questions
    legacy = dataset.schema_version == 1
    require(not legacy or len(questions) == 40, "题集须包含 40 题")
    require(not legacy or Counter(q.category for q in questions) ==
            {"single": 20, "cross": 8, "paraphrase": 6, "gap": 6}, "题型数量不匹配")
    require(not legacy or Counter(q.split for q in questions) == {"dev": 30, "holdout": 10}, "题集须按 30/10 划分")
    expected_ids = {f"{prefix}{i:02}" for prefix, a, b in
                    [("S", 1, 20), ("C", 21, 28), ("R", 29, 34), ("G", 35, 40)]
                    for i in range(a, b + 1)}
    require(len({q.id for q in questions}) == len(questions), "题号重复")
    require(not legacy or {q.id for q in questions} == expected_ids, "题号缺失、重复或与题型不匹配")
    require(len({q.question for q in questions}) == len(questions), "题面重复")
    books = {s.book for s in sources.values()}
    require(not legacy or len(books) == 5, "v1 题集固定覆盖五个集合")
    require(not legacy or Counter(q.book for q in questions if q.category == "single") ==
            {book: 4 for book in books}, "每个集合须有四道单集合题")
    holdout_books = {b for q in questions if q.split == "holdout" for b in q.required_books}
    require(not legacy or holdout_books == books, "保留题未覆盖五个集合")
    groups = defaultdict(set)
    for q in questions:
        groups[q.group].add(q.split)
        require(q.question.strip() == q.question and bool(q.question.strip()), f"{q.id}: 空问题")
        require(not legacy or q.id[0] == {"single": "S", "cross": "C", "paraphrase": "R", "gap": "G"}[q.category],
                f"{q.id}: 题号和题型不符")
        require(len(q.required_books) == len(set(q.required_books)) and
                set(q.required_books) <= books, f"{q.id}: 必要集合无效")
        require(q.book is None or q.book in books, f"{q.id}: 检索范围无效")
        require(q.book is None or set(q.required_books) == {q.book}, f"{q.id}: 范围与必要来源不符")
        require(q.category != "single" or q.book is not None, f"{q.id}: 单集合题未指定范围")
        require(q.category != "cross" or (q.book is None and len(q.required_books) >= 2),
                f"{q.id}: 跨集合题缺少必要集合")
        require((q.category == "gap") == (q.answerability != "answerable"), f"{q.id}: 可回答程度不符")
        require(bool(q.points) == (q.answerability != "insufficient"), f"{q.id}: 答案要点缺失或多余")
        require(len({p.id for p in q.points}) == len(q.points), f"{q.id}: 重复要点编号")
        require(bool(q.missing_information) == (q.category == "gap"), f"{q.id}: 缺失信息不符")
        require((q.review_scope is not None) == (q.category == "gap"), f"{q.id}: 缺少资料检查范围")
        if q.review_scope:
            scope = q.review_scope.source_ids
            require(len(scope) == len(set(scope)) and set(scope) <= sources.keys(), f"{q.id}: 检查来源无效")
            require(q.book is None or all(sources[s].book == q.book for s in scope), f"{q.id}: 检查范围越界")
        supported_books = set()
        for is_support, spans in [(True, [s for p in q.points for s in p.supports]),
                                  (False, q.distractors)]:
            for s in spans:
                require(s.source_id in texts, f"{q.id}: 标注来源不存在 {s.source_id}")
                text = texts[s.source_id]
                require(0 <= s.start_char < s.end_char <= len(text), f"{q.id}: 字符范围越界")
                require(text[s.start_char:s.end_char] == s.quote, f"{q.id}: 摘录不逐字匹配")
                require(s.start_line == text.count("\n", 0, s.start_char) + 1 and
                        s.end_line == text.count("\n", 0, s.end_char - 1) + 1, f"{q.id}: 行号不匹配")
                book = sources[s.source_id].book
                require(q.book is None or book == q.book, f"{q.id}: 标注超出检索范围")
                if is_support:
                    visible = _visible_quote(s, texts, masks)
                    require(bool(visible) and visible == normalize_quote(s.quote),
                            f"{q.id}: 支持标注包含被遮罩的内容")
                    supported_books.add(book)
        if q.answerability != "insufficient":
            require(set(q.required_books) <= supported_books, f"{q.id}: 必要集合缺少支持要点")
    require(all(len(splits) == 1 for splits in groups.values()), "同一学习目标跨越开发/保留划分")


def load_dataset(dataset_path: Path, data_dir: Path):
    raw = dataset_path.read_bytes()
    model = Dataset if json.loads(raw)["schema_version"] == 1 else EvaluationDataset
    dataset = model.model_validate_json(raw)
    manifest, chunks, sources = verified_chunks(data_dir, data_dir / "index.sqlite3")
    _, originals = load_corpus(data_dir)
    texts = {s.source_id: validate_text(raw) for s, raw in originals}
    masks = {s.source_id: prose_mask(mdx_mask(texts[s.source_id]) if s.path.endswith(".mdx")
                                    else texts[s.source_id]) for s, _ in originals}
    validate_dataset(dataset, manifest, texts, sources, masks)
    return dataset, hashlib.sha256(raw).hexdigest(), manifest, chunks, sources, texts, masks


def score_question(question: Question, evidence: list[dict], texts: dict[str, str],
                   masks: dict[str, str]) -> dict:
    def matches(span: Span, item: dict) -> bool:
        visible = _visible_quote(span, texts, masks)
        return (item["source_id"] == span.source_id and item["start_char"] <= span.start_char and
                item["end_char"] >= span.end_char and bool(visible) and
                visible == normalize_quote(span.quote) and
                visible in normalize_quote(item.get("context_text", "")))

    covered, seen, ranks = set(), set(), []
    for rank, item in enumerate(evidence, 1):
        key = (item["source_id"], item["start_char"], item["end_char"])
        duplicate = key in seen
        seen.add(key)
        points = [p.id for p in question.points if any(matches(s, item) for s in p.supports)]
        negatives = [i for i, s in enumerate(question.distractors, 1) if matches(s, item)]
        if not duplicate:
            covered.update(points)
        judgment = ("support_and_distractor" if points and negatives else "support" if points else
                    "distractor" if negatives else "unjudged")
        ranks.append({**item, "rank": rank, "judgment": judgment, "duplicate": duplicate,
                      "supported_points": points, "distractor_annotations": negatives})
    return {"id": question.id, "group": question.group, "split": question.split,
            "category": question.category, "question": question.question, "book": question.book,
            "required_books": question.required_books, "answerability": question.answerability,
            "covered_points": sorted(covered), "expected_points": len(question.points),
            "point_coverage": len(covered) / len(question.points) if question.points else None,
            "complete": len(covered) == len(question.points) if question.answerability == "answerable" else None,
            "missing_information": question.missing_information,
            "review_scope": question.review_scope.model_dump() if question.review_scope else None,
            "points": [p.model_dump() for p in question.points],
            "distractors": [s.model_dump() for s in question.distractors], "evidence": ranks}


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if r["answerability"] == "answerable"]
    gaps = [r for r in results if r["answerability"] != "answerable"]
    evidence = [e for r in results for e in r["evidence"] if not e["duplicate"]]
    expected = sum(r["expected_points"] for r in answerable)
    covered = sum(len(r["covered_points"]) for r in answerable)
    negatives = sum(bool(e["distractor_annotations"]) for e in evidence)
    unjudged = sum(e["judgment"] == "unjudged" for e in evidence)
    return {"questions": len(results), "answerable_questions": len(answerable),
            "support_points": expected, "covered_support_points": covered,
            "support_point_coverage": covered / expected if expected else None,
            "complete_questions": sum(r["complete"] is True for r in answerable),
            "any_support_questions": sum(bool(r["covered_points"]) for r in answerable),
            "unique_evidence": len(evidence), "distractor_evidence": negatives,
            "distractor_evidence_ratio": negatives / len(evidence) if evidence else None,
            "unjudged_evidence": unjudged,
            "unjudged_evidence_ratio": unjudged / len(evidence) if evidence else None,
            "gap_questions": len(gaps),
            "gap_known_points": sum(r["expected_points"] for r in gaps),
            "gap_covered_known_points": sum(len(r["covered_points"]) for r in gaps),
            "gap_distractor_evidence": sum(bool(e["distractor_annotations"]) for r in gaps
                                            for e in r["evidence"] if not e["duplicate"])}


def evaluate(dataset_path: Path, data_dir: Path, *, split: str = "dev", check_only: bool = False) -> dict:
    dataset, digest, manifest, chunks, sources, texts, masks = load_dataset(dataset_path, data_dir)
    report = {"status": "EVAL_DATASET_VALID" if check_only else "EVALUATED",
              "dataset_version": dataset.dataset_version, "dataset_sha256": digest,
              "dataset_path": str(dataset_path.resolve()), "corpus_version": manifest["corpus_version"],
              "documents": len(sources), "chunks": len(chunks), "baseline_chunks": dataset.baseline_chunks,
              "index_contract": index_contract(manifest), "retriever": RETRIEVER_VERSION,
              "evaluator": EVALUATOR_VERSION, "checked_at": datetime.now(timezone.utc).isoformat(),
              "model_calls": 0, "network_requests": 0, "split": split,
              "checked_questions": len(dataset.questions), "splits": dict(Counter(q.split for q in dataset.questions))}
    if check_only:
        return report
    if dataset.schema_version == 2 and any(q.review_status != "approved" for q in dataset.questions
            if split == "all" or q.split == split):
        raise ValueError("通用题集含待人工复核标注；请在诊断工作台复核或显式运行草稿实验")
    if split not in {"dev", "holdout", "all"}:
        raise ValueError("未知题集划分")
    results = []
    for q in dataset.questions:
        if split != "all" and q.split != split:
            continue
        started = time.perf_counter()
        pack = retrieve(data_dir, data_dir / "index.sqlite3", q.question, q.book, per_book=2)
        if pack["corpus_version"] != dataset.corpus_version or pack["retriever"] != RETRIEVER_VERSION:
            raise ValueError("运行期间语料或检索器版本发生变化")
        if len(pack["evidence"]) > 8 or any(n > 2 for n in Counter(e["book"] for e in pack["evidence"]).values()):
            raise ValueError("检索证据超过每集合 2 条、总计 8 条")
        result = score_question(q, pack["evidence"], texts, masks)
        result.update({"elapsed_seconds": round(time.perf_counter() - started, 6),
                       "books_without_match": pack["books_without_match"]})
        results.append(result)
    report["summary"] = summarize(results)
    report["by_split"] = {s: summarize([r for r in results if r["split"] == s])
                          for s in sorted({r["split"] for r in results})}
    report["results"] = results
    return report
