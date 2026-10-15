"""Offline provenance/position audit of the expanded snapshot and frozen labels."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus,load_corpus
from study_rag.source_views import source_view,locator
from study_rag.answer_schema import normalize_with_positions
from study_rag.qa_retrieval import body_mask
from study_rag.rag import visible_prose


def main():
    data=ROOT/'data/qa-overhaul-20261015-v2'
    manifest,chunks,sources,contents=verified_corpus(data,data/'index.sqlite3')
    raws={s.source_id:raw for s,raw in contents}
    texts={s.source_id:source_view(s.path,raw)[0] for s,raw in contents}
    old,originals=load_corpus(ROOT/'data/qa-20261014-v1')
    for source,raw in originals:
        if sources.get(source.source_id)!=source or raws[source.source_id]!=raw:raise ValueError('Prior source changed')
    positions=0
    for c in chunks:
        text=texts[c.source_id]
        if text[c.start_char:c.end_char]!=c.text:raise ValueError('Chunk range mismatch')
        if c.start_line!=text.count('\n',0,c.start_char)+1 or c.end_line!=text.count('\n',0,c.end_char-1)+1:raise ValueError('Chunk lines mismatch')
        if sources[c.source_id].path.endswith('.ipynb'):locator(sources[c.source_id],raws[c.source_id],c.start_char,c.end_char)
        positions+=1
    path=ROOT/'evals/qa-overhaul-v1.1.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='e117d1fc8991a39ef1dbcdb841e659ec45a73516f68c8db56b653b20c385ad30':raise ValueError('Frozen label hash changed')
    dataset=json.loads(raw);notebooks=set();spans=0
    if dataset['corpus_version']!=manifest['corpus_version'] or len(dataset['questions'])!=40:raise ValueError('Wrong gold corpus')
    for q in dataset['questions']:
        for p in q['points']:
            for s in p['supports']:
                source=sources[s['source_id']];text=texts[s['source_id']];a,b=s['start_char'],s['end_char']
                if text[a:b]!=s['quote']:raise ValueError(q['id']+': gold source mismatch')
                if s['start_line']!=text.count('\n',0,a)+1 or s['end_line']!=text.count('\n',0,b-1)+1:raise ValueError('Gold line mismatch')
                actual=locator(source,raws[source.source_id],a,b)
                if s.get('source_locator')!=actual:raise ValueError('Notebook source mapping changed')
                if actual:notebooks.add(q['id'])
                if s['kind']=='prose':
                    mask=body_mask(text,source.path.endswith('.mdx'))
                    if normalize_with_positions(visible_prose(s['quote'],mask[a:b]))[0]!=normalize_with_positions(s['quote'])[0]:raise ValueError('Masked gold')
                spans+=1
    coverage=json.loads((data/'coverage.json').read_text(encoding='utf-8'))
    if coverage['corpus_version']!=manifest['corpus_version'] or coverage['gaps']:raise ValueError('Unresolved inventory gaps')
    print(json.dumps({'status':'OVERHAUL_SOURCE_VALID','raw_files':len(contents),'preserved_files':len(originals),
                      'chunk_positions':positions,'gold_questions':40,'gold_support_positions':spans,
                      'notebook_questions':len(notebooks),'model_calls':0,'network_requests':0}))


if __name__=='__main__':main()
