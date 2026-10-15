"""One offline regression pass; old reports and frozen labels stay untouched."""
from pathlib import Path
import json
import sys
import time
import statistics

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from study_rag.qa_evaluation import evaluate_qa, QA_DATASET, qa_summary
from study_rag.evaluation import load_dataset, DEFAULT_DATASET, score_question, summarize
from study_rag.qa_retrieval import retrieve_qa
from study_rag.rag import retrieve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/qa-20261014-v1"
OUT = ROOT / "output/qa-speed-20261015-v1"


def main():
    report = evaluate_qa(QA_DATASET, DATA, split="all")
    dataset, sha, manifest, chunks, sources, texts, masks = load_dataset(DEFAULT_DATASET, ROOT / "data/courses-cases-20261010-v1")
    rows = []
    for q in dataset.questions:
        if q.split != "dev":
            continue
        pack = retrieve_qa(DATA, DATA / "index.sqlite3", q.question, q.book)
        rows.append(score_question(q, [e for e in pack["evidence"] if e["content_type"] != "code"], texts, masks))
    new = qa_summary([r for r in report["results"] if r["split"] == "dev"])
    old = summarize(rows)
    gates = {"old_points":old["covered_support_points"] >= 35, "old_complete":old["complete_questions"] >= 17,
             "new_points":new["covered"] >= 70, "new_complete":new["complete"] >= 18,
             "topic_minimum":all(t["coverage"] >= .75 for t in new["per_topic"].values())}
    scenarios = json.loads((ROOT / "evals/qa-speed-v1.json").read_text(encoding="utf-8"))["dev"]
    samples = []
    for q in scenarios:
        retrieve(DATA, DATA / "index.sqlite3", q["question"])
        for _ in range(3):
            started = time.perf_counter()
            retrieve(DATA, DATA / "index.sqlite3", q["question"])
            samples.append(time.perf_counter() - started)
    p95 = sorted(samples)[int((len(samples)-1)*.95)]
    result = {"new":new,"old":old,"gates":gates,"new_report":report,"old_results":rows,
              "benchmark":{"samples":samples,"median_seconds":statistics.median(samples),"p95_seconds":p95},"model_calls":0}
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / "retrieval.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"new":new,"old":old,"gates":gates,"benchmark":result["benchmark"]},ensure_ascii=True))


if __name__ == "__main__":
    main()
