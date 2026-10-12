"""Public synthetic corpus only. No real model calls or production account access."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from importlib.util import find_spec
from unittest.mock import patch

from fastapi.testclient import TestClient
from study_rag.core import Source,prepare_corpus,build_index
from study_rag.evaluation import load_dataset,EvaluationDataset,validate_dataset
from study_rag.lab import Lab
from study_rag.lab_models import ExperimentConfig,ClaimReview,DatasetReview,ImportRequest
from study_rag.lab_store import BudgetExhausted
from study_rag.diagnostics import diagnose_rules,validate_judgment,calibration
from study_rag.store import Store
from study_rag.web import create_app

TEXT="# 教材\n\n## RAG 与 Memory\n\nRAG 先检索外部资料，再根据证据生成回答。Memory 保存下一次需要的状态。\n"
QUOTE="RAG 先检索外部资料，再根据证据生成回答。"


class OfflineModel:
    model_name="test-offline"
    def __init__(self):self.calls=0
    def generate(self,messages):
        self.calls+=1
        data=json.loads(messages[-1]["content"])
        if "reference_points" in data:
            return json.dumps({"diagnostics":[{"claim_id":"C1.1","text":QUOTE,"judgment":"supported",
                "rationale":"测试替身按合成原文返回，非真实裁判质量证明。","evidence_ids":["E1"],"origin":"automatic","spans":[]}],
                "covered_point_ids":["p1"],"coverage_rationale":"合成回答包含参考事实"},ensure_ascii=False),{"prompt_tokens":10,"output_tokens":20}
        return json.dumps({"status":"answered","claims":[{"text":QUOTE,"evidence_id":"E1","quote":QUOTE}],
                          "missing_information":""},ensure_ascii=False),{"prompt_tokens":10,"output_tokens":20}


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/"corpus"
        prepare_corpus([Source("a","course","测试","example/test","a"*40,"a.md")],self.data,lambda _:TEXT.encode())
        build_index(self.data,self.data/"index.sqlite3")
        from study_rag.core import verified_chunks
        manifest,chunks,_=verified_chunks(self.data,self.data/"index.sqlite3")
        a=TEXT.index(QUOTE);b=a+len(QUOTE)
        span=dict(source_id="a",start_char=a,end_char=b,start_line=TEXT.count('\n',0,a)+1,end_line=TEXT.count('\n',0,b-1)+1,quote=QUOTE,rationale="Synthetic explicit fact")
        questions=[]
        for i,split in enumerate(["dev","calibration","holdout"],1):
            questions.append(dict(id=f"Q{i}",group=f"g{i}",split=split,category="single",question=f"RAG 怎样生成回答（题{i}）？",book="course",
                required_books=["course"],answerability="answerable",points=[dict(id="p1",answer=QUOTE,supports=[span])],
                distractors=[],missing_information=[],review_scope=None,review_status="approved",review_note="Synthetic fixture"))
        self.payload=dict(schema_version=2,dataset_version="synthetic-v2",annotated_on="2026-10-12",annotation_method="Synthetic tests",
            corpus_version=manifest["corpus_version"],documents=1,baseline_chunks=len(chunks),questions=questions)
        self.path=self.root/"dataset.json";self.write_dataset()
        self.model=OfflineModel()
        self.lab=Lab(self.data,self.root/"experiments.sqlite3",datasets={"agent-learning-v1":self.path,"agent-learning-v2":self.path},model=self.model)
        self.addCleanup(self.lab.close)

    def write_dataset(self):self.path.write_text(json.dumps(self.payload,ensure_ascii=False),encoding="utf-8")
    def config(self,**kwargs):
        return ExperimentConfig(request_key=f"test-key-{len(self.lab.store.list())}",**kwargs)
    def execute(self,config):
        rid=self.lab.create(config)["id"]
        owner="test-worker"
        self.assertEqual(self.lab.store.claim(owner),rid)
        self.lab.execute(rid,owner);self.lab.store.release(owner)
        return self.lab.report(rid)

    def test_generic_dataset_and_group_isolation(self):
        loaded=load_dataset(self.path,self.data)
        self.assertIsInstance(loaded[0],EvaluationDataset)
        self.payload["questions"][1]["group"]="g1";self.write_dataset()
        with self.assertRaisesRegex(ValueError,"跨越"):load_dataset(self.path,self.data)

    def test_forged_span_is_rejected(self):
        self.payload["questions"][0]["points"][0]["supports"][0]["quote"]="wrong"
        self.write_dataset()
        with self.assertRaisesRegex(ValueError,"摘录"):load_dataset(self.path,self.data)

    def test_pending_requires_explicit_draft_or_human_review(self):
        self.payload["questions"][0]["review_status"]="pending";self.write_dataset()
        with self.assertRaisesRegex(ValueError,"待人工"):self.lab.create(self.config())
        draft=self.execute(self.config(allow_pending=True))
        self.assertEqual(draft["snapshot"]["pending_questions"],["Q1"])
        self.lab.approve("agent-learning-v1",DatasetReview(question_id="Q1",rationale="确认合成原文"),"reviewer")
        result=self.execute(self.config())
        self.assertFalse(result["snapshot"]["pending_questions"])
        self.assertTrue(self.lab.report(draft["id"])["snapshot"]["pending_questions"])

    def test_retrieval_is_reproducible_and_never_calls_model(self):
        a=self.execute(self.config());b=self.execute(self.config())
        self.assertEqual(a["summary"],b["summary"])
        self.assertEqual(self.model.calls,0)
        self.assertEqual(a["summary"]["support_point_coverage"],1)
        self.assertTrue(a["results"][0]["trace"]["books"])
        comparison=self.lab.compare(a["id"],b["id"])
        self.assertTrue(comparison["complete_pair"])
        self.assertEqual(comparison["changes"],{"unchanged":1})

    def test_request_key_idempotence_and_mismatch(self):
        c=self.config();a=self.lab.create(c);b=self.lab.create(c)
        self.assertEqual(a["id"],b["id"]);self.assertTrue(b["reused"])
        with self.assertRaisesRegex(ValueError,"编号"):self.lab.create(c.model_copy(update={"body_only":True}))

    def test_snapshot_change_fails_before_execution(self):
        rid=self.lab.create(self.config())["id"]
        self.payload["dataset_version"]="changed";self.write_dataset()
        self.lab.store.claim("test");self.lab.execute(rid,"test");self.lab.store.release("test")
        self.assertEqual(self.lab.store.get(rid)["state"],"failed")
        self.assertFalse(self.lab.store.results(rid))

    def test_loaded_code_cannot_claim_new_disk_snapshot(self):
        with patch("study_rag.lab.code_contract",return_value={"changed":"hash"}):
            with self.assertRaisesRegex(ValueError,"重启"):self.lab.create(self.config())

    def test_live_requires_explicit_budgets(self):
        with self.assertRaises(ValueError):self.config(mode="generate")
        with self.assertRaises(ValueError):self.config(live=True)

    def test_judge_atomic_claim_and_calibration_review_preserved(self):
        r=self.execute(self.config(mode="judge",live=True,call_budget=2,token_budget=1000000,split="calibration"))
        self.assertEqual(r["state"],"completed");self.assertEqual(self.model.calls,2)
        self.assertEqual(r["generation"]["supported_claim_ratio"],1)
        self.lab.store.review(r["id"],ClaimReview(question_id="Q2",claim_id="C1.1",judgment="insufficient",rationale="演示人工分歧").model_dump(),"reviewer")
        report=self.lab.report(r["id"])
        self.assertEqual(report["calibration"]["agreement"],0)
        self.assertEqual(report["results"][0]["diagnostics"][0]["judgment"],"supported")
        self.assertEqual(report["human_reviews"][0]["judgment"],"insufficient")

    def test_judge_coverage_omission_and_forged_evidence_rejected(self):
        loaded=self.lab.dataset("agent-learning-v1");q=loaded[0].questions[0]
        answer={"claims":[{"text":QUOTE}]}
        raw=json.dumps({"diagnostics":[],"covered_point_ids":[],"coverage_rationale":""})
        with self.assertRaisesRegex(ValueError,"遗漏"):validate_judgment(raw,answer,[],q)
        raw=json.dumps({"diagnostics":[dict(claim_id="C1.1",text=QUOTE,judgment="supported",rationale="x",evidence_ids=["E9"],origin="automatic",spans=[])],"covered_point_ids":[],"coverage_rationale":""})
        with self.assertRaisesRegex(ValueError,"出处"):validate_judgment(raw,answer,[],q)

    def test_real_quote_does_not_auto_prove_claim(self):
        evidence=[dict(evidence_id="E1",source_id="a",start_char=0,end_char=len(TEXT),context_text=TEXT)]
        d=diagnose_rules({"claims":[{"text":"RAG 不需要外部资料。","quote":QUOTE,"evidence_id":"E1"}]},evidence)
        self.assertEqual(d[0]["judgment"],"unjudgeable")

    def test_budget_stops_judge_and_preserves_generate_response(self):
        r=self.execute(self.config(mode="judge",live=True,call_budget=1,token_budget=1000000))
        self.assertEqual(r["state"],"budget_exhausted");self.assertEqual(self.model.calls,1)
        self.assertEqual(len(self.lab.store.call_usage(r["id"])),1)
        self.assertEqual(r["completed"],1)
        self.assertTrue(r["results"][0]["answer"])
        self.assertEqual(r["results"][0]["status"],"MODEL_BUDGET_STOPPED")

    def test_interrupted_call_is_never_repeated(self):
        config=self.config(mode="generate",live=True,call_budget=2,token_budget=1000000)
        rid=self.lab.create(config)["id"];self.lab.store.claim("owner")
        messages=[{"role":"user","content":"test"}]
        self.lab.store.reserve_call(rid,"key",messages,100)
        with self.assertRaisesRegex(ValueError,"不自动重试"):self.lab.store.reserve_call(rid,"key",messages,100)
        self.lab.store.release("owner")
        self.assertEqual(self.model.calls,0)

    def test_completed_call_replays_without_spending_again(self):
        rid=self.lab.create(self.config(mode="generate",live=True,call_budget=1,token_budget=1000000))["id"]
        self.lab.store.claim("owner")
        self.lab.store.reserve_call(rid,"key",[],100)
        self.lab.store.finish_call(rid,"key","cached",{"output_tokens":2})
        replay=self.lab.store.reserve_call(rid,"key",[],100)
        self.assertEqual(replay,("cached",{"output_tokens":2}))
        self.assertEqual(self.lab.store.get(rid)["calls_reserved"],1)
        self.lab.store.release("owner")

    def test_single_worker_lease_and_recovery(self):
        rid=self.lab.create(self.config())["id"]
        self.assertEqual(self.lab.store.claim("one"),rid)
        self.assertIsNone(self.lab.store.claim("two"))
        with self.lab.store.db() as db:db.execute("UPDATE worker SET lease=0")
        self.assertIsNone(self.lab.store.claim("two"))
        self.assertEqual(self.lab.store.get(rid)["state"],"interrupted")

    def test_cancel_resume_checkpoints(self):
        rid=self.lab.create(self.config())["id"]
        self.lab.store.cancel(rid);self.assertEqual(self.lab.store.get(rid)["state"],"cancelled")
        self.lab.store.resume(rid);self.lab.store.claim("owner");self.lab.execute(rid,"owner");self.lab.store.release("owner")
        self.assertEqual(len(self.lab.store.results(rid)),1)
        self.lab.store.set_state(rid,"interrupted");self.lab.store.resume(rid)
        self.lab.store.claim("owner");self.lab.execute(rid,"owner");self.lab.store.release("owner")
        self.assertEqual(len(self.lab.store.results(rid)),1)

    def test_import_revalidates_source_and_marks_missing_context(self):
        request=ImportRequest(request_key="import-key",results=[{"id":"Q1"}])
        created=self.lab.import_results(request);r=self.lab.report(created["id"])
        self.assertEqual(r["unavailable_retrieval_cases"],1)
        self.assertIsNone(r["summary"]["support_point_coverage"])
        self.assertTrue(self.lab.import_results(request)["reused"])
        with self.assertRaisesRegex(ValueError,"导入结果"):self.lab.store.resume(created["id"])
        a=TEXT.index(QUOTE)
        forged=ImportRequest(request_key="forged-key",results=[{"id":"Q1","evidence":[dict(source_id="a",start_char=a,end_char=a+len(QUOTE),context_text="wrong")]}])
        with self.assertRaisesRegex(ValueError,"投影"):self.lab.import_results(forged)

    def test_import_authentic_citation_and_contradictory_claim_keeps_uncertainty(self):
        a=TEXT.index(QUOTE)
        request=ImportRequest(request_key="authentic-key",results=[{"id":"Q1","evidence":[dict(source_id="a",start_char=a,end_char=a+len(QUOTE),context_text=QUOTE)],
            "answer":dict(status="answered",claims=[dict(text="RAG 不需要外部资料。",evidence_id="E1",quote=QUOTE)],missing_information="")}])
        r=self.lab.report(self.lab.import_results(request)["id"])
        self.assertEqual(r["summary"]["support_point_coverage"],1)
        self.assertEqual(r["results"][0]["diagnostics"][0]["judgment"],"unjudgeable")

    def test_comparison_rejects_different_splits(self):
        a=self.execute(self.config());b=self.execute(self.config(split="holdout"))
        with self.assertRaisesRegex(ValueError,"分组"):self.lab.compare(a["id"],b["id"])

    def test_oracle_context_uses_original_spans(self):
        r=self.execute(self.config(mode="oracle",live=True,call_budget=2,token_budget=1000000))
        self.assertEqual(r["state"],"completed")
        evidence=r["results"][0]["oracle_evidence"]
        self.assertEqual(evidence[0]["context_text"],QUOTE)
        self.assertEqual(TEXT[evidence[0]["start_char"]:evidence[0]["end_char"]],QUOTE)

    @unittest.skipUnless(find_spec("numpy"),"Optional vector test requires numpy")
    def test_vector_windows_cache_and_hybrid_with_local_encoder_fixture(self):
        import numpy as np
        from study_rag.adapters import LocalRagAdapter
        class Tokenizer:
            def __call__(self,text,**kwargs):
                return {"input_ids":[ord(c) for c in text],"offset_mapping":[(i,i+1) for i in range(len(text))]}
            def decode(self,ids,**kwargs):return ''.join(chr(i) for i in ids)
        class Encoder:
            tokenizer=Tokenizer()
            def encode(self,texts,**kwargs):
                arr=np.zeros((len(texts),384),dtype='float32');arr[:,0]=1;return arr
        loaded=self.lab.dataset("agent-learning-v1")
        adapter=LocalRagAdapter(self.data,loaded,self.root/"vectors")
        adapter.model=Encoder()
        info=adapter.vector_index();self.assertFalse(info["cache_hit"])
        for strategy in ("vector","hybrid"):
            pack=adapter.retrieve(loaded[0].questions[0],self.config(strategy=strategy))
            self.assertLessEqual(len(pack["evidence"]),8)
            self.assertTrue(pack["evidence"])
            self.assertTrue(pack["trace"]["books"][0]["candidates"][0]["embedding_window"])
            e=pack["evidence"][0]
            self.assertEqual(TEXT[e["start_char"]:e["end_char"]],e["text"])
        second=LocalRagAdapter(self.data,loaded,self.root/"vectors");second.model=Encoder()
        self.assertTrue(second.vector_index()["cache_hit"])
        matrix=next((self.root/"vectors").glob('*.npy'));matrix.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,"哈希"):second.vector_index()

    def test_account_database_rejected_without_experiment_tables(self):
        users=Store(self.root/"real-users.sqlite3")
        users.register("learner","test-password-123")
        with self.assertRaisesRegex(ValueError,"账号库"):Lab(self.data,users.path)
        with users.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0],1)
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='runs'").fetchone())

    def test_refusal_status_is_separate_from_retrieval_coverage(self):
        q=self.payload["questions"][0]
        q.update(category="gap",answerability="insufficient",points=[],missing_information=["真实本机p99日志未收录"],
            review_scope={"source_ids":["a"],"checked_content":"完整合成原文","absence_basis":"合成正文只有概念说明，没有运行日志"})
        self.write_dataset()
        r=self.execute(self.config(mode="generate",live=True,call_budget=1,token_budget=1000000))
        self.assertEqual(r["generation"]["refusal_cases"],1)
        self.assertEqual(r["generation"]["refusal_status_matches"],0)
        self.assertIsNone(r["summary"]["support_point_coverage"])

    def test_admin_auth_and_csrf_no_private_chat_access(self):
        users=Store(self.root/"users.sqlite3");users.create_admin("maintainer","test-password-123")
        app=create_app(data_dir=self.data,store=users,model=self.model)
        app.state.lab=self.lab
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/lab/runs").status_code,401)
            client.post("/api/register",json={"username":"learner","password":"test-password-123"})
            self.assertEqual(client.get("/diagnostics").status_code,403)
            self.assertEqual(client.get("/api/lab/datasets").status_code,403)
            session=client.post("/api/login",json={"username":"maintainer","password":"test-password-123"}).json()
            self.assertEqual(client.get("/diagnostics").status_code,200)
            self.assertEqual(client.post("/api/lab/runs",json=self.config().model_dump()).status_code,403)
            with patch.object(self.lab,"start"):
                response=client.post("/api/lab/runs",json=self.config().model_dump(),headers={"X-CSRF-Token":session["csrf"]})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get("/api/lab/runs").status_code,200)
            self.assertEqual(client.get("/api/lab/datasets/agent-learning-v1").json()["questions"][0]["id"],"Q1")
            self.assertEqual(client.get("/api/lab/datasets/agent-learning-v1?split=wrong").status_code,422)


if __name__=="__main__":unittest.main()
