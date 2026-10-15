"""QA gold validation / span coverage. AI-assisted labels are not human approval."""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .core import verified_corpus,validate_text,index_contract
from .rag import normalize_quote,prose_mask,visible_prose
from .mdx import mdx_mask

QA_DATASET=Path(__file__).resolve().parents[1]/"evals/agent-qa-v1.1.json"
TOPICS=("tools","memory","rag","planning","context","mcp","multi_agent","observability")

class Contract(BaseModel):model_config=ConfigDict(extra="forbid",strict=True)
class QASpan(Contract):
    source_id:str; start_char:int=Field(ge=0);end_char:int=Field(gt=0)
    start_line:int=Field(ge=1);end_line:int=Field(ge=1)
    quote:str=Field(min_length=1);kind:Literal["prose","code"];rationale:str=Field(min_length=1)
class QAPoint(Contract):
    id:str;answer:str=Field(min_length=1);supports:list[QASpan]=Field(min_length=1)
    coverage:Literal["any","all"]="any"
class QAQuestion(Contract):
    id:str;topic:Literal["tools","memory","rag","planning","context","mcp","multi_agent","observability"]
    split:Literal["dev","acceptance"];question:str=Field(min_length=1,max_length=10000)
    group:str;book:str|None;points:list[QAPoint]=Field(min_length=1);distractors:list[QASpan]
    answerability:Literal["answerable","partial","insufficient"];missing_information:str
    review_origin:str;review_scope:dict
    @property
    def review_status(self):return "pending"
    @property
    def category(self):return "gap" if self.answerability!="answerable" else "cross"
class QADataset(Contract):
    schema_version:Literal[3];dataset_version:str;annotated_on:str;annotation_method:str
    scenario_sha256:str;corpus_version:str;documents:int;baseline_chunks:int;questions:list[QAQuestion]

def load_qa_dataset(path,data_dir):
    raw=path.read_bytes();dataset=QADataset.model_validate_json(raw)
    manifest,chunks,sources,contents=verified_corpus(data_dir,data_dir/"index.sqlite3")
    texts={s.source_id:validate_text(raw) for s,raw in contents}
    masks={s.source_id:prose_mask(mdx_mask(texts[s.source_id]) if s.path.endswith(".mdx") else texts[s.source_id]) for s,_ in contents}
    # baseline_chunks documents annotation-time chunking, not a gold label.
    # Changed chunk boundaries are allowed only when raw hashes and every span
    # still verify; this is why annotations use source offsets, not chunk IDs.
    if dataset.corpus_version!=manifest["corpus_version"] or dataset.documents!=len(sources):raise ValueError("QA 题集/语料版本不匹配")
    qs=dataset.questions
    if len(qs)!=32 or Counter(q.split for q in qs)!={"dev":24,"acceptance":8}:raise ValueError("QA 题数或划分错误")
    if len({q.id for q in qs})!=32 or len({q.question for q in qs})!=32:raise ValueError("QA 题号/题面重复")
    groups={}
    for topic in TOPICS:
        if Counter(q.split for q in qs if q.topic==topic)!={"dev":3,"acceptance":1}:raise ValueError("QA 主题未完整覆盖")
    for q in qs:
        if q.group in groups and groups[q.group]!=q.split:raise ValueError("相同学习目标跨越划分")
        groups[q.group]=q.split
        if "human approval" not in q.review_origin:raise ValueError("复核来源不明确")
        if (q.answerability=="partial")!=bool(q.missing_information):raise ValueError("缺口与可回答程度不符")
        if len({p.id for p in q.points})!=len(q.points):raise ValueError("要点编号重复")
        for span in [s for p in q.points for s in p.supports]+q.distractors:
            if span.source_id not in texts:raise ValueError("标注来源不存在")
            text=texts[span.source_id]
            if text[span.start_char:span.end_char]!=span.quote or not 0<=span.start_char<span.end_char<=len(text):raise ValueError("标注非逐字位置")
            if (span.start_line!=text.count("\n",0,span.start_char)+1 or span.end_line!=text.count("\n",0,span.end_char-1)+1):raise ValueError("标注行号错误")
            if span.kind=="prose":
                projected=visible_prose(span.quote,masks[span.source_id][span.start_char:span.end_char])
                if not normalize_quote(projected) or normalize_quote(projected)!=normalize_quote(span.quote):raise ValueError(q.id+": 正文标注含遮罩内容: "+span.source_id+":"+str(span.start_line))
            else:
                ranges=sorted((max(span.start_char,c.start_char),min(span.end_char,c.end_char)) for c in chunks
                    if c.source_id==span.source_id and (sources[span.source_id].path.endswith(".py") or c.section.startswith("[code]"))
                    and c.end_char>span.start_char and c.start_char<span.end_char)
                cursor=span.start_char
                for left,right in ranges:
                    if text[cursor:left].strip():raise ValueError(q.id+": 代码标注含非代码范围")
                    cursor=max(cursor,right)
                if text[cursor:span.end_char].strip():raise ValueError(q.id+": 代码标注超出代码范围")
    scenario=Path(__file__).resolve().parents[1]/"evals/qa-scenarios-v1.json"
    if hashlib.sha256(scenario.read_bytes()).hexdigest()!=dataset.scenario_sha256:raise ValueError("冻结题面已变化")
    return dataset,hashlib.sha256(raw).hexdigest(),manifest,chunks,sources,texts,masks

def span_matches(span,item,texts,masks):
    if item["source_id"]!=span.source_id or item["start_char"]>span.start_char or item["end_char"]<span.end_char:return False
    context=item.get("context_text","")
    if span.kind=="code":return item.get("content_type")=="code" and span.quote in context
    projected=visible_prose(span.quote,masks[span.source_id][span.start_char:span.end_char])
    return item.get("content_type","prose")!="code" and normalize_quote(projected)==normalize_quote(span.quote) and normalize_quote(projected) in normalize_quote(context)

def score_qa(q,evidence,texts,masks):
    hits={p.id:[any(span_matches(s,e,texts,masks) for e in evidence) for s in p.supports] for p in q.points}
    covered=[p.id for p in q.points if (all(hits[p.id]) if p.coverage=="all" else any(hits[p.id]))]
    ranks=[];seen=set()
    for rank,e in enumerate(evidence,1):
        key=(e["source_id"],e["start_char"],e["end_char"],e.get("content_type","prose"))
        supporting=[p.id for p in q.points if any(span_matches(s,e,texts,masks) for s in p.supports)]
        negatives=[i for i,s in enumerate(q.distractors) if span_matches(s,e,texts,masks)]
        ranks.append({**e,"rank":rank,"supporting_points":supporting,"supported_points":supporting,"distractor_annotations":negatives,
            "judgment":"support_and_distractor" if supporting and negatives else "support" if supporting else "distractor" if negatives else "unjudged","duplicate":key in seen})
        seen.add(key)
    return {"id":q.id,"topic":q.topic,"split":q.split,"question":q.question,"answerability":q.answerability,
        "group":q.group,"category":q.category,"book":q.book,"required_books":sorted({e["book"] for e in evidence if e.get("book")}),
        "points":[p.model_dump() for p in q.points],"distractors":[s.model_dump() for s in q.distractors],"review_scope":q.review_scope,
        "covered_points":covered,"expected_points":len(q.points),"span_hits":hits,
        "complete_known_support":len(covered)==len(q.points),"complete":len(covered)==len(q.points) if q.answerability=="answerable" else None,
        "missing_information":q.missing_information,"review_origin":q.review_origin,"evidence":ranks}

def qa_summary(results):
    expected=sum(r["expected_points"] for r in results);covered=sum(len(r["covered_points"]) for r in results)
    topics={}
    for t in TOPICS:
        rows=[r for r in results if r["topic"]==t];total=sum(r["expected_points"] for r in rows);hits=sum(len(r["covered_points"]) for r in rows)
        topics[t]={"covered":hits,"expected":total,"coverage":hits/total if total else None,"complete":sum(r["complete"] is True for r in rows)}
    ev=[e for r in results for e in r["evidence"] if not e["duplicate"]]
    return {"questions":len(results),"covered":covered,"expected":expected,"coverage":covered/expected if expected else None,
        "complete":sum(r["complete"] is True for r in results),"answerable_questions":sum(r["answerability"]=="answerable" for r in results),
        "complete_known_support":sum(r.get("complete_known_support",r["complete"] is True) for r in results),"any_support":sum(bool(r["covered_points"]) for r in results),
        "per_topic":topics,"macro_coverage":sum(v["coverage"] for v in topics.values() if v["coverage"] is not None)/max(1,sum(v["coverage"] is not None for v in topics.values())),
        "unjudged_evidence":sum(e["judgment"]=="unjudged" for e in ev),"distractor_evidence":sum(bool(e["distractor_annotations"]) for e in ev),
        "partial_questions":sum(r["answerability"]!="answerable" for r in results),"note":"必要已知要点覆盖，不代表生成答案正确率或模型拒答能力；缺口单独复核。"}

def evaluate_qa(path,data_dir,*,split="dev",strategy="bm25",check_only=False):
    dataset,sha,manifest,chunks,sources,texts,masks=load_qa_dataset(path,data_dir)
    report={"operation":"qa-evaluate","dataset_version":dataset.dataset_version,"dataset_sha256":sha,"corpus_version":manifest["corpus_version"],"index_contract":index_contract(manifest),"strategy":strategy,"split":split,"model_calls":0,"review_origin":"AI-assisted source labels; not human approval"}
    if check_only:return {**report,"status":"QA_DATASET_VALID","questions":32}
    from .qa_retrieval import retrieve_qa,RETRIEVER_VERSION
    results=[]
    for q in dataset.questions:
        if split!="all" and q.split!=split:continue
        started=time.perf_counter();pack=retrieve_qa(data_dir,data_dir/"index.sqlite3",q.question,q.book,strategy=strategy,trace=True)
        results.append({**score_qa(q,pack["evidence"],texts,masks),"elapsed_seconds":time.perf_counter()-started,"trace":pack.get("trace")})
    return {**report,"status":"QA_EVALUATED","retriever_version":RETRIEVER_VERSION,"finished_at":datetime.now(timezone.utc).isoformat(),"summary":qa_summary(results),"results":results}
