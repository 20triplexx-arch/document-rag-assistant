"""Public-data experiment orchestration, immutable snapshots and controlled replay."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
from importlib.metadata import version, PackageNotFoundError
import threading
import time
from uuid import uuid4

from .adapters import LocalRagAdapter, E5_MODEL, E5_REVISION, VECTOR_VERSION
from .diagnostics import (JUDGE_VERSION, calibration, diagnose_rules, generation_summary,
                          judge_messages, validate_judgment)
from .evaluation import (DEFAULT_DATASET, EVALUATOR_VERSION, Dataset, EvaluationDataset,
                         load_dataset, score_question, summarize)
from .lab_models import ExperimentConfig
from .lab_store import BudgetExhausted, LabStore
from .rag import (CitedDraft, DeepSeekModel, PROMPT_VERSION, RETRIEVER_VERSION, ProviderError,
                  build_messages, normalize_quote, validate_draft, visible_prose)
from .limits import MAX_EVIDENCE_CHARS, MODEL_OUTPUT_TOKENS
from .core import index_contract
from .answer_schema import AnswerV2,validate_v2
from .qa_evaluation import QA_DATASET,load_qa_dataset,score_qa


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def code_contract():
    root=Path(__file__).parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ("core.py","rag.py","adapters.py","evaluation.py","diagnostics.py","lab.py","lab_store.py","lab_models.py","limits.py",
             "question_plan.py","qa_retrieval.py","qa_vectors.py","qa_evaluation.py","code_index.py","answer_schema.py","qa_prompt.py","conversation.py","response_policy.py","support_context.py")}


def package_contract():
    packages={}
    for name in ("fastapi","pydantic","openai","numpy","sentence-transformers","transformers","torch"):
        try:packages[name]=version(name)
        except PackageNotFoundError:packages[name]=None
    return packages


LOADED_CODE_CONTRACT=code_contract()


def support_links(result,sources):
    for point in result["points"]:
        for span in point["supports"]:
            span["line_url"]=f"{sources[span['source_id']].source_url}#L{span['start_line']}-L{span['end_line']}"
    return result


class Lab:
    def __init__(self, data_dir: Path, database: Path, *, datasets=None, model=None, adapter_factory=LocalRagAdapter):
        self.data_dir = data_dir
        self.default_datasets = datasets is None
        self.store = LabStore(database)
        self.datasets = datasets or {"agent-learning-v1": DEFAULT_DATASET,
            "agent-learning-v2": DEFAULT_DATASET.with_name("agent-learning-v2.json"),"agent-qa-v1.1":QA_DATASET}
        self.model = model
        self.adapter_factory = adapter_factory
        self.stop_event = threading.Event()
        self.thread = None
        self.thread_lock = threading.Lock()

    def dataset(self, name):
        if name not in self.datasets:
            raise ValueError("未知题集")
        return (load_qa_dataset if name=="agent-qa-v1.1" else load_dataset)(self.datasets[name],self.dataset_dir(name))

    def dataset_dir(self,name):
        if self.default_datasets:
            return Path(__file__).resolve().parents[1]/"data"/("qa-20261014-v1" if name=="agent-qa-v1.1" else "courses-cases-20261010-v1")
        return self.data_dir

    def versions(self,manifest):
        if manifest["schema_version"]==3:
            from .qa_retrieval import RETRIEVER_VERSION as retriever
            from .qa_prompt import PROMPT_VERSION as prompt
            return retriever,prompt,2
        return RETRIEVER_VERSION,PROMPT_VERSION,1

    def dataset_info(self, name, split="dev"):
        loaded = self.dataset(name)
        dataset, digest = loaded[:2]
        approved = {r["question_id"] for r in self.store.approved(digest)}
        questions = []
        for q in dataset.questions:
            if split != "all" and q.split != split:
                continue
            record = q.model_dump()
            record["review_status"] = "approved" if dataset.schema_version == 1 or q.review_status == "approved" or q.id in approved else "pending"
            for point in record["points"]:
                for span in point["supports"]:
                    source = loaded[4][span["source_id"]]
                    span["line_url"] = f"{source.source_url}#L{span['start_line']}-L{span['end_line']}"
            questions.append(record)
        return {"name": name, "version": dataset.dataset_version, "sha256": digest,
                "splits": dict(Counter(q.split for q in dataset.questions)), "questions": questions}

    def approve(self, name, body, reviewer):
        dataset, digest = self.dataset(name)[:2]
        if body.question_id not in {q.id for q in dataset.questions}:
            raise ValueError("题号不存在")
        self.store.approve_dataset(digest, body.question_id, reviewer, body.rationale)

    def create(self, config: ExperimentConfig, *, importing=False):
        if code_contract()!=LOADED_CODE_CONTRACT:
            raise ValueError("运行中的代码与磁盘版本不同；请重启服务或使用新的 CLI 进程")
        loaded = self.dataset(config.dataset)
        dataset, digest, manifest, chunks = loaded[:4]
        approvals = self.store.approved(digest)
        approved = {r["question_id"] for r in approvals}
        questions = [q for q in dataset.questions if config.split == "all" or q.split == config.split]
        if not questions:
            raise ValueError("该题集没有选定分组")
        pending = [q.id for q in questions if dataset.schema_version >= 2 and q.review_status != "approved" and q.id not in approved]
        if pending and not config.allow_pending:
            raise ValueError(f"有 {len(pending)} 道题待人工复核；可显式创建草稿实验，结果不作为验收")
        retriever,prompt_version,schema=self.versions(manifest)
        prompt = build_messages("", [],schema_version=schema)[0]["content"]
        model_name = (self.model or DeepSeekModel()).model_name if config.live else None
        snapshot = {"dataset_sha256": digest, "dataset": dataset.model_dump(),
            "dataset_reviews": approvals, "pending_questions": pending,
            "corpus_version": manifest["corpus_version"], "index_contract": index_contract(manifest),
            "retriever": retriever, "evaluator": "qa-source-span-v1" if schema==2 else EVALUATOR_VERSION,
            "prompt_version": prompt_version, "prompt": prompt, "prompt_sha256": sha(prompt),
            "judge_version": JUDGE_VERSION, "vector_version": VECTOR_VERSION,
            "embedding_model": E5_MODEL, "embedding_revision": E5_REVISION,
            "model": model_name, "python": platform.python_version(),
            "code_sha256":LOADED_CODE_CONTRACT,"packages":package_contract(),
            "selected_question_ids": [q.id for q in questions], "imported": importing}
        snapshot["snapshot_sha256"] = sha(snapshot)
        run_id, reused = self.store.create(config.model_dump(), snapshot, len(questions)*config.repeat,
                                          initial_state="interrupted" if importing else "queued")
        return {"id": run_id, "reused": reused}

    def start(self):
        with self.thread_lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._loop, name="rag-lab-worker", daemon=True)
            self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        owner = uuid4().hex
        while not self.stop_event.is_set():
            if code_contract()!=LOADED_CODE_CONTRACT:
                return
            run_id = self.store.claim(owner)
            if run_id:
                heartbeat_stop=threading.Event()
                def beat():
                    while not heartbeat_stop.wait(30):
                        self.store.heartbeat(owner)
                heartbeat=threading.Thread(target=beat,daemon=True)
                heartbeat.start()
                try:
                    self.execute(run_id, owner)
                finally:
                    heartbeat_stop.set()
                    heartbeat.join(timeout=1)
                    self.store.release(owner)
            else:
                self.stop_event.wait(1)

    def _call(self, run_id, key, messages, model):
        # UTF-8 bytes plus output maximum and framing: conservative token reservation.
        estimate = len(json.dumps(messages, ensure_ascii=False).encode()) + MODEL_OUTPUT_TOKENS + 2048
        replay = self.store.reserve_call(run_id, key, messages, estimate)
        if replay is not None:
            return replay
        try:
            raw, usage = model.generate(messages)
        except ProviderError as error:
            self.store.fail_call(run_id, key, {**(error.usage or {}),"error_type":error.error_type,"attempts":error.attempts})
            raise
        self.store.finish_call(run_id, key, raw, usage)
        actual = (usage.get("prompt_tokens") or 0) + (usage.get("output_tokens") or 0)
        if actual > estimate:
            raise BudgetExhausted("实际用量超过保守预留；停止后续调用")
        return raw, usage

    def _oracle(self, question, loaded):
        if loaded[2]["schema_version"]==3:
            from .support_context import annotated_evidence
            return annotated_evidence(question,loaded)
        sources, texts, masks = loaded[4:]
        evidence = []
        # Merge all necessary spans per source; require the full set to fit existing limits.
        spans = {}
        for p in question.points:
            s = p.supports[0]
            if s.source_id not in spans:
                spans[s.source_id] = [s.start_char, s.end_char]
            else:
                spans[s.source_id] = [min(spans[s.source_id][0], s.start_char), max(spans[s.source_id][1], s.end_char)]
        counts = Counter(sources[sid].book for sid in spans)
        if len(spans) > 8 or any(n > 2 for n in counts.values()) or any(b-a > MAX_EVIDENCE_CHARS for a,b in spans.values()):
            raise ValueError("人工支持段落无法在现有证据窗口内完整容纳；此题不做 oracle 归因")
        for number, (sid, (a,b)) in enumerate(spans.items(),1):
            source, text = sources[sid], texts[sid]
            evidence.append({"evidence_id": f"E{number}", "source_id": sid, "book": source.book,
                "section": "人工标注支持段落", "start_char": a, "end_char": b,
                "start_line": text.count('\n',0,a)+1, "end_line": text.count('\n',0,b-1)+1,
                "text":text[a:b],"context_text": visible_prose(text[a:b], masks[sid][a:b]), "source_url": source.source_url,
                "line_url": f"{source.source_url}#L{text.count(chr(10),0,a)+1}", "score": 0.0})
        return evidence

    def execute(self, run_id, owner=None):
        try:
            run = self.store.get(run_id)
            config = ExperimentConfig.model_validate(run["config"])
            loaded = self.dataset(config.dataset)
            snapshot = run["snapshot"]
            actual_snapshot_hash = sha({k:v for k,v in snapshot.items() if k != "snapshot_sha256"})
            if (snapshot["snapshot_sha256"] != actual_snapshot_hash or loaded[1] != snapshot["dataset_sha256"]
                or loaded[2]["corpus_version"] != snapshot["corpus_version"]
                or index_contract(loaded[2]) != snapshot["index_contract"]
                or self.versions(loaded[2])[0] != snapshot["retriever"] or self.versions(loaded[2])[1] != snapshot["prompt_version"]
                or sha(build_messages("",[],schema_version=self.versions(loaded[2])[2])[0]["content"]) != snapshot["prompt_sha256"]
                or snapshot.get("code_sha256") != LOADED_CODE_CONTRACT or code_contract()!=LOADED_CODE_CONTRACT or snapshot.get("packages") != package_contract()
                or ("qa-source-span-v1" if self.versions(loaded[2])[2]==2 else EVALUATOR_VERSION) != snapshot["evaluator"] or JUDGE_VERSION != snapshot["judge_version"]):
                raise ValueError("快照或运行代码版本变化；请新建实验")
            adapter = self.adapter_factory(self.dataset_dir(config.dataset), loaded, self.store.path.parent / "vector-cache")
            model = (self.model or DeepSeekModel()) if config.live else None
            if model and model.model_name != snapshot["model"]:
                raise ValueError("模型配置已变化；请新建实验")
            done = {(r["id"],r.get("repetition",0)) for r in self.store.results(run_id)}
            for repetition in range(config.repeat):
                for q in loaded[0].questions:
                    if q.id not in snapshot["selected_question_ids"] or (q.id,repetition) in done:
                        continue
                    if code_contract()!=LOADED_CODE_CONTRACT:
                        raise ValueError("运行期间代码变化；保留检查点，请用新版本创建实验")
                    if self.stop_event.is_set() or self.store.cancelled(run_id):
                        self.store.set_state(run_id, "interrupted" if self.stop_event.is_set() else "cancelled")
                        return
                    if owner:
                        self.store.heartbeat(owner)
                    pack = adapter.retrieve(q, config)
                    result = support_links((score_qa if loaded[0].schema_version==3 else score_question)(q, pack["evidence"], loaded[5], loaded[6]),loaded[4])
                    result.update(repetition=repetition, trace=pack["trace"],
                        elapsed_seconds=pack["elapsed_seconds"], answer=None, diagnostics=[],
                        status="RETRIEVAL_ONLY", judgment=None, generation_error=None)
                    # Diagnostic labels are hypotheses unless a controlled test supplies evidence.
                    result["failure_signals"] = []
                    if q.answerability == "answerable" and not result["complete"]:
                        result["failure_signals"].append("本轮上下文未完整覆盖已标注支持要点；进一步查看候选排名和过滤过程")
                    if config.live:
                        try:
                            evidence = pack["evidence"]
                            if config.mode in {"oracle","oracle_generate"}:
                                if q.answerability != "answerable":
                                    result["status"] = "ORACLE_NOT_APPLICABLE"
                                    self.store.save_result(run_id,result)
                                    continue
                                evidence = self._oracle(q,loaded)
                                result["oracle_evidence"] = evidence
                                result["oracle_note"] = "已标注支持上下文干预；复核来源沿用题集记录，不据单次结果断言因果"
                            if not evidence:
                                result["status"] = "NO_RETRIEVAL_MATCH"
                            else:
                                modern=loaded[2]["schema_version"]==3
                                raw, usage = self._call(run_id,f"{q.id}:{repetition}:generate",build_messages(q.question,evidence,schema_version=2 if modern else 1),model)
                                result["answer"] = (validate_v2(raw,evidence) if modern else validate_draft(raw,evidence)).model_dump()
                                result["usage"] = usage
                                result["diagnostics"] = diagnose_rules(result["answer"],evidence)
                                result["status"] = "CITED_DRAFT"
                                if config.mode in {"judge","oracle"}:
                                    raw, usage = self._call(run_id,f"{q.id}:{repetition}:judge",
                                        judge_messages(q,result["answer"],evidence),model)
                                    result["judgment"] = validate_judgment(raw,result["answer"],evidence,q)
                                    result["diagnostics"] = result["judgment"]["diagnostics"]
                                    result["judge_usage"] = usage
                        except BudgetExhausted as error:
                            result["status"]="MODEL_BUDGET_STOPPED"
                            result["generation_error"]=str(error)
                            self.store.save_result(run_id,result)
                            raise
                        except (ValueError, ProviderError, TypeError) as error:
                            result["generation_error"] = str(error) if isinstance(error,ValueError) else type(error).__name__
                            result["status"] = "GENERATION_OR_JUDGE_FAILED"
                    self.store.save_result(run_id,result)
            self.store.set_state(run_id,"completed")
        except BudgetExhausted as error:
            self.store.set_state(run_id,"budget_exhausted",str(error))
        except Exception as error:
            self.store.set_state(run_id,"failed",str(error) if isinstance(error,ValueError) else type(error).__name__)

    def report(self, run_id, details=True):
        run = self.store.get(run_id)
        results, reviews = self.store.results(run_id), self.store.reviews(run_id)
        snapshot = run["snapshot"]
        # Reports expose selected split only, never hidden dataset questions by default.
        run["snapshot"] = {k:v for k,v in snapshot.items() if k not in {"dataset","dataset_reviews"}}
        run["summary"] = summarize([r for r in results if r.get("retrieval_evaluable",True)])
        run["generation"] = generation_summary(results)
        run["by_split"] = {s: summarize([r for r in results if r["split"] == s and r.get("retrieval_evaluable",True)])
                           for s in sorted({r["split"] for r in results})}
        run["calibration"] = calibration([r for r in results if r["split"] == "calibration"], reviews)
        run["by_repetition"] = [{"repetition":i,"retrieval":summarize([r for r in results if r.get("repetition",0)==i and r.get("retrieval_evaluable",True)]),
            "generation":generation_summary([r for r in results if r.get("repetition",0)==i])}
            for i in sorted({r.get("repetition",0) for r in results})]
        run["result_states"] = dict(Counter(r.get("status") for r in results))
        run["unavailable_retrieval_cases"] = sum(not r.get("retrieval_evaluable",True) for r in results)
        run["call_usage"] = self.store.call_usage(run_id)
        run["human_reviews"] = reviews
        if details:
            run["results"] = results
            run["model_records"] = self.store.call_records(run_id)
        return run

    def compare(self, left, right):
        a,b = self.report(left), self.report(right)
        for key in ("dataset_sha256","corpus_version","evaluator"):
            if a["snapshot"][key] != b["snapshot"][key]:
                raise ValueError("不同题集、语料或评分器的实验不能直接对比")
        for file in ("evaluation.py","diagnostics.py"):
            if a["snapshot"].get("code_sha256",{}).get(file) != b["snapshot"].get("code_sha256",{}).get(file):
                raise ValueError("评分实现发生变化，不能直接解释为算法改善")
        if a["config"]["split"] != b["config"]["split"] or a["config"]["repeat"] != b["config"]["repeat"]:
            raise ValueError("实验分组或重复次数不同")
        before = {(r["id"],r.get("repetition",0)):r for r in a["results"]}
        after = {(r["id"],r.get("repetition",0)):r for r in b["results"]}
        pairs=[]
        for key in sorted(before.keys() & after.keys()):
            x,y=before[key],after[key]
            if x.get("retrieval_evaluable",True) and y.get("retrieval_evaluable",True):
                delta=(y["point_coverage"]-x["point_coverage"]) if x["point_coverage"] is not None and y["point_coverage"] is not None else None
                pairs.append({"id":key[0],"repetition":key[1],"before":x["point_coverage"],"after":y["point_coverage"],
                              "delta":delta,"change":"improved" if delta and delta>0 else "regressed" if delta and delta<0 else "unchanged"})
                pairs[-1]["answer_points_before"] = x["judgment"]["covered_point_ids"] if x.get("judgment") else None
                pairs[-1]["answer_points_after"] = y["judgment"]["covered_point_ids"] if y.get("judgment") else None
                pairs[-1]["claim_labels_before"] = dict(Counter(d["judgment"] for d in x.get("diagnostics",[])))
                pairs[-1]["claim_labels_after"] = dict(Counter(d["judgment"] for d in y.get("diagnostics",[])))
        return {"left":left,"right":right,"paired_cases":len(pairs),"unpaired_cases":len(before.keys() ^ after.keys()),
                "complete_pair":a["state"]==b["state"]=="completed" and len(before)==len(after)==len(pairs),
                "changes":dict(Counter(p["change"] for p in pairs)),"questions":pairs,
                "before":a["summary"],"after":b["summary"],
                "generation_before":a["generation"],"generation_after":b["generation"],
                "controlled_model_and_prompt":a["snapshot"]["model"]==b["snapshot"]["model"] and a["snapshot"]["prompt_sha256"]==b["snapshot"]["prompt_sha256"],
                "note":"对照只解释同题集、同评分规则下的变化；样本量与未判定证据须一并报告。"}

    def import_results(self, body):
        loaded=self.dataset(body.dataset)
        dataset=loaded[0]
        selected={q.id:q for q in dataset.questions if body.split=="all" or q.split==body.split}
        records=[]
        seen=set()
        for item in body.results:
            q=selected.get(item.get("id"))
            if q is None or q.id in seen:
                raise ValueError("导入题号未知、跨分组或重复")
            seen.add(q.id)
            evidence=[]
            available=isinstance(item.get("evidence"),list)
            for index,e in enumerate(item.get("evidence") or [],1):
                sid=e.get("source_id")
                if sid not in loaded[5]:
                    raise ValueError("导入证据来源不存在")
                a,b=e.get("start_char"),e.get("end_char")
                if type(a) is not int or type(b) is not int or not 0<=a<b<=len(loaded[5][sid]) or b-a>MAX_EVIDENCE_CHARS:
                    raise ValueError("导入证据区间无效")
                text=loaded[5][sid]
                code=loaded[2]["schema_version"]==3 and e.get("content_type")=="code"
                if code:
                    ranges=sorted((max(a,c.start_char),min(b,c.end_char)) for c in loaded[3] if c.source_id==sid and
                        (loaded[4][sid].path.endswith(".py") or c.section.startswith("[code]")) and c.end_char>a and c.start_char<b)
                    cursor=a
                    for left,right in ranges:
                        if text[cursor:left].strip():raise ValueError("导入代码证据含非代码范围")
                        cursor=max(cursor,right)
                    if text[cursor:b].strip():raise ValueError("导入代码超出静态索引")
                context=text[a:b] if code else visible_prose(text[a:b],loaded[6][sid][a:b])
                if e.get("context_text") != context:
                    raise ValueError("导入上下文与原文投影不一致")
                source=loaded[4][sid]
                if q.book and source.book!=q.book:
                    raise ValueError("导入证据超出提问范围")
                evidence.append({"source_id":sid,"start_char":a,"end_char":b,"text":text[a:b],"context_text":context,
                    "content_type":"code" if code else "prose",
                    "evidence_id":f"E{index}","book":source.book,"section":e.get("section","离线导入"),
                    "start_line":text.count('\n',0,a)+1,"end_line":text.count('\n',0,b-1)+1,
                    "source_url":source.source_url,"line_url":f"{source.source_url}#L{text.count(chr(10),0,a)+1}"})
            if len(evidence)>8 or (loaded[2]["schema_version"]<3 and any(n>2 for n in Counter(e["book"] for e in evidence).values())) or sum(len(e["context_text"]) for e in evidence)>20000:
                raise ValueError("导入证据超过原有上限")
            answer=((AnswerV2 if item["answer"].get("schema_version")==2 else CitedDraft).model_validate(item["answer"]).model_dump()
                    if item.get("answer") is not None else None)
            if answer and answer.get("schema_version")==2:validate_v2(json.dumps(answer),evidence)
            r=support_links((score_qa if loaded[0].schema_version==3 else score_question)(q,evidence,loaded[5],loaded[6]),loaded[4])
            r.update(repetition=0,answer=answer,diagnostics=diagnose_rules(answer,evidence),judgment=None,
                     status="IMPORTED",retrieval_evaluable=available,trace={"strategy":"import","available":False},
                     elapsed_seconds=None,generation_error=None)
            if not available:
                r["point_coverage"]=None
                r["complete"]=None
            records.append(r)
        config=ExperimentConfig(dataset=body.dataset,split=body.split,request_key=body.request_key,name=body.name,allow_pending=True)
        created=self.create(config,importing=True)
        run_id=created["id"]
        if created["reused"]:
            if self.store.results(run_id)!=records:
                raise ValueError("导入请求编号已用于其他结果")
            return created
        for r in records:
            self.store.save_result(run_id,r)
        with self.store.db() as db:
            snapshot=json.loads(db.execute("SELECT snapshot FROM runs WHERE id=?",(run_id,)).fetchone()[0])
            snapshot["imported"]=True
            snapshot["import_sha256"]=sha(body.results)
            snapshot["snapshot_sha256"]=sha({k:v for k,v in snapshot.items() if k!="snapshot_sha256"})
            db.execute("UPDATE runs SET total=?,snapshot=?,state='completed' WHERE id=?",
                       (len(records),json.dumps(snapshot,ensure_ascii=False),run_id))
        return created
