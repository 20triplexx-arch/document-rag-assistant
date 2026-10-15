"""Quiet local retrieval benchmark; every sample rechecks all raw/index bytes."""
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.qa_retrieval_v4 import retrieve_v4


def distribution(values):
    ordered=sorted(values)
    return {'n':len(values),'median_seconds':statistics.median(values),
            'p95_seconds':ordered[math.ceil(.95*len(ordered))-1],'max_seconds':max(values)}


def main():
    data=ROOT/'data/qa-overhaul-20261015-v2';out=ROOT/'output/qa-overhaul-20261015-v2'
    questions=json.loads((ROOT/'evals/qa-overhaul-speed-v1.json').read_text(encoding='utf-8'))['questions']
    start=time.perf_counter();retrieve_v4(data,data/'index.sqlite3','解释工具调用与运行时数据的区别。')
    cold=time.perf_counter()-start;rows=[]
    for repetition in range(3):
        for q in questions:
            start=time.perf_counter();pack=retrieve_v4(data,data/'index.sqlite3',q['question'],q.get('book'))
            rows.append({'id':q['id'],'repetition':repetition,'seconds':time.perf_counter()-start,
                         'evidence':len(pack['evidence']),'source_verified':pack['source_verified']})
    result={'cold_start_seconds':cold,'all_warm':distribution([r['seconds'] for r in rows]),
            'first_query_per_question':distribution([r['seconds'] for r in rows if r['repetition']==0]),
            'repeated_queries':distribution([r['seconds'] for r in rows if r['repetition']>0]),'rows':rows,
            'model_calls':0,'network_requests':0,
            'conditions':'Separate process after HTTP trials; CPU E5 with four torch threads. Corpus/index fully reread per sample. Cold start excluded; repeated queries use cached query embeddings.'}
    (out/'retrieval-benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)


if __name__=='__main__':main()
