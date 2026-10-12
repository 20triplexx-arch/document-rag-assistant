"""Three controlled retrieval ablations, dev split only, zero model calls."""
import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from study_rag.lab import Lab
from study_rag.lab_models import ExperimentConfig
from study_rag.settings import DEFAULT_DATA


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=ROOT/"evals"/"experiments")
    p.add_argument("--vectors",action="store_true",help="Also compare prepared E5 and RRF; never downloads implicitly")
    args=p.parse_args()
    lab=Lab(DEFAULT_DATA,ROOT/"output"/"experiments.sqlite3")
    variants=[("baseline",{}),("no-expansion",{"expand":False}),("body-only",{"body_only":True}),
              ("no-intent-filter",{"intent_filter":False})]
    if args.vectors:variants += [("e5-vector",{"strategy":"vector"}),("rrf-hybrid",{"strategy":"hybrid"})]
    ids=[lab.create(ExperimentConfig(request_key=uuid4().hex,name=name,**settings))["id"] for name,settings in variants]
    print("Queued: "+', '.join(ids),flush=True)
    try:
        lab.start()
        while any(lab.store.get(i)["state"] in {"queued","running"} for i in ids):time.sleep(.5)
        summaries=[]
        args.out.mkdir(parents=True,exist_ok=True)
        for i in ids:
            r=lab.report(i,details=False)
            if r["state"] != "completed":raise ValueError(f"{r['config']['name']}: {r['error']}")
            summaries.append({"id":i,"name":r["config"]["name"],"config":r["config"],"summary":r["summary"],"snapshot":r["snapshot"]})
            print(f"{r['config']['name']}: {r['summary']['covered_support_points']}/{r['summary']['support_points']}",flush=True)
        (args.out/"ablation-summaries-2026-10-12.json").write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n',encoding="utf-8")
        for i in ids[1:]:
            c=lab.compare(ids[0],i)
            (args.out/(lab.store.get(i)["config"]["name"]+"-2026-10-12.json")).write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding="utf-8")
    finally:lab.close()


if __name__=="__main__":main()
