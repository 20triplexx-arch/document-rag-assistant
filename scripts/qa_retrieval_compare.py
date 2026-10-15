"""Offline new-corpus ablation and old fixed development regression. No holdouts."""
from pathlib import Path
import sys,json,time,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.qa_evaluation import QA_DATASET,evaluate_qa
from study_rag.evaluation import load_dataset,DEFAULT_DATASET,score_question,summarize
from study_rag.qa_retrieval import retrieve_qa
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/"data/qa-20261014-v1";OLD=ROOT/"data/courses-cases-20261010-v1"

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--strategy",choices=("bm25","hybrid"),required=True);args=p.parse_args()
    out=ROOT/"output/qa-v3";out.mkdir(exist_ok=True,parents=True)
    contract={name:hashlib.sha256((ROOT/"study_rag"/name).read_bytes()).hexdigest() for name in ("question_plan.py","qa_retrieval.py","qa_vectors.py","qa_evaluation.py")}
    report=evaluate_qa(QA_DATASET,DATA,strategy=args.strategy)
    dataset,sha,manifest,chunks,sources,texts,masks=load_dataset(DEFAULT_DATASET,OLD)
    results=[]
    for q in dataset.questions:
        if q.split!="dev":continue
        pack=retrieve_qa(DATA,DATA/"index.sqlite3",q.question,q.book,strategy=args.strategy)
        # All legacy spans still refer to identical raw bytes. Code evidence is not a concept hit.
        results.append(score_question(q,[e for e in pack["evidence"] if e["content_type"]!="code"],texts,masks))
    old=summarize(results);new=report["summary"]
    gates={"old_points":old["covered_support_points"]>=26,"old_complete":old["complete_questions"]>=9,
        "new_coverage":new["coverage"]>=.8,"topic_minimum":all(v["coverage"]>=.75 for v in new["per_topic"].values())}
    combined={"date":"2026-10-14","comparison":"same candidate corpus; old annotations use preserved source bytes", "strategy":args.strategy,
        "new":report,"code_contract":contract,"old_dataset_sha256":sha,"old":old,"old_results":results,"gates":gates,"eligible":all(gates.values()),"model_calls":0}
    dest=out/("retrieval-"+args.strategy+".json");dest.write_text(json.dumps(combined,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    archive=out/("retrieval-"+args.strategy+"-"+time.strftime("%Y%m%d-%H%M%S")+".json");archive.write_bytes(dest.read_bytes())
    print(json.dumps({"strategy":args.strategy,"old":old,"new":new,"gates":gates,"eligible":combined["eligible"]},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
