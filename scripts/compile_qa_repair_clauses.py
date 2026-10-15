"""Compile our fixed routing rules, never a collected source or evaluation answer."""
from pathlib import Path
import argparse
import ast
import json

ROOT=Path(__file__).resolve().parents[1]


def compile_rules():
    named={};overrides={};extras=[]
    for path in ['question_plan.py','qa_retrieval_v4.py','qa_retrieval_v5.py']:
        tree=ast.parse((ROOT/'study_rag'/path).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'rules','direct'} for t in node.targets):
                value=ast.literal_eval(node.value)
                if isinstance(value,dict):overrides.update(value)
                else:
                    for _,name,section,body in value:named[name]=(section,body)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='append' and node.args:
                try:value=ast.literal_eval(node.args[0])
                except (ValueError,TypeError):continue
                if isinstance(value,tuple) and len(value)==3 and all(isinstance(v,str) for v in value):named[value[0]]=value[1:]
            if isinstance(node,ast.Dict):
                try:value=ast.literal_eval(node)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and isinstance(value.get('id'),str) and isinstance(value.get('section'),str):named[value['id']]=(value['section'],value.get('body'))
    for name,body in overrides.items():
        if name in named:extras.append((named[name][0],body))
    pairs=set(named.values())|set(extras)
    return {'version':1,'basis':'Fixed code routing taxonomy; no questions, gold spans, or generated answers.',
            'clauses':[{'section':section,'body':body} for section,body in sorted(pairs,key=lambda pair:(pair[0],pair[1] or ''))]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    dest=ROOT/'study_rag/clause_specs.json';encoded=json.dumps(compile_rules(),ensure_ascii=False,indent=2)+'\n'
    if args.check:
        if dest.read_text(encoding='utf-8')!=encoded:raise SystemExit('Fixed routing clauses changed; rebuild derived warmup specification.')
    else:dest.write_text(encoded,encoding='utf-8')
    print('FIXED_CLAUSE_SPEC_VALID')
