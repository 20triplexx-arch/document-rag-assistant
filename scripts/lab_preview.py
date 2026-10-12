"""Isolated public experiment preview; temporary admin and zero live-model access."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi.responses import JSONResponse
from study_rag.lab import Lab
from study_rag.lab_models import ImportRequest
from study_rag.settings import DEFAULT_DATA
from study_rag.store import Store
from study_rag.web import create_app
from study_rag.rag import normalize_quote


class NoModel:
    model_name="offline-diagnostic-preview"
    def generate(self,messages):raise RuntimeError("Preview forbids model calls")


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--port",type=int,default=8767)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="rag-lab-preview-") as directory:
        temporary=Path(directory)
        users=Store(temporary/"users.sqlite3")
        users.create_admin("lab-preview","lab-preview-pass")
        model=NoModel();lab=Lab(DEFAULT_DATA,temporary/"experiments.sqlite3",model=model)
        original=Lab(DEFAULT_DATA,root/"output"/"experiments.sqlite3")
        records=[]
        for source_run in original.store.list():
            if source_run["state"]!="completed" or source_run["config"]["name"] not in {"baseline","no-expansion","body-only","no-intent-filter"}:continue
            if any(r["config"]["name"]==source_run["config"]["name"] for r in records):continue
            records.append(source_run)
        for source_run in reversed(records):
            config=deepcopy(source_run["config"]);config["request_key"]=uuid4().hex
            rid,_=lab.store.create(config,source_run["snapshot"],source_run["total"],initial_state="interrupted")
            for result in original.store.results(source_run["id"]):lab.store.save_result(rid,result)
            lab.store.set_state(rid,"completed")
        if records:
            q=original.store.results(records[-1]["id"])[0]
            if q["evidence"]:
                e=q["evidence"][0]
                answer={"status":"answered","claims":[{"heading":"离线构造的错误结论",
                    "text":"离线演示样例：只要带有原文引用，所有生成结论就一定正确。",
                    "quote":normalize_quote(e["context_text"])[:120],"evidence_id":"E1"}],"missing_information":""}
                lab.import_results(ImportRequest(request_key=uuid4().hex,name="引用真实，结论待核查 · 离线构造样例",
                    results=[{"id":q["id"],"evidence":[e],"answer":answer}]))
        app=create_app(data_dir=DEFAULT_DATA,store=users,model=model)
        app.state.lab=lab
        @app.middleware("http")
        async def prohibit_live(request,call_next):
            if request.method=="POST" and request.url.path=="/api/lab/runs":
                body=await request.json()
                if body.get("live"):
                    return JSONResponse({"detail":"隔离预览禁止真实模型调用。"},status_code=403)
            return await call_next(request)
        print(f"Preview: http://127.0.0.1:{args.port}/; temporary login lab-preview / lab-preview-pass",flush=True)
        uvicorn.run(app,host="127.0.0.1",port=args.port,access_log=False)


if __name__=="__main__":main()
