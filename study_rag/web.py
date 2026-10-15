"""多人本机开发应用：账号与记录服务端隔离，公共资料只读。"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import sqlite3
import json
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import CorpusError, corpus_catalog, verified_chunks, verified_corpus
from .rag import DeepSeekModel, Model, MODEL_LABELS, answer_from_pack, retrieve
from .providers import create_model, configured_models, provider_name
from .limits import MAX_QUESTION_CHARS, MAX_REQUEST_BYTES
from .store import AccessError, LimitError, Store
from .settings import DEFAULT_DATA
from .conversation import prepare_context

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
    explanation_style: Literal["auto", "deep", "practice", "compare"] = "auto"
    use_history: bool = True
    model: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value):
        if not value.strip():
            raise ValueError("问题不能为空白。")
        return value


def create_app(*, data_dir: Path = DEFAULT_DATA, store: Store | None = None,
               model: Model | None = None, secure_cookie: bool | None = None,
               session_cookie_name: str = "rag_session",
               model_options: dict[str, Model] | None = None) -> FastAPI:
    store = store or Store(PROJECT / "output" / "users.sqlite3",
                           user_daily_limit=int(os.getenv("RAG_USER_DAILY_LIMIT", "20")),
                           global_daily_limit=int(os.getenv("RAG_GLOBAL_DAILY_LIMIT", "100")),
                           max_concurrent=int(os.getenv("RAG_MAX_CONCURRENT", "2")))
    model = model or create_model()
    available_models = dict(model_options) if model_options is not None else {model.model_name: model}
    if model_options is None and isinstance(model, DeepSeekModel):
        available_models = configured_models(model)
    if model.model_name not in available_models or any(name != item.model_name for name, item in available_models.items()):
        raise ValueError("模型选项与默认型号不一致。")
    model_catalog = [{"id": name, "display_name": MODEL_LABELS.get(name, name),
                      "provider": provider_name(name),
                      "description": "官方费率高于 Flash" if name == "deepseek-v4-pro" else "",
                      "is_default": name == model.model_name}
                     for name in sorted(available_models, key=lambda name: (list(MODEL_LABELS).index(name)
                         if name in MODEL_LABELS else len(MODEL_LABELS), name))]
    secure_cookie = secure_cookie if secure_cookie is not None else os.getenv("RAG_COOKIE_SECURE", "false").lower() == "true"
    executor = ThreadPoolExecutor(max_workers=max(2, store.max_concurrent), thread_name_prefix="rag-answer")
    owned_models = list({id(item): item for item in available_models.values()}.values()) if model_options is None and isinstance(model, DeepSeekModel) else []

    @asynccontextmanager
    async def lifespan(app):
        try:
            underlying=getattr(model,'model',model)
            if isinstance(underlying,DeepSeekModel):
                cold_started=time.perf_counter()
                snapshot=verified_corpus(data_dir,data_dir/'index.sqlite3')
                if snapshot[0]['schema_version']==4:
                    from .qa_retrieval_v5 import indexed_materials
                    from .parent_vectors import parent_index,query_vector
                    manifest,chunks,_,contents=snapshot
                    mat=indexed_materials(manifest,contents,chunks,corpus_catalog(manifest))
                    parent_index(manifest['corpus_version'],mat['descriptors']);query_vector('初始化本地检索',2)
                app.state.startup_metrics={'cold_start_seconds':time.perf_counter()-cold_started,'model_calls':0,
                                           'corpus_version':snapshot[0]['corpus_version']}
            yield
        finally:
            # Already-started generations finish even when their HTTP reader left.
            executor.shutdown(wait=True)
            for item in owned_models:
                item.close()

    app = FastAPI(title="学有据 · 公共教材学习助手", docs_url=None, redoc_url=None, lifespan=lifespan)
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
            user = store.authenticate(request.cookies.get(session_cookie_name))
        except AccessError:
            raise HTTPException(401, "请先登录。") from None
        if request.method not in {"GET", "HEAD"}:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf, user["csrf"]):
                raise HTTPException(403, "请求校验失败，请刷新后重试。")
        return user

    def login_response(user: dict, response: Response):
        token, csrf = store.create_session(user["id"])
        response.set_cookie(session_cookie_name, token, httponly=True, secure=secure_cookie,
                            samesite="strict", max_age=7 * 86400, path="/")
        return {"username": user["username"], "role": user["role"], "csrf": csrf, "quota": store.quota(user["id"])}

    @app.get("/api/library")
    def library():
        manifest, chunks, sources, contents = verified_corpus(data_dir, data_dir / "index.sqlite3")
        from .source_views import source_view
        notebook_cells={s.source_id:len(source_view(s.path,raw)[1]) for s,raw in contents if s.path.endswith('.ipynb')}
        coverage_gaps=None
        coverage_path=data_dir/'coverage.json'
        if coverage_path.is_file():
            try:
                coverage=json.loads(coverage_path.read_text(encoding='utf-8'))
                if coverage.get('corpus_version')==manifest['corpus_version'] and isinstance(coverage.get('gaps'),list):coverage_gaps=coverage['gaps']
            except (ValueError,OSError):pass
        by_source = {}
        for chunk in chunks:
            by_source[chunk.source_id] = by_source.get(chunk.source_id, 0) + 1
        books = []
        catalog = corpus_catalog(manifest)
        for metadata in sorted(catalog["books"], key=lambda b: (b["order"], b["book"])):
            book = metadata["book"]
            files = [source for source in sources.values() if source.book == book]
            selected = sorted((source for source in files if source.path.endswith('.ipynb') or catalog["chapters"][source.source_id].get("kind") not in {"implementation","dependency"}),
                              key=lambda s: catalog["chapters"][s.source_id]["order"]
                              if manifest["schema_version"] >= 2 else chapter_order(s))
            books.append({"book": book, "display_name": metadata["display_name"],
                          "kind": metadata.get("kind", "course"), "documents": len(selected),
                          "source_files":len(files),"implementation_files":sum(s.path.endswith(".py") for s in files),
                          "raw_files":len(files),"notebook_files":sum(s.path.endswith('.ipynb') for s in files),
                          "notebook_cells":sum(notebook_cells.get(s.source_id,0) for s in files),
                          "dependency_files":sum(catalog["chapters"][s.source_id].get("kind")=="dependency" for s in files),
                          "chunks": sum(by_source.get(s.source_id, 0) for s in files),
                          "chapters": [{"title": s.chapter, "path": s.path, "source_url": s.source_url,
                                        "language": catalog["chapters"][s.source_id]["language"],
                                        "kind": catalog["chapters"][s.source_id].get("kind", "lesson"),
                                        "content_type":catalog["chapters"][s.source_id].get("content_type","prose"),
                                        "applicable_versions":catalog["chapters"][s.source_id].get("applicable_versions",["unknown"]),
                                        "topics": catalog["chapters"][s.source_id].get("topics", []),
                                        "implementation_links": [{"path": f["path"],"content_type":"code","applicable_versions":["unknown"],
                                            "ingested":any(code.path==f["path"] and code.repository==s.repository for code in files),
                                            "url": f"https://github.com/{s.repository}/blob/{s.commit}/{quote(f['path'])}"}
                                            for f in catalog["chapters"][s.source_id].get("implementation_files", [])],
                                        "dependencies":[{"source_id":dep,"path":sources[dep].path,"source_url":sources[dep].source_url,
                                            "content_type":catalog["chapters"][dep].get("content_type","snippet"),"applicable_versions":catalog["chapters"][dep].get("applicable_versions",["unknown"])}
                                            for dep in catalog["chapters"][s.source_id].get("dependencies",[])],
                                        "chunks": by_source.get(s.source_id, 0)} for s in selected],
                          "license": metadata["license"],
                          "license_url": f"https://github.com/{files[0].repository}/blob/{files[0].commit}/"
                                         + metadata["license_path"]})
        return {"corpus_version": manifest["corpus_version"], "snapshot":data_dir.name, "chunks": len(chunks),
                "source_files":len(sources),"raw_files":len(sources),"notebook_cells":sum(notebook_cells.values()),
                "coverage_gaps":coverage_gaps,"answer_schema_version":2 if manifest["schema_version"]>=3 else 1,
                "books": books, "model": model.model_name, "default_model": model.model_name,
                "models": model_catalog, "adaptive_answers": True, "streaming_answers": True}

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
        store.logout(request.cookies.get(session_cookie_name, ""))
        response.delete_cookie(session_cookie_name, path="/")
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

    def prepare_ask(body, user):
        started = time.perf_counter()
        selected_name = body.model if body.model is not None else model.model_name
        if selected_name not in available_models:
            raise HTTPException(422, "模型选项不存在，请刷新页面后重新选择。")
        selected_model = available_models[selected_name]
        try:
            store.require_chat(user["id"], body.chat_id)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None
        previous = store.previous_request(user["id"], body.request_key)
        if previous:
            result = previous["result"]
            requested_style = body.explanation_style if "explanation_style" in body.model_fields_set else None
            style_changed = (result["requested_explanation_style"] != requested_style
                             if "requested_explanation_style" in result else
                             "explanation_style" in body.model_fields_set
                             and result.get("explanation_style", "deep") != body.explanation_style)
            if (previous["chat_id"] != body.chat_id or previous["question"] != body.question
                    or result.get("book_filter") != body.book
                    or result.get("request_mode") != ("explain" if body.explain else "retrieve")
                    or style_changed
                    or result.get("history_enabled", True) != body.use_history
                    or result.get("requested_model") != body.model):
                raise HTTPException(409, "请求编号已用于不同问题。")
            return {"reused": {**result, "reused": True, "quota": store.quota(user["id"])}}
        context = prepare_context(body.question, store.recent_exchanges(user["id"], body.chat_id)
                                  if body.use_history else [], body.book, body.use_history)
        snapshot = verified_corpus(data_dir, data_dir / "index.sqlite3")
        manifest, _, sources, _ = snapshot
        if body.book is not None and body.book not in {s.book for s in sources.values()}:
            raise HTTPException(422, "教材筛选值不存在，请刷新教材目录。")
        if context["needs_topic"]:
            from .rag import RETRIEVER_VERSION
            pack = {"book_filter": body.book, "corpus_version": manifest["corpus_version"],
                    "retriever": RETRIEVER_VERSION, "evidence": [], "books_without_match": [],
                    "source_verified": True, "support_verified": False}
        else:
            pack = retrieve(data_dir, data_dir / "index.sqlite3", context["retrieval_question"], body.book, _verified=snapshot,_anchors=context.get('object_anchors'))
        pack.update({"question": body.question, "retrieval_question": context["retrieval_question"],
                     "context_turns": len(context["turns"]), "context_version": context["version"],
                     "inherited_topic": context["inherited_topic"], "history_enabled": body.use_history,
                     "explanation_style": body.explanation_style, "conversation_topic": context["topic_question"],
                     "requested_explanation_style": body.explanation_style if "explanation_style" in body.model_fields_set else None,
                     "requested_model": body.model, "selected_model": selected_name})
        pack["timings"] = {"retrieval_seconds": time.perf_counter() - started}
        job = store.reserve(user["id"], body.request_key) if body.explain and pack["evidence"] else None
        return {"pack":pack, "context":context, "job":job, "model":selected_model, "started":started}

    def complete_ask(body, user, prepared, emit=None):
        pack, context, job = prepared["pack"], prepared["context"], prepared["job"]
        result = {"status": "INTERNAL_FAILED", "model_calls": 0}
        try:
            if emit:
                emit({"type":"progress", "stage":"retrieval"})
                emit({"type":"evidence", "pack":pack})
                emit({"type":"progress", "stage":"generation"})
            result = answer_from_pack(pack, prepared["model"], explain=body.explain, context=context["turns"],
                                      style=body.explanation_style, on_event=emit)
            if context["needs_topic"]:
                result["status"] = "CONTEXT_REQUIRED"
            result["request_mode"] = "explain" if body.explain else "retrieve"
            result.setdefault("timings", {}).update({"total_seconds":time.perf_counter()-prepared["started"]})
            for key in ("first_content_seconds", "first_validated_block_seconds"):
                value = result["timings"].get(key)
                if value is not None:
                    result["timings"][key] = value + pack["timings"]["retrieval_seconds"]
            store.save_exchange(user["id"], body.chat_id, body.request_key, body.question, result)
        except AccessError:
            raise HTTPException(404, "讨论不存在。") from None
        except sqlite3.IntegrityError:
            raise HTTPException(409, "请求重复，请刷新讨论记录。") from None
        finally:
            if job:
                store.finish(job, result)
        return {**result, "quota": store.quota(user["id"])}

    @app.post("/api/ask")
    def ask(body: Ask, user=Depends(current_user)):
        prepared = prepare_ask(body, user)
        if "reused" in prepared:
            return prepared["reused"]
        return complete_ask(body, user, prepared)

    @app.post("/api/ask/stream")
    def ask_stream(body: Ask, user=Depends(current_user)):
        prepared = prepare_ask(body, user)
        events = queue.Queue()

        def work():
            try:
                result = complete_ask(body, user, prepared, events.put)
                events.put({"type":"result", "result":result})
            except Exception:
                # Never expose exception bodies, model output or another chat.
                events.put({"type":"error", "detail":"本次处理未完成，请刷新讨论查看最终结果。"})
            finally:
                events.put(None)

        if "reused" in prepared:
            events.put({"type":"result", "result":prepared["reused"]})
            events.put(None)
        else:
            # Submit before the generator is consumed. Disconnect/cancellation of
            # the response never cancels this one reserved model call or its save.
            try:
                executor.submit(work)
            except RuntimeError:
                if prepared["job"]:
                    store.finish(prepared["job"], {"status":"INTERNAL_FAILED", "model_calls":0})
                raise HTTPException(503, "服务正在关闭，请稍后再试。") from None

        def stream():
            while True:
                try:
                    event = events.get(timeout=5)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering":"no"})

    from .lab_web import register_lab_routes
    register_lab_routes(app, current_user, data_dir, store, model)

    app.mount("/static", StaticFiles(directory=PROJECT / "static"), name="static")

    @app.get("/")
    def homepage():
        return FileResponse(PROJECT / "static" / "index.html")

    return app
