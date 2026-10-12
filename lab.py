"""Local experiment CLI. Offline by default; explicit independent live budgets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
from study_rag.lab import Lab
from study_rag.lab_models import ExperimentConfig, ImportRequest
from study_rag.settings import DEFAULT_DATA

ROOT=Path(__file__).resolve().parent


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",type=Path,default=DEFAULT_DATA)
    p.add_argument("--database",type=Path,default=ROOT/"output"/"experiments.sqlite3")
    sub=p.add_subparsers(dest="command",required=True)
    run=sub.add_parser("run")
    run.add_argument("--dataset",choices=["agent-learning-v1","agent-learning-v2"],default="agent-learning-v1")
    run.add_argument("--split",choices=["dev","calibration","holdout","all"],default="dev")
    run.add_argument("--strategy",choices=["bm25","vector","hybrid"],default="bm25")
    run.add_argument("--mode",choices=["retrieval","generate","judge","oracle"],default="retrieval")
    run.add_argument("--name",default="本机实验")
    run.add_argument("--no-expand",action="store_true")
    run.add_argument("--body-only",action="store_true")
    run.add_argument("--no-intent-filter",action="store_true")
    run.add_argument("--live",action="store_true")
    run.add_argument("--call-budget",type=int,default=0)
    run.add_argument("--token-budget",type=int,default=0)
    run.add_argument("--repeat",type=int,default=1)
    run.add_argument("--allow-pending",action="store_true")
    run.add_argument("--request-key",default=None)
    for command in ["report","resume","cancel"]:
        sp=sub.add_parser(command);sp.add_argument("run_id")
        if command=="report":sp.add_argument("--out",type=Path)
    compare=sub.add_parser("compare");compare.add_argument("left");compare.add_argument("right");compare.add_argument("--out",type=Path)
    regression=sub.add_parser("regress");regression.add_argument("baseline");regression.add_argument("candidate")
    importer=sub.add_parser("import");importer.add_argument("file",type=Path)
    importer.add_argument("--dataset",default="agent-learning-v1",choices=["agent-learning-v1","agent-learning-v2"])
    importer.add_argument("--split",default="dev",choices=["dev","calibration","holdout","all"])
    vectors=sub.add_parser("prepare-vectors");vectors.add_argument("--download",action="store_true")
    args=p.parse_args(argv)
    lab=Lab(args.data_dir,args.database)
    try:
        if args.command=="run":
            c=ExperimentConfig(dataset=args.dataset,split=args.split,strategy=args.strategy,mode=args.mode,name=args.name,
                expand=not args.no_expand,body_only=args.body_only,intent_filter=not args.no_intent_filter,live=args.live,
                call_budget=args.call_budget,token_budget=args.token_budget,repeat=args.repeat,allow_pending=args.allow_pending,
                request_key=args.request_key or uuid4().hex)
            result=lab.create(c);rid=result["id"]
            print(f"Experiment {rid}; independent budget: {c.call_budget} calls / {c.token_budget} reserved tokens",flush=True)
            lab.start()
            while lab.store.get(rid)["state"] in {"queued","running"}:time.sleep(.25)
            result=lab.report(rid,details=False)
        elif args.command=="report":result=lab.report(args.run_id)
        elif args.command=="compare" or args.command=="regress":
            result=lab.compare(args.left,args.right) if args.command=="compare" else lab.compare(args.baseline,args.candidate)
            if args.command=="regress":
                print(json.dumps(result,ensure_ascii=False,indent=2))
                return 1 if not result["complete_pair"] or result["changes"].get("regressed",0) else 0
        elif args.command=="import":
            raw=json.loads(args.file.read_text(encoding="utf-8"))
            result=lab.import_results(ImportRequest(dataset=args.dataset,split=args.split,name="CLI离线结果导入",
                request_key=uuid4().hex,results=raw if isinstance(raw,list) else raw["results"]))
        elif args.command=="resume":
            lab.store.resume(args.run_id);lab.start()
            while lab.store.get(args.run_id)["state"] in {"queued","running"}:time.sleep(.25)
            result=lab.report(args.run_id,details=False)
        elif args.command=="cancel":lab.store.cancel(args.run_id);result={"status":"cancel_requested"}
        else:
            loaded=lab.dataset("agent-learning-v1")
            adapter=lab.adapter_factory(args.data_dir,loaded,args.database.parent/"vector-cache",download=args.download)
            result=adapter.vector_index()
        text=json.dumps(result,ensure_ascii=False,indent=2)
        if getattr(args,"out",None):args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(text,encoding="utf-8")
        else:print(text)
        return 1 if result.get("state") in {"failed","budget_exhausted","interrupted"} or result.get("result_states",{}).get("GENERATION_OR_JUDGE_FAILED",0) else 0
    except (ValueError,KeyError,OSError) as error:
        print(str(error) if isinstance(error,ValueError) else type(error).__name__,file=sys.stderr)
        return 2
    finally:lab.close()


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
