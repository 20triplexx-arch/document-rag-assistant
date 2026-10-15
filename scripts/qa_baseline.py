"""Capture the 16 public development questions before altering QA behavior."""
from pathlib import Path
import sys, json, hashlib, shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.rag import retrieve, answer_from_pack, DeepSeekModel, PROMPT_VERSION, RETRIEVER_VERSION
from study_rag.qa_budget import QABudget, BudgetedModel
from study_rag.settings import PROJECT, DEFAULT_DATA

def main():
    out = PROJECT / "output/qa-v3"
    out.mkdir(exist_ok=True,parents=True)
    scenarios = PROJECT / "evals/qa-scenarios-v1.json"
    budget = QABudget(out / "budget.sqlite3")
    budget.freeze("scenario_sha256",hashlib.sha256(scenarios.read_bytes()).hexdigest())
    budget.freeze("baseline_prompt",PROMPT_VERSION)
    budget.freeze("baseline_retriever",RETRIEVER_VERSION)
    frozen = out / "baseline-code"
    frozen.mkdir(exist_ok=True)
    contracts = {}
    for name in ("rag","core","conversation","response_policy","mdx","limits"):
        path = PROJECT / f"study_rag/{name}.py"
        contracts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = frozen / path.name
        if not dest.exists(): shutil.copyfile(path,dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != contracts[name]: raise ValueError("Baseline code changed")
    budget.freeze("baseline_code",json.dumps(contracts,sort_keys=True))
    model = DeepSeekModel("deepseek-flash")
    questions = [q for q in json.loads(scenarios.read_text(encoding="utf-8"))["questions"] if q["split"] == "dev" and q["id"].endswith(("D1","D2"))]
    for q in questions:
        dest = out / f"baseline-{q['id']}.json"
        if dest.exists(): continue
        pack = retrieve(DEFAULT_DATA,DEFAULT_DATA/"index.sqlite3",q["question"])
        result = answer_from_pack(pack,BudgetedModel(budget,"baseline",q["id"],model))
        dest.write_text(json.dumps({"scenario":q,"result":result,"code_contract":contracts,"review_origin":"pending AI source review; not human approved"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(q["id"],result["status"],flush=True)
    print(json.dumps(budget.summary()),flush=True)

if __name__ == "__main__": main()
