"""Separate transactional experiment database with leases and call reservations."""
from __future__ import annotations

from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .lab_models import ExperimentRun


class BudgetExhausted(ValueError):
    pass


class LabStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            version=db.execute("PRAGMA user_version").fetchone()[0]
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables & {"users","sessions","chats","exchanges"}:
                raise ValueError("账号库不可作为实验数据库")
            if version not in (0,1):
                raise ValueError("实验数据库版本不支持")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, state TEXT NOT NULL,
                  config TEXT NOT NULL, snapshot TEXT NOT NULL, total INTEGER NOT NULL,
                  created REAL NOT NULL, updated REAL NOT NULL, error TEXT, cancelled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS results (
                  run_id TEXT NOT NULL REFERENCES runs(id), question_id TEXT NOT NULL,
                  repetition INTEGER NOT NULL, result TEXT NOT NULL,
                  PRIMARY KEY(run_id,question_id,repetition));
                CREATE TABLE IF NOT EXISTS calls (
                  run_id TEXT NOT NULL REFERENCES runs(id), call_key TEXT NOT NULL,
                  tokens_reserved INTEGER NOT NULL, messages TEXT NOT NULL, response TEXT, usage TEXT,
                  state TEXT NOT NULL, PRIMARY KEY(run_id,call_key));
                CREATE TABLE IF NOT EXISTS reviews (
                  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), review TEXT NOT NULL,
                  reviewer TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS dataset_reviews (
                  id TEXT PRIMARY KEY, dataset_sha TEXT NOT NULL, question_id TEXT NOT NULL,
                  reviewer TEXT NOT NULL, rationale TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY CHECK(id=1),owner TEXT,lease REAL);
                INSERT OR IGNORE INTO worker VALUES (1,NULL,0);
                PRAGMA user_version=1;
            """)
            worker=db.execute("SELECT lease FROM worker WHERE id=1").fetchone()
            if worker[0] <= time.time():
                db.execute("UPDATE runs SET state='interrupted',error='工作进程已离线；可恢复检查点',updated=? WHERE state='running'",(time.time(),))

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    def create(self, config, snapshot, total, *, initial_state="queued"):
        values = json.dumps(config, ensure_ascii=False, sort_keys=True)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT id,config,snapshot FROM runs WHERE request_key=?", (config["request_key"],)).fetchone()
            if previous:
                if previous["config"] != values or json.loads(previous["snapshot"])["dataset_sha256"] != snapshot["dataset_sha256"]:
                    raise ValueError("请求编号已用于不同实验")
                return previous["id"], True
            run_id, now = uuid4().hex, time.time()
            db.execute("INSERT INTO runs(id,request_key,state,config,snapshot,total,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                       (run_id, config["request_key"], initial_state, values, json.dumps(snapshot, ensure_ascii=False), total, now, now))
            return run_id, False

    def get(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("实验不存在")
            completed = db.execute("SELECT COUNT(*) FROM results WHERE run_id=?", (run_id,)).fetchone()[0]
            calls = db.execute("SELECT COUNT(*),COALESCE(SUM(tokens_reserved),0) FROM calls WHERE run_id=?", (run_id,)).fetchone()
        return ExperimentRun(id=row["id"], state=row["state"], config=json.loads(row["config"]),
            snapshot=json.loads(row["snapshot"]), completed=completed, total=row["total"],
            calls_reserved=calls[0], tokens_reserved=calls[1], created=row["created"], updated=row["updated"],
            error=row["error"]).model_dump()

    def list(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM runs ORDER BY created DESC LIMIT 100")]
        return [self.get(i) for i in ids]

    def claim(self, owner):
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            worker = db.execute("SELECT * FROM worker WHERE id=1").fetchone()
            if worker["owner"] and worker["lease"] > now:
                return None
            db.execute("UPDATE runs SET state='interrupted',error='工作进程中断；可恢复已保存检查点',updated=? WHERE state='running'", (now,))
            row = db.execute("SELECT id FROM runs WHERE state='queued' AND cancelled=0 ORDER BY created LIMIT 1").fetchone()
            if not row:
                db.execute("UPDATE worker SET owner=NULL,lease=0 WHERE id=1")
                return None
            db.execute("UPDATE worker SET owner=?,lease=? WHERE id=1", (owner, now + 360))
            db.execute("UPDATE runs SET state='running',updated=?,error=NULL WHERE id=?", (now, row[0]))
            return row[0]

    def heartbeat(self, owner):
        with self.db() as db:
            if db.execute("UPDATE worker SET lease=? WHERE id=1 AND owner=?", (time.time()+360, owner)).rowcount != 1:
                raise ValueError("实验工作进程租期已被接管")

    def release(self, owner):
        with self.db() as db:
            db.execute("UPDATE worker SET owner=NULL,lease=0 WHERE id=1 AND owner=?", (owner,))

    def set_state(self, run_id, state, error=None):
        with self.db() as db:
            db.execute("UPDATE runs SET state=?,error=?,updated=? WHERE id=?", (state, error, time.time(), run_id))

    def cancelled(self, run_id):
        with self.db() as db:
            return bool(db.execute("SELECT cancelled FROM runs WHERE id=?", (run_id,)).fetchone()[0])

    def cancel(self, run_id):
        self.get(run_id)
        with self.db() as db:
            db.execute("UPDATE runs SET cancelled=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,updated=? WHERE id=?",
                       (time.time(), run_id))

    def resume(self, run_id):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,snapshot FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("实验不存在")
            if json.loads(row["snapshot"]).get("imported"):
                raise ValueError("导入结果仅作重放，不能恢复为新检索任务")
            if row[0] not in {"interrupted", "failed", "cancelled"}:
                raise ValueError("仅中断、失败或取消的实验可恢复；预算耗尽请新建实验")
            db.execute("UPDATE runs SET state='queued',cancelled=0,error=NULL,updated=? WHERE id=?", (time.time(), run_id))

    def results(self, run_id):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT result FROM results WHERE run_id=? ORDER BY question_id,repetition", (run_id,))]

    def save_result(self, run_id, result):
        with self.db() as db:
            db.execute("INSERT INTO results VALUES(?,?,?,?)", (run_id, result["id"], result.get("repetition", 0), json.dumps(result, ensure_ascii=False)))
            db.execute("UPDATE runs SET updated=? WHERE id=?", (time.time(), run_id))

    def reserve_call(self, run_id, key, messages, token_estimate):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM calls WHERE run_id=? AND call_key=?", (run_id, key)).fetchone()
            if prior:
                if prior["messages"] != json.dumps(messages, ensure_ascii=False):
                    raise ValueError("模型调用快照不一致")
                if prior["state"] == "done":
                    return prior["response"], json.loads(prior["usage"])
                raise ValueError("上次模型调用未完整落盘；恢复时不自动重试或重复计费")
            row = db.execute("SELECT config,cancelled,state FROM runs WHERE id=?", (run_id,)).fetchone()
            config = json.loads(row["config"])
            count, tokens = db.execute("SELECT COUNT(*),COALESCE(SUM(tokens_reserved),0) FROM calls WHERE run_id=?", (run_id,)).fetchone()
            if row["cancelled"] or row["state"] != "running":
                raise ValueError("实验已取消或未在运行")
            if count + 1 > config["call_budget"] or tokens + token_estimate > config["token_budget"]:
                raise BudgetExhausted("实验调用次数或 token 预留预算耗尽")
            db.execute("INSERT INTO calls VALUES(?,?,?,?,NULL,NULL,'reserved')",
                       (run_id, key, token_estimate, json.dumps(messages, ensure_ascii=False)))
        return None

    def finish_call(self, run_id, key, response, usage):
        with self.db() as db:
            db.execute("UPDATE calls SET state='done',response=?,usage=? WHERE run_id=? AND call_key=?",
                       (response, json.dumps(usage, ensure_ascii=False), run_id, key))

    def fail_call(self, run_id, key, usage):
        with self.db() as db:
            db.execute("UPDATE calls SET state='failed',usage=? WHERE run_id=? AND call_key=?",
                       (json.dumps(usage, ensure_ascii=False), run_id, key))

    def call_usage(self, run_id):
        with self.db() as db:
            return [{"call_key": r["call_key"], "state": r["state"], "tokens_reserved": r["tokens_reserved"],
                     "usage": json.loads(r["usage"]) if r["usage"] else None} for r in db.execute("SELECT * FROM calls WHERE run_id=?", (run_id,))]

    def call_records(self, run_id):
        with self.db() as db:
            return [{"call_key":r["call_key"],"state":r["state"],"messages":json.loads(r["messages"]),
                     "response":r["response"],"usage":json.loads(r["usage"]) if r["usage"] else None}
                    for r in db.execute("SELECT * FROM calls WHERE run_id=?",(run_id,))]

    def review(self, run_id, review, reviewer):
        results = self.results(run_id)
        result = next((r for r in results if r["id"] == review["question_id"] and r.get("repetition",0) == review["repetition"]), None)
        if result is None or review["claim_id"] not in {d["claim_id"] for d in result.get("diagnostics", [])}:
            raise ValueError("待复核声明不存在")
        with self.db() as db:
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?)", (uuid4().hex, run_id, json.dumps(review, ensure_ascii=False), reviewer, time.time()))

    def reviews(self, run_id):
        with self.db() as db:
            return [{**json.loads(r["review"]), "reviewer": r["reviewer"], "created": r["created"]}
                    for r in db.execute("SELECT * FROM reviews WHERE run_id=? ORDER BY created,id", (run_id,))]

    def approve_dataset(self, sha, qid, reviewer, rationale):
        with self.db() as db:
            db.execute("INSERT INTO dataset_reviews VALUES(?,?,?,?,?,?)", (uuid4().hex, sha, qid, reviewer, rationale, time.time()))

    def approved(self, sha):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM dataset_reviews WHERE dataset_sha=? ORDER BY created,id", (sha,))]
