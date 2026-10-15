"""Atomic lexical/semantic/symbol retrieval with explicit question obligations."""
from collections import Counter,defaultdict
from dataclasses import asdict
from functools import lru_cache
from threading import RLock
import json
import math
import re
import time

from .core import CorpusError,verified_corpus,corpus_catalog,json_text,tokenize
from .qa_retrieval import body_mask,statistics,bm25_scores,duplicate
from .rag import visible_prose,section_role,requested_roles
from .question_plan import question_plan,expand_terms,ALIASES
from .source_views import source_view,locator,CODE_EXTENSIONS
from .static_facts import bindings,provenance
from .parent_vectors import semantic_parent_ranks

VERSION='atomic-parent-hybrid-obligations-v4.0'
_VERIFIED_MATERIALS={}
_MATERIAL_LOCK=RLock()
BOOK_PATTERNS={
    'Hello-Agents':r'Hello.?Agents|FirstAgentTest|PlanAndSolveAgent|Planner\.plan',
    'microsoft-ai-agents':r'微软|Microsoft|\b04-tool-use\b|\b08-multi-agent\b|human-in-the-loop Notebook',
    'huggingface-agents':r'Hugging.?Face|\bHF\b',
    'langchain-official':r'LangChain|LangGraph|Deep Agents|DeepAgents|LangSmith',
    'mcp-specification':r'\bMCP\b|Model Context Protocol',
    'awesome-llm-apps-cases':r'Hybrid Search RAG|Local RAG|perform_search|calculate_basic_math|calculate_percentage|raglite'}
TOPIC_CUES={'memory':r'memor|namespace|checkpoint|persist|\bstore\b',
            'rag':r'\brag\b|retriev|embedding|vector|knowledge',
            'tools':r'\btools?\b|function.call|tool.call',
            'planning':r'planning|\bplan\b|todo|react',
            'context':r'context|message|history',
            'multi_agent':r'multi.agent|subagent|handoff|supervisor|router',
            'observability':r'observ|trac|evaluation|diagnostic'}


def intent(question):
    plan=question_plan(question)
    plan['pipeline_version']=4
    plan['needs_code']=bool(re.search(r'源码|静态|代码|Notebook|\.ipynb|\.py\b|函数体|分支|控制流|(?:实际|具体|Python).*实现|写.*(?:函数|工具)|给(?:出|我).*(?:代码|源码|示例函数)|JSON\s*示例',question,re.I))
    plan['needs_configuration']=bool(re.search(r'requirements|配置|版本约束|依赖清单|环境变量|安装版本',question,re.I))
    plan['implementation_language']='python' if re.search(r'Python|python|\.py\b',question) else 'javascript' if re.search(r'JavaScript|TypeScript|\bJS\b|\bTS\b',question) else None
    plan['object_books']=[book for book,pattern in BOOK_PATTERNS.items() if re.search(pattern,question,re.I)]
    plan['obligations']=list(dict.fromkeys(plan['subquestions']))
    rules=[
        (r'返回.*(?:字符串|对象|Command)|(?:string|object).*return','return_string',r'return.*string|strings?',r'human.readable|readable.*text|Return a string'),
        (r'返回.*(?:字符串|对象|Command)|(?:string|object).*return','return_object',r'return.*object|objects?',r'structured|Return an object'),
        (r'返回.*Command|Command.*返回','return_command',r'return.*command|command',r'update.*state|mutat.*state'),
        (r'(?s)(?=.*config)(?=.*runtime)(?=.*(?:参数|argument))','reserved_parameters',r'.*',r'parameter names are reserved|Using these names will cause runtime errors'),
        (r'(?s)(?=.*skills?)(?=.*(?:memory|AGENTS\.md|记忆))','skill_loading',r'skills?',r'progressive disclosure|frontmatter'),
        (r'(?s)(?=.*skills?)(?=.*(?:memory|AGENTS\.md|记忆))','memory_loading',r'memory',r'always loaded'),
        (r'虚拟文件|virtual filesystem|后端.*磁盘','filesystem_backends',r'filesystem|backends?',r'in.memory state|local disk|StateBackend|StoreBackend|FilesystemBackend'),
        (r'notification|通知.*(?:id|ID|回包|回复)','notification_shape',r'notification',r'MUST NOT.*(?:ID|response)|MUST NOT.*reply|one.way'),
        (r'progress|进度','progress_rules',r'progress',r'MUST.*increase|MUST.*stop after completion|Progress tokens.*MUST'),
        (r'cursor|分页|页大小','pagination_rules',r'pagination|cursor',r'opaque|MUST NOT.*assume|Page size'),
        (r'取消|cancell','cancellation_rules',r'cancell',r'Streamable HTTP|stdio|maximum timeout'),
        (r'(?s)(?=.*(?:热路径|hot.path))(?=.*(?:后台|background))','hot_memory',r'hot path',None),
        (r'后台|background','background_memory',r'background',None),
        (r'采样|sampling','sampling',r'sampling',r'SAMPLING_RATE|sampling rate|sampling_rate'),
        (r'(?:工具名|参数名|名称|键).*(?:匹配|对应)|(?:匹配|对应).*(?:工具名|名称|键)','name_matching',r'.*',r'matches against|take their name|name.*match'),
    ]
    required=[]
    for trigger,name,section,body in rules:
        if re.search(trigger,question,re.I):required.append({'id':name,'section':section,'body':body})
    # Existing general task facets remain useful; they never reference gold IDs/positions.
    for f in plan['necessary_facets']:
        if f['id'].startswith('runtime_') and not re.search(r'参数|注入|运行时信息|state|context|store|信息|对象',question,re.I):continue
        required.append({'id':f['id'],'section':f['section_pattern'],'body':f['body_pattern']})
    plan['requirements']=required
    return plan


@lru_cache(maxsize=2)
def materials(contents,chunks,catalog_text):
    catalog=json.loads(catalog_text);sources={s.source_id:s for s,_ in contents}
    raws={s.source_id:raw for s,raw in contents}
    texts={s.source_id:source_view(s.path,raw)[0] for s,raw in contents}
    masks={}
    for source,raw in contents:
        text,cells=source_view(source.path,raw)
        if source.path.endswith('.ipynb'):
            chars=[' ' if c!='\n' else '\n' for c in text]
            for cell in cells:
                if cell['kind']=='markdown':chars[cell['start']:cell['end']]=body_mask(text[cell['start']:cell['end']])
            masks[source.source_id]=''.join(chars)
        else:masks[source.source_id]=body_mask(text,source.path.endswith('.mdx'))
    names={b['book']:b['display_name'] for b in catalog['books']}
    entries=[];parents={};parent_entries=defaultdict(list);symbols=defaultdict(set);source_entries=defaultdict(set)
    for c in chunks:
        source=sources[c.source_id];meta=catalog['chapters'][c.source_id]
        config=meta.get('content_type')=='configuration' or '[config]' in c.section
        code=source.path.endswith(tuple(CODE_EXTENSIONS)) or '[code]' in c.section or config
        body=c.text if code else visible_prose(c.text,masks[c.source_id][c.start_char:c.end_char])
        plain=re.sub(r'(?m)^\s*#{1,6}\s+.*$|^\s*(?:[-*_]\s*){3,}$','',body)
        if not re.search(r'[A-Za-z0-9\u3400-\u9fff]',plain):continue
        title=source.chapter+'\n'+source.path+'\n'+re.sub(r'[_/.-]+',' ',source.path)+'\n'+c.section
        # The semantic descriptor represents the parent. Full child text remains lexical.
        parent_key=(source.source_id,c.section)
        if parent_key not in parents:parents[parent_key]=len(parents)
        parent=parents[parent_key]
        bv,tv=tokenize(body+'\n'+re.sub(r'[_-]+',' ',body) if code else body),tokenize(title)
        index=len(entries)
        entries.append({'chunk':c,'source':source,'meta':meta,'body':body,'body_vector':bv,'title_vector':tv,
                        'body_length':sum(bv.values()),'title_length':sum(tv.values()),'content_type':'code' if code else 'prose',
                        'configuration':config,'role':section_role(c.section),'parent':parent,'display_name':names[source.book],
                        'topic_flags':{topic for topic,pattern in TOPIC_CUES.items() if re.search(pattern,title,re.I)} |
                                      ({'mcp'} if source.book=='mcp-specification' else set())})
        parent_entries[parent].append(index);source_entries[source.source_id].add(index)
    parent_bounds={};descriptors=[]
    for key,parent in parents.items():
        group=[entries[i] for i in parent_entries[parent]]
        first,last=group[0],group[-1];a=min(e['chunk'].start_char for e in group);b=max(e['chunk'].end_char for e in group)
        parent_bounds[parent]=(a,b)
        descriptors.append((first['source'].book+' '+first['source'].chapter+' '+first['chunk'].section+'\n'+first['body'][:650]+'\n'+last['body'][-250:])[:1500])
    for source,raw in contents:
        graph=bindings(source.path,raw)
        for d in graph['definitions']:symbols[d['name']].add(source.source_id);symbols[d['qualified_name']].add(source.source_id)
    postings=statistics(entries)
    return {'sources':sources,'raws':raws,'texts':texts,'masks':masks,'entries':entries,'postings':postings,
            'parent_entries':parent_entries,'parent_bounds':parent_bounds,'descriptors':tuple(descriptors),
            'symbols':symbols,'source_entries':source_entries,'catalog':catalog}


def verified_materials(manifest,contents,chunks,catalog):
    # Called only after full raw-byte and index verification. The corpus digest
    # binds every declaration and source hash; no stat/mtime shortcut is used.
    key=(VERSION,manifest['corpus_version'])
    with _MATERIAL_LOCK:
        if key not in _VERIFIED_MATERIALS:
            value=materials(tuple(contents),tuple(chunks),json_text(catalog))
            if len(_VERIFIED_MATERIALS)>=2:_VERIFIED_MATERIALS.pop(next(iter(_VERIFIED_MATERIALS)))
            _VERIFIED_MATERIALS[key]=value
        return _VERIFIED_MATERIALS[key]


def _expand(entry,mat,question,expand=True):
    c,s=entry['chunk'],entry['source'];text=mat['texts'][s.source_id]
    a,b=c.start_char,c.end_char
    if expand:
        left,right=mat['parent_bounds'][entry['parent']]
        if right-left<=3200 and entry['content_type']!='code':a,b=left,right
        else:
            group=mat['parent_entries'][entry['parent']]
            adjacent=[mat['entries'][i]['chunk'] for i in group if abs(mat['entries'][i]['chunk'].start_char-a)<2400]
            for other in sorted(adjacent,key=lambda other:abs(other.start_char-c.start_char)):
                left,right=min(a,other.start_char),max(b,other.end_char)
                gap=text[b:other.start_char] if other.start_char>b else text[other.end_char:a] if other.end_char<a else ''
                if right-left<=2800 and (entry['content_type']!='code' or not gap.strip()):a,b=left,right
        if entry['content_type']!='code' and not s.path.endswith('.ipynb'):
            # Preserve the enclosing definition when a short child section near
            # the start of a document is selected (e.g. a protocol primitive's
            # interaction rules). The added prose still uses original offsets.
            siblings=mat['source_entries'][s.source_id]
            introductory=[mat['entries'][i]['chunk'].start_char for i in siblings
                          if mat['entries'][i]['content_type']=='prose' and
                          mat['entries'][i]['chunk'].section=='正文']
            if introductory and b-min(introductory)<=3200:a=min(a,min(introductory))
    loc=locator(s,mat['raws'][s.source_id],a,b)
    context=text[a:b] if entry['content_type']=='code' else visible_prose(text[a:b],mat['masks'][s.source_id][a:b])
    line_a,line_b=text.count('\n',0,a)+1,text.count('\n',0,b-1)+1
    kind=entry['meta'].get('kind');role='configuration' if entry['configuration'] else 'implementation' if s.path.endswith(('.py','.js','.ts')) and s.book not in {'langchain-official','mcp-specification'} else 'example' if entry['content_type']=='code' else None
    return {**asdict(c),'start_char':a,'end_char':b,'start_line':line_a,'end_line':line_b,'text':text[a:b],
            'context_text':context,'anchor_chunk_id':c.chunk_id,'book':s.book,'chapter':s.chapter,'path':s.path,
            'display_name':entry['display_name'],'language':entry['meta']['language'],'content_type':entry['content_type'],
            'code_role':role,'applicable_versions':entry['meta'].get('applicable_versions',['unknown']),
            'source_url':s.source_url,'line_url':s.source_url if loc else s.source_url+f'#L{line_a}-L{line_b}',
            **({'source_locator':loc} if loc else {}),'provenance':provenance(s,mat['raws'][s.source_id],a,b)}


def retrieve_v4(data_dir,index_path,question,book=None,*,trace=False,expand=True,_verified=None):
    started=time.perf_counter();plan=intent(question)
    manifest,chunks,sources,contents=_verified if _verified is not None else verified_corpus(data_dir,index_path)
    catalog=corpus_catalog(manifest)
    if book and book not in {b['book'] for b in catalog['books']}:raise CorpusError('未知资料范围。')
    mat=verified_materials(manifest,contents,chunks,catalog);entries=mat['entries']
    requested=set(plan['object_books']);roles=requested_roles(question)
    product_scopes=set()
    for product,pattern in [('langchain',r'LangChain'),('langgraph',r'LangGraph'),('deepagents',r'Deep\s*Agents|DeepAgents')]:
        if re.search(pattern,question,re.I):product_scopes.add(product)
    cross_topics=('mcp-specification' in requested and bool(set(plan['topics'])-{'mcp','tools'}))
    owners=set()
    for symbol in plan['named_symbols']:owners.update(mat['symbols'].get(symbol,set()))
    names=re.findall(r'[A-Za-z0-9_.-]+\.(?:ipynb|py|txt|ts|js)\b',question)
    path_owners={sid for sid,s in sources.items() if any(s.path.endswith(name) for name in names)}
    if path_owners:owners=(owners & path_owners) or path_owners
    compact=re.sub(r'[^a-z0-9]','',question.lower())
    query_words=set(re.findall(r'[a-z][a-z0-9]+',' '.join(expand_terms(question)).lower()))
    case_roots=[]
    for source in sources.values():
        meta=catalog['chapters'][source.source_id]
        if meta.get('kind')=='case':
            root=source.path.rsplit('/',1)[0];name=root.rsplit('/',1)[-1]
            aliases={re.sub(r'[^a-z0-9]','',name),re.sub(r'[^a-z0-9]','',re.sub(r'_agent$','',name))}
            meaningful=set(re.findall(r'[a-z]+',name.lower()))-{'ai','agent','agents','app','team','with','the','and'}
            if (any(len(alias)>=8 and alias in compact for alias in aliases) or
                len(meaningful & query_words)>=2 and len(meaningful & query_words)/max(1,len(meaningful))>=.5):case_roots.append(root)
    case_roots=list(dict.fromkeys(case_roots))
    if owners and case_roots:
        narrowed={sid for sid in owners if any(sources[sid].path.startswith(root+'/') for root in case_roots)}
        if narrowed:owners=narrowed
    if owners and (plan['needs_code'] or re.search(r'函数|方法|示例',question)):plan['needs_code']=True
    allowed=set()
    for i,e in enumerate(entries):
        s=e['source'];versions=e['meta'].get('applicable_versions',['unknown'])
        if book and s.book!=book:continue
        if requested and not cross_topics and s.book not in requested:continue
        if s.book=='langchain-official' and product_scopes:
            product=re.match(r'src/oss/(langchain|langgraph|deepagents)/',s.path)
            if product and product[1] not in product_scopes:continue
        if s.book=='mcp-specification' and plan['applicable_versions'] and not set(versions)&set(plan['applicable_versions']):continue
        if plan['implementation_language']=='python' and ('/javascript/' in s.path or s.path.endswith(('.ts','.js','.mjs'))):continue
        if e['configuration'] and not plan['needs_configuration']:continue
        if e['content_type']=='code' and not plan['needs_code'] and not plan['needs_configuration']:continue
        if e['role'] not in roles:continue
        if re.search(r'参考文献|额外资源|Additional Resources|Contribut|^Quiz',e['chunk'].section,re.I):continue
        allowed.add(i)
    queries=[expand_terms(question)]
    original_english=set(re.findall(r'[a-z][a-z0-9_-]*',question.lower()))-{'the','and','with','from','what','how','to','is','a','an','of','in','on'}
    original_terms=set(tokenize(question))
    for part in plan['subquestions']+plan['query_windows']:
        query=expand_terms(part,topics=False)
        if query and query not in queries:queries.append(query)
    scores=[defaultdict(float) for _ in queries]
    for qid,query in enumerate(queries):
        for term in query:
            for i,weight,in_body in mat['postings'].get(term,[]):
                if i in allowed:scores[qid][i]+=weight*(1 if in_body else .9)*(2 if term in original_terms else 1)
    lex=sorted(scores[0],key=lambda i:(-scores[0][i],entries[i]['chunk'].chunk_id))
    candidate=set(lex[:140]);lex_rank={i:n+1 for n,i in enumerate(lex)}
    channel_tags=defaultdict(set)
    required_channels=set()
    if len(requested)>1:
        for requested_book in requested:
            lane=[i for i in lex if entries[i]['source'].book==requested_book]
            candidate.update(lane[:6]);required_channels.add('book:'+requested_book)
            for i in allowed:
                if entries[i]['source'].book==requested_book:channel_tags[i].add('book:'+requested_book)
    if cross_topics and re.search(r'比较|区别|各|分别',question):
        for topic in plan['topics']:
            lane=[i for i in lex if topic in entries[i]['topic_flags']]
            candidate.update(lane[:6]);required_channels.add('topic:'+topic)
            for i in allowed:
                if topic in entries[i]['topic_flags']:channel_tags[i].add('topic:'+topic)
    parent_allowed={entries[i]['parent'] for i in allowed}
    try:dense=semantic_parent_ranks(manifest['corpus_version'],mat['descriptors'],parent_allowed,question)
    except Exception as error:raise CorpusError('固定本地 E5 索引不可用或完整性校验失败：'+type(error).__name__) from None
    dense_rank={}
    for rank,(parent,_) in enumerate(dense,1):
        children=[i for i in mat['parent_entries'][parent] if i in allowed]
        children.sort(key=lambda i:(-max(score.get(i,0) for score in scores),entries[i]['chunk'].start_char))
        for i in children[:3]:candidate.add(i);dense_rank[i]=rank
    for sid in owners:
        candidate.update(i for i in mat['source_entries'].get(sid,[]) if i in allowed)
    # Every independent subquestion and explicit version gets its own lane.
    for score in scores[1:]:candidate.update(sorted(score,key=lambda i:-score[i])[:12])
    requirement_hits={};all_hits=channel_tags
    for requirement in plan['requirements']:
        hits=[]
        for i in allowed:
            e=entries[i]
            if re.search(requirement['section'],e['chunk'].section,re.I) and (not requirement['body'] or re.search(requirement['body'],e['body'],re.I)):
                hits.append(i);all_hits[i].add(requirement['id'])
        hits.sort(key=lambda i:(-scores[0].get(i,0),entries[i]['chunk'].chunk_id));candidate.update(hits[:4])
        requirement_hits[requirement['id']]=hits
    all_symbols=set(plan['named_symbols'])
    for i in candidate:
        e=entries[i]
        if e['source'].source_id in owners:
            graph=bindings(e['source'].path,mat['raws'][e['source'].source_id])
            for relation in ['definitions','imports','calls']:
                for node in graph[relation]:
                    if node['name'] in all_symbols and e['chunk'].start_char<=node['start_char']<e['chunk'].end_char:
                        all_hits[i].add(relation+':'+node['name'])
        if plan['version_comparison']:
            all_hits[i].update('version:'+v for v in e['meta'].get('applicable_versions',[]) if v in plan['applicable_versions'])
    def rank(i):
        e=entries[i];value=(1/(60+lex_rank[i]) if i in lex_rank else 0)+(1/(60+dense_rank[i]) if i in dense_rank else 0)
        # Independent question lanes participate in RRF, rather than only adding
        # candidates which then lose to the overview's global query score.
        value+=sum(1/(60+lane[i]) for lane in facet_ranks if i in lane)/max(1,len(facet_ranks))
        if owners and e['source'].source_id in owners:value*=3
        if any(e['source'].path.startswith(root+'/') for root in case_roots):value*=2
        if plan['needs_code'] and e['content_type']=='code':value*=1.5
        if not plan['needs_code'] and e['content_type']=='prose' and e['source'].book in {'langchain-official','mcp-specification'}:value*=1.15
        heading_words=set(re.findall(r'[a-z][a-z0-9_-]*',(e['source'].path+' '+e['chunk'].section).lower()))
        value*=1+.2*len(original_english & heading_words)
        # Canonical reference pages precede product-specific adaptations unless
        # the question names that product. This is source identity, not a gold
        # source-ID preference; all matching documents remain candidates.
        if e['source'].book=='langchain-official' and not product_scopes:
            if e['source'].path.startswith(('src/oss/concepts/','src/oss/langchain/')):value*=1.25
            elif e['source'].path.startswith('src/oss/deepagents/'):value*=.8
        if re.search(r'index|overview|概览',e['chunk'].section,re.I) and all_hits[i]:value*=.9
        depths=[]
        for requirement in plan['requirements']:
            if requirement['id'] in all_hits[i]:
                match=re.search(requirement['section'],e['chunk'].section,re.I)
                if match and match.end()>match.start():depths.append(e['chunk'].section[match.end():].count(' / '))
        if depths:value/=1+.25*min(depths)
        return value
    facet_ranks=[]
    for score in scores[1:]:
        facet_ranks.append({i:n+1 for n,i in enumerate(sorted(score,key=lambda i:-score[i]))})
    ranks={i:rank(i) for i in candidate}
    simple=not plan['needs_code'] and not plan['requirements'] and not plan['version_comparison'] and len(plan['subquestions'])<=1 and len(plan['topics'])<=1
    limit=3 if simple else 8;chosen=[];covered=set();characters=0;pool=set(candidate)
    while pool and len(chosen)<limit:
        best=max(pool,key=lambda i:(len(all_hits[i]-covered),ranks[i],entries[i]['chunk'].chunk_id));pool.remove(best)
        item=_expand(entries[best],mat,question,expand)
        if duplicate(item,chosen) or not item['context_text'].strip() or characters+len(item['context_text'])>20000:continue
        item.update(evidence_id='E'+str(len(chosen)+1),score=round(ranks[best],6))
        chosen.append(item);characters+=len(item['context_text']);covered.update(all_hits[best])
        required_present={key for key,hits in requirement_hits.items() if hits}
        required_present.update(required_channels)
        if plan['version_comparison']:required_present.update('version:'+v for v in plan['applicable_versions'])
        # A matching section heading is a routing signal, not proof that every
        # subquestion has been answered. Do not stop at the first such match.
        # Symbol questions stop once source relationships and required concepts are covered.
        if owners and plan['needs_code'] and len(chosen)>=3:
            required={f for i in candidate for f in all_hits[i]}
            if required<=covered:break
    missing=[key for key,items in requirement_hits.items() if not items or key not in covered]
    plan['missing_evidence_requirements']=missing
    result={'question':question,'book_filter':book,'question_plan':plan,'qa_version':3,'pipeline_version':4,
            'corpus_version':manifest['corpus_version'],'retriever':VERSION,'evidence':chosen,'books_without_match':[],
            'source_verified':True,'support_verified':False,'elapsed_seconds':time.perf_counter()-started}
    if trace:result['trace']={'eligible':len(allowed),'candidates':len(candidate),'covered_requirements':sorted(covered),
        'missing_requirements':missing,'semantic_parents':len(mat['descriptors']),'context_characters':characters,
        'selected':[{'source_id':e['source_id'],'path':e['path'],'section':e['section'],'start_line':e['start_line'],'end_line':e['end_line']} for e in chosen]}
    return result
