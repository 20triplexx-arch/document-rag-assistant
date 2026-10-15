"""Independent, crash-safe public trial budget; never uses the previous QA ledger."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


class TrialBudget:
    limits = {"baseline": 4, "dev": 8, "acceptance": 8}
    max_calls, max_tokens = 20, 1_000_000

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS contracts (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, phase TEXT, question_id TEXT, reserved INTEGER, state TEXT, messages TEXT, raw TEXT, usage TEXT, error TEXT, created TEXT, UNIQUE(phase,question_id))")
        self.freeze("limits", json.dumps([self.limits, self.max_calls, self.max_tokens], sort_keys=True))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def freeze(self, name, value):
        with self.connect() as db:
            row = db.execute("SELECT value FROM contracts WHERE name=?", (name,)).fetchone()
            if row and row[0] != value:
                raise ValueError("Frozen trial contract changed: " + name)
            db.execute("INSERT OR IGNORE INTO contracts VALUES (?,?)", (name, value))

    def reserve(self, phase, question_id, messages):
        if phase not in self.limits:
            raise ValueError("Unknown trial phase")
        # UTF-8 byte count is a conservative input token bound, plus output cap.
        reservation = max(25_000, len(json.dumps(messages, ensure_ascii=False).encode()) + 8192 + 2048)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count, tokens = db.execute("SELECT count(*),coalesce(sum(reserved),0) FROM calls").fetchone()
            phase_count = db.execute("SELECT count(*) FROM calls WHERE phase=?", (phase,)).fetchone()[0]
            if count >= self.max_calls or tokens + reservation > self.max_tokens or phase_count >= self.limits[phase]:
                raise ValueError("Trial budget exhausted")
            if db.execute("SELECT 1 FROM calls WHERE phase=? AND question_id=?", (phase, question_id)).fetchone():
                raise ValueError("Trial already reserved; never retry a lost response")
            cur = db.execute("INSERT INTO calls(phase,question_id,reserved,state,messages,created) VALUES(?,?,?,'reserved',?,?)",
                             (phase, question_id, reservation, json.dumps(messages, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            return cur.lastrowid

    def finish(self, call_id, raw=None, usage=None, error=None):
        with self.connect() as db:
            changed = db.execute("UPDATE calls SET state=?,raw=?,usage=?,error=? WHERE id=? AND state='reserved'",
                                 ("failed" if error else "completed", raw, json.dumps(usage or {}), error, call_id)).rowcount
            if changed != 1:
                raise ValueError("Trial completion is not repeatable")

    def summary(self):
        with self.connect() as db:
            count, tokens = db.execute("SELECT count(*),coalesce(sum(reserved),0) FROM calls").fetchone()
            return {"calls_reserved": count, "tokens_reserved": tokens, "limit_calls": self.max_calls,
                    "limit_tokens": self.max_tokens, "phases": {p: db.execute("SELECT count(*) FROM calls WHERE phase=?", (p,)).fetchone()[0] for p in self.limits}}


class TrialModel:
    model_name = "deepseek-flash"
    span_references = True

    def __init__(self, budget, phase, question_id, model, *, expected_question=None, public_texts=None):
        self.budget, self.phase, self.question_id, self.model = budget, phase, question_id, model
        self.expected_question, self.public_texts = expected_question, public_texts

    def _run(self, messages, callback=None):
        if self.public_texts is not None:
            payload = json.loads(messages[1]["content"])
            if payload.get("DISCUSSION_CONTEXT") or payload.get("QUESTION") != self.expected_question:
                raise ValueError("Trial can only send its frozen public question without history")
            for evidence in payload["EVIDENCE"]:
                text = self.public_texts.get((evidence["book"], evidence["path"]))
                if text is None or any(span["text"] not in text for span in evidence.get("spans", [])):
                    raise ValueError("Trial evidence is not an approved public source")
        call_id = self.budget.reserve(self.phase, self.question_id, messages)
        try:
            result = self.model.generate_stream(messages, callback) if callback is not None else self.model.generate(messages)
        except Exception as error:
            self.budget.finish(call_id, error=type(error).__name__, usage=getattr(error, "usage", None))
            raise
        self.budget.finish(call_id, *result)
        return result

    def generate(self, messages):
        return self._run(messages)

    def generate_stream(self, messages, callback):
        return self._run(messages, callback)
