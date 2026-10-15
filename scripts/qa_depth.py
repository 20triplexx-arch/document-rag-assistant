"""Public source-first experiments and HTTP acceptance under the current spending policy."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import importlib
import json
import secrets
import socket
import sys
import threading
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
import uvicorn
from study_rag.core import verified_corpus,validate_text
from study_rag.qa_experiment import ExperimentLedger,RecordedModel
from study_rag.providers import create_model,ENABLED_MODELS
from study_rag.store import Store
from study_rag.web import create_app
from study_rag.rag import retrieve,answer_from_pack
from study_rag.rag import visible_prose,prose_mask
from study_rag.mdx import mdx_mask
from study_rag.conversation import prepare_context

OUT=ROOT/'output/qa-depth-20261015-v1'
DATA=ROOT/'data/qa-20261014-v1'
GOLD=ROOT/'evals/qa-depth-v1.json'
PUBLIC_REPOS={'langchain-ai/docs','modelcontextprotocol/modelcontextprotocol','WenyuChiou/awesome-agentic-ai-zh',
              'datawhalechina/hello-agents','huggingface/agents-course','Shubhamsaboo/awesome-llm-apps','microsoft/ai-agents-for-beginners'}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(label, baseline=False):
    folder=OUT/('baseline-code' if baseline else label+'-code')
    if not baseline:
        for sub,pattern in [('study_rag','*.py'),('static','*')]:
            for path in (ROOT/sub).glob(pattern):
                if not path.is_file():continue
                target=folder/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists() and sha(path)!=sha(target):raise ValueError('Frozen phase code changed')
                if not target.exists():target.write_bytes(path.read_bytes())
        for path in [Path(__file__),ROOT/'scripts/build_qa_depth_gold.py']:
            target=folder/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and sha(path)!=sha(target):raise ValueError('Frozen runner changed')
            if not target.exists():target.write_bytes(path.read_bytes())
    contract={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file() and p.suffix not in {'.pyc'}}
    return folder,contract


def load_baseline():
    directory=OUT/'baseline-code/study_rag'
    name='qa_depth_baseline'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,directory/'__init__.py',submodule_search_locations=[str(directory)])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return importlib.import_module(name+'.web').create_app,importlib.import_module(name+'.rag').DeepSeekModel


def source_guard(data, question):
    _,_,_,contents=verified_corpus(data,data/'index.sqlite3')
    if any(s.repository not in PUBLIC_REPOS for s,_ in contents):raise ValueError('Non-public trial corpus')
    texts={(s.book,s.path):validate_text(raw) for s,raw in contents}
    legacy_texts={}
    for s,_ in contents:
        text=texts[s.book,s.path]
        legacy_texts.setdefault(s.book,[]).extend([text,visible_prose(text,prose_mask(mdx_mask(text) if s.path.endswith('.mdx') else text))])
    def guard(messages):
        payload=json.loads(messages[1]['content'])
        if payload['QUESTION']!=question['question']:raise ValueError('Not the frozen public question')
        for turn in payload.get('DISCUSSION_CONTEXT',[]):
            if turn!={'question':question.get('prelude'),'unverified_answer_summary':''}:raise ValueError('Unexpected discussion content')
        for e in payload['EVIDENCE']:
            original=texts.get((e.get('book'),e.get('path')))
            if original is None:
                if 'path' in e or not any(e.get('text','') in text for text in legacy_texts.get(e.get('book'),[])):
                    raise ValueError('Not a public source')
                continue
            if any(s['text'] not in original for s in e.get('spans',[])):raise ValueError('Not literal public source spans')
    return guard


def public_questions(split):
    if split=='holdout':return json.loads(GOLD.read_text(encoding='utf-8'))['questions']
    previous=json.loads((ROOT/'evals/agent-qa-v1.1.json').read_text(encoding='utf-8'))['questions']
    exposed=json.loads((ROOT/'evals/qa-speed-v1.json').read_text(encoding='utf-8'))['acceptance']
    legacy=json.loads((ROOT/'evals/agent-learning-v1.json').read_text(encoding='utf-8'))['questions']
    legacy=[{**q,'topic':'legacy_learning','missing_information':'；'.join(q['missing_information']),
             'points':[{**p,'supports':[{**s,'kind':'prose'} for s in p['supports']]} for p in q['points']]} for q in legacy]
    result=[]
    for q in previous+exposed+legacy:
        if q['question'] not in {r['question'] for r in result}:result.append({**q,'prelude':None})
    return result


def http_answer(app, question, model_name, request_key):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    worker=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);worker.start()
    try:
        deadline=time.monotonic()+10
        while not server.started:
            if not worker.is_alive() or time.monotonic()>deadline:raise RuntimeError('Trial server start failed')
            time.sleep(.02)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=140) as client:
            response=client.post('/api/register',json={'username':'depth-'+uuid4().hex[:16],'password':secrets.token_urlsafe(24)});response.raise_for_status()
            client.headers['X-CSRF-Token']=response.json()['csrf']
            chat=client.post('/api/chats',json={'title':'公开问答验证 '+question['id']});chat.raise_for_status();chat_id=chat.json()['id']
            if question.get('prelude'):
                prelude=client.post('/api/ask',json={'chat_id':chat_id,'request_key':uuid4().hex,'question':question['prelude'],'explain':False,'use_history':False,'model':model_name})
                prelude.raise_for_status()
            body={'chat_id':chat_id,'request_key':request_key,'question':question['question'],'explain':True,
                  'use_history':bool(question.get('prelude')),'model':model_name,'book':question.get('book')}
            started=time.perf_counter();events=[];first=None;result=None
            with client.stream('POST','/api/ask/stream',json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith('data: '):continue
                    event=json.loads(line[6:]);elapsed=time.perf_counter()-started
                    events.append({'type':event['type'],'seconds':elapsed})
                    if event['type']=='block' and first is None:first=elapsed
                    if event['type']=='result':result=event['result']
            if result is None:raise ValueError('Missing terminal result')
            total=time.perf_counter()-started
            saved=client.get('/api/chats/'+chat_id);saved.raise_for_status()
            if len(saved.json())!=1+bool(question.get('prelude')):raise ValueError('Not saved exactly once')
            # Replaying the request is a read of the saved answer, never generation.
            replay=client.post('/api/ask',json=body);replay.raise_for_status()
            if not replay.json().get('reused'):raise ValueError('Request replay generated again')
            return result,{'client_total_seconds':total,'client_first_block_seconds':first,'events':events}
    finally:
        server.should_exit=True;worker.join(timeout=10);sock.close()


def run(args):
    OUT.mkdir(parents=True,exist_ok=True)
    ledger=ExperimentLedger(OUT/'ledger.sqlite3')
    with ledger.connect() as db:
        policy=db.execute("SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()
    if not policy:raise ValueError('No active Flash spending policy; live validation is stopped.')
    ledger.freeze('gold',sha(GOLD))
    baseline=args.phase in {'baseline','legacy','speed-before'}
    _,contract=snapshot(args.phase,baseline)
    ledger.freeze(args.phase+'-code',contract)
    data=ROOT/'data/courses-cases-20261010-v1' if args.phase in {'legacy','speed-before'} else DATA
    manifest,_,_,verified=verified_corpus(data,data/'index.sqlite3')
    ledger.freeze(args.phase+'-corpus',{'version':manifest['corpus_version'],'index_sha256':sha(data/'index.sqlite3'),
                 'source_sha256':{source.source_id:hashlib.sha256(raw).hexdigest() for source,raw in verified}})
    factory,model_cls=load_baseline() if baseline else (create_app,None)
    underlying=model_cls(args.model) if model_cls else create_model(args.model)
    questions=public_questions(args.split)
    if args.ids:questions=[q for q in questions if q['id'] in args.ids.split(',')]
    if args.limit:questions=questions[:args.limit]
    folder=OUT/args.phase/args.model;folder.mkdir(parents=True,exist_ok=True)
    store=Store(OUT/(args.phase+'-users.sqlite3'),user_daily_limit=100000,global_daily_limit=1000000,max_concurrent=2)
    try:
        for repetition in range(args.repeat):
            for q in questions:
                key=f'{args.phase}/{args.model}/{q["id"]}/{repetition}'
                dest=folder/f'{q["id"]}-{repetition}.json'
                if dest.exists():continue
                if ledger.exists(key):
                    print(key,'ALREADY_RESERVED_NO_RETRY',flush=True);continue
                model=RecordedModel(ledger,key,underlying,'answer',source_guard(data,q))
                if args.phase.startswith('compare'):
                    # One immutable pack per question, independent of generation model.
                    pack_path=OUT/(args.phase+'-packs')/(q['id']+'.json');pack_path.parent.mkdir(exist_ok=True)
                    if not pack_path.exists():
                        previous=[{'question':q['prelude'],'result':{'status':'RETRIEVAL_ONLY'}}] if q.get('prelude') else []
                        ctx=prepare_context(q['question'],previous,q.get('book'),bool(previous))
                        pack=retrieve(DATA,DATA/'index.sqlite3',ctx['retrieval_question'],q.get('book'))
                        pack.update(question=q['question'],trial_context=ctx['turns'])
                        pack_path.write_text(json.dumps(pack,ensure_ascii=False),encoding='utf-8')
                    pack=json.loads(pack_path.read_text(encoding='utf-8'))
                    started=time.perf_counter();events=[]
                    def emit(event):events.append({'type':event['type'],'seconds':time.perf_counter()-started})
                    result=answer_from_pack(pack,model,on_event=emit,context=pack.get('trial_context'))
                    timing={'client_total_seconds':time.perf_counter()-started,'client_first_block_seconds':next((e['seconds'] for e in events if e['type']=='block'),None),'events':events,'measurement':'same-pack generation, not HTTP'}
                else:
                    app=factory(data_dir=data,store=store,model=model,model_options={args.model:model},session_cookie_name='qa_depth_session')
                    try:
                        result,timing=http_answer(app,q,args.model,str(uuid4()))
                    except Exception as error:
                        result={'status':'HTTP_TRIAL_FAILED','answer':None,'error_type':type(error).__name__,'model_calls':int(ledger.exists(key))}
                        timing={'client_total_seconds':None,'client_first_block_seconds':None,'events':[]}
                record={'scenario':q,'phase':args.phase,'repetition':repetition,'result':result,**timing,'gold_sha256':sha(GOLD),
                        'code_contract':contract,'review_origin':'pending model-assisted source review; not human approval'}
                dest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(key,result['status'],round(timing['client_total_seconds'],3) if timing['client_total_seconds'] is not None else None,timing['client_first_block_seconds'],flush=True)
                if result['status'] in {'MODEL_FAILED','HTTP_TRIAL_FAILED'}:
                    print('STOP_ON_PROVIDER_ERROR_NO_RETRY',flush=True)
                    return
    finally:underlying.close()
    print(json.dumps(ledger.summary()),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('phase');parser.add_argument('--model',choices=ENABLED_MODELS,default='deepseek-flash')
    parser.add_argument('--split',choices=['holdout','regression'],default='holdout');parser.add_argument('--ids');parser.add_argument('--limit',type=int);parser.add_argument('--repeat',type=int,default=1)
    run(parser.parse_args())
