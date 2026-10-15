"""Public experiments with preserved history, incremental cost caps and no retries."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from .limits import MODEL_OUTPUT_TOKENS
from .rag import ProviderError


class ValidationStopped(ProviderError):
    def __init__(self, reason):
        super().__init__('VALIDATION_BUDGET_STOPPED', attempts=0)
        self.reason = reason


class ExperimentLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS contracts(name TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,call_key TEXT UNIQUE NOT NULL,provider TEXT,model TEXT,purpose TEXT,reserved INTEGER,state TEXT,messages TEXT,raw TEXT,usage TEXT,error TEXT,created TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS flash_spend(call_key TEXT PRIMARY KEY,reserved_micros INTEGER NOT NULL,settled_micros INTEGER,state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS spend_authorizations(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,limit_micros INTEGER NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS experiment_phases(name TEXT PRIMARY KEY,purpose TEXT UNIQUE NOT NULL,max_calls INTEGER NOT NULL,limit_micros INTEGER NOT NULL,protected INTEGER NOT NULL,created TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS phase_calls(call_key TEXT PRIMARY KEY,phase TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db: yield db
        finally: db.close()

    def freeze(self, name, value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.connect() as db:
            old = db.execute("SELECT value FROM contracts WHERE name=?", (name,)).fetchone()
            if old and old[0] != encoded: raise ValueError("Experiment contract changed: " + name)
            db.execute("INSERT OR IGNORE INTO contracts VALUES(?,?)", (name, encoded))

    def exists(self, key):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM calls WHERE call_key=?", (key,)).fetchone() is not None

    def reserve(self, key, model, purpose, messages):
        encoded = json.dumps(messages, ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            policy=db.execute("SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()
            if policy:
                policy=json.loads(policy[0])
                latest=db.execute('SELECT limit_micros FROM spend_authorizations ORDER BY id DESC LIMIT 1').fetchone()
                if latest:policy['limit_micros']=latest[0]
                if model.model_name!='deepseek-flash' or getattr(model,'provider','deepseek')!='deepseek':
                    raise ValidationStopped('Only DeepSeek Flash is authorized; Pro and Max are disabled.')
                # Peak CNY rates, treating every input token as a cache miss.
                # UTF-8 bytes plus framing bound input tokens conservatively.
                reserve=(len(encoded.encode('utf-8'))+1024)*2+MODEL_OUTPUT_TOKENS*8
                used=db.execute("SELECT coalesce(sum(coalesce(settled_micros,reserved_micros)),0) FROM flash_spend").fetchone()[0]
                phases=db.execute('SELECT name,purpose,max_calls,limit_micros,protected FROM experiment_phases').fetchall()
                own=None;protected=0
                for name,phase_purpose,max_calls,phase_limit,is_protected in phases:
                    count,phase_used=db.execute('SELECT count(*),coalesce(sum(coalesce(s.settled_micros,s.reserved_micros)),0) FROM phase_calls p JOIN flash_spend s ON p.call_key=s.call_key WHERE p.phase=?',(name,)).fetchone()
                    if purpose==phase_purpose:
                        own=name
                        if count>=max_calls or phase_used+reserve>phase_limit:raise ValidationStopped('Experiment phase call/cost bound reached.')
                    elif is_protected:protected+=max(0,phase_limit-phase_used)
                if used+reserve+protected>policy['limit_micros']:raise ValidationStopped('Flash total bound or protected acceptance allocation reached.')
                db.execute("INSERT INTO flash_spend VALUES(?,?,NULL,'authorized')",(key,reserve))
                if own:db.execute('INSERT INTO phase_calls VALUES(?,?)',(key,own))
            return db.execute("INSERT INTO calls(call_key,provider,model,purpose,reserved,state,messages,created) VALUES(?,?,?,?,?,'reserved',?,?)",
                (key, getattr(model,'provider','custom'),model.model_name,purpose,len(encoded.encode())+10240,encoded,datetime.now(timezone.utc).isoformat())).lastrowid

    def finish(self, call_id, *, raw=None, usage=None, error=None):
        with self.connect() as db:
            n = db.execute("UPDATE calls SET state=?,raw=?,usage=?,error=? WHERE id=? AND state='reserved'",
                ('failed' if error else 'completed',raw,json.dumps(usage or {}),error,call_id)).rowcount
            if n != 1: raise ValueError("Experiment completion is not repeatable")
            row=db.execute('SELECT call_key FROM calls WHERE id=?',(call_id,)).fetchone()
            if usage and type(usage.get('prompt_tokens')) is int and type(usage.get('output_tokens')) is int and usage['prompt_tokens']>=0 and usage['output_tokens']>=0:
                upper=usage['prompt_tokens']*2+usage['output_tokens']*8
                db.execute("UPDATE flash_spend SET settled_micros=?,state='settled' WHERE call_key=?",(upper,row[0]))
            else:db.execute("UPDATE flash_spend SET state='usage_unknown' WHERE call_key=?",(row[0],))

    def enable_flash_budget(self, limit_micros=500_000):
        self.freeze('flash-only-resume-20261015',{'limit_micros':limit_micros,'input_micros_per_token':2,
                    'output_micros_per_token':8,'basis':'DeepSeek official CNY peak rates checked 2026-10-15',
                    'authorization':'User resumed Flash; Pro and Max prohibited. Alibaba requires verified free-only protection.'})
        with self.connect() as db:
            db.execute('DROP TRIGGER IF EXISTS user_stopped_paid_validation')
            db.execute("CREATE TRIGGER user_stopped_paid_validation BEFORE INSERT ON calls WHEN NEW.model!='deepseek-flash' OR NOT EXISTS(SELECT 1 FROM flash_spend WHERE call_key=NEW.call_key AND state='authorized') BEGIN SELECT RAISE(ABORT,'ONLY_BUDGETED_FLASH_ALLOWED'); END")

    def authorize_total_budget(self, name, limit_micros, reason):
        if not isinstance(limit_micros,int) or limit_micros<=0 or not reason.strip():
            raise ValueError('Explicit total budget and authorization are required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM contracts WHERE name='flash-only-resume-20261015'").fetchone():
                raise ValueError('Original Flash policy must be preserved first')
            old=db.execute('SELECT limit_micros,reason FROM spend_authorizations WHERE name=?',(name,)).fetchone()
            if old:
                if old!=(limit_micros,reason):raise ValueError('Authorization changed')
                return
            db.execute('INSERT INTO spend_authorizations(name,limit_micros,reason,created) VALUES(?,?,?,?)',
                       (name,limit_micros,reason,datetime.now(timezone.utc).isoformat()))

    def authorize_phase(self, name, purpose, max_calls, limit_micros, *, protected=False):
        """Append an immutable subdivision; never resets global historical spending."""
        if not name or not purpose or type(max_calls) is not int or max_calls<=0 or type(limit_micros) is not int or limit_micros<=0:
            raise ValueError('Positive phase limits required')
        values=(purpose,max_calls,limit_micros,int(protected))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT purpose,max_calls,limit_micros,protected FROM experiment_phases WHERE name=?',(name,)).fetchone()
            if old and old!=values:raise ValueError('Phase authorization changed')
            db.execute('INSERT OR IGNORE INTO experiment_phases VALUES(?,?,?,?,?,?)',(name,*values,datetime.now(timezone.utc).isoformat()))

    def phase_summary(self):
        with self.connect() as db:
            rows=db.execute('SELECT name,purpose,max_calls,limit_micros,protected FROM experiment_phases').fetchall()
            result=[]
            for name,purpose,count,limit,protected in rows:
                actual,used=db.execute('SELECT count(*),coalesce(sum(coalesce(s.settled_micros,s.reserved_micros)),0) FROM phase_calls p JOIN flash_spend s ON p.call_key=s.call_key WHERE p.phase=?',(name,)).fetchone()
                result.append(dict(name=name,purpose=purpose,max_calls=count,limit_micros=limit,protected=bool(protected),calls=actual,used_upper_micros=used))
            return result

    def summary(self):
        with self.connect() as db:
            rows = db.execute("SELECT state,reserved,usage,provider,purpose FROM calls").fetchall()
            spend=db.execute("SELECT coalesce(sum(coalesce(settled_micros,reserved_micros)),0) FROM flash_spend").fetchone()[0]
            latest=db.execute('SELECT limit_micros FROM spend_authorizations ORDER BY id DESC LIMIT 1').fetchone()
            original=db.execute("SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()
            limit=latest[0] if latest else json.loads(original[0])['limit_micros'] if original else None
        usage=[json.loads(row[2] or '{}') for row in rows]
        return {"calls_reserved":len(rows),"tokens_reserved":sum(r[1] for r in rows),"call_limit":None,"token_limit":None,
                "completed":sum(r[0]=='completed' for r in rows),"failed":sum(r[0]=='failed' for r in rows),
                "unresolved":sum(r[0]=='reserved' for r in rows),
                "input_tokens":sum(u.get('prompt_tokens') or 0 for u in usage),
                "output_tokens":sum(u.get('output_tokens') or 0 for u in usage),"resumed_flash_cost_bound_cny":spend/1_000_000,
                "flash_total_limit_cny":limit/1_000_000 if limit is not None else None}


class RecordedModel:
    span_references = True

    def __init__(self, ledger, key, model, purpose, guard=None):
        self.ledger,self.key,self.model,self.purpose,self.guard = ledger,key,model,purpose,guard
        self.model_name,self.provider = model.model_name,getattr(model,'provider','custom')

    def _run(self, messages, callback=None):
        if self.guard: self.guard(messages)
        call = self.ledger.reserve(self.key,self.model,self.purpose,messages)
        try:
            raw, usage = self.model.generate_stream(messages,callback) if callback is not None else self.model.generate(messages)
        except Exception as error:
            self.ledger.finish(call,error=getattr(error,'error_type',type(error).__name__),usage=getattr(error,'usage',None))
            raise
        self.ledger.finish(call,raw=raw,usage=usage)
        return raw, usage

    def generate(self, messages): return self._run(messages)
    def generate_stream(self, messages, callback): return self._run(messages,callback)
