"""Frozen public scenarios and real HTTP measurements; bounded to 4+8+8 calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from study_rag.qa_trial import TrialBudget, TrialModel
from study_rag.rag import DeepSeekModel
from study_rag.store import Store
from study_rag.web import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/qa-speed-20261015-v1"
DATA = ROOT / "data/qa-20261014-v1"
SCENARIOS = ROOT / "evals/qa-speed-v1.json"
BASELINE = {"TOOL-D2", "MEM-D1", "RAG-D1", "MCP-D1"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_contract():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in sorted((ROOT / "study_rag").glob("*.py"))}


def freeze():
    gold = json.loads((ROOT / "evals/agent-qa-v1.1.json").read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in gold["questions"]}
    dev = [by_id[key] for key in ("TOOL-D2", "MEM-D1", "RAG-D1", "PLAN-D1", "CTX-D1", "MCP-D1", "MULTI-D1", "OBS-D1")]
    specs = [
        ("tools", "计算器工具收到表达式 1/0 或非法字符时怎样返回失败？请用 calculate_basic_math 的实际 Python 实现解释，并说明这能否证明框架会校验所有参数。", ["TOOL-D2"]),
        ("memory", "用户隔天开了新 thread，希望保留饮食偏好，但不自动带回上次聊天。thread、namespace/key 和后台写入记忆各负责什么？", ["MEM-D1", "MEM-D3:2"]),
        ("rag", "Hybrid RAG 页面先展示了 reranker 排序，后面再点生成回答。perform_search 和 rag(search=hybrid_search) 是什么关系，能保证回答复用了刚才那批重排片段吗？请依据实际源码说明。", ["RAG-D2"]),
        ("planning", "研究助手把 write_todos 全部标为 completed，就能证明报告完成了吗？请说明 Deep Agents 用文件系统、摘要和 task 管理长任务时，哪些是内部状态，哪些结果仍需核查。", ["PLAN-D2"]),
        ("context", "工具通过 runtime 得到用户身份，聊天历史又越来越长。应该把身份作为模型生成的参数吗？model context 与 tool context 有何区别，trim 和 delete 分别改变什么？", ["TOOL-D3:2", "CTX-D1:2", "CTX-D1:3", "CTX-D2:2"]),
        ("mcp", "一个 MCP 客户端从 2025-11-25 迁移到 2026-07-28，还能只在 initialize 时协商能力吗？请按版本解释状态边界、请求携带的信息和发现服务端能力的入口。", ["MCP-D2"]),
        ("multi_agent", "退款专员需要直接接待用户，后台检索员只需交回核查报告。这两项分别适合 handoffs 还是 subagents？总控是否自动看到后台检索员的完整聊天历史？", ["MULTI-D1", "MULTI-D2:2"]),
        ("observability", "同一讨论连续问两次，第二次经历模型、工具、模型三个步骤。LangSmith 应如何组织 run、trace 和 thread？HTTP 200 能证明答案正确吗，还需要什么评估？", ["OBS-D1", "OBS-D2:2", "OBS-D2:3"]),
    ]
    acceptance = []
    for number, (topic, question, refs) in enumerate(specs, 1):
        points = []
        for ref in refs:
            key, _, index = ref.partition(":")
            points.extend([by_id[key]["points"][int(index)-1]] if index else by_id[key]["points"])
        acceptance.append({"id": f"SPEED-A{number}", "topic": topic, "question": question, "split": "acceptance", "points": points,
                           "answerability": "answerable", "review_origin": "AI-assisted raw-source annotation; not human approval"})
    document = {"version": "qa-speed-v1", "date": "2026-10-15", "corpus_version": gold["corpus_version"],
                "source_gold_sha256": digest(ROOT / "evals/agent-qa-v1.1.json"),
                "note": "New scenarios reuse verified source spans and concepts; small AI-labelled sample, not an independent human benchmark.",
                "dev": dev, "acceptance": acceptance}
    encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if SCENARIOS.exists() and SCENARIOS.read_text(encoding="utf-8") != encoded:
        raise ValueError("Frozen scenarios changed")
    if not SCENARIOS.exists():
        SCENARIOS.write_text(encoded, encoding="utf-8")
    budget = TrialBudget(OUT / "budget.sqlite3")
    budget.freeze("scenarios", digest(SCENARIOS))
    snapshot = OUT / "baseline-code"
    snapshot.mkdir(exist_ok=True)
    for path in sorted((ROOT / "study_rag").glob("*.py")):
        target = snapshot / path.name
        if not target.exists():
            target.write_bytes(path.read_bytes())
    budget.freeze("baseline_code", json.dumps(code_contract(), sort_keys=True))
    print(json.dumps({"frozen": str(SCENARIOS), "budget": budget.summary(), "key_available": bool(os.getenv("DEEPSEEK_API_KEY", "").strip())}))


def run(phase):
    budget = TrialBudget(OUT / "budget.sqlite3")
    budget.freeze("scenarios", digest(SCENARIOS))
    contract = code_contract()
    budget.freeze(phase + "_code", json.dumps(contract, sort_keys=True))
    snapshot = OUT / (phase + "-code")
    snapshot.mkdir(exist_ok=True)
    for relative, expected in contract.items():
        target = snapshot / Path(relative).name
        if not target.exists():
            target.write_bytes((ROOT / relative).read_bytes())
        if digest(target) != expected:
            raise ValueError("Frozen phase snapshot changed")
    document = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    from study_rag.core import load_corpus, validate_text
    manifest, contents = load_corpus(DATA)
    public_repositories = {"langchain-ai/docs", "modelcontextprotocol/modelcontextprotocol", "WenyuChiou/awesome-agentic-ai-zh",
                           "datawhalechina/hello-agents", "huggingface/agents-course", "Shubhamsaboo/awesome-llm-apps",
                           "microsoft/ai-agents-for-beginners"}
    if any(source.repository not in public_repositories for source, raw in contents):
        raise ValueError("Trial has an unapproved source repository")
    public_texts = {(source.book, source.path):validate_text(raw) for source, raw in contents}
    questions = document["acceptance" if phase == "acceptance" else "dev"]
    if phase == "baseline":
        questions = [q for q in questions if q["id"] in BASELINE]
    store = Store(OUT / "users.sqlite3", user_daily_limit=20, global_daily_limit=100)
    underlying = DeepSeekModel("deepseek-flash")
    try:
        for q in questions:
            dest = OUT / f"{phase}-{q['id']}.json"
            if dest.exists():
                continue
            with budget.connect() as db:
                reserved = db.execute("SELECT state,error FROM calls WHERE phase=? AND question_id=?", (phase, q["id"])).fetchone()
            if reserved:
                print(q["id"], "ALREADY_RESERVED_NO_RETRY", reserved, flush=True)
                continue
            if code_contract() != contract:
                raise ValueError("Code changed during phase")
            model = TrialModel(budget, phase, q["id"], underlying, expected_question=q["question"], public_texts=public_texts)
            app = create_app(data_dir=DATA, store=store, model=model, session_cookie_name="qa_speed_session")
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
            worker.start()
            deadline = time.monotonic() + 10
            while not server.started:
                if not worker.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("Isolated HTTP server did not start")
                time.sleep(.02)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=140) as client:
                    auth = client.post("/api/register", json={"username": "speed-" + uuid4().hex[:16], "password": secrets.token_urlsafe(24)})
                    auth.raise_for_status()
                    client.headers["X-CSRF-Token"] = auth.json()["csrf"]
                    chat = client.post("/api/chats", json={"title": "公开速度验证 " + q["id"]})
                    chat.raise_for_status()
                    body = {"chat_id": chat.json()["id"], "request_key": str(uuid4()), "question": q["question"],
                            "explain": True, "use_history": False, "model": "deepseek-flash"}
                    events = []
                    started = time.perf_counter()
                    first_block = None
                    if phase == "baseline":
                        response = client.post("/api/ask", json=body)
                        response.raise_for_status()
                        result = response.json()
                    else:
                        result = None
                        with client.stream("POST", "/api/ask/stream", json=body) as response:
                            response.raise_for_status()
                            for line in response.iter_lines():
                                if not line.startswith("data: "):
                                    continue
                                event = json.loads(line[6:])
                                elapsed = time.perf_counter() - started
                                events.append({"type": event["type"], "seconds": elapsed})
                                if event["type"] == "block" and first_block is None:
                                    first_block = elapsed
                                if event["type"] == "result":
                                    result = event["result"]
                        if result is None:
                            raise RuntimeError("Stream ended without persisted result")
                    total = time.perf_counter() - started
                    history = client.get("/api/chats/" + body["chat_id"])
                    history.raise_for_status()
                    if len(history.json()) != 1:
                        raise ValueError("Result was not saved exactly once")
                record = {"scenario": q, "result": result, "phase": phase, "code_contract": contract,
                          "scenario_sha256": digest(SCENARIOS), "client_total_seconds": total,
                          "client_first_block_seconds": first_block, "events": events, "review_origin": "pending AI source review; not human approval"}
                dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(q["id"], result["status"], round(total, 3), first_block, flush=True)
            finally:
                server.should_exit = True
                worker.join(timeout=10)
                sock.close()
    finally:
        if hasattr(underlying, "close"):
            underlying.close()
    print(json.dumps(budget.summary()), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("freeze", "baseline", "dev", "acceptance"))
    args = parser.parse_args()
    freeze() if args.phase == "freeze" else run(args.phase)
