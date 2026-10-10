"""本机开发入口；不部署公网。"""
from __future__ import annotations

import os
import uvicorn

from study_rag.web import create_app


def app_factory():
    return create_app()


if __name__ == "__main__":
    print("学有据：本机多人开发版，打开 http://127.0.0.1:8765")
    print("DeepSeek Key 仅从服务端环境读取；讲解每题最多一次 API 请求，原文检索零模型请求。")
    uvicorn.run("serve:app_factory", factory=True, host="127.0.0.1",
                port=int(os.getenv("RAG_PORT", "8765")), proxy_headers=False, access_log=False)
