"""多人本机开发应用：账号与记录服务端隔离，公共资料只读。"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import sqlite3
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import CorpusError, corpus_catalog, verified_chunks
from .rag import DeepSeekModel, Model, answer_from_pack, retrieve
from .limits import MAX_QUESTION_CHARS, MAX_REQUEST_BYTES
from .store import AccessError, LimitError, Store
from .settings import DEFAULT_DATA

PROJECT = Path(__file__).resolve().parent.parent


def chapter_order(source):
    """目录先展示主线正文并按章排序，补充资料随后，避免第10章排在第2章前。"""
    if source.book == "Hello-Agents":
        if source.path == "docs/前言.md":
            return (0, 0, source.path)
        match = re.match(r"docs/chapter(\d+)/", source.path)
        if match:
            return (1, int(match[1]), source.path)
        match = re.match(r"Extra-Chapter/Extra(\d+)", source.path)
        if match:
            return (2, int(match[1]), source.path)
        return (3, 0, source.path)
    match = re.match(r"stages/([\d.]+)-", source.path)
    if match:
        return (0, float(match[1]), source.path)
    return (1, 0, source.path)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=128)


class NewChat(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(default="新的学习讨论", max_length=80)


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    chat_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    request_key: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    book: str | None = Field(default=None, max_length=100)
    explain: bool = True


def create_app(*, data_dir: Path = DEFAULT_DATA, store: Store | None = None,
               model: Model | None = None, secure_cookie: bool | None = None) -> FastAPI:
    store = store or Store(PROJECT / "output" / "users.sqlite3",
                           user_daily_limit=int(os.getenv("RAG_USER_DAILY_LIMIT", "20")),
                           global_daily_limit=int(os.getenv("RAG_GLOBAL_DAILY_LIMIT", "100")),
                           max_concurrent=int(os.getenv("RAG_MAX_CONCURRENT", "2")))
    model = model or DeepSeekModel()
    secure_cookie = secure_cookie if secure_cookie is not None else os.getenv("RAG_COOKIE_SECURE", "false").lower() == "true"
    app = FastAPI(title="学有据 · 公共教材学习助手", docs_url=None, redoc_url=None)
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if origin and origin != expected:
                return JSONResponse({"detail": "请求来源不允许。"}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0") or 0)
            except ValueError:
                return JSONResponse({"detail": "请求长度无效。"}, status_code=400)
            if size > MAX_REQUEST_BYTES:
                return JSONResponse({"detail": "请求过大。"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # 不把包含密码的输入回显到错误对象或日志。
        return JSONResponse({"detail": "输入格式不正确，请检查用户名、密码或问题长度。"}, status_code=422)

    @app.exception_handler(LimitError)
    async def limit_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=429)

    @app.exception_handler(CorpusError)
    async def corpus_error(request, error):
        return JSONResponse({"detail": "教材或索引核对失败，请联系维护者。"}, status_code=503)

    def current_user(request: Request):
        try:
            user = store.authenticate(request.cookies.get("rag_session"))
        except AccessError:
            raise HTTPException(401, "请先登录。") from None
        if request.method not in {"GET", "HEAD"}:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf, user["csrf"]):
                raise HTTPException(403, "请求校验失败，请刷新后重试。")
        return user

    def login_response(user: dict, response: Response):
        token, csrf = store.create_session(user["id"])
        response.set_cookie("rag_session", token, httponly=True, secure=secure_cookie,
                            samesite="strict", max_age=7 * 86400, path="/")
        return {"username": user["username"], "role": user["role"], "csrf": csrf, "quota": store.quota(user["id"])}

    @app.get("/api/library")
    def library():
        manifest, chunks, sources = verified_chunks(data_dir, data_dir / "index.sqlite3")
        by_source = {}
        for chunk in chunks:
            by_source[chunk.source_id] = by_source.get(chunk.source_id, 0) + 1
        books = []
        catalog = corpus_catalog(manifest)
        for metadata in sorted(catalog["books"], key=lambda b: (b["order"], b["book"])):
            book = metadata["book"]
            selected = sorted((source for source in sources.values() if source.book == book),
                              key=lambda s: catalog["chapters"][s.source_id]["order"]
                              if manifest["schema_version"] == 2 else chapter_order(s))
            books.append({"book": book, "display_name": metadata["display_name"],
                          "kind": metadata.get("kind", "course"), "documents": len(selected),
                          "chunks": sum(by_source.get(s.source_id, 0) for s in selected),
                          "chapters": [{"title": s.chapter, "path": s.path, "source_url": s.source_url,
                                        "language": catalog["chapters"][s.source_id]["language"],
                                        "kind": catalog["chapters"][s.source_id].get("kind", "lesson"),
                                        "topics": catalog["chapters"][s.source_id].get("topics", []),
                                        "implementation_links": [{"path": f["path"],
                                            "url": f"https://github.com/{s.repository}/blob/{s.commit}/{quote(f['path'])}"}
                                            for f in catalog["chapters"][s.source_id].get("implementation_files", [])],
                                        "chunks": by_source.get(s.source_id, 0)} for s in selected],
                          "license": metadata["license"],
                          "license_url": f"https://github.com/{selected[0].repository}/blob/{selected[0].commit}/"
                                         + metadata["license_path"]})
        return {"corpus_version": manifest["corpus_version"], "chunks": len(chunks),
                "books": books, "model": model.model_name}

    @app.post("/api/register")
    def register(body: Credentials, response: Response):
        try:
            user = store.register(body.username, body.password)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return login_response(user, response)

    @app.post("/api/login")
    def login(body: Credentials, request: Request, response: Response):
        try:
            user = store.login(body.username, body.password, request.client.host if request.client else "unknown")
        except AccessError:
            raise HTTPException(401, "用户名或密码不正确。") from None
        return login_response(user, response)

    @app.get("/api/me")
    def me(user=Depends(current_user)):
        return {"username": user["username"], "role": user["role"], "csrf": user["csrf"], "quota": store.quota(user["id"])}

    @app.get("/api/admin/overview")
    def admin_overview(user=Depends(current_user)):
        try:
            return store.admin_overview(user["id"])
        except AccessError:
            raise HTTPException(403, "需要管理员权限。") from None

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(current_user)):
        store.logout(request.cookies.get("rag_session", ""))
        response.delete_cookie("rag_session", path="/")
        return {"status": "logged_out"}

    @app.get("/api/chats")
    def chats(user=Depends(current_user)):
        return store.list_chats(user["id"])

    @app.post("/api/chats")
    def new_chat(body: NewChat, user=Depends(current_user)):
        return store.create_chat(user["id"], body.title)

    @app.get("/api/chats/{chat_id}")
    def history(chat_id: str, user=Depends(current_user)):
        try:
            return store.history(user["id"], chat_id)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None

    @app.delete("/api/chats/{chat_id}")
    def delete_chat(chat_id: str, user=Depends(current_user)):
        try:
            store.delete_chat(user["id"], chat_id)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None
        return {"status": "deleted"}

    @app.post("/api/ask")
    def ask(body: Ask, user=Depends(current_user)):
        if body.book is not None:
            _, _, sources = verified_chunks(data_dir, data_dir / "index.sqlite3")
            if body.book not in {s.book for s in sources.values()}:
                raise HTTPException(422, "教材筛选值不存在，请刷新教材目录。")
        try:
            store.require_chat(user["id"], body.chat_id)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None
        previous = store.previous_request(user["id"], body.request_key)
        if previous:
            result = previous["result"]
            if (previous["chat_id"] != body.chat_id or previous["question"] != body.question
                    or result.get("book_filter") != body.book
                    or result.get("request_mode") != ("explain" if body.explain else "retrieve")):
                raise HTTPException(409, "请求编号已用于不同问题。")
            return {**result, "reused": True, "quota": store.quota(user["id"])}
        pack = retrieve(data_dir, data_dir / "index.sqlite3", body.question, body.book)
        job = store.reserve(user["id"], body.request_key) if body.explain and pack["evidence"] else None
        result = {"status": "INTERNAL_FAILED", "model_calls": 0}
        try:
            result = answer_from_pack(pack, model, explain=body.explain)
            result["request_mode"] = "explain" if body.explain else "retrieve"
            store.save_exchange(user["id"], body.chat_id, body.request_key, body.question, result)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None
        except sqlite3.IntegrityError:
            raise HTTPException(409, "请求重复，请刷新讨论记录。") from None
        finally:
            if job:
                store.finish(job, result)
        return {**result, "quota": store.quota(user["id"])}

    from .lab_web import register_lab_routes
    register_lab_routes(app, current_user, data_dir, store, model)

    app.mount("/static", StaticFiles(directory=PROJECT / "static"), name="static")

    @app.get("/")
    def homepage():
        return FileResponse(PROJECT / "static" / "index.html")

    return app
