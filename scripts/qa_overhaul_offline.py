"""Previously exposed regression only. Frozen new holdouts are never used to tune."""
from pathlib import Path
import argparse
import json
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.evaluation import load_dataset,DEFAULT_DATASET,score_question,summarize
from study_rag.qa_evaluation import load_qa_dataset,QA_DATASET,score_qa,qa_summary
from study_rag.qa_retrieval_v4 import retrieve_v4
from study_rag.answer_schema import normalize_with_positions

DATA=ROOT/'data/qa-overhaul-20261015-v2';OUT=ROOT/'output/qa-overhaul-20261015-v2'


def coverage(question,evidence):
    def supported(span,item):
        if span['source_id']!=item['source_id'] or item['start_char']>span['start_char'] or item['end_char']<span['end_char']:return False
        if span['kind']=='code' and item.get('content_type')!='code':return False
        if span['kind']=='prose' and item.get('content_type')=='code':return False
        quote=normalize_with_positions(span['quote'])[0];body=normalize_with_positions(item['context_text'])[0]
        return bool(quote) and quote in body
    covered=[]
    for point in question['points']:
        hits=[any(supported(span,item) for item in evidence) for span in point['supports']]
        if all(hits) if point.get('coverage','any')=='all' else any(hits):covered.append(point['id'])
    return covered


def run(args):
    old=load_dataset(DEFAULT_DATASET,ROOT/'data/courses-cases-20261010-v1')
    new=load_qa_dataset(QA_DATASET,ROOT/'data/qa-20261014-v1')
    oldq=[q for q in old[0].questions if q.split=='dev'];newq=[q for q in new[0].questions if q.split=='dev']
    exposed=json.loads((ROOT/'evals/qa-depth-v1.json').read_text(encoding='utf-8'))['questions']
    results={'old':[],'new':[],'exposed':[],'old_extra':[],'new_extra':[]};timings=[]
    groups=[('old',oldq),('new',newq),('exposed',exposed)]
    if args.all_exposed:
        groups.extend([('old_extra',[q for q in old[0].questions if q.split!='dev']),
                       ('new_extra',[q for q in new[0].questions if q.split!='dev'])])
    for name,questions in groups:
        for q in questions:
            identifier=q['id'] if isinstance(q,dict) else q.id
            if args.ids and identifier not in args.ids.split(','):continue
            question=q['question'] if isinstance(q,dict) else q.question
            book=q.get('book') if isinstance(q,dict) else q.book
            started=time.perf_counter();pack=retrieve_v4(DATA,DATA/'index.sqlite3',question,book,trace=True)
            elapsed=time.perf_counter()-started;timings.append(elapsed)
            if name.startswith('old'):row=score_question(q,[e for e in pack['evidence'] if e['content_type']!='code'],old[5],old[6])
            elif name.startswith('new'):row=score_qa(q,pack['evidence'],new[5],new[6])
            else:
                covered=coverage(q,pack['evidence']);row={'id':identifier,'question':question,'covered_points':covered,'expected_points':len(q['points']),
                                                      'complete':len(covered)==len(q['points']),'evidence':pack['evidence']}
            row.update(trace=pack['trace'],elapsed_seconds=elapsed)
            results[name].append(row)
            print(name,identifier,len(row['covered_points']),row['expected_points'],round(elapsed,3),flush=True)
            if args.limit and sum(len(rows) for rows in results.values())>=args.limit:break
        if args.limit and sum(len(rows) for rows in results.values())>=args.limit:break
    old_summary=summarize(results['old']) if results['old'] else {}
    new_summary=qa_summary(results['new']) if results['new'] else {}
    result={'model_calls':0,'network_requests':0,'old':old_summary,'new':new_summary,'results':results,
            'warm_median_seconds':statistics.median(timings[1:]) if len(timings)>1 else None,
            'warm_p95_seconds':sorted(timings[1:])[int((len(timings)-2)*.95)] if len(timings)>1 else None,
            'cold_seconds':timings[0] if timings else None,
            'gates':{'old_45_of_49':old_summary.get('covered_support_points',0)>=45,'new_70_of_72':new_summary.get('covered',0)>=70}}
    path=OUT/(args.label+'.json');path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--label',default='offline-round1')
    p.add_argument('--ids');p.add_argument('--limit',type=int);p.add_argument('--all-exposed',action='store_true');run(p.parse_args())
