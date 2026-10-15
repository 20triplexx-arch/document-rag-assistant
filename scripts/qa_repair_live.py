"""Gated, isolated Flash HTTP/SSE trials. Never automatically retry a call."""
from pathlib import Path
from uuid import uuid4
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus,corpus_catalog
from study_rag.source_views import source_text
from study_rag.qa_experiment import ExperimentLedger,RecordedModel
from study_rag.qa_retrieval_v5 import indexed_materials
from study_rag.parent_vectors import parent_index,query_vector
from study_rag.providers import create_model
from study_rag.store import Store
from study_rag.web import create_app
from scripts.qa_depth import http_answer,PUBLIC_REPOS

OUT=ROOT/'output/qa-repair-20261015-v5';DATA=ROOT/'data/qa-overhaul-20261015-v2'
LEDGER=ROOT/'output/qa-depth-20261015-v1/ledger.sqlite3'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    report=json.loads((OUT/args.offline_report).read_text(encoding='utf-8'))
    if set(report['gates'])!={'old_45_of_49','new_70_of_72','previous_all'} or not all(report['gates'].values()):
        raise SystemExit('OFFLINE_GATE_STOP: no provider created; no generation or budget reservation.')
    if {name:len(rows) for name,rows in report['results'].items()}!={'old':30,'new':24,'exposed':40,'old_extra':10,'new_extra':8,'previous_frozen':40}:
        raise SystemExit('INCOMPLETE_REGRESSION_STOP: all 152 exposed records required.')
    for path,expected in report['code_contract'].items():
        if sha(ROOT/path)!=expected:raise SystemExit('OFFLINE_CODE_CHANGED: rerun offline checks before generation.')
    ledger=ExperimentLedger(LEDGER)
    if ledger.summary()['flash_total_limit_cny']!=5:raise ValueError('CNY5 total authorization required')
    ledger.authorize_phase('repair-v5-development','repair-v5-development',8,250000)
    ledger.authorize_phase('repair-v5-acceptance','repair-v5-acceptance',40,1200000,protected=True)
    phase='repair-v5-'+args.phase
    gold=ROOT/'evals'/('qa-overhaul-dev-v1.json' if args.phase=='development' else 'qa-repair-frozen-v1.json')
    questions=json.loads(gold.read_text(encoding='utf-8'))['questions']
    if args.phase=='acceptance' and len(questions)!=40:raise ValueError('Full frozen set required')
    ledger.freeze(phase+'-questions',sha(gold));ledger.freeze(phase+'-offline',sha(OUT/args.offline_report))
    code={}
    paths=list((ROOT/'study_rag').glob('*.py'))+list((ROOT/'study_rag').glob('*.json'))+list((ROOT/'static').glob('*'))+[Path(__file__),ROOT/'scripts/qa_depth.py']
    for source in paths:
        if not source.is_file():continue
        relative=source.relative_to(ROOT);code[str(relative)]=sha(source)
        dest=OUT/(phase+'-code')/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and sha(dest)!=sha(source):raise ValueError('Trial code changed')
        if not dest.exists():dest.write_bytes(source.read_bytes())
    ledger.freeze(phase+'-code',code)
    manifest,chunks,_,contents=verified_corpus(DATA,DATA/'index.sqlite3')
    if any(s.repository not in PUBLIC_REPOS for s,_ in contents):raise ValueError('Non-public trial input')
    ledger.freeze(phase+'-corpus',{'corpus_version':manifest['corpus_version'],'index_sha256':sha(DATA/'index.sqlite3')})
    texts={(s.book,s.path):source_text(s,raw) for s,raw in contents}
    # Cold startup is local-only and occurs before the HTTP trial timeout.
    import time
    cold=time.perf_counter();mat=indexed_materials(manifest,contents,chunks,corpus_catalog(manifest))
    parent_index(manifest['corpus_version'],mat['descriptors']);query_vector('初始化本地检索',2)
    (OUT/(phase+'-cold.json')).write_text(json.dumps({'local_index_warmup_seconds':time.perf_counter()-cold,'model_calls':0}),encoding='utf-8')
    store=Store(OUT/(phase+'-users.sqlite3'),user_daily_limit=100000,global_daily_limit=1000000,max_concurrent=2)
    folder=OUT/phase;folder.mkdir(exist_ok=True)
    model=create_model('deepseek-flash')
    try:
        for q in questions:
            key=phase+'/'+q['id'];dest=folder/(q['id']+'.json')
            if dest.exists() or ledger.exists(key):raise SystemExit('PRIOR_ATTEMPT_STOP: failed/completed/reserved calls are never rerun.')
            def guard(messages):
                payload=json.loads(messages[1]['content'])
                if payload['QUESTION']!=q['question']:raise ValueError('Not frozen public question')
                for turn in payload.get('DISCUSSION_CONTEXT',[]):
                    if turn!={'question':q.get('prelude'),'unverified_answer_summary':''}:raise ValueError('Private history prohibited')
                for evidence in payload['EVIDENCE']:
                    text=texts.get((evidence.get('book'),evidence.get('path')))
                    if text is None or any(s['text'] not in text for s in evidence.get('spans',[])):raise ValueError('Source input mismatch')
            recorded=RecordedModel(ledger,key,model,phase,guard)
            app=create_app(data_dir=DATA,store=store,model=recorded,model_options={'deepseek-flash':recorded},session_cookie_name='repair_trial')
            try:result,timings=http_answer(app,q,'deepseek-flash',str(uuid4()))
            except Exception as error:
                result={'status':'HTTP_TRIAL_FAILED','model_calls':int(ledger.exists(key)),'error_type':type(error).__name__};timings={}
            record={'scenario':q,'phase':phase,'result':result,**timings,'dataset_sha256':sha(gold),
                    'code_contract':code,'review_origin':'Code assistant must compare each point with source; model-assisted, not human accuracy.'}
            dest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(q['id'],result['status'],flush=True)
            if result['status'] in {'MODEL_FAILED','HTTP_TRIAL_FAILED','INTERNAL_FAILED'}:
                raise SystemExit('PROVIDER_OR_HTTP_STOP: no retry.')
    finally:model.close()
    (OUT/(phase+'-budget.json')).write_text(json.dumps({'total':ledger.summary(),'phases':ledger.phase_summary()},indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['development','acceptance']);p.add_argument('--offline-report',default='offline-final.json');run(p.parse_args())
