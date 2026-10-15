"""Indexed object/facet retrieval over verified bytes. No generated facts or code execution."""
from collections import defaultdict
from functools import lru_cache
from threading import RLock
import re
import time
import json
import hashlib
from pathlib import Path

from .core import CorpusError, verified_corpus, corpus_catalog, tokenize
from .qa_retrieval_v4 import verified_materials, intent as base_intent, _expand
from .question_plan import expand_terms
from .rag import requested_roles
from .qa_retrieval import duplicate, statistics
from .static_facts import bindings
from .parent_vectors import semantic_parent_ranks

VERSION = 'indexed-objects-facets-v5.0'
_CACHE = {}; _LOCK = RLock()
DOMAIN_TERMS={'reflection','retrieval','observation','subagents','subagent','handoffs','react','runtime','config','cursor','notification','tracing','evaluation','skills','summarize','trim','delete'}
COURSE_NAMES={'helloagents','hello','microsoft','hugging','face','awesome','langchain','langgraph','langsmith','deep','agents','agent','notebook','python','memory','schema','tools'}


def explicit_terms(tokens):
    return {n.lower() for n in tokens if len(n)>=4 and n.lower() not in COURSE_NAMES and
            ('_' in n or '.' in n or re.search(r'[a-z][A-Z]',n) or n.lower() in DOMAIN_TERMS)}


def indexed_materials(manifest, contents, chunks, catalog):
    cohort_raw=Path(__file__).with_name('curriculum_sources.json').read_bytes()
    clause_raw=Path(__file__).with_name('clause_specs.json').read_bytes()
    key = (manifest['corpus_version'],hashlib.sha256(cohort_raw).hexdigest(),hashlib.sha256(clause_raw).hexdigest())
    with _LOCK:
        if key in _CACHE: return _CACHE[key]
        mat = dict(verified_materials(manifest, contents, chunks, catalog))
        entries = mat['entries']; sets = defaultdict(set); sections = defaultdict(set)
        objects = defaultdict(list); relations = defaultdict(set); paths = defaultdict(set)
        for i, e in enumerate(entries):
            source = e['source']; meta = e['meta']
            for field, value in [('book',source.book), ('type',e['content_type']), ('role',e['role']),
                                  ('configuration',e['configuration']), ('source',source.source_id)]:
                sets[field,value].add(i)
            for version in meta.get('applicable_versions', ['unknown']): sets['version',version].add(i)
            product = re.match(r'src/oss/(langchain|langgraph|deepagents)/',source.path)
            if product: sets['product',product[1]].add(i)
            if '/javascript/' in source.path or source.path.endswith(('.ts','.js','.mjs')): sets['language','javascript'].add(i)
            if re.search(r'参考文献|额外资源|Additional Resources|Contribut|^Quiz',e['chunk'].section,re.I): sets['excluded',True].add(i)
            sections[e['chunk'].section].add(i)
            for topic in e['topic_flags']: sets['topic',topic].add(i)
        cases = set()
        for source, raw in contents:
            paths[source.path.rsplit('/',1)[-1]].add(source.source_id)
            meta = catalog['chapters'][source.source_id]
            if source.book=='awesome-llm-apps-cases' and source.path.rsplit('/',1)[-1].lower()=='readme.md':cases.add(source.path.rsplit('/',1)[0])
            graph = bindings(source.path,raw)
            for row in graph['definitions']+graph['assignments']:
                record = {'source_id':source.source_id,'path':source.path,'book':source.book,
                    'symbol':row['qualified_name'],'cell_index':row['cell_index'],'scope_id':row['scope_id'],
                    'kind':row.get('kind','assignment'),'start_char':row['start_char'],'end_char':row['end_char']}
                for name in {row['name'],row['qualified_name']}: objects[name].append(record)
            for kind in ['definitions','imports','calls','branches','assignments','returns']:
                for row in graph[kind]:
                    names = {row.get('name',''), row.get('qualified_name',''), row.get('owner','')}
                    for i in mat['source_entries'][source.source_id]:
                        c = entries[i]['chunk']
                        if e_is_code(entries[i]) and c.start_char < row['end_char'] and c.end_char > row['start_char']:
                            for name in names-{'','module'}: relations[name].add(i)
        cohort=json.loads(cohort_raw)['sources']
        core_sources={source.source_id for source,raw in contents if cohort.get(source.source_id)==hashlib.sha256(raw).hexdigest()}
        core_ids=sorted(set().union(*(sets['source',sid] for sid in core_sources)))
        core_postings={term:[(core_ids[i],weight,body) for i,weight,body in values]
                       for term,values in statistics([entries[i] for i in core_ids]).items()}
        mat.update(filters=sets, sections=sections, objects=objects, relations=relations, paths=paths,
                   curriculum_ids=set(core_ids),curriculum_postings=core_postings,
                   all_ids=set(range(len(entries))), case_roots=tuple(sorted(cases)), clause_cache={})
        if len(_CACHE)>=2: _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key]=mat
        for spec in json.loads(clause_raw)['clauses']:clause_lane(mat,spec['section'],spec['body'])
        return mat


def e_is_code(entry): return entry['content_type']=='code'


def clause_lane(mat, section, body):
    key = (section,body)
    with _LOCK:
        if key not in mat['clause_cache']:
            section_re = re.compile(section,re.I); body_re = re.compile(body,re.I) if body else None
            routed=set()
            for title,ids in mat['sections'].items():
                target=title if body or ' / ' in section else title.split(' / ')[-1]
                if section_re.search(target):routed.update(ids)
                elif body:routed.update(i for i in ids if section_re.search(mat['entries'][i]['source'].path))
            # Headings route only; at least a non-heading body must support a facet.
            hits = {i for i in routed if re.search(r'[\w\u3400-\u9fff]',re.sub(r'(?m)^\s*#{1,6}.*$','',mat['entries'][i]['body']))
                    and (body_re is None or body_re.search(mat['entries'][i]['body']))}
            mat['clause_cache'][key] = hits
        return mat['clause_cache'][key]


def intent(question):
    plan=base_intent(question); plan['pipeline_version']=5
    if re.search(r'awesome|Memory\s*指南|Reflection/Self.Refine',question,re.I):plan['object_books'].append('awesome-agentic-ai-zh')
    if re.search(r'案例|Function Tools',question,re.I):
        if re.search(r'SQLite|持久会话|计算器|带推理\s*RAG|RAG\s*案例|Function Tools',question,re.I):plan['object_books'].append('awesome-llm-apps-cases')
    plan['needs_configuration'] |= bool(re.search(r'依赖|requirements|\.env|环境变量|版本约束|安装版本',question,re.I))
    plan['needs_configuration'] |= bool(re.search(r'变量名|tracing_sampling_rate|采样率.*(?:0|1)',question,re.I))
    replacements=[]
    if re.search(r'progress|进度',question,re.I):
        if re.search(r'token|类型|关联|规则|约束',question,re.I): replacements.append(('progress_type',r'progress',r'Progress tokens.*MUST|(?:string|integer).*progress|progressToken'))
        if re.search(r'递增|增长|单调|倒退|规则|progress.*值|进度.*(?:值|数值)',question,re.I): replacements.append(('progress_increase',r'progress',r'MUST.*increase'))
        if re.search(r'结束|停止|完成|规则',question,re.I): replacements.append(('progress_completion',r'progress',r'MUST.*stop after completion'))
    if re.search(r'分页|cursor|页大小|pagination',question,re.I):
        replacements.extend([('pagination_cursor',r'pagination',r'opaque'),('pagination_size',r'pagination',r'Page size|MUST NOT.*assume')])
        if re.search(r'返回|字段|结束|下一|next',question,re.I): replacements.append(('pagination_next',r'pagination',r'nextCursor'))
    if re.search(r'取消|cancell',question,re.I):
        if re.search(r'HTTP|stdio|通知|requestId',question,re.I): replacements.append(('cancel_transport',r'cancell',r'Streamable HTTP|stdio|requestId'))
        if re.search(r'服务端|server|通知',question,re.I): replacements.append(('cancel_server',r'cancell',r'(?:server|servers).*MUST|MUST.*(?:cancel|stop|cease)'))
        if re.search(r'timeout|超时',question,re.I): replacements.append(('cancel_timeout',r'cancell',r'timeout|SHOULD.*maximum'))
    removed = {'progress_rules','pagination_rules','cancellation_rules'} if replacements else set()
    plan['requirements']=[r for r in plan['requirements'] if r['id'] not in removed]
    plan['requirements'].extend({'id':name,'section':section,'body':body} for name,section,body in replacements)
    if re.search(r'Schema|工具定义',question,re.I) and not plan['needs_code']:
        plan['requirements'].append({'id':'schema_description','section':r'tool|工具','body':r'函数/工具 Schema|function.?tool schema|工具功能|tool.s name|tool schema'})
    if re.search(r'2.step|两步',question,re.I) and re.search(r'Agentic',question,re.I):
        plan['requirements'].extend([
            {'id':'two_step_order','section':r'retrieval|rag architectures|2.step rag','body':r'retrieval.*(?:before|always)|retrieval step is always'},
            {'id':'agentic_decision','section':r'retrieval|agentic rag','body':r'decides.*when.*how'},
            {'id':'rag_latency','section':r'retrieval|rag architectures','body':r'predictab.*(?:LLM|calls)|maximum number of LLM calls'}])
    if re.search(r'MCP',question,re.I) and re.search(r'超时|timeout',question,re.I):
        plan['requirements'].append({'id':'request_timeout','section':r'cancellation','body':r'timeout.*clock|maximum timeout'})
    direct={
        'subagent_inputs':r'Passing only|task description|conversation history|input context',
        'memory_limit':r'context window|long context|distract|上下文窗口|无关.*内容',
        'react_mechanism':r'ReAct|Thought.*Action|思考.*行动',
        'plan_mechanism':r'Plan.and.Solve',
        'paradigm_boundary':r'Plan.and.Solve',
        'multi_cost':r'More calls|token consumption|token usage|higher.*cost|成本|消耗',
    }
    for f in plan['requirements']:
        if f['id'] in direct:f['body']=direct[f['id']]
    rules=[
        (r'(?s)(?=.*(?:RAG|retrieval))(?=.*(?:记忆|Memory))','memory_role',r'memory|记忆',r'跨步骤|会话|session|specific facts|user.*facts'),
        (r'(?s)(?=.*(?:RAG|retrieval))(?=.*(?:记忆|Memory))','retrieval_role',r'rag|retriev|记忆',r'外部知识|外部知识来源|external knowledge|retriev.*documents|知识库.*检索'),
        (r'工作记忆','working_memory',r'工作记忆|Working Memory',r'工作记忆|working|临时|当前|short'),
        (r'情景记忆','episodic_memory',r'情景记忆|Episodic Memory',r'情景|episodic|经历|experience'),
        (r'Observation|观察阶段','observation_feedback',r'观察|observe|observation',r'收集反馈|附加结果|feedback|tool.*result'),
        (r'Observation.*(?:回答|下一步)','observation_next',r'观察|observe|observation',r'足够|回答|final answer|enough|决定'),
        (r'SQLite|持久会话','session_persistence',r'session|会话|storage',r'DatabaseSessionService.*stores|Persistent storage|survives program restarts|SQLite.*持久'),
        (r'(?s)(?=.*(?:thread|长期记忆))(?=.*namespace)','memory_address',r'memory|storage|store',r'namespace.*key|key.*namespace|organization ID'),
        (r'(?s)(?=.*(?:Reflection))(?=.*(?:指令|权重|改进))','instruction_reflection',r'procedural memory',r'current instructions|model weights|modify their own prompts'),
        (r'(?s)(?=.*retriev)(?=.*(?:限制|哪两))','retrieval_limits',r'正文',r'Finite context|Static knowledge'),
        (r'(?s)(?=.*retriev)(?=.*(?:时间|何时|引入))','retrieval_time',r'正文',r'external knowledge at query time'),
        (r'(?s)(?=.*(?:内置|built.in))(?=.*(?:调用次数|执行次数|limit))','call_limits',r'正文|built.in middleware',r'Model call limit|Tool call limit'),
    ]
    for trigger,name,section,body in rules:
        if re.search(trigger,question,re.I):plan['requirements'].append({'id':name,'section':section,'body':body})
    return plan


def retrieve_v5(data_dir,index_path,question,book=None,*,trace=False,expand=True,_verified=None,anchors=None):
    started=time.perf_counter(); plan=intent(question)
    snapshot=_verified if _verified is not None else verified_corpus(data_dir,index_path)
    verified_at=time.perf_counter()
    manifest,chunks,sources,contents=snapshot; catalog=corpus_catalog(manifest)
    mat=indexed_materials(manifest,contents,chunks,catalog); entries=mat['entries']; filters=mat['filters']
    indexed_at=time.perf_counter()
    if book and book not in {s.book for s in sources.values()}: raise CorpusError('未知资料范围。')
    requested=set(plan['object_books']); cross=len(requested)>1
    allowed=mat['all_ids']-filters['excluded',True]
    if book: allowed &= filters['book',book]
    if requested and not book: allowed &= set().union(*(filters['book',b] for b in requested))
    products=[p for p,pattern in [('langchain',r'LangChain'),('langgraph',r'LangGraph'),('deepagents',r'Deep\s*Agents|DeepAgents')] if re.search(pattern,question,re.I)]
    if products:
        disallowed=set().union(*(filters['product',p] for p in {'langchain','langgraph','deepagents'}-set(products)))
        shared={i for i in disallowed if entries[i]['source'].path.rsplit('/',1)[-1] in {'retrieval.mdx','memory.mdx','context-engineering.mdx'}}
        allowed-=disallowed-shared
    if plan['applicable_versions']:
        allowed-=filters['book','mcp-specification']-set().union(*(filters['version',v] for v in plan['applicable_versions']))
    if plan['implementation_language']=='python': allowed-=filters['language','javascript']
    allowed &= set().union(*(filters['role',role] for role in requested_roles(question)))
    tokens=re.findall(r'\b[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*\b',question)
    names=[]
    function_question=bool(re.search(r'函数|方法|返回|实参|参数|分支|定义|函数体',question))
    for n in tokens:
        records=[r for r in mat['objects'].get(n,[]) if filters['source',r['source_id']] & allowed]
        functions=[r for r in records if r['kind'] in {'FunctionDef','AsyncFunctionDef'}]
        explicit=bool('_' in n or '.' in n or re.search(r'[a-z][A-Z]',n) or '`'+n+'`' in question)
        if records and (explicit or functions and len(n)>=3 and n not in {'name','agent','Agent','Memory','Client'} and
                        (function_question or len(functions)==1 and n.lower() not in DOMAIN_TERMS)):
            names.append(n)
    object_records=[r for name in names for r in mat['objects'][name] if filters['source',r['source_id']] & allowed]
    path_owners=set().union(*(mat['paths'].get(n,set()) for n in re.findall(r'[A-Za-z0-9_.-]+\.(?:ipynb|py|txt|ts|js|toml|json|yaml|yml)\b',question)))
    if re.search(r'Notebook|笔记本',question,re.I):
        chapters=re.findall(r'\b\d{2}-[a-z][a-z-]+\b',question,re.I)
        chapter_owners={sid for sid,s in sources.items() if s.path.endswith('.ipynb') and any(s.path.startswith(c+'/') for c in chapters)}
        if chapter_owners:path_owners=(path_owners&chapter_owners) or chapter_owners
    if path_owners: object_records=[r for r in object_records if r['source_id'] in path_owners]
    compact=re.sub(r'[^a-z0-9]','',question.lower()); words=set(re.findall(r'[a-z][a-z0-9]+',' '.join(expand_terms(question)).lower()))
    if re.search(r'SQLite|持久会话',question,re.I):words.update({'persistent','conversation'})
    if re.search(r'带推理|推理.*RAG',question,re.I):words.add('reasoning')
    case_roots=[]
    case_requested='awesome-llm-apps-cases' in requested or bool(re.search(r'案例|Function Tools',question,re.I))
    for root in mat['case_roots']:
        name=root.rsplit('/',1)[-1]; meaningful=set(re.findall(r'[a-z]+',name))-{'ai','agent','agents','app','team','with','the','and'}
        aliases={re.sub(r'[^a-z0-9]','',name),re.sub(r'[^a-z0-9]','',re.sub(r'_agent$','',name))}
        if any(len(alias)>=8 and alias in compact for alias in aliases) or case_requested and (len(meaningful&words)>=2 or len(meaningful)==1 and any(len(w)>=6 for w in meaningful&words)) and len(meaningful&words)/max(1,len(meaningful))>=.5: case_roots.append(root)
    if case_roots:
        scoped=[r for r in object_records if any(r['path'].startswith(root+'/') for root in case_roots)]
        object_records=scoped
        names=[n for n in names if any(r['symbol']==n or r['symbol'].split('.')[-1]==n for r in scoped)]
    if anchors:
        anchored=[r for r in object_records if any(r['source_id']==a.get('source_id') and r['scope_id']==a.get('scope_id') and r['symbol']==a.get('symbol') for a in anchors)]
        if anchored: object_records=anchored
    owners={r['source_id'] for r in object_records}|path_owners
    if object_records: plan['needs_code']=True
    if not plan['needs_configuration']: allowed-=filters['configuration',True]
    if not plan['needs_code'] and not plan['needs_configuration']: allowed-=filters['type','code']
    plan['object_status']='ambiguous' if len({(r['source_id'],r['scope_id'],r['symbol']) for r in object_records})>1 and len(names)==1 else 'indexed' if object_records or path_owners else 'not_identified'
    # Object names are identities, not an invitation to search every same-name example.
    relation_ids=set().union(*(mat['relations'].get(n,set()) for n in names)) & allowed
    if object_records:
        selected_scopes={(r['source_id'],r['scope_id']) for r in object_records}
        relation_ids={i for i in relation_ids if any(entries[i]['source'].source_id==sid and any(
            node['scope_id']==scope and node['start_char']<entries[i]['chunk'].end_char and node['end_char']>entries[i]['chunk'].start_char
            for kind in ['definitions','imports','calls','branches','assignments','returns'] for node in bindings(sources[sid].path,mat['raws'][sid])[kind]) for sid,scope in selected_scopes)}
    queries=[expand_terms(question)]
    queries.extend(expand_terms(part,topics=False) for part in plan['subquestions'] if part!=question)
    scores=[]; original_terms=set(tokenize(question))
    for query in queries:
        score=defaultdict(float)
        for term in query:
            for i,weight,body in mat['postings'].get(term,()):
                if i in allowed:score[i]+=weight*(1 if body else .65)*(2 if term in original_terms else 1)
        scores.append(score)
    lexical=sorted(scores[0],key=lambda i:(-scores[0][i],entries[i]['chunk'].chunk_id))
    curriculum_score=defaultdict(float)
    for term in queries[0]:
        for i,weight,body in mat['curriculum_postings'].get(term,()):
            if i in allowed:curriculum_score[i]+=weight*(1 if body else .65)*(2 if term in original_terms else 1)
    curriculum=sorted(curriculum_score,key=lambda i:(-curriculum_score[i],entries[i]['chunk'].chunk_id))
    lanes=[lexical,curriculum]; tags=defaultdict(set); facets=[]
    # Rare explicit terms get their own candidate lane. Chinese question length
    # and broad translated aliases must not drown out the named concept.
    terms=explicit_terms(tokens)
    concept_exists=any(i in allowed for term in terms for i,_,body in mat['postings'].get(term,()) if body)
    if concept_exists and plan['object_status']=='not_identified':plan['object_status']='indexed'
    explicit_files=re.findall(r'[A-Za-z0-9_.-]+\.(?:ipynb|py|txt|ts|js|toml|json|yaml|yml)\b',question)
    plan['source_availability']={'kind':'ambiguous' if plan['object_status']=='ambiguous' else 'indexed' if plan['object_status']=='indexed'
        else 'not_collected' if explicit_files and not path_owners else 'unresolved',
        'reason':'Verified object/file registry; missing lexical hits alone never prove corpus absence.'}
    for term in terms:
        ids={i for i,_,body in mat['postings'].get(term,()) if body and i in allowed}
        if ids:lanes.append(sorted(ids,key=lambda i:-scores[0].get(i,0)))
    def lane(identifier, ids, definition=None, *, required=True):
        ids=set(ids)&allowed
        ordered=sorted(ids,key=lambda i:(i not in mat['curriculum_ids'],-scores[0].get(i,0),entries[i]['chunk'].chunk_id))
        lanes.append(ordered)
        if required:facets.append({'id':identifier,**(definition or {}),'available':bool(ids)})
        for i in ids:tags[i].add(identifier)
    for requirement in plan['requirements']:
        hits=clause_lane(mat,requirement['section'],requirement['body']) & allowed
        versions=plan['applicable_versions'] if plan['version_comparison'] else [None]
        for version in versions:
            for scope in sorted(requested) if cross else [None]:
                scoped=hits & filters['version',version] if version else hits
                if scope:scoped &= filters['book',scope]
                lane(requirement['id']+(':'+version if version else '')+(':'+scope if scope else ''),scoped,{'dimension':requirement['id'],'version':version,'book':scope})
    for name in names:
        ids=relation_ids & mat['relations'][name]
        lane('symbol:'+name,ids,{'dimension':'source_relations','object':name})
    if plan['needs_configuration'] and (case_roots or path_owners):
        ids={i for i in filters['configuration',True]&allowed if entries[i]['source'].source_id in path_owners or any(entries[i]['source'].path.startswith(root+'/') for root in case_roots)}
        lane('configuration',ids,{'dimension':'dependency_or_environment_declaration'})
    for b in requested if cross else []:
        lane('book:'+b,filters['book',b],{'object':b},required=not any(f.get('book')==b for f in facets))
    for n,score in enumerate(scores[1:]):
        ordered=sorted(score,key=lambda i:-score[i]);lanes.append(ordered)
    lexical_at=time.perf_counter()
    try:
        dense=semantic_parent_ranks(manifest['corpus_version'],mat['descriptors'],{entries[i]['parent'] for i in allowed},question, max_queries=2)
    except Exception as error:raise CorpusError('固定本地E5索引不可用：'+type(error).__name__) from None
    semantic_at=time.perf_counter()
    dense_ids=[]
    for parent,_ in dense:
        ids=mat['parent_entries'][parent]
        dense_ids.extend(sorted((i for i in ids if i in allowed),key=lambda i:-scores[0].get(i,0))[:3])
    lanes.append(dense_ids)
    candidate=set(lexical[:120])|set(curriculum[:60])|set(dense_ids)|relation_ids
    for ordered in lanes[1:]:candidate.update(ordered[:12])
    rrf=defaultdict(float)
    for ordered in lanes:
        for rank,i in enumerate(ordered[:300],1):rrf[i]+=1/(60+rank)
    def rank(i):
        e=entries[i]; value=rrf[i]
        if e['source'].source_id in owners:value*=3
        if i in mat['curriculum_ids']:value*=2
        if relation_ids and i in relation_ids:value*=2
        if case_roots and any(e['source'].path.startswith(root+'/') for root in case_roots):value*=2
        if plan['needs_configuration'] and e['configuration']:value*=3
        if plan['needs_code'] and e_is_code(e):value*=1.5
        if e['source'].book=='mcp-specification' and e['source'].path.endswith('schema.mdx'):value*=.35
        if e['source'].book=='mcp-specification' and not e['source'].path.endswith(('index.mdx','schema.mdx')) and any(
            re.search(r['section'],e['source'].path.rsplit('/',1)[-1],re.I) for r in plan['requirements']):value*=2.5
        # Original-language canonical docs precede translated/code adaptations unless named.
        if not re.search(r'英文|English',question,re.I):
            if e['meta'].get('language') in {'zh-CN','zh','zh-Hans'}:value*=1.25
        exact=terms
        heading=(e['source'].path+' '+e['chunk'].section).lower()
        value*=1+sum(.8 for n in set(exact) if n in heading)
        value*=1+.6*sum(1 for n in set(exact) if n in e['body_vector'])
        if not plan['needs_code'] and e['source'].book=='Hello-Agents' and e['source'].path.startswith('code/'):value*=.3
        if e['source'].book=='langchain-official' and not products:
            if e['source'].path.startswith(('src/oss/concepts/','src/oss/langchain/')):value*=1.25
            elif e['source'].path.startswith('src/oss/deepagents/'):value*=.8
        return value
    ranks={i:rank(i) for i in candidate}; chosen=[]; covered=set(); chars=0
    complex_query=bool(facets or plan['needs_code'] or plan['version_comparison'] or len(plan['subquestions'])>1 or len(plan['topics'])>1)
    limit=8 if complex_query else 3
    while candidate and len(chosen)<limit:
        best=max(candidate,key=lambda i:(len(tags[i]-covered),ranks[i],entries[i]['chunk'].chunk_id)); candidate.remove(best)
        item=_expand(entries[best],mat,question,expand)
        # Short concept pages are one parent context even when all headings are
        # leaves (there may be no literal "正文" section at the beginning).
        source_text=mat['texts'][item['source_id']]
        if expand and item['content_type']=='prose' and not item['path'].endswith('.ipynb') and len(source_text)<=3200:
            from .rag import visible_prose
            item.update(start_char=0,end_char=len(source_text),start_line=1,end_line=source_text.count('\n')+1,
                        text=source_text,context_text=visible_prose(source_text,mat['masks'][item['source_id']]))
            item['line_url']=item['source_url']+f"#L1-L{item['end_line']}"
        if expand and item['content_type']=='code' and not item['path'].endswith('.ipynb') and not item['path'].endswith(('.py','.js','.ts','.tsx','.mjs','.cjs')):
            opening=None
            for marker in re.finditer(r'(?m)^[ \t]*(`{3,}|~{3,})([^\n]*)\n?',source_text):
                if opening is None:opening=marker
                elif marker[1][0]==opening[1][0] and len(marker[1])>=len(opening[1]) and not marker[2].strip():
                    if opening.end()<=item['start_char']<item['end_char']<=marker.start() and marker.end()-opening.start()<=3200:
                        a,b=opening.start(),marker.end()
                        item.update(start_char=a,end_char=b,start_line=source_text.count('\n',0,a)+1,end_line=source_text.count('\n',0,b-1)+1,
                                    text=source_text[a:b],context_text=source_text[a:b])
                        item['line_url']=item['source_url']+f"#L{item['start_line']}-L{item['end_line']}"
                        break
                    opening=None
        expanded_tags=set(tags[best])
        for i in mat['source_entries'][item['source_id']] & allowed:
            c=entries[i]['chunk']
            if c.start_char>=item['start_char'] and c.end_char<=item['end_char'] and entries[i]['content_type']==item['content_type']:expanded_tags.update(tags[i])
        replacing=next((n for n,old in enumerate(chosen) if old['source_id']==item['source_id'] and old['content_type']==item['content_type'] and
                       item['start_char']<=old['start_char'] and item['end_char']>=old['end_char'] and expanded_tags-covered),None)
        if replacing is not None:
            old=chosen[replacing];item.update(evidence_id=old['evidence_id'],score=round(ranks[best],6),facet_ids=sorted(set(old['facet_ids'])|expanded_tags))
            chars+=len(item['context_text'])-len(old['context_text']);chosen[replacing]=item;covered.update(expanded_tags)
            continue
        if duplicate(item,chosen) or not item['context_text'].strip() or chars+len(item['context_text'])>20000:continue
        item.update(evidence_id='E'+str(len(chosen)+1),score=round(ranks[best],6),facet_ids=sorted(expanded_tags))
        chosen.append(item);chars+=len(item['context_text']);covered.update(expanded_tags)
    if not facets:
        facets=[{'id':'answer','dimension':question,'available':bool(chosen)}]
        for item in chosen:item['facet_ids']=['answer']
        if chosen:covered.add('answer')
    for facet in facets:
        facet['evidence_ids']=[e['evidence_id'] for e in chosen if facet['id'] in e['facet_ids']]
        facet['status']='retrieved' if facet['id'] in covered else 'not_retrieved' if facet['available'] else 'not_located'
    plan.update(necessary_faces=facets,missing_evidence_requirements=[f['id'] for f in facets if not f['evidence_ids']],
                object_anchors=list({(r['source_id'],r['scope_id'],r['symbol']):r for r in object_records}.values())[:8])
    result={'question':question,'book_filter':book,'question_plan':plan,'qa_version':3,'pipeline_version':5,
        'corpus_version':manifest['corpus_version'],'retriever':VERSION,'evidence':chosen,'books_without_match':[],
        'object_anchors':plan['object_anchors'],'source_verified':True,'support_verified':False,'elapsed_seconds':time.perf_counter()-started}
    result['retrieval_timings']={'verification_seconds':verified_at-started,'derived_index_seconds':indexed_at-verified_at,
        'lexical_and_scope_seconds':lexical_at-indexed_at,'semantic_seconds':semantic_at-lexical_at,
        'selection_expansion_seconds':time.perf_counter()-semantic_at}
    if trace:result['trace']={'eligible':len(allowed),'candidates':len(ranks),'covered_requirements':sorted(covered),
        'missing_requirements':plan['missing_evidence_requirements'],'semantic_parents':len(mat['descriptors']),
        'context_characters':chars,'objects':object_records,'case_roots':case_roots,'facets':facets,'selected':[{'source_id':e['source_id'],'path':e['path'],'section':e['section'],'start_line':e['start_line'],'end_line':e['end_line']} for e in chosen]}
    return result
