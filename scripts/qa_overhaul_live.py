"""Account-isolated authenticated HTTP trials; all costs use the existing ledger."""
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import source_text
from study_rag.providers import create_model
from study_rag.qa_experiment import ExperimentLedger,RecordedModel
from study_rag.store import Store
from study_rag.web import create_app
from scripts.qa_depth import http_answer,PUBLIC_REPOS

OUT=ROOT/'output/qa-overhaul-20261015-v2'
DATA=ROOT/'data/qa-overhaul-20261015-v2'
LEDGER=ROOT/'output/qa-depth-20261015-v1/ledger.sqlite3'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def old_factory():
    directory=OUT/'baseline-code/study_rag';name='qa_overhaul_baseline'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,directory/'__init__.py',submodule_search_locations=[str(directory)])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return importlib.import_module(name+'.web').create_app,importlib.import_module(name+'.rag').DeepSeekModel


def run(args):
    ledger=ExperimentLedger(LEDGER)
    if ledger.summary()['flash_total_limit_cny']!=5:raise ValueError('Expected explicit total CNY5 authorization')
    dataset=ROOT/'evals'/({'speed':'qa-overhaul-speed-v1.json','dev':'qa-overhaul-dev-v1.json','acceptance':'qa-overhaul-v1.1.json'}[args.set])
    questions=json.loads(dataset.read_text(encoding='utf-8'))['questions']
    ledger.freeze('overhaul/'+args.set,digest(dataset))
    if args.ids:questions=[q for q in questions if q['id'] in args.ids.split(',')]
    before=args.phase=='speed-before'
    data=ROOT/'data/qa-20261014-v1' if before else DATA
    factory,model_cls=old_factory() if before else (create_app,None)
    code=OUT/'baseline-code' if before else OUT/(args.phase+'-code')
    if not before:
        for path in list((ROOT/'study_rag').glob('*.py'))+list((ROOT/'static').glob('*'))+[Path(__file__)]:
            if not path.is_file():continue
            dest=code/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists() and digest(dest)!=digest(path):raise ValueError('Frozen trial implementation changed')
            if not dest.exists():dest.write_bytes(path.read_bytes())
    contract={p.relative_to(code).as_posix():digest(p) for p in code.rglob('*') if p.is_file() and p.suffix!='.pyc'}
    ledger.freeze('overhaul/'+args.phase+'-code',contract)
    manifest,_,_,contents=verified_corpus(data,data/'index.sqlite3')
    if any(s.repository not in PUBLIC_REPOS for s,_ in contents):raise ValueError('Non-public corpus')
    ledger.freeze('overhaul/'+args.phase+'-corpus',{'corpus_version':manifest['corpus_version'],'index_sha256':digest(data/'index.sqlite3')})
    texts={(s.book,s.path):source_text(s,raw) for s,raw in contents}
    model=model_cls('deepseek-flash') if model_cls else create_model('deepseek-flash')
    store=Store(OUT/(args.phase+'-users.sqlite3'),user_daily_limit=100000,global_daily_limit=1000000,max_concurrent=2)
    folder=OUT/args.phase;folder.mkdir(exist_ok=True,parents=True)
    try:
        for repetition in range(args.repeat):
            for q in questions:
                key=f'overhaul/{args.phase}/{q["id"]}/{repetition}';dest=folder/f'{q["id"]}-{repetition}.json'
                if dest.exists():continue
                if ledger.exists(key):print(key,'ALREADY_RESERVED_NO_RETRY',flush=True);continue
                def guard(messages):
                    payload=json.loads(messages[1]['content'])
                    if payload['QUESTION']!=q['question']:raise ValueError('Not frozen question')
                    for turn in payload.get('DISCUSSION_CONTEXT',[]):
                        if turn!={'question':q.get('prelude'),'unverified_answer_summary':''}:raise ValueError('Private history forbidden')
                    for e in payload['EVIDENCE']:
                        original=texts.get((e.get('book'),e.get('path')))
                        if original is None or any(span['text'] not in original for span in e.get('spans',[])):raise ValueError('Not verified public source')
                recorded=RecordedModel(ledger,key,model,'answer',guard)
                app=factory(data_dir=data,store=store,model=recorded,model_options={'deepseek-flash':recorded},session_cookie_name='overhaul_trial')
                try:result,timing=http_answer(app,q,'deepseek-flash',str(uuid4()))
                except Exception as error:
                    result={'status':'HTTP_TRIAL_FAILED','model_calls':int(ledger.exists(key)),'error_type':type(error).__name__}
                    timing={'client_total_seconds':None,'client_first_block_seconds':None,'events':[]}
                record={'scenario':q,'phase':args.phase,'repetition':repetition,'result':result,**timing,
                        'dataset_sha256':digest(dataset),'code_contract':contract,
                        'review_origin':'source-assisted review required; not human accuracy'}
                dest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(key,result['status'],timing['client_total_seconds'],timing['client_first_block_seconds'],flush=True)
                if result['status'] in {'MODEL_FAILED','HTTP_TRIAL_FAILED'}:
                    print('STOP_PROVIDER_HTTP_OR_BUDGET_NO_RETRY',flush=True);return
    finally:model.close()
    print(json.dumps(ledger.summary()),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('phase');p.add_argument('--set',choices=['speed','dev','acceptance'],default='acceptance')
    p.add_argument('--repeat',type=int,default=1);p.add_argument('--ids');run(p.parse_args())
