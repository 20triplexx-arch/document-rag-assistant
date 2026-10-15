"""Public QA experiment ledger. Reservations survive crashes; no implicit retry."""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

PHASE_LIMITS = {"baseline":16, "candidate":24, "oracle":8, "acceptance":8, "retest":4}
MAX_CALLS, MAX_TOKENS, RESERVATION = 60, 3_000_000, 50_000

class QABudget:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, phase TEXT, question_id TEXT, reserved INTEGER, state TEXT, messages TEXT, raw TEXT, usage TEXT, error TEXT, created TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS contracts (name TEXT PRIMARY KEY, value TEXT)")

    @contextmanager
    def connect(self):
        database=sqlite3.connect(self.path,timeout=30)
        try:
            with database:yield database
        finally:database.close()

    def freeze(self, name, value):
        with self.connect() as db:
            row = db.execute("SELECT value FROM contracts WHERE name=?", (name,)).fetchone()
            if row and row[0] != value:
                raise ValueError("Frozen QA experiment contract changed: " + name)
            db.execute("INSERT OR IGNORE INTO contracts VALUES (?, ?)", (name,value))

    def reserve(self, phase, question_id, messages):
        if phase not in PHASE_LIMITS:
            raise ValueError("Unknown QA phase")
        from .limits import MODEL_OUTPUT_TOKENS
        reservation=max(25_000,len(json.dumps(messages,ensure_ascii=False).encode("utf-8"))+MODEL_OUTPUT_TOKENS+2048)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total, tokens = db.execute("SELECT count(*), coalesce(sum(reserved),0) FROM calls").fetchone()
            count = db.execute("SELECT count(*) FROM calls WHERE phase=?", (phase,)).fetchone()[0]
            if total >= MAX_CALLS or tokens + reservation > MAX_TOKENS or count >= PHASE_LIMITS[phase]:
                raise ValueError("QA experiment budget exhausted")
            if phase != "retest" and db.execute("SELECT 1 FROM calls WHERE phase=? AND question_id=?", (phase,question_id)).fetchone():
                raise ValueError("Call already reserved; do not retry or replay a lost response")
            cur = db.execute("INSERT INTO calls(phase,question_id,reserved,state,messages,created) VALUES(?,?,?,'reserved',?,?)",
                             (phase,question_id,reservation,json.dumps(messages,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
            return cur.lastrowid

    def finish(self, call_id, raw=None, usage=None, error=None):
        with self.connect() as db:
            changed = db.execute("UPDATE calls SET state=?,raw=?,usage=?,error=? WHERE id=? AND state='reserved'",
                                ("failed" if error else "completed",raw,json.dumps(usage or {},ensure_ascii=False),error,call_id)).rowcount
            if changed != 1:
                raise ValueError("Call completion is not repeatable")

    def summary(self):
        with self.connect() as db:
            total,tokens = db.execute("SELECT count(*),coalesce(sum(reserved),0) FROM calls").fetchone()
            return {"calls_reserved":total,"tokens_reserved":tokens,"limit_calls":MAX_CALLS,"limit_tokens":MAX_TOKENS,
                    "phases":{p:db.execute("SELECT count(*) FROM calls WHERE phase=?",(p,)).fetchone()[0] for p in PHASE_LIMITS}}

class BudgetedModel:
    model_name = "deepseek-flash"
    def __init__(self, budget, phase, question_id, model):
        self.budget,self.phase,self.question_id,self.model = budget,phase,question_id,model
    def generate(self, messages):
        call_id = self.budget.reserve(self.phase,self.question_id,messages)
        try:
            raw,usage = self.model.generate(messages)
        except Exception as exc:
            self.budget.finish(call_id,error=type(exc).__name__,usage=getattr(exc,"usage",None))
            raise
        self.budget.finish(call_id,raw,usage)
        return raw,usage
