"""直接在 PyCharm 运行，或从项目根目录按子命令运行。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from uuid import uuid4

from study_rag.core import (
    build_index, load_corpus, prepare_corpus, read_evidence, read_source_manifest,
    search, verified_chunks,
)
from study_rag.rag import DeepSeekModel, MODEL_LABELS, answer_from_pack, retrieve
from study_rag.providers import create_model, ENABLED_MODELS
from study_rag.settings import DEFAULT_DATA, DEFAULT_SOURCES
from study_rag.evaluation import DEFAULT_DATASET, evaluate

PROJECT = Path(__file__).resolve().parent


def save_report(output_dir: Path, report: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report['operation']}_{uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="教材导入、检索与单次 DeepSeek 开发试答")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "output")
    commands = parser.add_subparsers(dest="operation")
    importer = commands.add_parser("import", help="下载固定版本公开教材，或复用已有快照")
    importer.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    commands.add_parser("verify", help="离线核对原文和索引")
    query = commands.add_parser("search", help="离线检索候选，不生成答案")
    query.add_argument("question")
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--book", help="当前语料中的教材 ID（见 verify）")
    reader = commands.add_parser("read", help="按片段 ID 读取可核查原文")
    reader.add_argument("chunk_id")
    answering = commands.add_parser("ask", help="开发试答：最多一次 DeepSeek 请求，可能消耗账户额度")
    answering.add_argument("question")
    answering.add_argument("--book", help="当前语料中的教材 ID（见 verify）")
    answering.add_argument("--style", choices=("auto", "deep", "practice", "compare"), default="auto",
                           help="讲解重点：自动篇幅（默认）、深入讲解、实战步骤或方案对比")
    answering.add_argument("--model", choices=ENABLED_MODELS, help="生成型号；省略时使用服务端默认")
    evaluating = commands.add_parser("evaluate", help="离线固定题集校验/检索评分，0 次模型调用")
    evaluating.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    evaluating.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    evaluating.add_argument("--check-only", action="store_true", help="只检查题集、原文位置和版本，不运行检索")
    # 同时接受既有全局参数和子命令后的同名参数。
    evaluating.add_argument("--data-dir", type=Path, default=argparse.SUPPRESS)
    evaluating.add_argument("--output-dir", type=Path, default=argparse.SUPPRESS)
    qa_eval=commands.add_parser("qa-evaluate",help="八主题题集静态校验或离线检索，0 次模型调用")
    from study_rag.qa_evaluation import QA_DATASET
    qa_eval.add_argument("--dataset",type=Path,default=QA_DATASET)
    qa_eval.add_argument("--data-dir",type=Path,default=PROJECT/"data/qa-20261014-v1")
    qa_eval.add_argument("--output-dir",type=Path,default=argparse.SUPPRESS)
    qa_eval.add_argument("--split",choices=("dev","acceptance","all"),default="dev")
    qa_eval.add_argument("--strategy",choices=("bm25","hybrid"),default="bm25")
    qa_eval.add_argument("--check-only",action="store_true")
    args = parser.parse_args(argv)
    if args.operation is None:
        print("文档 RAG 学习助手：教材导入与检索基线")
        print("1 导入完整教材（按固定来源清单下载公开文本，0 次模型调用）")
        print("2 核对原文与索引（离线）\n3 检索问题（离线）\n4 读取片段（离线）")
        print("5 DeepSeek 开发试答（最多一次请求，消耗账户额度）\n0 退出")
        choice = input("选择：").strip()
        if choice == "0":
            return 0
        if choice == "1":
            args.operation, args.sources = "import", DEFAULT_SOURCES
        elif choice == "2":
            args.operation = "verify"
        elif choice == "3":
            args.operation = "search"
            args.question = input("学习问题：").strip()
            args.book = None
            args.top_k = 5
        elif choice == "4":
            args.operation = "read"
            args.chunk_id = input("片段 ID：").strip()
        elif choice == "5":
            args.operation = "ask"
            args.question = input("学习问题：").strip()
            args.book = None
        else:
            print("选项无效。")
            return 2

    started = time.monotonic()
    report = {"operation": args.operation, "started_at": datetime.now(timezone.utc).isoformat(),
              "model_calls": 0, "answer_generated": False}
    index_path = args.data_dir / "index.sqlite3"
    try:
        if args.operation == "import":
            sources, catalog = read_source_manifest(args.sources)
            print("首次导入只下载来源清单中的公开章节；不上传资料、不请求模型。")
            imported = prepare_corpus(sources, args.data_dir, catalog=catalog)
            report.update(imported)
            report["index"] = build_index(args.data_dir, index_path)
            report["documents_detail"] = load_corpus(args.data_dir)[0]["documents"]
        elif args.operation == "verify":
            manifest, chunks, sources = verified_chunks(args.data_dir, index_path)
            counts = Counter(chunk.source_id for chunk in chunks)
            report.update({"status": "VERIFIED", "corpus_version": manifest["corpus_version"],
                           "source_verified": True, "network_requests": 0,
                           "chunks": len(chunks), "by_source": dict(counts),
                           "documents": len(sources), "books": list(dict.fromkeys(source.book for source in sources.values()))})
        elif args.operation == "search":
            report.update(search(args.data_dir, index_path, args.question,
                                 top_k=args.top_k, book=args.book))
        elif args.operation == "ask":
            print("模型只读取所属供应商的服务端配置；本题最多一次生成请求，不自动重试。")
            pack = retrieve(args.data_dir, index_path, args.question, args.book)
            selected_model = create_model(getattr(args, "model", None))
            try:
                report.update(answer_from_pack(pack, selected_model, style=getattr(args, "style", "auto")))
            finally:
                selected_model.close()
            report["selected_model"] = selected_model.model_name
            report["answer_generated"] = bool(report.get("answer"))
        elif args.operation == "evaluate":
            report.update(evaluate(args.dataset, args.data_dir, split=args.split,
                                   check_only=args.check_only))
        elif args.operation == "qa-evaluate":
            from study_rag.qa_evaluation import evaluate_qa
            report.update(evaluate_qa(args.dataset,args.data_dir,split=args.split,strategy=args.strategy,check_only=args.check_only))
        else:
            report.update({"status": "EVIDENCE_READ", "network_requests": 0,
                           "evidence": read_evidence(args.data_dir, index_path, args.chunk_id)})
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        report.update({"status": "FAILED", "error_type": type(error).__name__})
        if args.operation in {"evaluate","qa-evaluate"}:
            # 题集错误仅包含公开教材标注；保留诊断以便维护者定位。
            report["validation_error"] = str(error)
            print(f"评测校验失败：{error}")
        # 不打印服务端响应或异常正文，避免暴露请求数据及凭证。
        print(f"操作失败：{type(error).__name__}。请检查来源、网络或原文/索引完整性。")
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    path = save_report(args.output_dir, report)
    if report["status"] != "FAILED":
        printable = {k: v for k, v in report.items() if k != "results"}
        print(json.dumps(printable, ensure_ascii=False, indent=2))
        if args.operation == "search":
            print("这些是候选原文，尚未判断它们是否足以支持答案。")
    print(f"运行记录：{path}")
    return 1 if report["status"] in {"FAILED", "MODEL_FAILED", "CITATION_VALIDATION_FAILED"} else 0


if __name__ == "__main__":
    # Windows 的终端/管道默认编码可能无法显示中文教材名。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
