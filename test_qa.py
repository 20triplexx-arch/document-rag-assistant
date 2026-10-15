"""Typed QA contracts / offsets / source isolation. No live calls or full gold runs."""
import json,hashlib,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient
from study_rag.core import Source,prepare_corpus,build_index,verified_corpus,validate_text,validate_catalog,CorpusError
from study_rag.code_index import python_chunks,markdown_code_chunks
from study_rag.answer_schema import AnswerV2,validate_v2,as_blocks,answer_units,quote_locations
from study_rag.qa_evaluation import QASpan,QAPoint,QAQuestion,score_qa
from study_rag.qa_budget import QABudget,PHASE_LIMITS
from study_rag.question_plan import question_plan,followups_for
from study_rag.qa_retrieval import retrieve_qa,body_mask
from study_rag.rag import answer_from_pack
from study_rag.conversation import prepare_context
from study_rag.store import Store
from study_rag.web import create_app
from qa_import import local_mdx_dependencies

def blob(raw):return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
def evidence(sid="a",eid="E1",text="A tool is a callable function with defined input and output.",kind="prose"):
    return {"source_id":sid,"evidence_id":eid,"book":"examples","section":"概念","text":text,"context_text":text,
        "content_type":kind,"start_char":0,"end_char":len(text),"start_line":1,"end_line":text.count("\n")+1}
def paragraph(text="工具负责执行动作。",refs=None):return {"type":"paragraph","text":text,"references":refs or [{"evidence_id":"E1","quote":"A tool is a callable function"}]}
def answer(blocks=None,status="answered",missing=""):
    return {"schema_version":2,"status":status,"blocks":[paragraph()] if blocks is None else blocks,"missing_information":missing}
class Model:
    model_name="deepseek-flash"
    def __init__(self,payload):self.payload=payload;self.calls=0
    def generate(self,messages):self.calls+=1;self.messages=messages;return json.dumps(self.payload),{"model":self.model_name,"attempts":1}

class AnswerTests(unittest.TestCase):
    def test_display_links_and_emphasis_keep_raw_source_positions(self):
        text="A [tool](/tools) returns **data** from `runtime.state`."
        e=evidence(text=text);q="A tool returns data from runtime.state."
        refs=[{"evidence_id":"E1","quote":q}]
        a=validate_v2(json.dumps(answer([paragraph(refs=refs)])),[e]).model_dump()
        positions=quote_locations(a,[e]);self.assertEqual(positions[0]["start_char"],0);self.assertEqual(positions[0]["end_char"],len(text))
    def test_answered_default_gap_field_is_present_in_api_contract(self):
        a=answer();a.pop("missing_information");self.assertEqual(AnswerV2.model_validate(a).model_dump()["missing_information"],"")
    def test_multiple_sources_preserved_and_located(self):
        es=[evidence(),evidence("b","E2","A memory is stored information about previous interactions.")]
        refs=[{"evidence_id":"E1","quote":"A tool is a callable function"},{"evidence_id":"E2","quote":"A memory is stored information"}]
        a=validate_v2(json.dumps(answer([paragraph(refs=refs)])),es).model_dump()
        self.assertEqual([p["source_id"] for p in quote_locations(a,es)],["a","b"])
        self.assertEqual(len(answer_units(a)[0]["references"]),2)
    def test_unknown_number_rejected(self):
        with self.assertRaises(CorpusError):validate_v2(json.dumps(answer([paragraph(refs=[{"evidence_id":"E8","quote":"A tool is a callable function"}])])),[evidence()])
    def test_non_contiguous_quote_rejected_even_if_mask_projection_bridges(self):
        e=evidence(text="A tool is useful.\nSECRET HIDDEN CODE\nIt returns results.");e["context_text"]="A tool is useful. It returns results."
        with self.assertRaises(CorpusError):validate_v2(json.dumps(answer([paragraph(refs=[{"evidence_id":"E1","quote":"A tool is useful. It returns results."}])])),[e])
    def test_source_code_keeps_indentation(self):
        code="def example():\n    if True:\n        return 12\n";e=evidence(text=code,kind="code")
        a=answer([{"type":"code","origin":"source","language":"python","code":code,"references":[{"evidence_id":"E1","quote":"    if True:\n        return 12"}]}])
        self.assertEqual(validate_v2(json.dumps(a),[e]).blocks[0].code,code)
        a["blocks"][0]["code"]=code.replace("        return","return")
        with self.assertRaises(CorpusError):validate_v2(json.dumps(a),[e])
    def test_code_quote_cannot_drop_internal_indentation(self):
        e=evidence(text="    if True:\n        return 12",kind="code")
        with self.assertRaises(CorpusError):validate_v2(json.dumps(answer([paragraph(refs=[{"evidence_id":"E1","quote":"if True:\nreturn 12"}])])),[e])
    def test_table_width_and_reference_validation(self):
        table={"type":"table","columns":["方案","条件"],"rows":[{"cells":["工具","执行动作"],"references":paragraph()["references"]}]}
        validate_v2(json.dumps(answer([table])),[evidence()])
        table["rows"][0]["cells"].pop()
        with self.assertRaises(ValueError):AnswerV2.model_validate(answer([table]))
    def test_illustrative_code_is_distinct_from_original(self):
        b={"type":"code","origin":"illustrative","language":"python","code":"# teaching example\nprint('example')","references":paragraph()["references"]}
        validate_v2(json.dumps(answer([b])),[evidence()])
        b["origin"]="source"
        with self.assertRaises(CorpusError):validate_v2(json.dumps(answer([b])),[evidence()])
    def test_partial_and_insufficient_shape(self):
        for a in [answer(status="partial"),answer([],"insufficient",""),answer(status="answered",missing="missing")]:
            with self.assertRaises(ValueError):AnswerV2.model_validate(a)
        AnswerV2.model_validate(answer([],"insufficient","缺少协议版本和运行证据。"))
    def test_legacy_read_adapter_does_not_mutate(self):
        old={"status":"answered","format":"steps","claims":[{"heading":"旧标题","text":"原有内容","evidence_id":"E1","quote":"原文依据至少十个字符"}],"missing_information":""};copy=deepcopy(old)
        self.assertTrue(as_blocks(old)["blocks"][0]["ordered"]);self.assertEqual(old,copy)
    def test_single_generation_structure_and_quote_failures(self):
        pack={"question":"工具是什么？","qa_version":3,"evidence":[evidence()]}
        for payload,stage in [({**answer(),"private-field":"must not leak"},"response_schema"),(answer([paragraph(refs=[{"evidence_id":"E1","quote":"Fabricated continuous source quote"}])]),"quote_source")]:
            model=Model(payload);r=answer_from_pack(pack,model)
            self.assertEqual(model.calls,1);self.assertEqual(r["failure_stage"],stage);self.assertIsNone(r["answer"])
            self.assertNotIn("must not leak",json.dumps(r))
    def test_raw_and_no_evidence_call_zero(self):
        model=Model(answer());pack={"question":"工具是什么？","qa_version":3,"evidence":[evidence()]}
        answer_from_pack(pack,model,explain=False);pack["evidence"]=[];answer_from_pack(pack,model);self.assertEqual(model.calls,0)
    def test_prompt_contract_and_brief_question(self):
        model=Model(answer());r=answer_from_pack({"question":"一句话解释工具","qa_version":3,"evidence":[evidence()]},model)
        self.assertEqual(r["status"],"CITED_DRAFT");self.assertEqual(json.loads(model.messages[1]["content"])["ANSWER_SCHEMA"],AnswerV2.model_json_schema())
        self.assertEqual(len(r["followups"]),2)

class SourceTests(unittest.TestCase):
    def test_unicode_python_offsets_decorators_and_nested_class(self):
        source=Source("python-test","examples","实现","example/repo","a"*40,"cases/tools.py")
        raw='中文 = 1\n@decorator\ndef function():\n    """中文说明"""\n    return 中文\n\nclass C:\n    def method(self):\n        return 2\n'.encode()
        text=validate_text(raw);chunks=python_chunks(source,raw)
        for c in chunks:self.assertEqual(c.text,text[c.start_char:c.end_char])
        self.assertTrue(any(c.text.startswith("@decorator") for c in chunks));self.assertTrue(any("def method" in c.text for c in chunks))
    def test_fence_fake_heading_is_code_with_raw_position(self):
        source=Source("mdx-test","examples","正文","example/repo","a"*40,"page.mdx")
        raw=b'---\ntitle: Example\n---\n# Body\nUseful teaching body.\n```python\n# fake heading\nprint(1)\n```\n'
        c=markdown_code_chunks(source,raw)[0];self.assertEqual(c.text,"# fake heading\nprint(1)\n");self.assertEqual(c.start_line,7)
        mask=body_mask(raw.decode(),True);self.assertEqual(len(mask),len(raw));self.assertNotIn("title:",mask);self.assertNotIn("fake heading",mask)
    def test_recursive_dependency_resolution_and_remote_or_js_exclusion(self):
        text="import A from '/snippets/one.mdx';\nimport B from '../two.mdx';\nimport C from '/widget.jsx';\nimport D from 'https://x/a.mdx';"
        self.assertEqual(local_mdx_dependencies(text,"src/docs/page.mdx",{"src/snippets/one.mdx","src/two.mdx"},"langchain-ai/docs"),["src/snippets/one.mdx","src/two.mdx"])
        with self.assertRaises(ValueError):local_mdx_dependencies("import A from './missing.mdx'","a.mdx",set(),"example/repo")
    def test_nested_list_fences_are_separate_code_not_concept(self):
        source=Source("nested-code","examples","正文","example/repo","a"*40,"nested.md")
        raw=b'# Body\n\n    ```python\n    tool_call_id = 123\n    ```\n\nTool execution returns a result.\n'
        chunks=markdown_code_chunks(source,raw)
        self.assertEqual(chunks[0].text,"    tool_call_id = 123\n")
        self.assertNotIn("tool_call_id",body_mask(raw.decode()))
    def test_long_query_keeps_tail_and_detects_versions(self):
        q="字"*9400+" 请比較 MCP 2025-11-25 与 2026-07-28"
        plan=question_plan(q);self.assertEqual(plan["question"],q);self.assertIn("2026-07-28",plan["query_windows"][-1]);self.assertTrue(plan["version_comparison"])
    def test_followups_are_contextual_and_at_most_two(self):
        f=followups_for("Hybrid RAG 的 Python 代码怎么处理异常？");self.assertEqual(len(f),2);self.assertTrue(all("Hybrid RAG" in x["question"] for x in f))
    def test_named_new_topic_resets_old_summary(self):
        old={"question":"RAG 如何检索？","result":{"status":"CITED_DRAFT","answer":answer(),"book_filter":None}}
        self.assertEqual(prepare_context("This MCP architecture has which components?",[old],None)["turns"],[])
        self.assertEqual(len(prepare_context("它如何工作？",[old],None)["turns"]),1)

class ScoringBudgetTests(unittest.TestCase):
    def test_conjunction_alternatives_partial_and_duplicates(self):
        text="A tool is a callable function. A tool returns execution results."
        spans=[]
        for a,b in [(0,29),(30,len(text))]:spans.append(QASpan(source_id="a",start_char=a,end_char=b,start_line=1,end_line=1,quote=text[a:b],kind="prose",rationale="fixture"))
        q=QAQuestion(id="TEST",topic="tools",split="dev",question="tools",group="g",book=None,
            points=[QAPoint(id="both",answer="both",supports=spans,coverage="all"),QAPoint(id="either",answer="either",supports=spans)],
            distractors=[],answerability="answerable",missing_information="",review_origin="AI; no human approval",review_scope={})
        e=evidence(text=text);e["end_char"]=29;e["context_text"]=text[:29]
        r=score_qa(q,[e,e],{"a":text},{"a":text});self.assertEqual(r["covered_points"],["either"]);self.assertTrue(r["evidence"][1]["duplicate"])
        unknown=evidence("b");r=score_qa(q,[unknown],{"a":text},{"a":text});self.assertEqual(r["evidence"][0]["judgment"],"unjudged")
    def test_masked_concept_quote_not_a_hit(self):
        text="A tool is a callable function.";span=QASpan(source_id="a",start_char=0,end_char=len(text),start_line=1,end_line=1,quote=text,kind="prose",rationale="fixture")
        from study_rag.qa_evaluation import span_matches
        self.assertFalse(span_matches(span,evidence(text=text),{"a":text},{"a":" "*len(text)}))
    def test_budget_shared_across_phases_and_failures_count(self):
        with tempfile.TemporaryDirectory() as temp:
            b=QABudget(Path(temp)/"budget.sqlite3")
            for phase,n in PHASE_LIMITS.items():
                for i in range(n):call=b.reserve(phase,str(i),[{"role":"user","content":"public"}]);b.finish(call,error="failure" if i==0 else None)
            self.assertEqual(b.summary()["calls_reserved"],60)
            with self.assertRaises(ValueError):b.reserve("retest","overflow",[])
            self.assertLessEqual(b.summary()["tokens_reserved"],3000000)
    def test_budget_lost_response_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            b=QABudget(Path(temp)/"b.sqlite3");b.reserve("candidate","q",[])
            with self.assertRaises(ValueError):b.reserve("candidate","q",[])
            b.freeze("gold","one")
            with self.assertRaises(ValueError):b.freeze("gold","two")

class V3IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.sources=[];self.raws={};chapters={};books=[]
        declarations=[("cases","case_collection",[("case-parent","cases/README.md","# Case\n\n工具接收参数，返回执行结果。案例用于解释工具调用机制。",{"kind":"case","topics":["工具调用"]}),
            ("case-code","cases/tools.py","def calculate(value: int):\n    \"\"\"工具执行一次计算并返回结果。\"\"\"\n    return value + 1\n",{"kind":"implementation","content_type":"code","parent_source_ids":["case-parent"],"applicable_versions":["unknown"]})]),
            ("mcp-specification","official_documentation",[("spec-old","2025/index.mdx","# Architecture\n\nMCP is a stateful session protocol. The host manages clients and servers.",{"kind":"official","content_type":"prose","applicable_versions":["2025-11-25"]}),
            ("spec-new","2026/index.mdx","# Architecture\n\nMCP is a stateless protocol. Every request carries protocol version and capabilities. The host manages clients and servers.",{"kind":"official","content_type":"prose","applicable_versions":["2026-07-28"]})])]
        for bi,(book,kind,rows) in enumerate(declarations):
            repo="example/"+book;license_raw=b'Test-only permission notice'
            books.append({"book":book,"display_name":book,"order":bi,"kind":kind,"repository":repo,"commit":"a"*40,
                "license":"TEST","license_path":"LICENSE","license_text":license_raw.decode(),"license_git_blob":blob(license_raw)})
            for order,(sid,path,text,extra) in enumerate(rows):
                source=Source(sid,book,sid,repo,"a"*40,path);raw=text.encode();self.sources.append(source);self.raws[sid]=raw
                chapters[sid]={"language":"en","canonical_path":path,"order":order,"git_blob":blob(raw),"bytes":len(raw),**extra}
        chapters["case-parent"]["implementation_files"]=[{"path":"cases/tools.py","git_blob":blob(self.raws["case-code"]),"bytes":len(self.raws["case-code"])}]
        self.catalog={"version":3,"books":books,"chapters":chapters};self.data=self.root/"data"
        prepare_corpus(self.sources,self.data,lambda s:self.raws[s.source_id],catalog=self.catalog);build_index(self.data,self.data/"index.sqlite3")
    def test_byte_and_metadata_integrity_and_reuse(self):
        self.assertEqual(prepare_corpus(self.sources,self.data,catalog=self.catalog)["network_requests"],0)
        changed=deepcopy(self.catalog);changed["chapters"]["case-code"]["parent_source_ids"]=[]
        with self.assertRaises(CorpusError):validate_catalog(changed,self.sources)
        (self.data/"case-code.md").write_bytes(b"corrupt")
        with self.assertRaises(CorpusError):verified_corpus(self.data,self.data/"index.sqlite3")
    def test_protocol_default_explicit_old_and_comparison(self):
        for question,expected in [("MCP architecture",{"spec-new"}),("MCP 2025-11-25 architecture",{"spec-old"}),("MCP 2025-11-25 与 2026-07-28 比较",{"spec-new","spec-old"})]:
            pack=retrieve_qa(self.data,self.data/"index.sqlite3",question,"mcp-specification")
            self.assertEqual({e["source_id"] for e in pack["evidence"]},expected)
        self.assertEqual(retrieve_qa(self.data,self.data/"index.sqlite3","MCP 2024-01-01","mcp-specification")["evidence"],[])
    def test_library_case_count_and_code_metadata(self):
        with TestClient(create_app(data_dir=self.data,store=Store(self.root/"users.sqlite3"),model=Model(answer()))) as client:
            data=client.get("/api/library").json();book=next(b for b in data["books"] if b["book"]=="cases")
            self.assertEqual(book["documents"],1);self.assertEqual(book["source_files"],2);self.assertEqual(book["implementation_files"],1)
            self.assertTrue(book["chapters"][0]["implementation_links"][0]["ingested"]);self.assertEqual(data["answer_schema_version"],2)
    def test_qa_unknown_scope_and_accounts_keep_call_budget(self):
        model=Model(answer());store=Store(self.root/"users.sqlite3",user_daily_limit=1)
        app=create_app(data_dir=self.data,store=store,model=model)
        with TestClient(app) as a,TestClient(app) as b:
            for i,client in enumerate((a,b)):
                auth=client.post("/api/register",json={"username":"qa-test-"+str(i),"password":"test-password-only-123"}).json();client.headers["X-CSRF-Token"]=auth["csrf"]
            chat=a.post("/api/chats",json={"title":"private fixture"}).json()["id"]
            body={"chat_id":chat,"request_key":"b"*32,"question":"MCP architecture","book":"missing"}
            self.assertEqual(a.post("/api/ask",json=body).status_code,422)
            body["book"]="mcp-specification";self.assertEqual(b.post("/api/ask",json=body).status_code,404)
            self.assertEqual(model.calls,0)
            self.assertEqual(a.post("/api/ask",json=body).status_code,200)
            self.assertEqual(model.calls,1)
            body["request_key"]="c"*32
            self.assertEqual(a.post("/api/ask",json=body).status_code,429)
            self.assertEqual(model.calls,1)
    def test_single_collection_can_supply_more_than_two_evidence_items(self):
        sources=[Source("same-"+str(i),"examples","工具工作机制 "+str(i),"example/repo","a"*40,str(i)+".md") for i in range(6)]
        data=self.root/"many";prepare_corpus(sources,data,lambda s:("# 工具机制\n\n模型决定调用工具，程序执行工具，并把执行结果交回模型。不同函数返回不同计算结果。\n"+s.source_id).encode());build_index(data,data/"index.sqlite3")
        pack=retrieve_qa(data,data/"index.sqlite3","工具执行机制是什么？","examples")
        self.assertGreater(len(pack["evidence"]),2);self.assertLessEqual(len(pack["evidence"]),8)
        self.assertLessEqual(sum(len(e["context_text"]) for e in pack["evidence"]),20000)
    def test_lab_oracle_uses_all_conjunctive_supports_without_book_quota(self):
        from study_rag.support_context import annotated_evidence
        from types import SimpleNamespace
        manifest,chunks,sources,raws=verified_corpus(self.data,self.data/"index.sqlite3")
        texts={s.source_id:validate_text(raw) for s,raw in raws};masks={sid:body_mask(text, sources[sid].path.endswith('.mdx')) for sid,text in texts.items()}
        spans=[]
        for sid in ('case-parent','spec-old','spec-new'):
            text=texts[sid];start=text.index('\n\n')+2
            spans.append(SimpleNamespace(source_id=sid,start_char=start,end_char=len(text),kind='prose',start_line=3,end_line=3))
        q=SimpleNamespace(points=[SimpleNamespace(supports=spans,coverage='all')])
        ev=annotated_evidence(q,(None,None,manifest,chunks,sources,texts,masks));self.assertEqual(len(ev),3)
        self.assertEqual({e['source_id'] for e in ev},{'case-parent','spec-old','spec-new'})

if __name__=="__main__":unittest.main()
