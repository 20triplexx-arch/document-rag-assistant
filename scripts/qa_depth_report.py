"""Offline audit of preserved answers. Never creates a provider or calls a model."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study_rag.answer_schema import validate_v2
from study_rag.core import verified_corpus, validate_text
from study_rag.qa_experiment import ExperimentLedger
from study_rag.rag import visible_prose
from study_rag.qa_retrieval import body_mask

OUT = ROOT / 'output/qa-depth-20261015-v1'
DATA = ROOT / 'data/qa-20261014-v1'


def median(values):
    return statistics.median(values) if values else None


def main():
    _, _, _, verified = verified_corpus(DATA, DATA / 'index.sqlite3')
    originals = {source.source_id: validate_text(raw) for source, raw in verified}
    masks = {source.source_id: body_mask(originals[source.source_id], source.path.endswith('.mdx'))
             for source, _ in verified}
    report = {'origin': 'offline structural/source audit; semantic judgments remain separate; not human accuracy',
              'model_calls': 0, 'network_requests': 0, 'phases': {},
              'default_changed': False, 'quality_gate_passed': False, 'full_speed_gate_passed': False}
    reviews = OUT / 'reviews/citation-index-review-v2/qwen3.8-max-0902/compare-accept1/deepseek-flash'
    by_question = {}
    for path in reviews.glob('*.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        by_question[row['question_id']] = {key: row.get(key) for key in ('state', 'passed', 'rationale', 'error_type')}
    for phase in ('baseline', 'compare-accept1', 'http-flash-final'):
        report['phases'][phase] = {}
        for directory in sorted((OUT / phase).iterdir()):
            if not directory.is_dir():
                continue
            rows, first, total = [], [], []
            for path in sorted(directory.glob('*.json')):
                record = json.loads(path.read_text(encoding='utf-8'))
                result, q = record['result'], record['scenario']
                check = 'not_returned'
                if result.get('status') == 'CITED_DRAFT':
                    try:
                        for evidence in result['evidence']:
                            original = originals[evidence['source_id']]
                            start, end = evidence['start_char'], evidence['end_char']
                            raw = original[start:end]
                            projected = raw if evidence.get('content_type') == 'code' else visible_prose(
                                raw, masks[evidence['source_id']][start:end])
                            if raw != evidence['text'] or projected != evidence['context_text']:
                                raise ValueError('Evidence differs from verified original')
                        validate_v2(json.dumps(result['answer'], ensure_ascii=False), result['evidence'])
                        check = 'passed'
                    except (ValueError, KeyError, TypeError):
                        check = 'failed'
                row = {'question_id': q['id'], 'question': q['question'], 'status': result['status'],
                       'failure_stage': result.get('failure_stage'), 'error_type': result.get('error_type'),
                       'offline_source_check': check, 'support_verified': False,
                       'record': path.relative_to(ROOT).as_posix(),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                if phase == 'compare-accept1' and directory.name == 'deepseek-flash':
                    row['historical_auxiliary_review'] = by_question.get(q['id'], {'state': 'not_completed'})
                rows.append(row)
                if check == 'passed':
                    if record.get('client_first_block_seconds') is not None:
                        first.append(record['client_first_block_seconds'])
                    if record.get('client_total_seconds') is not None:
                        total.append(record['client_total_seconds'])
            report['phases'][phase][directory.name] = {
                'attempts': len(rows), 'statuses': dict(Counter(row['status'] for row in rows)),
                'offline_source_checks': dict(Counter(row['offline_source_check'] for row in rows)),
                'structural_samples_first_block_median_seconds': median(first),
                'structural_samples_total_median_seconds': median(total),
                'timing_scope': 'same-pack generation only' if phase.startswith('compare') else 'authenticated HTTP stream',
                'semantic_eligibility_not_implied': True, 'questions': rows}
    ledger = ExperimentLedger(OUT / 'ledger.sqlite3')
    report['ledger'] = ledger.summary()
    with ledger.connect() as db:
        report['incremental_flash_calls'] = db.execute('SELECT count(*) FROM flash_spend').fetchone()[0]
        report['incremental_flash_limit_cny'] = json.loads(db.execute(
            "SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()[0])['limit_micros'] / 1_000_000
    report['incremental_cost_basis'] = 'conservative peak price with all input as cache miss; not an invoice'
    report['alibaba_free_only_verified'] = False
    report['completion_limits'] = [
        'Flash frozen output has one invalid JSON response; 40/40 gate failed.',
        'Independent semantic review incomplete; no 38/40 or zero-serious-error claim.',
        'Eight final HTTP samples, one repetition; fewer than twenty eligible paired questions.',
        'Paid Pro/Max stopped by user; no further Pro/Max calls are authorized.',
        'Bailian console unavailable; free quota and stop-on-exhaustion not confirmed.']
    report['source_assisted_review'] = 'reviews/qa-depth-source-review-2026-10-15.json'
    log_path = OUT / 'verify-final-flash-only.log'
    log = log_path.read_text(encoding='utf-8', errors='replace')
    report['engineering_validation'] = {
        'backend_tests': int(re.search(r'Ran (\d+) tests', log)[1]),
        'frontend_tests': int(re.search(r'ℹ pass (\d+)', log)[1]),
        'offline_log': log_path.relative_to(ROOT).as_posix()}
    report['final_code_sha256'] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (ROOT / 'study_rag').glob('*.py')}
    report['post_measurement_changes'] = ('Only disabled-model transport guard and experiment spending/fail-fast '
                                          'controls; Flash QA prompt and retrieval unchanged.')
    dest = OUT / 'final-summary.json'
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(dest), 'incremental_flash_calls': report['incremental_flash_calls'],
                      'cost_upper_bound_cny': report['ledger']['resumed_flash_cost_bound_cny'],
                      'model_calls': 0, 'quality_gate_passed': False}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
