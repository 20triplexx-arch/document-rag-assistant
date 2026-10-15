"""V5 behavior tests with synthetic sources and fake transport only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile
import unittest

from study_rag.core import prepare_corpus, build_index, verified_corpus, CorpusError
from study_rag.static_facts import bindings, provenance
from study_rag.provenance import named_symbols
from study_rag.facet_contract import FacetContract
from study_rag.qa_retrieval_v5 import retrieve_v5
from study_rag.conversation import prepare_context
from study_rag.qa_experiment import ExperimentLedger, ValidationStopped
from test_overhaul import fixture


class ObjectTests(unittest.TestCase):
    def test_concept_word_does_not_activate_an_unrequested_case(self):
        from study_rag.qa_retrieval_v5 import indexed_materials
        from study_rag.core import corpus_catalog
        source,raw,catalog=fixture(body={'nbformat':4,'cells':[{'cell_type':'code','source':'def embed(texts):\n    return [[1, 2]]\n'}]})
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);prepare_corpus([source],data,lambda _:raw,catalog=catalog);build_index(data,data/'index.sqlite3')
            snapshot=verified_corpus(data,data/'index.sqlite3')
            mat=dict(indexed_materials(snapshot[0],snapshot[3],snapshot[1],corpus_catalog(snapshot[0])),case_roots=('tutorials/memory_agent',))
            with patch('study_rag.qa_retrieval_v5.indexed_materials',return_value=mat),patch('study_rag.qa_retrieval_v5.semantic_parent_ranks',return_value=[]):
                pack=retrieve_v5(data,data/'index.sqlite3','记忆文档的 embed 返回什么？',book='course',trace=True,_verified=snapshot)
            self.assertEqual(pack['trace']['case_roots'],[]);self.assertTrue(pack['question_plan']['needs_code'])
            self.assertEqual(pack['object_anchors'][0]['symbol'],'embed')

    def test_markdown_and_notebook_fences_keep_independent_names_and_offsets(self):
        code='```python\nfrom external import helper\ndef same():\n    return helper()\n```\n\n```python\ndef helper():\n    return 3\ndef same():\n    return helper()\n```\n'
        graph=bindings('lesson.mdx',code.encode())
        same=[r for r in graph['definitions'] if r['name']=='same']
        self.assertEqual(len(same),2);self.assertNotEqual(same[0]['scope_id'],same[1]['scope_id'])
        source=fixture()[0]
        from dataclasses import replace
        s=replace(source,path='lesson.mdx')
        first=provenance(s,code.encode(),same[0]['start_char'],same[0]['end_char'])['python']
        self.assertIn('helper',first['module_imported_names']);self.assertNotIn('helper',first['module_local_names'])
        self.assertEqual(code[same[0]['start_char']:same[0]['end_char']],'def same():\n    return helper()\n')
        nb={'nbformat':4,'cells':[{'cell_type':'markdown','source':code}]}
        self.assertEqual(bindings('lesson.ipynb',json.dumps(nb).encode())['definitions'][0]['cell_index'],1)

    def test_qualified_method_enables_code_without_source_keyword(self):
        source,raw,catalog=fixture(body={'nbformat':4,'cells':[{'cell_type':'code','source':'class Planner:\n    def plan(self):\n        return []\n'}]})
        self.assertIn('Planner.plan',named_symbols('请解释 Planner.plan。'))
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);prepare_corpus([source],data,lambda _:raw,catalog=catalog);build_index(data,data/'index.sqlite3')
            with patch('study_rag.qa_retrieval_v5.semantic_parent_ranks',return_value=[]):
                # Do not infer a course restriction merely from the familiar name.
                pack=retrieve_v5(data,data/'index.sqlite3','Planner.plan 做什么？',book='course')
            self.assertTrue(pack['question_plan']['needs_code']);self.assertTrue(any(e['content_type']=='code' for e in pack['evidence']))
            self.assertEqual(pack['object_anchors'][0]['symbol'],'Planner.plan')
            self.assertFalse(pack['support_verified'])
            (data/(source.source_id+'.md')).write_bytes(raw+b' ')
            with self.assertRaises(CorpusError):verified_corpus(data,data/'index.sqlite3')

    def test_followup_anchor_and_explicit_topic_reset(self):
        anchor={'source_id':'a','path':'chapter/lesson.ipynb','symbol':'book_flight','scope_id':'cell:3','cell_index':3}
        recent=[{'question':'解释 book_flight。','result':{'status':'CITED_DRAFT','object_anchors':[anchor]}}]
        follow=prepare_context('这里的函数会调用外部接口吗？',recent,None)
        self.assertEqual(follow['object_anchors'],[anchor]);self.assertIn('chapter/lesson.ipynb',follow['retrieval_question'])
        reset=prepare_context('现在换到 MCP，notification 有 id 吗？',recent,None)
        self.assertEqual(reset['object_anchors'],[]);self.assertNotIn('book_flight',reset['retrieval_question'])


class ContractTests(unittest.TestCase):
    def test_valid_preview_is_discarded_when_final_facet_coverage_fails(self):
        from study_rag.rag import answer_from_pack
        from test_qa import evidence
        class Fake:
            span_references=True;model_name='deepseek-flash';calls=0
            def generate_stream(self,messages,callback):
                self.calls+=1;payload=json.loads(messages[1]['content']);ref=payload['EVIDENCE'][0]['spans'][0]['span_id']
                raw=json.dumps({'blocks':[{'face_id':'one','text':'中文转义 \\"测试。','references':[ref]}],'missing_face_ids':['unknown']},ensure_ascii=False)
                for offset in range(0,len(raw),3):callback(raw[offset:offset+3])
                return raw,{}
        model=Fake();events=[];plan=self.make().plan
        pack={'qa_version':3,'pipeline_version':5,'question':'解释概念','evidence':[evidence()],
              'question_plan':{**plan,'pipeline_version':5},'support_verified':False}
        result=answer_from_pack(pack,model,on_event=events.append)
        self.assertTrue(any(e['type']=='block' for e in events));self.assertEqual(result['status'],'CITATION_VALIDATION_FAILED')
        self.assertIsNone(result['answer']);self.assertEqual(model.calls,1)

    def make(self):
        plan={'question':'解释关系','object_status':'indexed','necessary_faces':[
            {'id':'one','dimension':'mechanism','evidence_ids':['E1']},
            {'id':'two','dimension':'result','evidence_ids':['E2']}]}
        spans={'E1':[{'span_id':'S1','text':'The first literal statement.'}], 'E2':[{'span_id':'S1','text':'The second literal statement.'}]}
        return FacetContract(plan,spans,{})

    def test_units_cannot_repeat_faces_or_borrow_another_sources_citation(self):
        unit={'face_id':'one','text':'第一个要点。','references':['E1:S1']}
        c=self.make();self.assertEqual(c.unit(unit)['type'],'paragraph')
        with self.assertRaises(CorpusError):c.unit(unit)
        with self.assertRaises(CorpusError):self.make().unit({**unit,'references':['E2:S1']})
        with self.assertRaises(CorpusError):self.make().unit({**unit,'face_id':'invented'})

    def test_gaps_are_owned_ids_not_model_authored_absence_claims(self):
        c=self.make();a=c.final({'blocks':[{'face_id':'one','text':'第一个要点。','references':['E1:S1']}],'missing_face_ids':['two']})
        self.assertEqual(a['status'],'partial');self.assertIn('对象已在语料中收录',a['missing_information'])
        for value in [{'blocks':[],'missing_face_ids':['one']},{'blocks':[],'missing_information':'课件没有'},
                      {'blocks':[],'missing_face_ids':['one','two','two']}]:
            with self.assertRaises(CorpusError):self.make().final(value)

    def test_controlled_group_cannot_be_rewritten_as_free_text(self):
        c=self.make();c.faces['one']['dimension']='source_relations'
        c.groups={'G1':{'face_id':'one','fact_ids':['F1']}}
        c.facts={'F1':{'text':'源码调用 `helper`。','references':['E1:S1']}}
        with self.assertRaises(CorpusError):c.unit({'face_id':'one','text':'同义改写','references':['E1:S1']})
        result=c.unit({'face_id':'one','type':'fact_group','group_id':'G1'})
        self.assertEqual(result['text'],'源码调用 `helper`。')
        self.assertNotIn('face_id',result)


class PhaseBudgetTests(unittest.TestCase):
    def test_phase_cap_count_and_acceptance_hold_are_transactional(self):
        flash=SimpleNamespace(model_name='deepseek-flash',provider='deepseek')
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');ledger.enable_flash_budget(240000)
            ledger.authorize_phase('dev','repair-development',2,140000)
            ledger.authorize_phase('frozen','repair-acceptance',40,100000,protected=True)
            def reserve(key):
                try:return ledger.reserve(key,flash,'repair-development',[])
                except ValidationStopped:return None
            with ThreadPoolExecutor(max_workers=3) as pool:ids=list(pool.map(reserve,['a','b','c']))
            self.assertEqual(sum(i is not None for i in ids),2)
            self.assertEqual(ledger.phase_summary()[0]['calls'],2)
            with self.assertRaises(ValidationStopped):ledger.reserve('outside',flash,'unallocated',[])
            with self.assertRaises(ValueError):ledger.authorize_phase('dev','repair-development',3,140000)
            # Unknown usage keeps its full reservation, even on a recorded failure.
            ledger.finish(next(i for i in ids if i),error='HTTP_AMBIGUOUS')
            self.assertGreater(ledger.phase_summary()[0]['used_upper_micros'],130000)
            ledger.reserve('frozen-one',flash,'repair-acceptance',[])


if __name__=='__main__':unittest.main()
