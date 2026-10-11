"""检索评测契约与评分测试：合成原文，不访问模型、真实语料或账号。"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import starter
from study_rag.evaluation import (
    Dataset, Point, Question, Span, evaluate, score_question, summarize, validate_dataset,
)
from study_rag.mdx import mdx_mask
from study_rag.rag import RETRIEVER_VERSION, prose_mask


TEXT = '# Chapter\nFirst supporting fact.\nAlternative supporting fact.\nSecond necessary fact.\nInstall dependencies.\nUnlabelled background.\n'


def annotation(quote, source='a', text=TEXT):
    start = text.index(quote)
    end = start + len(quote)
    return Span(source_id=source, start_char=start, end_char=end,
                start_line=text.count('\n', 0, start) + 1,
                end_line=text.count('\n', 0, end-1) + 1, quote=quote, rationale='Manual source annotation.')


def question(*, answerability='answerable'):
    return Question(id='S01', group='objective', split='dev', category='single',
        question='What does the agent do?', book='a', required_books=['a'],
        answerability=answerability,
        points=[Point(id='p1', answer='First fact', supports=[annotation('First supporting fact.'),
                    annotation('Alternative supporting fact.')]),
                Point(id='p2', answer='Second fact', supports=[annotation('Second necessary fact.')])],
        distractors=[annotation('Install dependencies.')], missing_information=[], review_scope=None)


def evidence(quote, *, source='a', text=TEXT, context=None, start=None, end=None):
    s = annotation(quote, source, text)
    return dict(source_id=source, book=source, start_char=s.start_char if start is None else start,
                end_char=s.end_char if end is None else end, context_text=quote if context is None else context,
                source_url='https://github.com/example/repo/blob/fixed/doc.md',
                line_url=f'https://github.com/example/repo/blob/fixed/doc.md#L{s.start_line}', score=1.0)


def fixture_dataset():
    records=[]
    held={'S04','S08','S12','S16','S20','C27','C28','R32','R33','G40'}
    for prefix,low,high,category in [('S',1,20,'single'),('C',21,28,'cross'),
                                    ('R',29,34,'paraphrase'),('G',35,40,'gap')]:
        for n in range(low,high+1):
            q=question().model_dump()
            qid=f'{prefix}{n:02}'
            book='abcde'[(n-1)//4] if prefix=='S' else 'a'
            q.update(id=qid, group=qid, question=f'Question {qid}', category=category,
                     split='holdout' if qid in held else 'dev', book=book, required_books=[book])
            for p in q['points']:
                for s in p['supports']: s['source_id']=book
            q['distractors'][0]['source_id']=book
            if prefix=='C':
                q.update(book=None, required_books=['a','b'])
                q['points'][1]['supports'][0]['source_id']='b'
            if prefix=='G':
                q.update(answerability='partial' if n<38 else 'insufficient',
                         missing_information=['Uncollected run log.'],
                         review_scope=dict(source_ids=['a'],checked_content='Full reference.',
                                           absence_basis='No run log in the fixed reference.'))
                if n>=38: q['points']=[]
            records.append(q)
    return Dataset(schema_version=1,dataset_version='agent-learning-v1',annotated_on='2026-10-11',
                   annotation_method='Manual.',corpus_version='0'*64,documents=5,
                   baseline_chunks=5,questions=[Question.model_validate(q) for q in records])


class ScoringTests(TestCase):
    def setUp(self):
        self.texts={'a':TEXT,'b':TEXT}
        self.masks={k:prose_mask(v) for k,v in self.texts.items()}

    def score(self, items, q=None):
        return score_question(q or question(),items,self.texts,self.masks)

    def test_alternative_and_partial_support(self):
        r=self.score([evidence('Alternative supporting fact.')])
        self.assertEqual(r['covered_points'],['p1'])
        self.assertEqual(r['point_coverage'],0.5)
        self.assertFalse(r['complete'])
        complete=self.score([evidence('Alternative supporting fact.'), evidence('Second necessary fact.')])
        self.assertTrue(complete['complete'])

    def test_source_position_and_model_context_are_all_required(self):
        s=annotation('First supporting fact.')
        invalid=[evidence(s.quote,source='b'),evidence(s.quote,start=s.start_char+1),
                 evidence(s.quote,end=s.end_char-1),evidence(s.quote,context='Only a heading.')]
        for item in invalid:
            with self.subTest(item=item):
                self.assertEqual(self.score([item])['covered_points'],[])
        # 相同文字出现在正文另一位置，仍不能代替标注位置。
        self.assertEqual(self.score([evidence(s.quote,start=s.end_char,end=s.end_char+100)])['covered_points'],[])

    def test_duplicate_does_not_add_point_or_evidence_credit(self):
        item=evidence('First supporting fact.')
        r=self.score([item,item])
        self.assertEqual(r['covered_points'],['p1'])
        self.assertTrue(r['evidence'][1]['duplicate'])
        self.assertEqual(summarize([r])['unique_evidence'],1)

    def test_distractor_and_unjudged_are_distinct(self):
        r=self.score([evidence('Install dependencies.'),evidence('Unlabelled background.')])
        self.assertEqual([e['judgment'] for e in r['evidence']],['distractor','unjudged'])
        summary=summarize([r])
        self.assertEqual(summary['distractor_evidence_ratio'],0.5)
        self.assertEqual(summary['unjudged_evidence_ratio'],0.5)

    def test_one_evidence_can_have_support_and_distractor(self):
        r=self.score([evidence('First supporting fact.',context=TEXT,start=0,end=len(TEXT))])
        self.assertEqual(r['evidence'][0]['judgment'],'support_and_distractor')
        self.assertEqual(summarize([r])['distractor_evidence'],1)

    def test_masked_code_and_mdx_cannot_count_even_if_context_forged(self):
        for text in ['# Doc\n```python\nHidden supporting fact.\n```\nVisible body.\n',
                     '# Doc\n<Video\n  description="Hidden supporting fact."\n/>\nVisible body.\n']:
            q=question()
            q.points=[Point(id='p1',answer='Hidden fact',supports=[annotation('Hidden supporting fact.',text=text)])]
            q.distractors=[]
            r=score_question(q,[evidence('Hidden supporting fact.',text=text)],
                             {'a':text},{'a':prose_mask(mdx_mask(text))})
            self.assertEqual(r['covered_points'],[])
        q=question()
        # 可见 HTML 加粗、空白变化与已有 Prompt 正规化方式一致。
        r=self.score([evidence('First supporting fact.',context='<strong>First</strong> supporting   fact.')],q)
        self.assertEqual(r['covered_points'],['p1'])

    def test_gap_results_never_claim_complete_support_or_refusal(self):
        q=question(answerability='partial')
        q.category='gap'
        q.missing_information=['Actual run log.']
        partial=self.score([evidence('First supporting fact.'),evidence('Second necessary fact.')],q)
        self.assertIsNone(partial['complete'])
        q.answerability='insufficient'
        q.points=[]
        absent=self.score([evidence('Install dependencies.')],q)
        summary=summarize([partial,absent])
        self.assertEqual(summary['answerable_questions'],0)
        self.assertIsNone(summary['support_point_coverage'])
        self.assertEqual(summary['gap_covered_known_points'],2)
        self.assertEqual(summary['gap_distractor_evidence'],1)


class DatasetTests(TestCase):
    def setUp(self):
        self.dataset=fixture_dataset()
        self.manifest={'schema_version':1,'corpus_version':'0'*64}
        self.texts={s:TEXT for s in 'abcde'}
        self.masks={s:prose_mask(TEXT) for s in 'abcde'}
        self.sources={s:SimpleNamespace(book=s,path='doc.md') for s in 'abcde'}

    def validate(self,dataset=None):
        validate_dataset(dataset or self.dataset,self.manifest,self.texts,self.sources,self.masks)

    def test_valid_40_questions_and_corpus_version_mismatch(self):
        self.validate()
        self.dataset.corpus_version='1'*64
        with self.assertRaisesRegex(ValueError,'语料版本'):self.validate()

    def test_exact_quote_source_position_line_and_visible_annotation(self):
        for field,value in [('quote','Edited answer'),('source_id','missing'),('start_char',9999),('start_line',99)]:
            d=deepcopy(self.dataset)
            setattr(d.questions[0].points[0].supports[0],field,value)
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(d)
        self.masks['a']=' '*len(TEXT)
        with self.assertRaisesRegex(ValueError,'遮罩'):self.validate()

    def test_count_group_split_and_cross_collection_requirements(self):
        mutations=[lambda d:d.questions.pop(),
                   lambda d:setattr(d.questions[0],'group','S04'),
                   lambda d:setattr(d.questions[20].points[1].supports[0],'source_id','a'),
                   lambda d:setattr(d.questions[0],'id','S02')]
        for mutate in mutations:
            d=deepcopy(self.dataset)
            mutate(d)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.validate(d)

    def test_check_only_never_retrieves_and_dev_does_not_expose_holdout(self):
        loaded=(self.dataset,'hash',self.manifest,[],self.sources,self.texts,self.masks)
        def pack(data,index,question,book,per_book):
            self.assertEqual(per_book,2)
            return dict(corpus_version='0'*64,retriever=RETRIEVER_VERSION,
                        evidence=[],books_without_match=['a'])
        with patch('study_rag.evaluation.load_dataset',return_value=loaded), \
             patch('study_rag.evaluation.retrieve',side_effect=pack) as retrieval:
            checked=evaluate(Path('set.json'),Path('data'),check_only=True)
            retrieval.assert_not_called()
            self.assertEqual(checked['checked_questions'],40)
            report=evaluate(Path('set.json'),Path('data'))
        self.assertEqual(retrieval.call_count,30)
        self.assertEqual(report['summary']['questions'],30)
        self.assertEqual(report['summary']['complete_questions'],0)
        self.assertTrue(all(q['split']=='dev' for q in report['results']))
        self.assertNotIn('Question S04',json.dumps(report))
        self.assertEqual(report['model_calls'],0)

    def test_low_score_cli_success_and_validation_failure_exit_nonzero(self):
        with TemporaryDirectory() as root, redirect_stdout(io.StringIO()):
            args=['evaluate','--data-dir',root,'--output-dir',root]
            with patch('starter.evaluate',return_value={'status':'EVALUATED','summary':{'complete_questions':0}}), \
                 patch('starter.DeepSeekModel',side_effect=AssertionError('No model allowed')):
                self.assertEqual(starter.main(args),0)
            with patch('starter.evaluate',side_effect=ValueError('题集与语料版本不匹配')):
                self.assertEqual(starter.main(args),1)
            reports=[json.loads(p.read_text(encoding='utf-8')) for p in Path(root).glob('evaluate_*.json')]
            self.assertEqual({r['status'] for r in reports},{'EVALUATED','FAILED'})
            self.assertTrue(all(r['model_calls']==0 for r in reports))

    def test_changed_pack_or_evidence_cap_rejected(self):
        loaded=(self.dataset,'hash',self.manifest,[],self.sources,self.texts,self.masks)
        packs=[dict(corpus_version='1'*64,retriever=RETRIEVER_VERSION,evidence=[]),
               dict(corpus_version='0'*64,retriever='changed',evidence=[]),
               dict(corpus_version='0'*64,retriever=RETRIEVER_VERSION,
                    evidence=[evidence('First supporting fact.')]*3)]
        for pack in packs:
            with self.subTest(pack=pack),patch('study_rag.evaluation.load_dataset',return_value=loaded), \
                 patch('study_rag.evaluation.retrieve',return_value=pack),self.assertRaises(ValueError):
                evaluate(Path('set.json'),Path('data'))
