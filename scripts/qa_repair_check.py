"""Check immutable source-first labels and original Notebook coordinates, no retrieval."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import source_view,locator
from study_rag.qa_retrieval import body_mask
from study_rag.rag import visible_prose
from study_rag.answer_schema import normalize_with_positions


def main():
    path=ROOT/'evals/qa-repair-frozen-v1.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!='bdad1835bc823d2a2be26b2211ad079070a0132ca68a5a6370e1772af9e386fe':raise ValueError('Frozen set changed')
    gold=json.loads(path.read_text(encoding='utf-8'));data=ROOT/'data/qa-overhaul-20261015-v2'
    manifest,_,sources,contents=verified_corpus(data,data/'index.sqlite3');raws={s.source_id:raw for s,raw in contents}
    assert gold['corpus_version']==manifest['corpus_version'] and len(gold['questions'])==40
    assert len(set(gold['representative_sample_ids']))==12
    counts={};notebooks=set();positions=0
    for q in gold['questions']:
        counts[q['topic']]=counts.get(q['topic'],0)+1
        for point in q['points']:
            assert point['supports'] and point['answer'] and point['coverage']=='all'
            for span in point['supports']:
                source=sources[span['source_id']];text,_=source_view(source.path,raws[source.source_id]);a,b=span['start_char'],span['end_char']
                assert text[a:b]==span['quote'],q['id']
                assert (span['start_line'],span['end_line'])==(text.count('\n',0,a)+1,text.count('\n',0,b-1)+1),q['id']
                actual=locator(source,raws[source.source_id],a,b);assert span['source_locator']==actual,q['id']
                if actual:notebooks.add(q['id']);assert '#L' not in span['line_url']
                if span['kind']=='prose':
                    mask=body_mask(text,source.path.endswith('.mdx'))
                    assert normalize_with_positions(visible_prose(span['quote'],mask[a:b]))[0]==normalize_with_positions(span['quote'])[0],q['id']
                positions+=1
    assert counts==dict(tools=4,memory=4,rag=4,planning=4,context=4,mcp=4,multi_agent=4,observability=4,cross=8)
    assert len(notebooks)>=4
    print(json.dumps({'status':'REPAIR_SOURCE_VALID','questions':40,'points':67,'support_positions':positions,'notebook_questions':len(notebooks),'model_calls':0}))


if __name__=='__main__':main()
