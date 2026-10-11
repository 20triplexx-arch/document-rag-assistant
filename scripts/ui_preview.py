"""隔离 UI 预览：只读公开快照、临时账号库、离线模型，禁止真实模型调用。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi.responses import JSONResponse
from study_rag.rag import answer_from_pack, normalize_quote, retrieve
from study_rag.store import Store
from study_rag.web import create_app


class PreviewModel:
    model_name = "offline-ui-preview"

    def generate(self, messages):
        data = json.loads(messages[-1]["content"])
        claims = []
        for item in (data["EVIDENCE"] * 4)[:4]:
            text = normalize_quote(item["text"])
            claims.append({
                "text": "离线预览样例（仅检查界面排版）：" + text[:440],
                "evidence_id": item["evidence_id"], "quote": text[:120],
            })
        return json.dumps({"status": "answered", "claims": claims, "missing_information": ""}, ensure_ascii=False), {"model": self.model_name, "attempts": 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="study-rag-ui-") as temporary:
        store = Store(Path(temporary) / "preview.sqlite3")
        learner = store.create_admin("ui-preview", "ui-preview-pass")
        chat = store.create_chat(learner["id"], "RAG 与记忆 · 离线排版样例")
        model = PreviewModel()
        for question in ("RAG 和长期记忆有什么区别？", "多 Agent 怎样分工与协作？"):
            result = answer_from_pack(retrieve(args.data_dir, args.data_dir / "index.sqlite3", question), model)
            store.save_exchange(learner["id"], chat["id"], str(uuid4()), question, result)
        print(f"Offline preview: http://127.0.0.1:{args.port}/; temporary account: ui-preview / ui-preview-pass", flush=True)
        app = create_app(data_dir=args.data_dir, store=store, model=model, secure_cookie=False)

        @app.middleware("http")
        async def preview_failures(request, call_next):
            if request.method == "POST" and request.url.path == "/api/ask":
                question = (await request.json()).get("question")
                if question in {"预览请求失败", "预览额度限制"}:
                    detail = "离线预览：请求失败，请手动重试。" if question == "预览请求失败" else "离线预览：今日讲解额度已用完。"
                    return JSONResponse({"detail": detail}, status_code=503 if question == "预览请求失败" else 429)
            return await call_next(request)

        uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
