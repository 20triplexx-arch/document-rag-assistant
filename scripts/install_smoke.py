"""Real HTTP installation check. Refuses an existing account DB; never generates."""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]


def entry(script, environment, *arguments):
    # Start-Process children can retain inherited pipe handles on Windows 5.1.
    # Capture to a file so completion depends on the shell exit, not pipe EOF.
    args=['powershell.exe','-NoProfile','-ExecutionPolicy','RemoteSigned','-File',
          str(ROOT/script),*map(str,arguments)]
    path=ROOT/'output'/('smoke-entry-'+uuid4().hex+'.log')
    with path.open('wb') as log:
        result=subprocess.run(args,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=115)
    return subprocess.CompletedProcess(args,result.returncode,stdout=path.read_bytes(),stderr=b'')


def main():
    if (ROOT/'output/users.sqlite3').exists():
        raise SystemExit('Refusing existing account DB. Run only in a fresh isolated checkout.')
    report={'status':'FAILED','model_calls':0,'checks':[]}
    environment=os.environ.copy()
    for key in ('DEEPSEEK_API_KEY','DASHSCOPE_API_KEY','DASHSCOPE_WORKSPACE_ID',
                'RAG_BAILIAN_FREE_ONLY_CONFIRMED','OPENAI_API_KEY','RAG_DEFAULT_MODEL'):
        environment.pop(key,None)
    environment['DEEPSEEK_MODEL']='deepseek-flash'
    environment['RAG_COOKIE_SECURE']='false'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    environment['RAG_PORT']=str(port)
    started=time.perf_counter()
    process=None
    launch_attempted=False
    try:
        print('Checking occupied-port protection...',flush=True)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen();occupied_port=occupied.getsockname()[1]
            for script in ('start.ps1','background.ps1','stop.ps1'):
                refused=entry(script,environment,'-Port',occupied_port)
                assert refused.returncode!=0,script+' must refuse unrelated occupied port'
                assert occupied.getsockname()[1]==occupied_port
        report['checks'].append('occupied_port_and_unknown_process_not_stopped')
        print('Starting isolated background server...',flush=True)
        launch_attempted=True
        process=entry('background.ps1',environment)
        if process.returncode:
            # Startup logs have no passwords/tokens; preserve locally, not in CI artifacts.
            (ROOT/'output/install-smoke-start.log').write_bytes(process.stdout+process.stderr)
            raise AssertionError('background startup failed; see local install-smoke-start.log')
        report['checks'].append('background_ready_with_environment_port')
        print('Checking authenticated retrieval and persistence...',flush=True)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30,trust_env=False) as client:
            assert client.get('/').status_code==200
            library=client.get('/api/library');library.raise_for_status();library=library.json()
            assert library['source_files']==216 and library['chunks']==4220
            assert library['answer_schema_version']==1 and library['default_model']=='deepseek-flash'
            report['checks'].append('real_default_corpus_http')
            username='install-'+uuid4().hex[:10];password=secrets.token_urlsafe(24)
            registration=client.post('/api/register',json={'username':username,'password':password})
            registration.raise_for_status();client.headers['X-CSRF-Token']=registration.json()['csrf']
            client.post('/api/logout').raise_for_status()
            login=client.post('/api/login',json={'username':username,'password':password})
            login.raise_for_status();client.headers['X-CSRF-Token']=login.json()['csrf']
            report['checks'].append('register_logout_login')
            chat=client.post('/api/chats',json={'title':'安装验收临时讨论'});chat.raise_for_status()
            chat_id=chat.json()['id']
            result=client.post('/api/ask',json={'chat_id':chat_id,'request_key':uuid4().hex,
                'question':'工具调用是什么？','book':None,'explain':False})
            result.raise_for_status();answer=result.json()
            assert answer['model_calls']==0 and answer['status']=='RETRIEVAL_ONLY' and answer['evidence']
            history=client.get('/api/chats/'+chat_id);history.raise_for_status()
            assert len(history.json())==1
            report['checks'].append('retrieval_only_and_saved_discussion')
            # Streaming retrieval exercises the real SSE endpoint without generation.
            stream=client.post('/api/ask/stream',json={'chat_id':chat_id,'request_key':uuid4().hex,
                'question':'长期记忆是什么？','book':None,'explain':False})
            stream.raise_for_status()
            assert 'text/event-stream' in stream.headers['content-type'] and 'RETRIEVAL_ONLY' in stream.text
            report['checks'].append('streaming_retrieval_only')
        database=ROOT/'output/users.sqlite3'
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
            assert db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0]==2
        report['checks'].append('zero_model_job_reservations')
        # An isolated synthetic active job tests stop protection without generating.
        job=uuid4().hex
        with sqlite3.connect(database) as db:
            user=db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()[0]
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                       (job,user,'synthetic-stop-test','installation-test','active',time.time()+120,None))
        try:
            assert entry('stop.ps1',environment).returncode!=0
            with httpx.Client(trust_env=False) as probe:
                assert probe.get(f'http://127.0.0.1:{port}/').status_code==200
            report['checks'].append('active_job_prevents_stop_synthetic_fixture')
        finally:
            with sqlite3.connect(database) as db:db.execute("UPDATE jobs SET state='finished' WHERE id=?",(job,))
        report['status']='PASSED'
    except Exception as error:
        report['error_type']=type(error).__name__
        report['failure']=str(error) if isinstance(error,AssertionError) else 'Check local server logs.'
        raise
    finally:
        if launch_attempted:
            stopped=entry('stop.ps1',environment)
            report['stop_exit_code']=stopped.returncode
            if stopped.returncode!=0:report['status']='FAILED'
        report['elapsed_seconds']=round(time.perf_counter()-started,3)
        (ROOT/'output').mkdir(exist_ok=True)
        (ROOT/'output/install-smoke-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status']=='PASSED' else 1


if __name__=='__main__':sys.exit(main())
