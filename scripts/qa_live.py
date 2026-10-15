"""Bounded public Flash trial through the authenticated API / isolated account DB."""
from pathlib import Path
import argparse,hashlib,json,secrets,sys
from uuid import uuid4
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from study_rag.qa_evaluation import load_qa_dataset,QA_DATASET,score_qa
from study_rag.qa_retrieval import retrieve_qa
from study_rag.qa_budget import QABudget,BudgetedModel
from study_rag.rag import DeepSeekModel
from study_rag.core import corpus_catalog
from study_rag.mdx import mdx_mask
from study_rag.rag import visible_prose,prose_mask
from study_rag.store import Store
from study_rag.web import create_app

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/"data/qa-20261014-v1";OUT=ROOT/"output/qa-v3"
MODULES=("rag.py","core.py","mdx.py","code_index.py","question_plan.py","qa_retrieval.py","qa_vectors.py","answer_schema.py","qa_prompt.py","conversation.py","response_policy.py")
def code_contract():return {name:hashlib.sha256((ROOT/"study_rag"/name).read_bytes()).hexdigest() for name in MODULES}

def oracle_pack(q,loaded):
    dataset,sha,manifest,chunks,sources,texts,masks=loaded;catalog=corpus_catalog(manifest)
    spans=[]
    for point in q.points:
        spans.extend(point.supports if point.coverage=="all" else point.supports[:1])
    unique={}
    for s in spans:unique[(s.source_id,s.start_char,s.end_char,s.kind)]=s
    ev=[]
    for s in unique.values():
        source=sources[s.source_id];meta=catalog["chapters"][s.source_id];text=texts[s.source_id][s.start_char:s.end_char]
        # Support interventions use actual raw positions. No synthetic reference facts.
        ev.append({"evidence_id":f"E{len(ev)+1}","source_id":s.source_id,"book":source.book,"chapter":source.chapter,
            "display_name":next(b["display_name"] for b in catalog["books"] if b["book"]==source.book),
            "path":source.path,"section":"已标注支持上下文（AI 辅助复核）","language":meta["language"],"content_type":s.kind,
            "applicable_versions":meta.get("applicable_versions",["unknown"]),"start_char":s.start_char,"end_char":s.end_char,
            "start_line":s.start_line,"end_line":s.end_line,"text":text,
            "context_text":text if s.kind=="code" else visible_prose(text,masks[s.source_id][s.start_char:s.end_char]),
            "source_url":source.source_url,"line_url":f"{source.source_url}#L{s.start_line}-L{s.end_line}","score":0.0})
    if len(ev)>8 or any(len(e["context_text"])>3200 for e in ev) or sum(len(e["context_text"]) for e in ev)>20000:raise ValueError("Oracle support does not fit evidence budget")
    return {"question":q.question,"book_filter":None,"qa_version":3,"evidence":ev,"retriever":"support-context-intervention-v1",
        "corpus_version":manifest["corpus_version"],"books_without_match":[],"source_verified":True,"support_verified":False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--phase",choices=("candidate","oracle","acceptance","retest"),required=True)
    parser.add_argument("--strategy",choices=("bm25","hybrid"),default="bm25");parser.add_argument("--question")
    args=parser.parse_args();OUT.mkdir(exist_ok=True,parents=True)
    loaded=load_qa_dataset(QA_DATASET,DATA);dataset,sha,manifest=loaded[:3]
    budget=QABudget(OUT/"budget.sqlite3");contract=code_contract()
    budget.freeze("gold_sha256-v1.1",sha);budget.freeze(args.phase+"_code",json.dumps(contract,sort_keys=True))
    code_dir=OUT/(args.phase+"-code")
    code_dir.mkdir(exist_ok=True)
    for name in MODULES:
        dest=code_dir/name
        if not dest.exists():dest.write_bytes((ROOT/"study_rag"/name).read_bytes())
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=contract[name]:raise ValueError("Frozen phase source changed")
    if args.phase=="acceptance":budget.freeze("acceptance_frozen_strategy",args.strategy)
    questions=[q for q in dataset.questions if q.split==("acceptance" if args.phase=="acceptance" else "dev")]
    if args.phase=="oracle":questions=[q for q in questions if q.id.endswith("D1")]
    if args.phase=="retest":
        if not args.question:raise ValueError("Retest requires a specific development question")
        questions=[q for q in questions if q.id==args.question]
    store=Store(OUT/"live-users.sqlite3")
    for q in questions:
        path=OUT/f"{args.phase}-{q.id}.json"
        if path.exists() and args.phase!="retest":continue
        if code_contract()!=contract:raise ValueError("QA code changed during phase; stop without retry")
        model=BudgetedModel(budget,args.phase,q.id,DeepSeekModel("deepseek-flash"))
        app=create_app(data_dir=DATA,store=store,model=model,session_cookie_name="qa_experiment_session")
        pack=oracle_pack(q,loaded) if args.phase=="oracle" else retrieve_qa(DATA,DATA/"index.sqlite3",q.question,strategy=args.strategy,trace=True)
        with TestClient(app) as client:
            auth=client.post("/api/register",json={"username":"qa-"+uuid4().hex[:20],"password":secrets.token_urlsafe(24)})
            if auth.status_code!=200:raise ValueError("Isolated account registration failed")
            client.headers["X-CSRF-Token"]=auth.json()["csrf"]
            chat=client.post("/api/chats",json={"title":"公开质量题 "+q.id})
            if chat.status_code!=200:raise ValueError("Isolated chat creation failed")
            with patch("study_rag.web.retrieve",return_value=pack):
                response=client.post("/api/ask",json={"chat_id":chat.json()["id"],"request_key":str(uuid4()),
                    "question":q.question,"explain":True,"use_history":False,"model":"deepseek-flash"})
            if response.status_code!=200:raise ValueError("QA API request failed before an answer: "+str(response.status_code))
            result=response.json()
        record={"scenario":q.model_dump(),"result":result,"retrieval_score":score_qa(q,pack["evidence"],loaded[5],loaded[6]),
            "dataset_sha256":sha,"corpus_version":manifest["corpus_version"],"code_contract":contract,
            "review_origin":"pending AI source review; not human approval","phase":args.phase}
        if args.phase=="retest":path=OUT/f"retest-{q.id}-{uuid4().hex[:8]}.json"
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(q.id,result["status"],result.get("failure_stage",""),flush=True)
    print(json.dumps(budget.summary()),flush=True)

if __name__=="__main__":main()
