"""Aggregate immutable trial records, manual source review and preservation audit."""
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.qa_experiment import ExperimentLedger
from study_rag.core import load_corpus
from scripts.qa_overhaul_offline import coverage

OUT=ROOT/'output/qa-overhaul-20261015-v2'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def stat(values):
    values=sorted(v for v in values if v is not None)
    return {'n':len(values),'median':statistics.median(values) if values else None,
            'p95':values[math.ceil(.95*len(values))-1] if values else None}


def phase(name):
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((OUT/name).glob('*.json'))]
    good=[r for r in rows if r['result']['status']=='CITED_DRAFT']
    return {'n':len(rows),'statuses':dict(Counter(r['result']['status'] for r in rows)),
        'answer_states':dict(Counter((r['result'].get('answer') or {}).get('status','failed') for r in rows)),
        'http_total':stat([r['client_total_seconds'] for r in good]),
        'http_first_validated_block':stat([r['client_first_block_seconds'] for r in good]),
        'server':{key:stat([r['result'].get('timings',{}).get(key) for r in good]) for key in
                  ['retrieval_seconds','first_content_seconds','first_validated_block_seconds','generation_seconds','validation_seconds','total_seconds']},
        'failed':[{'id':r['scenario']['id'],'repetition':r['repetition'],'status':r['result']['status'],
                   'stage':r['result'].get('failure_stage'),'error':r['result'].get('error_type')} for r in rows]},rows


def main():
    review=json.loads((OUT/'acceptance-source-review.json').read_text(encoding='utf-8'))
    regress=json.loads((OUT/'offline-final.json').read_text(encoding='utf-8'))
    retrieval=json.loads((OUT/'retrieval-benchmark.json').read_text(encoding='utf-8'))
    phases={};records={}
    for name in ['speed-before','dev-round1','acceptance-final','speed-after-final']:phases[name],records[name]=phase(name)
    pairs=defaultdict(lambda:defaultdict(list))
    for name in ['speed-before','speed-after-final']:
        for r in records[name]:pairs[r['scenario']['id']][name].append(r)
    pair_rows=[]
    for identifier,values in sorted(pairs.items()):
        complete=all(len(values[name])==3 and all(r['result']['status']=='CITED_DRAFT' for r in values[name]) for name in ['speed-before','speed-after-final'])
        pair_rows.append({'id':identifier,'six_structurally_complete':complete,
            **{name:stat([r['client_total_seconds'] for r in values[name] if r['result']['status']=='CITED_DRAFT']) for name in values}})
    eligible=[r for r in pair_rows if r['six_structurally_complete']]
    paired_before=statistics.median(r['speed-before']['median'] for r in eligible)
    paired_after=statistics.median(r['speed-after-final']['median'] for r in eligible)
    gold=json.loads((ROOT/'evals/qa-overhaul-v1.1.json').read_text(encoding='utf-8'))
    attribution=[]
    for row,record,q in zip(review['rows'],records['acceptance-final'],gold['questions']):
        retrieved=coverage(q,record['result']['evidence']);covered={p['id'] for p in row['points'] if p['covered']}
        expected={p['id'] for p in q['points']}
        attribution.append({'id':q['id'],'material_missing':[],
            'retrieval_missing_gold_points':sorted(expected-set(retrieved)),
            'generation_missing_retrieved_points':sorted(set(retrieved)-covered),
            'citation_support_failure':not row['citation_support_pass'],'focus_failure':not row['focus_pass'],
            'repetition_observed':any(word in row['reason'] for word in ['重复','复述','反复','再次']),
            'reason':row['reason'],'gold_scope_note':'Exact frozen span coverage; equivalent unannotated evidence is not automatically scored as a failure of meaning.'})
    manifest,contents=load_corpus(ROOT/'data/qa-overhaul-20261015-v2');raws={s.source_id:raw for s,raw in contents}
    old={}
    for folder in ['courses-cases-20261010-v1','qa-20261014-v1']:
        previous,docs=load_corpus(ROOT/'data'/folder)
        old[folder]={'files':len(docs),'all_ids_and_bytes_preserved':all(raws.get(s.source_id)==raw for s,raw in docs),'corpus_version':previous['corpus_version']}
    baseline=json.loads((OUT/'baseline-contract.json').read_text(encoding='utf-8'))
    historical_ledgers={name:{'initial_sha256':sha,'current_sha256':digest(ROOT/name),'unchanged':digest(ROOT/name)==sha}
                        for name,sha in baseline['ledgers'].items() if 'qa-depth-' not in name}
    ledger=ExperimentLedger(ROOT/'output/qa-depth-20261015-v1/ledger.sqlite3')
    with ledger.connect() as db:
        calls=db.execute("SELECT provider,model,usage,state FROM calls WHERE call_key LIKE 'overhaul/%'").fetchall()
        spending=db.execute("SELECT sum(coalesce(settled_micros,reserved_micros)) FROM flash_spend WHERE call_key LIKE 'overhaul/%'").fetchone()[0]
        authorizations=db.execute('SELECT name,limit_micros,reason FROM spend_authorizations ORDER BY id').fetchall()
    cost={'total_cny_bound_including_prior':ledger.summary()['resumed_flash_cost_bound_cny'],'this_round_cny_bound':spending/1e6,
        'previous_cny_bound':round(ledger.summary()['resumed_flash_cost_bound_cny']-spending/1e6,6),
        'limit_cny':5,'this_round_calls':len(calls),'providers_models':dict(Counter(provider+'/'+model for provider,model,_,_ in calls)),
        'this_round_input_tokens':sum((json.loads(u or '{}').get('prompt_tokens') or 0) for _,_,u,_ in calls),
        'this_round_output_tokens':sum((json.loads(u or '{}').get('output_tokens') or 0) for _,_,u,_ in calls),
        'unresolved':ledger.summary()['unresolved'],'authorizations':authorizations,
        'basis':'Conservative peak input cache-miss/output rates; not an invoice. Unknown usage retains full reservation. No Pro/Max/Bailian/judge calls this round.'}
    primary_topics={}
    for topic in review['by_topic']:
        primary=[row for row in review['rows'][:32] if row['topic']==topic]
        expected=sum(len(row['points']) for row in primary);covered=sum(sum(p['covered'] for p in row['points']) for row in primary)
        primary_topics[topic]={'questions':len(primary),'points':expected,'covered':covered,'coverage':covered/expected,'passed':sum(row['pass'] for row in primary)}
    gates={'legacy_45_of_49':regress['gates']['old_45_of_49'],'development_70_of_72':regress['gates']['new_70_of_72'],
        'frozen_structure_40_of_40':review['structure_and_source']==40,'frozen_quality_38_of_40':review['content_and_focus_pass']>=38,
        'points_95_percent':review['point_coverage']>=.95,'each_topic_90_percent':all(t['coverage']>=.9 for t in primary_topics.values()),
        'serious_errors_zero':review['serious_errors']==0,
        'warm_retrieval_p95_500ms':retrieval['all_warm']['p95_seconds']<=.5,
        'validated_first_block_median_2_5s':phases['acceptance-final']['http_first_validated_block']['median']<=2.5}
    result={'decision':'KEEP_PREVIOUS_DEFAULT','default_corpus':'courses-cases-20261010-v1','default_model':'deepseek-flash',
        'candidate_corpus':manifest['corpus_version'],'gates':gates,'cost':cost,
        'coverage':json.loads((ROOT/'data/qa-overhaul-20261015-v2/coverage.json').read_text(encoding='utf-8')),
        'preservation':{'snapshots':old,'previous_ledgers':historical_ledgers,'account_and_discussion_databases':'No evaluation uses production accounts; all trials use phase-specific isolated stores.'},
        'regression':{k:v for k,v in regress.items() if k!='results'},'acceptance':{k:v for k,v in review.items() if k!='rows'},
        'primary_topic_coverage':primary_topics,'cross_scenario_ids':[row['id'] for row in review['rows'][32:]],
        'phases':phases,'retrieval_benchmark':retrieval,
        'paired_speed':{'questions':20,'repetitions_per_side':3,'six_structurally_complete_questions':len(eligible),
            'quality_valid_pairs_at_most':len(eligible),'quality_reviewed_pairs':0,'declared_25_percent_speedup':False,
            'descriptive_before_median':paired_before,'descriptive_after_median':paired_after,
            'descriptive_change_percent':(paired_after/paired_before-1)*100,'rows':pair_rows,
            'conditions':'Before=301-file v3 baseline code saved before changes; after=2164-file v4.1 candidate. Baseline overlapped public-source downloads, not vector construction. Cold requests retained. These 19 pairs only satisfy structural completeness and are not a quality-valid sample.'},
        'failure_attribution':attribution,'frozen_holdout_state':'Retired to development regression after this report. Any tuning on these answers requires forty newly frozen source-annotated questions.',
        'local_application':json.loads((OUT/'local-application-check.json').read_text(encoding='utf-8')) if (OUT/'local-application-check.json').exists() else None,
        'static_analysis_audit':json.loads((OUT/'static-analysis-gaps.json').read_text(encoding='utf-8')) if (OUT/'static-analysis-gaps.json').exists() else None,
        'review_origin':'Codex source-assisted review; no independent judge and not human accuracy','public_support_verified':False}
    path=OUT/'delivery-report.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'decision':result['decision'],'gates':gates,'cost':cost,'paired_speed':{k:v for k,v in result['paired_speed'].items() if k!='rows'}},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
