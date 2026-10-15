"""Source-observed Python relations rendered by the server, never executed."""
import ast
from functools import lru_cache
import re

from .source_views import source_view


def python_units(path, raw):
    """Independent parse scopes; offsets always refer to the verified source view."""
    text, cells = source_view(path, raw)
    units = []
    for cell in cells:
        if cell['kind'] == 'code' and cell['language'].lower() == 'python':
            units.append({**cell, 'scope_id': f"cell:{cell['cell_index']}" if cell['cell_index'] else 'file'})
        elif cell['kind'] == 'markdown':
            body = text[cell['start']:cell['end']]
            fence = None; ordinal = 0
            for match in re.finditer(r'(?m)^[ \t]*(`{3,}|~{3,})([^\n]*)\n?', body):
                marker, info = match[1], match[2].strip()
                if fence is None:
                    ordinal += 1
                    fence = (marker, info, match.end(), ordinal)
                elif marker[0] == fence[0][0] and len(marker) >= len(fence[0]) and not info:
                    if re.match(r'^(?:python|py)(?:\s|$)', fence[1], re.I):
                        units.append({**cell, 'start':cell['start']+fence[2], 'end':cell['start']+match.start(),
                            'kind':'code', 'language':'python', 'scope_id':f"cell:{cell['cell_index']}:fence:{fence[3]}"})
                    fence = None
    return text, units


@lru_cache(maxsize=4096)
def bindings(path, raw):
    text, cells = python_units(path, raw)
    result = {'definitions': [], 'imports': [], 'calls': [], 'branches': [], 'assignments':[], 'returns':[], 'analysis_gaps': []}
    for cell in cells:
        if cell['kind'] != 'code' or cell['language'] != 'python': continue
        original = text[cell['start']:cell['end']]
        clean = re.sub(r'(?m)^[ \t]*[%!].*$', lambda m: ' '*len(m[0]), original)
        try: tree = ast.parse(clean)
        except (SyntaxError, ValueError, RecursionError):
            result['analysis_gaps'].append({'cell_index':cell['cell_index'],'scope_id':cell['scope_id'],'reason':'Python syntax not statically parsed'});continue
        offsets=[cell['start']]
        for line in original.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
        def bounds(node):
            a,b=offsets[node.lineno-1],offsets[min(node.end_lineno,len(offsets)-1)]
            return {'start_char':a,'end_char':b,'start_line':text.count('\n',0,a)+1,
                    'end_line':text.count('\n',0,b-1)+1,'cell_index':cell['cell_index'],'scope_id':cell['scope_id']}
        def expression(node):
            try:return ast.unparse(node)
            except (ValueError,RecursionError):return '<unresolved expression>'
        def walk(node,owner='module',conditions=()):
            for child in ast.iter_child_nodes(node):
                nested=owner
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    nested=child.name if owner=='module' else owner+'.'+child.name
                    result['definitions'].append({'name':child.name,'qualified_name':nested,'kind':type(child).__name__,**bounds(child)})
                elif isinstance(child,ast.ImportFrom):
                    result['imports'].extend({'name':n.asname or n.name,'module':'.'*child.level+(child.module or ''),'imported_name':n.name,**bounds(child)} for n in child.names)
                elif isinstance(child,ast.Import):
                    result['imports'].extend({'name':n.asname or n.name.split('.')[0],'module':n.name,'imported_name':None,**bounds(child)} for n in child.names)
                elif isinstance(child,ast.Call):
                    arguments=[{'name':str(i+1),'expression':expression(arg)} for i,arg in enumerate(child.args[:6])]
                    arguments += [{'name':kw.arg or '**','expression':expression(kw.value)} for kw in child.keywords[:8]]
                    complete=len(child.args)<=6 and len(child.keywords)<=8 and all(len(a['expression'])<=180 for a in arguments)
                    result['calls'].append({'name':expression(child.func),'owner':owner,'arguments':arguments if complete else [],'arguments_complete':complete,**bounds(child)})
                elif isinstance(child,ast.If):
                    returns=[statement for statement in child.body if isinstance(statement,ast.Return)]
                    if returns:result['branches'].append({'owner':owner,'condition':expression(child.test),
                        'return_expression':expression(returns[0].value) if returns[0].value is not None else 'None',**bounds(child)})
                elif isinstance(child,(ast.Assign,ast.AnnAssign)):
                    targets=child.targets if isinstance(child,ast.Assign) else [child.target]
                    for target in targets:
                        if isinstance(target,ast.Name):result['assignments'].append({'name':target.id,'owner':owner,
                            'qualified_name':target.id if owner=='module' else owner+'.'+target.id,
                            'expression':expression(child.value) if child.value else 'None','conditions':list(conditions),**bounds(child)})
                elif isinstance(child,ast.Return):
                    result['returns'].append({'owner':owner,'expression':expression(child.value) if child.value else 'None','conditions':list(conditions),**bounds(child)})
                if isinstance(child,ast.If):
                    # Traverse each arm with its own condition, never detach a return from its guard.
                    condition=expression(child.test)
                    for arm,label in [(child.body,condition),(child.orelse,'not ('+condition+')')]:
                        holder=ast.Module(body=arm,type_ignores=[])
                        walk(holder,nested,conditions+(label,))
                else:walk(child,nested,conditions)
        walk(tree)
    return result


def provenance(source, raw, start, end):
    from .provenance import source_scope
    base=source_scope(source);graph=bindings(source.path,raw)
    scopes={cell['scope_id'] for cell in python_units(source.path,raw)[1] if cell['start']<end and cell['end']>start}
    imports=[r for r in graph['imports'] if r['scope_id'] in scopes]
    definitions=[r for r in graph['definitions'] if r['scope_id'] in scopes]
    base['framework_imports']=sorted({r['module'] for r in imports if r['module'].startswith(('langchain','langgraph','agent_framework','google.adk','agno','autogen'))})
    if source.path.endswith(('.py','.ipynb','.js','.ts')):base['claim_boundary']='static code in a pinned teaching source, not execution proof'
    overlap=lambda row:row['start_char']<end and row['end_char']>start
    base['python']={'local_definitions':[r for r in graph['definitions'] if overlap(r)],
                    'imports':[r for r in graph['imports'] if overlap(r)],
                    'calls':[r for r in graph['calls'] if overlap(r)],
                    'branches':[r for r in graph['branches'] if overlap(r)],
                    'assignments':[r for r in graph['assignments'] if overlap(r)],
                    'returns':[r for r in graph['returns'] if overlap(r)],
                    'module_local_names':sorted({r['name'] for r in definitions if '.' not in r['qualified_name']}),
                    'module_imported_names':sorted({r['name'] for r in imports}),
                    'analysis_gaps':graph['analysis_gaps']}
    return base


def fact_pool(question, evidence, spans, *, minimal=False):
    """Every relation is bound to actual span IDs and exact source intervals."""
    words=set(re.findall(r'\b[A-Za-z][A-Za-z0-9_]*\b',question))
    records=[]
    for item in evidence:
        py=item.get('provenance',{}).get('python',{})
        imported=set(py.get('module_imported_names',[]));local=set(py.get('module_local_names',[]))
        def refs(row,definition=False):
            start,end=row['start_char'],row['end_char']
            if definition:
                relative=start-item['start_char']
                if relative<0:return []
                line_end=item['text'].find('\n',relative)
                end=item['start_char']+(line_end if line_end>=0 else len(item['text']))
            if start<item['start_char'] or end>item['end_char']:return []
            selected=[s for s in spans[item['evidence_id']] if s['start_char']<end and s['end_char']>start]
            if not selected or len(selected)>4:return []
            if min(s['start_char'] for s in selected)>start or max(s['end_char'] for s in selected)<end-1:return []
            return [item['evidence_id']+':'+s['span_id'] for s in selected]
        for row in py.get('local_definitions',[]):
            references=refs(row,True)
            if references:
                label='类' if row['kind']=='ClassDef' else '函数'
                records.append((row['name'] in words,{'text':f"这份源码在本地定义{label} `{row['qualified_name']}`。",'references':references,'kind':'definition','subject':row['name']}))
        for row in py.get('imports',[]):
            references=refs(row)
            if references:
                target=f"{row['module']}.{row['imported_name']}" if row['imported_name'] else row['module']
                records.append((row['name'] in words,{'text':f"这份源码从 `{target}` 导入，绑定名称为 `{row['name']}`。",'references':references,'kind':'import','subject':row['name']}))
        for row in py.get('calls',[]):
            if minimal and row['name'].split('.')[-1] in {'print','now','strftime','utcnow','isoformat'} and not re.search(r'print|时间戳|日期|日志',question):continue
            if minimal and any(r['start_char']==row['start_char'] and r['end_char']==row['end_char']
                               for kind in ['assignments','returns'] for r in py.get(kind,[])):continue
            references=refs(row)
            if not references:continue
            arguments='、'.join(f"`{a['name']}={a['expression']}`" for a in row['arguments'])
            if len(arguments)>700:continue
            text=f"`{row['owner']}` 的源码调用 `{row['name']}`"+('，显式实参表达式为 '+arguments if arguments else '')+('（长实参未在此摘要展开）' if not row.get('arguments_complete',True) else '')+'。'
            root=row['name'].split('.')[0]
            if root in imported and root not in local:
                text+='这只描述调用方的写法，未验证该依赖的内部执行行为。'
            records.append((root in words or row['owner'].split('.')[-1] in words,
                {'text':text,'references':references,'kind':'call','subject':row['name'],'owner':row['owner'],'position':row['start_char']}))
        for row in py.get('branches',[]):
            if minimal:continue  # guarded returns below already include the same branch fact
            references=refs(row)
            if references and len(row['return_expression'])<500:
                records.append((row['owner'].split('.')[-1] in words,{'text':f"`{row['owner']}` 中，源码条件 `{row['condition']}` 成立的分支显式返回 `{row['return_expression']}`。这是静态分支描述。",
                    'references':references,'kind':'branch','subject':row['owner'],'owner':row['owner']}))
        if minimal:
            for kind in ['assignments','returns']:
                for row in py.get(kind,[]):
                    references=refs(row)
                    if not references or len(row['expression'])>260:continue
                    text=f"`{row['owner']}` 中，"+('当源码条件 '+ ' 且 '.join('`'+c+'`' for c in row['conditions'])+' 成立时，' if row['conditions'] else '')
                    text+=(f"将 `{row['expression']}` 赋给 `{row['name']}`。" if kind=='assignments' else f"显式返回 `{row['expression']}`。")
                    records.append((row['owner'].split('.')[-1] in words,{'text':text,'references':references,
                        'kind':kind,'subject':row.get('name',row['owner']),'owner':row['owner'],'position':row['start_char']}))
    records.sort(key=lambda r:(not r[0],r[1].get('position',-1) if minimal else 0))
    result={};seen=set()
    for relevant,record in records:
        if minimal and not relevant:continue
        if record['text'] in seen:continue
        seen.add(record['text']);result['F'+str(len(result)+1)]=record
        if len(result)>=24:break
    return result


def validate_boundaries(answer,evidence,facts):
    """Reject unsupported explicit dependency-internal guarantees, not entailment scoring."""
    from .answer_schema import answer_units
    from .provenance import ProvenanceError
    controlled={fact['text'] for fact in facts.values()}
    external=set()
    for e in evidence:
        py=e.get('provenance',{}).get('python',{})
        external.update(set(py.get('module_imported_names',[]))-set(py.get('module_local_names',[])))
    for unit in answer_units(answer):
        text=unit['text']
        for sentence in controlled:text=text.replace(sentence,'')
        if not text.strip():continue
        for symbol in external:
            pattern=re.escape(symbol)+r'[`\s]*(?:内部)?(?:一定|必然|始终|不会|没有|并未|从不)[^。；\n]{0,35}(?:检索|重排|缓存|复用|调用|执行)'
            if re.search(pattern,text) and not re.search(r'(?:不能|无法|尚不能|不足以).{0,15}(?:断言|证明|确定)',text):
                raise ProvenanceError('调用方证据不足以确定依赖内部行为。')
