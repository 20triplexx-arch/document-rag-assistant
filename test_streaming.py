"""Streaming safety, persistence, exact references, connection and budget limits."""
from contextlib import closing
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4

import httpx
import uvicorn
from fastapi.testclient import TestClient
from study_rag.answer_stream import AnswerArrayReader
from study_rag.answer_schema import validate_v2
from study_rag.citation_spans import spans_for_evidence, hydrate, generation_schema
from study_rag.core import Source, prepare_corpus, build_index, verified_corpus, CorpusError, _compiled_chunks
from study_rag.qa_trial import TrialBudget
from study_rag.rag import answer_from_pack, DeepSeekModel, ProviderError, retrieve
from study_rag.store import Store
from study_rag.web import create_app


def make_evidence(text="A tool is a callable function with defined inputs and outputs.", **extra):
    return {"evidence_id":"E1","source_id":"fixture","book":"examples","section":"概念", "text":text,"context_text":text,
            "start_char":0,"end_char":len(text),"start_line":1,"end_line":text.count("\n")+1,"content_type":"prose",**extra}


class StreamingModel:
    model_name = "deepseek-flash"
    span_references = True

    def __init__(self, mode="valid", gate=None):
        self.calls, self.mode, self.gate = 0, mode, gate
        self.entered = threading.Event()

    def generate_stream(self, messages, callback):
        self.calls += 1
        evidence = json.loads(messages[1]["content"])["EVIDENCE"][0]
        if "spans" in evidence:
            refs = {"evidence_id":evidence["evidence_id"],"span_id":evidence["spans"][0]["span_id"]}
            block = {"type":"paragraph","text":"工具执行动作，并返回结果。中文、引号\"与括号 ] } 都是文字。","references":[refs]}
            payload = {"schema_version":2,"status":"answered","blocks":[block],"missing_information":""}
        else:
            payload = {"status":"answered","format":"plain","claims":[{"text":"工具执行动作并返回结果。","heading":"",
                       "evidence_id":evidence["evidence_id"],"quote":evidence["text"][:80]}],"missing_information":""}
        if self.mode == "invalid_reference":
            payload["blocks"][0]["references"][0]["span_id"] = "S999"
        if self.mode == "invalid_final":
            payload["status"] = "partial"
        raw = json.dumps(payload, ensure_ascii=False)
        for char in raw:
            callback(char)
        self.entered.set()
        if self.gate:
            self.gate.wait(5)
        if self.mode == "timeout":
            raise ProviderError("MODEL_TOTAL_TIMEOUT")
        if self.mode == "truncated":
            raise ProviderError("MODEL_OUTPUT_LIMIT")
        return raw, {"model":self.model_name,"attempts":1}

    def generate(self, messages):
        return self.generate_stream(messages, lambda _: None)


class StreamParserTests(unittest.TestCase):
    def test_every_character_split_handles_escaped_strings_and_nested_arrays(self):
        units = [{"text":'中文 \\ \" ] } : blocks',"rows":[{"cells":["一","二"]}]},{"code":"x = '\\\"'\n"}]
        raw = json.dumps({"note":"blocks [ fake", "schema_version":2,"status":"answered","blocks":units,"missing_information":""}, ensure_ascii=False)
        seen = []; parser = AnswerArrayReader("blocks", seen.append)
        for index, char in enumerate(raw):
            parser.feed(char)
            for unit in seen:
                self.assertIn(json.dumps(unit,ensure_ascii=False), raw[:index+1])
        self.assertEqual(seen, units)

    def test_truncated_unit_is_never_emitted(self):
        seen=[]; parser=AnswerArrayReader("blocks",seen.append)
        parser.feed('{"blocks":[{"text":"incomplete')
        self.assertEqual(seen,[])

    def test_spans_keep_exact_code_indent_and_reject_unknown_ids(self):
        e=make_evidence("def calculate(value):\n    return value + 1\n",content_type="code")
        spans=spans_for_evidence([e]);self.assertTrue(spans["E1"])
        span=next(s for s in spans["E1"] if "return" in s["text"])
        self.assertIn("\n    return",span["text"])
        hydrated=hydrate({"references":[{"evidence_id":"E1","span_id":span["span_id"]}]},spans)
        self.assertEqual(hydrated["references"][0]["quote"],span["text"])
        with self.assertRaises(CorpusError):hydrate({"references":[{"evidence_id":"E2","span_id":"S1"}]},spans)
        self.assertEqual(generation_schema()["$defs"]["Reference"]["required"],["evidence_id","span_id"])
        source=hydrate({"type":"code","origin":"source","language":"python",
                        "code_reference":{"evidence_id":"E1","span_ids":[span["span_id"]]}},spans)
        self.assertEqual(source["code"],e["text"])
        validate_v2(json.dumps({"schema_version":2,"status":"answered","blocks":[source],"missing_information":""}),[e])

    def test_source_selection_rejects_noncontiguous_or_prose_spans(self):
        e=make_evidence(("    value = 'some long source line'\n"*65),content_type="code")
        spans=spans_for_evidence([e]);self.assertGreaterEqual(len(spans["E1"]),3)
        ids=[spans["E1"][0]["span_id"],spans["E1"][2]["span_id"]]
        with self.assertRaises(CorpusError):hydrate({"type":"code","origin":"source","language":"python","code_reference":{"evidence_id":"E1","span_ids":ids}},spans)
        prose=spans_for_evidence([make_evidence()])
        with self.assertRaises(CorpusError):hydrate({"type":"code","origin":"source","language":"python","code_reference":{"evidence_id":"E1","span_ids":["S1"]}},prose)

    def test_parent_summary_only_accepts_existing_child_references(self):
        e=make_evidence();spans=spans_for_evidence([e]);ref={"evidence_id":"E1","span_id":"S1"}
        wire={"type":"list","ordered":False,"references":[ref],"items":[{"text":"执行动作。","references":[ref]}]}
        output=hydrate(wire,spans);self.assertNotIn("references",output)
        wire["items"][0]["references"]=[]
        with self.assertRaises(CorpusError):hydrate(wire,spans)

    def test_spans_do_not_join_hidden_text_or_invent_source_positions(self):
        raw="Visible original paragraph with sufficient facts.\nHIDDEN PRIVATE CODE\nAnother visible original paragraph with sufficient facts."
        e=make_evidence(raw,context_text="Visible original paragraph with sufficient facts.\n\nAnother visible original paragraph with sufficient facts.")
        spans=spans_for_evidence([e])["E1"]
        self.assertEqual(len(spans),2)
        for span in spans:
            self.assertEqual(raw[span["start_char"]:span["end_char"]],span["text"])
            self.assertNotIn("HIDDEN",span["text"])

    def test_invalid_reference_or_final_status_never_passes_full_validation(self):
        pack={"question":"工具是什么？","qa_version":3,"evidence":[make_evidence()]}
        for mode, expected_events in [("valid",1),("invalid_reference",0),("invalid_final",1),("truncated",1),("timeout",1)]:
            model=StreamingModel(mode); events=[]
            result=answer_from_pack(pack,model,on_event=events.append)
            self.assertEqual(model.calls,1)
            self.assertEqual(sum(e["type"]=="block" for e in events),expected_events)
            self.assertEqual(result["status"]=="CITED_DRAFT",mode=="valid")
            self.assertIn("generation_seconds",result["timings"])
            if mode=="valid":
                validate_v2(json.dumps(result["answer"]),pack["evidence"])


class CacheAndBudgetTests(unittest.TestCase):
    def test_cached_parse_still_rechecks_same_size_source_and_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=Source("fixture","examples","工具","example/repo","a"*40,"tool.md")
            raw="# Tools\n\nTools execute actions and return results. 工具执行动作并返回结果。".encode()
            prepare_corpus([source],root,lambda _:raw);build_index(root,root/"index.sqlite3")
            verified_corpus(root,root/"index.sqlite3")
            from study_rag import core
            with patch("study_rag.core.split_document",wraps=core.split_document) as split:
                verified_corpus(root,root/"index.sqlite3");split.assert_not_called()
            (root/"fixture.md").write_bytes(raw.replace(b"Tools",b"Wrong"))
            with self.assertRaises(CorpusError):verified_corpus(root,root/"index.sqlite3")
            (root/"fixture.md").write_bytes(raw)
            with closing(sqlite3.connect(root/"index.sqlite3")) as db,db:
                db.execute("UPDATE chunks SET payload='{}'")
            with self.assertRaises(CorpusError):verified_corpus(root,root/"index.sqlite3")

    def test_independent_budget_limits_failures_and_reserved_crashes_count(self):
        with tempfile.TemporaryDirectory() as temp:
            budget=TrialBudget(Path(temp)/"budget.sqlite3")
            for phase, count in budget.limits.items():
                for i in range(count):
                    call=budget.reserve(phase,str(i),[])
                    if i:budget.finish(call,error="offline fixture")
            self.assertEqual(budget.summary()["calls_reserved"],20)
            with self.assertRaises(ValueError):budget.reserve("dev","extra",[])
            with self.assertRaises(ValueError):budget.reserve("baseline","0",[])
            self.assertLessEqual(budget.summary()["tokens_reserved"],1_000_000)


class StreamWebTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing tiny public-contract fixture, not downloaded corpus
        # or the user's account database.
        from test_qa import V3IntegrationTests
        self.fixture=V3IntegrationTests(methodName="runTest");self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root,self.data=self.fixture.root,self.fixture.data
        self.store=Store(self.root/"users.sqlite3",user_daily_limit=10)

    def auth(self,client,name="stream-test"):
        response=client.post("/api/register",json={"username":name,"password":"offline-test-password-123"})
        self.assertEqual(response.status_code,200)
        client.headers["X-CSRF-Token"]=response.json()["csrf"]
        chat=client.post("/api/chats",json={"title":"public fixture"}).json()["id"]
        return {"chat_id":chat,"request_key":str(uuid4()),"question":"MCP architecture","use_history":False}

    def events(self,response):
        self.assertEqual(response.status_code,200)
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    def test_stream_and_json_share_save_dedup_and_failure_retraction_contract(self):
        model=StreamingModel();app=create_app(data_dir=self.data,store=self.store,model=model)
        with TestClient(app) as client:
            body=self.auth(client)
            events=self.events(client.post("/api/ask/stream",json=body))
            self.assertIn("block",[e["type"] for e in events])
            result=events[-1]["result"];self.assertEqual(result["status"],"CITED_DRAFT")
            self.assertLessEqual(result["timings"]["first_validated_block_seconds"],result["timings"]["total_seconds"])
            reused=client.post("/api/ask",json=body).json();self.assertTrue(reused["reused"])
            replay=self.events(client.post("/api/ask/stream",json=body));self.assertEqual(len(replay),1)
            self.assertEqual(model.calls,1)
            self.assertEqual(len(client.get("/api/chats/"+body["chat_id"]).json()),1)
            body["question"]="different question"
            self.assertEqual(client.post("/api/ask/stream",json=body).status_code,409)

    def test_authorization_and_scope_fail_before_stream_headers_or_model(self):
        model=StreamingModel();app=create_app(data_dir=self.data,store=self.store,model=model)
        with TestClient(app) as client,TestClient(app) as other:
            body=self.auth(client);self.auth(other,"stream-other")
            self.assertEqual(other.post("/api/ask/stream",json=body).status_code,404)
            body["book"]="unknown"
            self.assertEqual(client.post("/api/ask/stream",json=body).status_code,422)
            self.assertEqual(model.calls,0)

    def test_final_failure_has_no_answer_and_zero_call_retrieval_still_works(self):
        model=StreamingModel("invalid_final");app=create_app(data_dir=self.data,store=self.store,model=model)
        with TestClient(app) as client:
            body=self.auth(client)
            events=self.events(client.post("/api/ask/stream",json=body))
            self.assertIn("block",[e["type"] for e in events])
            result=events[-1]["result"]
            self.assertIsNone(result["answer"]);self.assertEqual(result["failure_stage"],"response_schema")
            body.update(request_key=str(uuid4()),explain=False)
            result=self.events(client.post("/api/ask/stream",json=body))[-1]["result"]
            self.assertEqual(result["status"],"RETRIEVAL_ONLY");self.assertEqual(model.calls,1)

    def test_legacy_claims_can_stream_without_rewriting_history(self):
        data=self.root/"legacy";source=Source("legacy","examples","工具","example/repo","a"*40,"tool.md")
        prepare_corpus([source],data,lambda _:b"# Tools\n\nTools execute actions and return results with defined inputs and outputs.")
        build_index(data,data/"index.sqlite3");model=StreamingModel()
        with TestClient(create_app(data_dir=data,store=self.store,model=model)) as client:
            body=self.auth(client);body["question"]="Tools execute actions"
            events=self.events(client.post("/api/ask/stream",json=body))
            self.assertIn("claims",events[-1]["result"]["answer"])
            self.assertTrue(any(e["type"]=="block" for e in events))

    def test_real_http_disconnect_finishes_one_save_and_one_budget_reservation(self):
        gate=threading.Event();model=StreamingModel(gate=gate)
        app=create_app(data_dir=self.data,store=self.store,model=model)
        sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level="error"))
        worker=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);worker.start()
        try:
            deadline=time.monotonic()+5
            while not server.started:
                if time.monotonic()>deadline: self.fail("HTTP fixture failed to start")
                time.sleep(.01)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}",timeout=5) as client:
                body=self.auth(client)
                with client.stream("POST","/api/ask/stream",json=body) as response:
                    for line in response.iter_lines():
                        if line.startswith("data: ") and json.loads(line[6:])["type"]=="block":break
                self.assertTrue(model.entered.wait(1))
                self.assertEqual(client.post("/api/ask/stream",json=body).status_code,429)
                gate.set();deadline=time.monotonic()+3
                while True:
                    rows=client.get("/api/chats/"+body["chat_id"]).json()
                    if rows:break
                    if time.monotonic()>deadline:self.fail("Disconnected generation not saved")
                    time.sleep(.02)
                self.assertEqual(rows[0]["result"]["status"],"CITED_DRAFT")
                self.assertEqual(client.post("/api/ask",json=body).json()["quota"]["used"],1)
                self.assertEqual(model.calls,1)
        finally:
            gate.set();server.should_exit=True;worker.join(6);sock.close()


class ClientReuseTests(unittest.TestCase):
    def test_nonstream_client_reused_and_explicitly_closed(self):
        with patch.dict("os.environ",{"DEEPSEEK_API_KEY":"offline-placeholder"}),patch("study_rag.rag.OpenAI") as factory:
            client=factory.return_value
            client.chat.completions.create.return_value=SimpleNamespace(model="deepseek-flash",usage=None,
                choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(content='{"valid":"json"}'))])
            model=DeepSeekModel();model.generate([]);model.generate([]);model.close()
            factory.assert_called_once();self.assertEqual(client.chat.completions.create.call_count,2);client.close.assert_called_once()

    def test_stream_usage_only_tail_and_incomplete_output_are_handled_once(self):
        for reason in ("stop","length",None):
            with self.subTest(reason=reason),patch.dict("os.environ",{"DEEPSEEK_API_KEY":"offline-placeholder"}),patch("study_rag.rag.OpenAI") as factory:
                stream=MagicMock()
                parts=[SimpleNamespace(model="deepseek-flash",usage=None,choices=[SimpleNamespace(finish_reason=None,delta=SimpleNamespace(content='{"中文":"内容"}'))]),
                       SimpleNamespace(model="deepseek-flash",usage=SimpleNamespace(prompt_tokens=7,completion_tokens=8),choices=[])]
                if reason:parts.insert(1,SimpleNamespace(model="deepseek-flash",usage=None,choices=[SimpleNamespace(finish_reason=reason,delta=SimpleNamespace(content=None))]))
                stream.__iter__.return_value=iter(parts);factory.return_value.chat.completions.create.return_value=stream
                model=DeepSeekModel();seen=[]
                if reason=="stop":
                    raw,usage=model.generate_stream([],seen.append);self.assertEqual(usage["output_tokens"],8)
                else:
                    with self.assertRaises(ProviderError):model.generate_stream([],seen.append)
                self.assertEqual(seen,['{"中文":"内容"}']);factory.return_value.chat.completions.create.assert_called_once();model.close()


if __name__=="__main__":unittest.main()
