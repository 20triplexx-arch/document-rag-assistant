"""Source ownership and Python bindings derived only from verified text. No imports."""
import ast
from functools import lru_cache
import re

from .core import CorpusError

VERSION = "source-bindings-v1"


class ProvenanceError(CorpusError): pass


@lru_cache(maxsize=128)
def python_bindings(text):
    tree=ast.parse(text)
    lines=text.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    def bounds(node):
        return {'start_char':offsets[node.lineno-1], 'end_char':offsets[node.end_lineno],
                'start_line':node.lineno,'end_line':node.end_lineno}
    definitions=[];imports=[];calls=[]
    def walk(node, owner='module'):
        for child in ast.iter_child_nodes(node):
            nested=owner
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                nested=child.name if owner=='module' else owner+'.'+child.name
                definitions.append({'name':child.name,'qualified_name':nested,'kind':type(child).__name__,**bounds(child)})
            if isinstance(child,ast.ImportFrom):
                imports.extend({'name':v.asname or v.name,'module':'.'*child.level+(child.module or ''),'imported_name':v.name,**bounds(child)} for v in child.names)
            elif isinstance(child,ast.Import):
                imports.extend({'name':v.asname or v.name.split('.')[0],'module':v.name,'imported_name':None,**bounds(child)} for v in child.names)
            elif isinstance(child,ast.Call):
                try:name=ast.unparse(child.func)
                except (ValueError,RecursionError):name=''
                if name:calls.append({'name':name,'owner':owner,**bounds(child)})
            walk(child,nested)
    walk(tree)
    return definitions,imports,calls


def source_scope(source):
    path=source.path
    if source.book=='langchain-official':
        framework='Deep Agents' if '/deepagents/' in path else 'LangSmith' if '/langsmith/' in path else 'LangChain / LangGraph'
    elif source.book=='mcp-specification':framework='MCP'
    elif path.endswith('.py'):
        framework='Google ADK' if '/google_adk_crash_course/' in path else 'example application'
    else:framework=source.book
    return {'version':VERSION,'repository':source.repository,'commit':source.commit,'framework':framework,
            'case_path':path.rsplit('/',1)[0] if source.book not in {'langchain-official','mcp-specification'} else None,
            'claim_boundary':'static implementation, not execution proof' if path.endswith('.py') else 'documentation or teaching example, not application execution proof'}


def evidence_provenance(source,text,item):
    scope=source_scope(source)
    if source.path.endswith('.py'):
        definitions,imports,calls=python_bindings(text)
        a,b=item['start_char'],item['end_char']
        overlaps=lambda row:row['start_char']<b and row['end_char']>a
        scope['python']={'local_definitions':[d for d in definitions if overlaps(d)][:20],
                         'imports':[d for d in imports if overlaps(d)][:30],
                         'calls':[d for d in calls if overlaps(d)][:30],
                         'module_imported_names':sorted({d['name'] for d in imports}),
                         'module_local_names':sorted({d['name'] for d in definitions if '.' not in d['qualified_name']})[:80]}
    return scope


def named_symbols(question):
    tokens=re.findall(r'\b[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*\b',question)
    return list(dict.fromkeys(t for t in tokens if '_' in t or '.' in t or re.search(r'[a-z][A-Z]',t)))


def validate_provenance(answer,evidence):
    """Reject explicit local-definition/import contradictions, not semantic entailment."""
    from .answer_schema import answer_units
    by_id={e['evidence_id']:e for e in evidence}
    for unit in answer_units(answer):
        if unit['kind']!='prose':continue
        selected=[by_id[r['evidence_id']] for r in unit['references'] if r['evidence_id'] in by_id]
        for e in selected:
            py=e.get('provenance',{}).get('python',{})
            for name in py.get('module_local_names',[]):
                if name in py.get('module_imported_names',[]):continue
                # An explicit subject relation only: do not infer natural-language
                # truth from token overlap or reject discussion of called imports.
                subject=re.escape(name)+r'(?:\s*[`函数()（）]|\s|和\s*[A-Za-z_][A-Za-z0-9_]*|、[A-Za-z_][A-Za-z0-9_]*)*'
                relation=r'(?:都)?(?:是)?(?:从\s*[A-Za-z_][\w.]*\s*(?:包|库)?\s*导入|来自\s*[A-Za-z_][\w.]*\s*(?:包|库)|is imported from\s+\w+)'
                if re.search(subject+relation,unit['text']):
                    raise ProvenanceError('本地定义被错误归属于外部导入。')
