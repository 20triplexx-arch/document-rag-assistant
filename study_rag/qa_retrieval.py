"""Global BM25F / local E5 RRF, typed evidence and task/version coverage."""
from __future__ import annotations
from collections import Counter,defaultdict
from dataclasses import asdict
from functools import lru_cache
import math,re,time
from pathlib import Path
from .core import CorpusError,verified_corpus,validate_text,corpus_catalog,tokenize
from .rag import prose_mask,visible_prose,section_role,requested_roles,expand_evidence
from .mdx import mdx_mask,blank
from .question_plan import question_plan,expand_terms,ALIASES,relevant_sections
from .limits import MAX_EVIDENCE_CHARS
from .provenance import python_bindings, evidence_provenance

RETRIEVER_VERSION="global-symbol-facet-bm25f-v3.1"
MAX_CONTEXT_CHARS=20000

def body_mask(text,mdx=False):
    structural=mdx_mask(text) if mdx else text
    lines=[];fence="";length=0
    for line in structural.splitlines(keepends=True):
        token=re.match(r"^[ \t]*(`{3,}|~{3,})(.*)$",line)
        hidden=bool(fence or token)
        if token:
            marker,suffix=token.groups()
            if not fence:fence,length=marker[0],len(marker)
            elif marker[0]==fence and len(marker)>=length and not suffix.strip():fence=""
        lines.append(blank(line) if hidden else line)
    masked=prose_mask("".join(lines))
    front=re.match(r"\A---\s*\n.*?\n---(?:\n|$)",masked,re.S)
    if front:masked=blank(masked[:front.end()])+masked[front.end():]
    masked=re.sub(r"(?m)^\s*:::[^\n]*",lambda m:blank(m[0]),masked)
    # Conventional indented Python examples; prose nested in MDX cards is preserved.
    masked=re.sub(r"(?m)^(?: {4}|\t)(?:from \w+ import|import \w+|(?:async )?def \w+\(|class \w+).*",lambda m:blank(m[0]),masked)
    return masked

@lru_cache(maxsize=2)
def materials(contents,chunks,catalog_text):
    import json
    catalog=json.loads(catalog_text)
    sources={s.source_id:s for s,_ in contents};texts={s.source_id:validate_text(raw) for s,raw in contents}
    masks={s.source_id:body_mask(texts[s.source_id],s.path.endswith(".mdx")) for s,_ in contents}
    names={b["book"]:b["display_name"] for b in catalog["books"]};neighbors=defaultdict(list);entries=[]
    for c in chunks:neighbors[(c.source_id,c.section)].append(c)
    for c in chunks:
        s=sources[c.source_id];meta=catalog["chapters"][c.source_id]
        code=s.path.endswith(".py") or c.section.startswith("[code]")
        body=c.text if code else visible_prose(c.text,masks[c.source_id][c.start_char:c.end_char])
        plain=re.sub(r"(?m)^ {0,3}#{1,6}\s+.*$|^\s*(?:[-*_]\s*){3,}$","",body)
        if not re.search(r"[A-Za-z0-9\u3400-\u9fff]",plain):continue
        title=s.chapter+"\n"+c.section+"\n"+" ".join(meta.get("topics",[]))
        index_body=body
        if code:
            index_body+="\n"+re.sub(r"[_-]+"," ",re.sub(r"([a-z])([A-Z])",r"\1 \2",body))
        body_vector, title_vector = tokenize(index_body), tokenize(title)
        entries.append({"chunk":c,"source":s,"meta":meta,"body":body,"body_vector":body_vector,"title_vector":title_vector,
            "body_length":sum(body_vector.values()),"title_length":sum(title_vector.values()),
            "content_type":"code" if code else "prose","role":section_role(c.section),"display_name":names[s.book]})
    return texts,masks,neighbors,entries

def duplicate(item,chosen):
    for prev in chosen:
        if item["source_id"]!=prev["source_id"] or item["content_type"]!=prev["content_type"]:continue
        overlap=max(0,min(item["end_char"],prev["end_char"])-max(item["start_char"],prev["start_char"]))
        if overlap/min(item["end_char"]-item["start_char"],prev["end_char"]-prev["start_char"])>.6:return True
    return False

def eligible(entry,plan,roles,book):
    c,s,m=entry["chunk"],entry["source"],entry["meta"]
    if book and s.book!=book:return False
    if entry["content_type"]=="code" and not plan["needs_code"]:return False
    if entry["role"] not in roles:return False
    if re.search(r"(?:^| / )(?:习题|练习|参考文献|额外资源|附加资源|参考资源|Additional Resources|目录)(?:\s|$)",c.section,re.I):return False
    if s.book=="mcp-specification" and "mcp" in plan["topics"]:
        if not set(m.get("applicable_versions",[])) & set(plan["applicable_versions"]):return False
    return True

def statistics(entries):
    n=len(entries);df=Counter()
    for e in entries:df.update(set(e["body_vector"])|set(e["title_vector"]))
    body_avg=sum(e["body_length"] for e in entries)/max(1,n)
    title_avg=sum(e["title_length"] for e in entries)/max(1,n)
    postings=defaultdict(list)
    for index,e in enumerate(entries):
        b,t=e["body_vector"],e["title_vector"]
        bn=.25+.75*e["body_length"]/max(1,body_avg);tn=.25+.75*e["title_length"]/max(1,title_avg)
        for term in set(b)|set(t):
            tf=b.get(term,0)/bn+2*t.get(term,0)/tn
            weight=math.log(1+(n-df[term]+.5)/(df[term]+.5))*tf*2.2/(tf+1.2)
            postings[term].append((index,weight,term in b))
    return postings


@lru_cache(maxsize=4)
def cached_statistics(contents,chunks,catalog_text,ids):
    allowed = set(ids)
    entries = materials(contents,chunks,catalog_text)[3]
    return statistics([e for e in entries if e["chunk"].chunk_id in allowed])


def bm25_scores(entries,queries,stats=None):
    postings = stats if stats is not None else statistics(entries)
    scores=[defaultdict(float) for _ in queries];body_hits=set()
    for qi,query in enumerate(queries):
        for term in sorted(query):
            for index,weight,in_body in postings.get(term,()):
                scores[qi][index]+=weight
                if qi==0 and in_body:body_hits.add(index)
    results=[]
    for index in sorted(body_hits):
        values=[query_scores.get(index,0.0) for query_scores in scores]
        results.append({**entries[index],"lexical_score":values[0],"facet_scores":values[1:]})
    return results

def evidence_item(e,texts,masks,neighbors,*,expand=True):
    c,s,m=e["chunk"],e["source"],e["meta"]
    if e["content_type"]=="code":
        mask=texts[s.source_id]
        item=expand_evidence(c,neighbors[(c.source_id,c.section)],mask,mask) if expand else {**asdict(c),"anchor_chunk_id":c.chunk_id,"context_text":c.text}
        # Code remains byte-for-character, including indentation; never prose-normalize.
        item["context_text"]=texts[s.source_id][item["start_char"]:item["end_char"]]
    else:item=expand_evidence(c,neighbors[(c.source_id,c.section)],texts[s.source_id],masks[s.source_id]) if expand else {**asdict(c),"anchor_chunk_id":c.chunk_id,"context_text":e["body"]}
    return {**item,"book":s.book,"display_name":e["display_name"],"chapter":s.chapter,"path":s.path,
        "provenance":evidence_provenance(s,texts[s.source_id],item),
        "language":m["language"],"content_type":e["content_type"],"applicable_versions":m.get("applicable_versions",["unknown"]),
        "code_role":"implementation" if s.path.endswith(".py") else "example" if e["content_type"]=="code" else None,
        "parent_source_ids":m.get("parent_source_ids",[]),"source_url":s.source_url,
        "line_url":f"{s.source_url}#L{item['start_line']}-L{item['end_line']}"}

def retrieve_qa(data_dir,index_path,question,book=None,*,strategy="bm25",trace=False,expand=True,_verified=None):
    started=time.perf_counter();plan=question_plan(question)
    if strategy not in {"bm25","hybrid"}:raise CorpusError("未知 QA 检索策略。")
    manifest,chunks,sources,contents=_verified if _verified is not None else verified_corpus(data_dir,index_path);catalog=corpus_catalog(manifest)
    books=[b["book"] for b in catalog["books"]]
    if book and book not in books:raise CorpusError("教材筛选值不存在。")
    from .core import json_text
    contents_key,chunks_key,catalog_key=tuple(contents),tuple(chunks),json_text(catalog)
    texts,masks,neighbors,all_entries=materials(contents_key,chunks_key,catalog_key)
    symbols=set(plan['named_symbols']);bindings={}
    owners=set()
    if symbols:
        for source in sources.values():
            if source.path.endswith('.py'):
                binding=python_bindings(texts[source.source_id]);bindings[source.source_id]=binding
                if any(d['name'] in symbols for d in binding[0]):owners.add(source.source_id)
        if owners:plan['needs_code']=True
    roles=requested_roles(question)
    entries=[e for e in all_entries if eligible(e,plan,roles,book)]
    full_query=expand_terms(question)
    queries=[full_query]
    for query in [expand_terms(f,topics=False) for f in plan["subquestions"]+plan["query_windows"]]:
        if query and query not in queries:queries.append(query)
    ranked=bm25_scores(entries,queries,cached_statistics(contents_key,chunks_key,catalog_key,tuple(e["chunk"].chunk_id for e in entries)))
    dense_meta=None
    if strategy=="hybrid":
        from .qa_vectors import dense_ranks
        dense,dense_meta=dense_ranks(data_dir,manifest,all_entries,question)
        allowed={e["chunk"].chunk_id:e for e in entries}
        lexical=sorted(ranked,key=lambda e:(-e["lexical_score"],e["chunk"].chunk_id))[:100]
        dense=[cid for cid in dense if cid in allowed][:100]
        sparse_ranks={e["chunk"].chunk_id:i+1 for i,e in enumerate(lexical)}
        vector_ranks={cid:i+1 for i,cid in enumerate(dense)}
        pool=set(sparse_ranks)|set(vector_ranks);by_scored={e["chunk"].chunk_id:e for e in ranked}
        ranked=[{**by_scored.get(cid,{**allowed[cid],"lexical_score":0,"facet_scores":[0]*(len(queries)-1)}),
            "rrf_score":(1/(60+sparse_ranks[cid]) if cid in sparse_ranks else 0)+(1/(60+vector_ranks[cid]) if cid in vector_ranks else 0)} for cid in pool]
    maximum=max([e.get("rrf_score",e["lexical_score"]) for e in ranked] or [1])
    section_patterns=relevant_sections(question)
    protocol_focused="mcp" in plan["topics"] and not set(plan["topics"])-{"tools","mcp"}
    for e in ranked:
        e["rank_score"]=e.get("rrf_score",e["lexical_score"])/maximum
        if plan["needs_code"]:
            if e["content_type"]=="code":e["rank_score"]*=2.0
            elif e["meta"].get("kind")=="case":e["rank_score"]*=.35
            if e["source"].path.endswith(".py"):e["rank_score"]*=1.6
            elif e["content_type"]=="code" and e["meta"].get("kind")=="case":e["rank_score"]*=.5
        if section_patterns:
            e["rank_score"]*=1+.6*sum(bool(re.search(pattern,e["chunk"].section,re.I)) for pattern in section_patterns)/len(section_patterns)
        if re.search(r"LangChain|LangSmith|Deep Agents",question,re.I) and e["source"].book=="langchain-official":
            e["rank_score"]*=1.4
            if re.search(r"LangSmith",question,re.I) and e["source"].path.startswith("src/langsmith/"):e["rank_score"]*=1.5
        if not re.search(r"错误|异常|排错|error|exception",question,re.I) and re.search(r"error handling|错误处理",e["chunk"].section,re.I):e["rank_score"]*=.45
        if re.search(r"延伸阅读|必读材料|推荐资源|tutorial examples|goals?$",e["chunk"].section,re.I):e["rank_score"]*=.35
        if re.search(r"<strong>.*[？?]",e["chunk"].section,re.I):e["rank_score"]*=.3
        if protocol_focused:
            if e["source"].book=="mcp-specification":e["rank_score"]*=1.4
            elif not plan["needs_code"]:e["rank_score"]*=.5
        if owners:
            if e['source'].source_id in owners:e['rank_score']*=4
            elif e['source'].path.endswith('.py') and not any(e['source'].path.rsplit('/',1)[0]==sources[sid].path.rsplit('/',1)[0] for sid in owners):
                e['rank_score']*=.15
        e["topic_coverage"]={t for t in plan["topics"] if t in e["meta"].get("topics",[]) or any(e["body_vector"][w] for w in ALIASES[t].split())}
    ranked.sort(key=lambda e:(-e["rank_score"],e["chunk"].chunk_id))
    for e in ranked:
        e["facets"]={f["id"] for f in plan["necessary_facets"] if re.search(f["section_pattern"],e["chunk"].section if "/" in f["section_pattern"] else e["chunk"].section.split(" / ")[-1],re.I)
            and (not f["body_pattern"] or re.search(f["body_pattern"],e["body"],re.I))}
        if e['source'].source_id in owners:
            definitions,imports,calls=bindings[e['source'].source_id]
            a,b=e['chunk'].start_char,e['chunk'].end_char
            def inside(row):return a<=row['start_char']<b
            e['facets'].update('definition:'+d['name'] for d in definitions if d['name'] in symbols and inside(d))
            e['facets'].update('import:'+d['name'] for d in imports if d['name'] in symbols and inside(d))
            e['facets'].update('caller:'+c['name'] for c in calls if c['name'] in symbols and inside(c))
        if e["source"].book=="mcp-specification" and plan["version_comparison"]:
            e["facets"].update("version-"+v for v in e["meta"].get("applicable_versions",[]) if v in plan["applicable_versions"])
            if "capabilities" in e["facets"]:e["facets"].update("capabilities-"+v for v in e["meta"].get("applicable_versions",[]))
    # Independent subquestion ranks remain eligible even when the full query is
    # dominated by one named framework. Selection round-robins these lanes before
    # filling remaining slots from the global ranking.
    lanes=[]
    if len(plan["subquestions"]) > 1:
        for query in queries[1:]:
            lane=[e for e in ranked if query.intersection(e["body_vector"])]
            lane.sort(key=lambda e:(-len(query.intersection(e["body_vector"])), -e["rank_score"],e["chunk"].chunk_id))
            if lane:lanes.append(lane[:12])
    if len(plan["topics"]) > 1:
        for topic in plan["topics"]:
            lane=[e for e in ranked if topic in e["topic_coverage"]]
            lane.sort(key=lambda e:(-e["rank_score"],e["chunk"].chunk_id))
            if lane:lanes.append(lane[:12])
    chosen=[];covered=set();selected_ids=set();context_total=0
    pool=ranked[:120]
    for facet in {f for e in ranked for f in e["facets"]}:
        pool.extend(e for e in [e for e in ranked if facet in e["facets"]][:3] if e not in pool)
    covered_facets=set()
    required_symbols={f for e in ranked for f in e['facets'] if f.startswith(('definition:','import:','caller:'))}
    required_concepts={f for e in ranked for f in e['facets'] if not f.startswith(('definition:','import:','caller:'))}
    from .response_policy import response_plan
    simple = response_plan(question)["kind"] in {"brief","definition"} and len(plan["topics"]) <= 1 and len(plan["subquestions"]) <= 1 and not plan["needs_code"] and not plan["version_comparison"] and not plan["necessary_facets"]
    limit=3 if simple else 8
    # Reserve a best candidate per independently queried subject, while keeping
    # explicit required facets ahead of optional breadth within each subject.
    priority=[]
    for lane in lanes:
        best=max(lane,key=lambda e:(len(e["facets"]),e["rank_score"],e["chunk"].chunk_id))
        if best not in priority:priority.append(best)
    for e in reversed(priority):
        if e not in pool:pool.append(e)
    while pool and len(chosen)<limit:
        if owners and required_symbols and required_symbols<=covered_facets and required_concepts<=covered_facets:
            break
        def gain(e):
            novelty=len(e["topic_coverage"]-covered)/max(1,len(plan["topics"]))
            # Required subquestions get a slot before spending remaining slots on
            # another high-scoring passage about an already covered subquestion.
            return (len(e["facets"]-covered_facets),e["rank_score"]*(1+.35*novelty))
        e=max(pool,key=lambda e:(gain(e),e["chunk"].chunk_id))
        if not gain(e)[0]:
            missing_topic=next((candidate for candidate in priority if candidate in pool and candidate["topic_coverage"]-covered),None)
            if missing_topic is not None:e=missing_topic
        pool.remove(e)
        item=evidence_item(e,texts,masks,neighbors,expand=expand)
        if duplicate(item,chosen) or not item["context_text"].strip():continue
        if len(item["context_text"])>MAX_EVIDENCE_CHARS:raise CorpusError("单条证据超过上限。")
        if context_total+len(item["context_text"])>MAX_CONTEXT_CHARS:continue
        item["score"]=round(e["rank_score"],6);item["evidence_id"]=f"E{len(chosen)+1}"
        context_total+=len(item["context_text"]);chosen.append(item);covered.update(e["topic_coverage"]);covered_facets.update(e["facets"]);selected_ids.add(e["chunk"].chunk_id)
    result={"question":question,"question_plan":plan,"qa_version":3,"book_filter":book,"corpus_version":manifest["corpus_version"],
        "retriever":RETRIEVER_VERSION+":"+strategy,"evidence":chosen,"books_without_match":[],"source_verified":True,"support_verified":False,
        "elapsed_seconds":time.perf_counter()-started}
    if trace:result["trace"]={"strategy":strategy,"eligible":len(entries),"scored":len(ranked),"context_characters":context_total,
        "query_windows":len(plan["query_windows"]),"vector":dense_meta,"selected_chunk_ids":list(selected_ids),
        "candidates":[{"chunk_id":e["chunk"].chunk_id,"source_id":e["source"].source_id,"section":e["chunk"].section,
            "start_char":e["chunk"].start_char,"end_char":e["chunk"].end_char,
            "line_url":f"{e['source'].source_url}#L{e['chunk'].start_line}-L{e['chunk'].end_line}",
            "score":e["rank_score"],"content_type":e["content_type"],"facets":sorted(e["facets"])} for e in ranked[:40]]}
    return result
