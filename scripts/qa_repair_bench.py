"""Fixed 20 questions x 3, plus concurrency 2. No generation and no network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import math
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus,corpus_catalog
from study_rag.qa_retrieval_v5 import indexed_materials,retrieve_v5
from study_rag.parent_vectors import parent_index,query_vector

DATA=ROOT/'data/qa-overhaul-20261015-v2';OUT=ROOT/'output/qa-repair-20261015-v5'


def metrics(rows):
    values=sorted(r['seconds'] for r in rows)
    return {'samples':len(values),'median_ms':statistics.median(values)*1000,
            'p95_ms':values[math.ceil(.95*len(values))-1]*1000,'max_ms':max(values)*1000}


def main():
    dest=OUT/'retrieval-benchmark-final.json'
    if dest.exists():raise SystemExit('Fixed final measurements already exist; preserve them.')
    dataset=ROOT/'evals/qa-overhaul-speed-v1.json';questions=json.loads(dataset.read_text(encoding='utf-8'))['questions'];assert len(questions)==20
    cold=time.perf_counter();manifest,chunks,_,contents=verified_corpus(DATA,DATA/'index.sqlite3')
    mat=indexed_materials(manifest,contents,chunks,corpus_catalog(manifest))
    parent_index(manifest['corpus_version'],mat['descriptors']);query_vector('初始化本地检索',2)
    cold_seconds=time.perf_counter()-cold
    rows=[]
    def sample(q,repetition,concurrent=False):
        started=time.perf_counter();pack=retrieve_v5(DATA,DATA/'index.sqlite3',q['question'],q.get('book'))
        assert pack['source_verified']
        return {'id':q['id'],'repetition':repetition,'concurrent':concurrent,'seconds':time.perf_counter()-started,
                'parts':pack['retrieval_timings'],'evidence_count':len(pack['evidence'])}
    for repetition in range(3):
        for q in questions:rows.append(sample(q,repetition))
    with ThreadPoolExecutor(max_workers=2) as pool:concurrent=list(pool.map(lambda q:sample(q,0,True),questions))
    result={'model_calls':0,'network_requests':0,'dataset_sha256':hashlib.sha256(dataset.read_bytes()).hexdigest(),
        'code_contract':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'study_rag').glob('*.py'))+list((ROOT/'study_rag').glob('*.json'))},
        'cold_start_seconds':cold_seconds,'warm':metrics(rows),'new_query':metrics([r for r in rows if r['repetition']==0]),
        'repeated_query':metrics([r for r in rows if r['repetition']>0]),'concurrency_2':metrics(concurrent),'measurements':rows+concurrent}
    result['warm_p95_gate']=result['warm']['p95_ms']<=500
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'measurements','code_contract'}},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
