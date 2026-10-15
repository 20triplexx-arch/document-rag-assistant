"""Offline validation of frozen source-first questions; zero model/network calls."""
from pathlib import Path
import hashlib
import json
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus,validate_text


def check():
    path=ROOT/'evals/qa-depth-v1.json'
    gold=json.loads(path.read_text(encoding='utf-8'))
    data=ROOT/'data/qa-20261014-v1'
    manifest,_,_,contents=verified_corpus(data,data/'index.sqlite3')
    texts={s.source_id:validate_text(raw) for s,raw in contents}
    questions=gold['questions']
    if len(questions)!=40 or len({q['id'] for q in questions})!=40 or len({q['question'] for q in questions})!=40:raise ValueError('Frozen question count/uniqueness')
    if gold['corpus_version']!=manifest['corpus_version']:raise ValueError('Frozen corpus changed')
    if set(Counter(q['topic'] for q in questions[:32]).values())!={4}:raise ValueError('Unbalanced first 32 questions')
    for q in questions:
        if not q['points'] and q['answerability']!='insufficient':raise ValueError('Answerable question without necessary points')
        for point in q['points']:
            for span in point['supports']:
                text=texts[span['source_id']];a,b=span['start_char'],span['end_char']
                if text[a:b]!=span['quote'] or not 0<=a<b<=len(text):raise ValueError('Frozen source excerpt mismatch')
                if text.count('\n',0,a)+1!=span['start_line'] or text.count('\n',0,b-1)+1!=span['end_line']:raise ValueError('Frozen source line mismatch')
    print(json.dumps({'status':'DEPTH_GOLD_VALID','questions':40,'points':sum(len(q['points']) for q in questions),
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'model_calls':0,'network_requests':0}))


if __name__=='__main__':check()
