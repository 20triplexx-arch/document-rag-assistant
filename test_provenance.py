"""Offline provider, ownership and experimental accounting regressions."""
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import test_multiuser as fixtures
from study_rag.providers import BailianModel,create_model,configured_models
from study_rag.rag import DeepSeekModel,ProviderError
from study_rag.provenance import python_bindings,validate_provenance,ProvenanceError
from study_rag.qa_experiment import ExperimentLedger,RecordedModel,ValidationStopped
from study_rag.citation_spans import generation_schema
from study_rag.citation_spans import hydrate
from study_rag.web import create_app


class ProviderTests(unittest.TestCase):
    def test_bailian_uses_only_its_key_and_provider_parameters_and_reuses_connection(self):
        response=SimpleNamespace(model='qwen3.8-flash',usage=None,choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason='stop')])
        with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'bailian-offline','DASHSCOPE_WORKSPACE_ID':'offline-workspace','DEEPSEEK_API_KEY':'deepseek-offline','RAG_BAILIAN_FREE_ONLY_CONFIRMED':'1'}),patch('study_rag.rag.OpenAI') as factory:
            factory.return_value.chat.completions.create.return_value=response
            model=BailianModel('qwen3.8-flash')
            for _ in range(2):raw,usage=model.generate([{'role':'user','content':'JSON'}])
            options=factory.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(factory.call_count,1)
            self.assertEqual(factory.call_args.kwargs['api_key'],'bailian-offline')
            self.assertEqual(factory.call_args.kwargs['base_url'],'https://offline-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1')
            self.assertEqual(factory.call_args.kwargs['max_retries'],0)
            self.assertEqual(options['extra_body'],{'enable_thinking':False,'enable_search':False})
            self.assertNotIn('stream_options',options)
            self.assertEqual(usage['provider'],'bailian')
            model.close();factory.return_value.close.assert_called_once()

    def test_bailian_key_does_not_prove_free_quota_or_stop_when_exhausted(self):
        with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'offline-key','DASHSCOPE_WORKSPACE_ID':'workspace','RAG_BAILIAN_FREE_ONLY_CONFIRMED':''}),patch('study_rag.rag.OpenAI') as factory:
            model=BailianModel()
            with self.assertRaises(ProviderError) as raised:model.generate([])
            self.assertEqual((raised.exception.error_type,raised.exception.attempts),('BAILIAN_FREE_ONLY_UNCONFIRMED',0))
            factory.assert_not_called()
            self.assertEqual(list(configured_models(DeepSeekModel('deepseek-flash'))),['deepseek-flash'])

    def test_disabled_paid_models_cannot_bypass_factory_by_using_transport_directly(self):
        for model in (DeepSeekModel('deepseek-v4-pro'), BailianModel('qwen3.8-max-0902')):
            with self.subTest(model=model.model_name),patch('study_rag.rag.OpenAI') as factory:
                with self.assertRaises(ProviderError) as raised:model.generate([])
                self.assertEqual((raised.exception.error_type,raised.exception.attempts),('MODEL_DISABLED',0))
                factory.assert_not_called()

    def test_missing_or_invalid_bailian_configuration_never_uses_other_credentials(self):
        for key,workspace,reason in [('', 'good','BAILIAN_KEY_MISSING'),('placeholder','bad/path','BAILIAN_WORKSPACE_INVALID')]:
            with self.subTest(reason=reason),patch.dict('os.environ',{'DASHSCOPE_API_KEY':key,'DASHSCOPE_WORKSPACE_ID':workspace,'OPENAI_API_KEY':'unrelated','DEEPSEEK_API_KEY':'unrelated'}),patch('study_rag.rag.OpenAI') as factory:
                with self.assertRaises(ProviderError) as raised:BailianModel().generate([])
                self.assertEqual((raised.exception.error_type,raised.exception.attempts),(reason,0));factory.assert_not_called()

    def test_registry_and_factory_keep_explicit_model_and_do_not_generate(self):
        with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'placeholder','DASHSCOPE_WORKSPACE_ID':'workspace','RAG_DEFAULT_MODEL':'qwen3.8-flash'}):
            default=create_model();self.assertIsInstance(default,BailianModel)
            self.assertEqual(list(configured_models(default)),['qwen3.8-flash','deepseek-flash'])
            self.assertIsInstance(create_model('deepseek-flash'),DeepSeekModel)
            self.assertEqual(create_model('deepseek-flash').provider,'deepseek')
            with self.assertRaises(ValueError):create_model('deepseek-v4-pro')
            with self.assertRaises(ValueError):create_model('qwen3.8-max-0902')

    def test_native_bailian_schema_is_explicit_and_does_not_change_output_contract(self):
        schema={'type':'object','title':'ignored','properties':{'version':{'const':2,'title':'ignored'}},'required':['version'],'additionalProperties':False}
        payload=json.dumps({'ANSWER_SCHEMA':schema})
        fmt=BailianModel()._response_format([{'role':'user','content':payload}])
        self.assertEqual(fmt['type'],'json_schema');self.assertTrue(fmt['json_schema']['strict'])
        self.assertEqual(fmt['json_schema']['schema']['properties']['version'],{'enum':[2]})
        self.assertEqual(schema['properties']['version']['const'],2)


class OwnershipTests(unittest.TestCase):
    def test_ast_distinguishes_local_definition_import_alias_and_caller_without_execution(self):
        text='from external import rag as generate\n\ndef perform_search(query):\n    """中文说明。"""\n    return generate(query)\n\nraise RuntimeError("never execute")\n'
        definitions,imports,calls=python_bindings(text)
        self.assertEqual(definitions[0]['name'],'perform_search')
        self.assertEqual((imports[0]['name'],imports[0]['imported_name']),('generate','rag'))
        self.assertEqual((calls[0]['name'],calls[0]['owner']),('generate','perform_search'))
        self.assertTrue(text[definitions[0]['start_char']:definitions[0]['end_char']].startswith('def perform_search'))

    def test_explicit_local_import_contradiction_is_rejected_but_call_or_negation_is_allowed(self):
        evidence=[{'evidence_id':'E1','provenance':{'python':{'module_local_names':['perform_search']}}}]
        for text,valid in [('perform_search 是从 raglite 导入的。',False),('perform_search 和 rag 都来自 raglite 包。',False),
                           ('perform_search 不是从 raglite 导入的，而是本地定义。',True),('perform_search 调用的 rag 是从 raglite 导入的。',True)]:
            answer={'claims':[{'text':text,'evidence_id':'E1','quote':'literal reference'}]}
            if valid:validate_provenance(answer,evidence)
            else:
                with self.assertRaises(ProvenanceError):validate_provenance(answer,evidence)

    def test_generation_schema_enumerates_only_actual_turn_ids(self):
        ref=generation_schema(spans={'E1':[{'span_id':'S1'},{'span_id':'S2'}],'E2':[{'span_id':'S1'}]})['$defs']['Reference']
        self.assertEqual(ref,{'type':'string','enum':['E1:S1','E1:S2','E2:S1']})

    def test_qualified_id_is_resolved_without_guessing_a_different_evidence_pair(self):
        spans={'E1':[{'span_id':'S1','text':'literal source quote'}]}
        self.assertEqual(hydrate({'references':['E1:S1']},spans),{'references':[{'evidence_id':'E1','quote':'literal source quote'}]})
        with self.assertRaises(ValueError):hydrate({'references':['E2:S1']},spans)

    def test_minimal_wire_derives_public_state_without_coercing_or_rewriting_content(self):
        self.assertEqual(generation_schema()['required'],['blocks'])
        result=hydrate({'blocks':[],'missing_information':'缺少本机实测数据。'},{})
        self.assertEqual(result,{'schema_version':2,'status':'insufficient','blocks':[],'missing_information':'缺少本机实测数据。'})
        with self.assertRaises(ValueError):hydrate({'blocks':[],'missing_information':[]},{})
        self.assertEqual(hydrate({'blocks':[]},{})['missing_information'],'')
        spans={'E1':[{'span_id':'S1','text':'literal source quote'}]}
        unit={'text':'A supported statement.','references':['E1:S1']}
        self.assertEqual(hydrate(unit,spans)['type'],'paragraph')
        result=hydrate({'blocks':[unit,{'type':'list','items':[unit]}]},spans)
        self.assertEqual(result['blocks'][0]['type'],'paragraph')
        self.assertNotIn('type',result['blocks'][1]['items'][0])


class ExperimentTests(unittest.TestCase):
    def test_budget_increase_is_append_only_and_preserves_existing_spend(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');ledger.enable_flash_budget(100000)
            flash=SimpleNamespace(model_name='deepseek-flash',provider='deepseek')
            ledger.reserve('one',flash,'test',[])
            ledger.authorize_total_budget('explicit-increase',200000,'User authorized total increase')
            ledger.reserve('two',flash,'test',[])
            with self.assertRaises(ValidationStopped):ledger.reserve('three',flash,'test',[])
            ledger.authorize_total_budget('explicit-increase',200000,'User authorized total increase')
            with self.assertRaises(ValueError):ledger.authorize_total_budget('explicit-increase',300000,'changed')
            with ledger.connect() as db:
                self.assertEqual(json.loads(db.execute("SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()[0])['limit_micros'],100000)
                self.assertEqual(db.execute('SELECT count(*) FROM spend_authorizations').fetchone()[0],1)
            self.assertGreater(ledger.summary()['resumed_flash_cost_bound_cny'],.13)

    def test_flash_resume_has_atomic_cost_bound_and_rejects_pro_before_any_call(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');ledger.enable_flash_budget(100000)
            flash=SimpleNamespace(model_name='deepseek-flash',provider='deepseek')
            first=ledger.reserve('one',flash,'test',[])
            with self.assertRaises(ValidationStopped):ledger.reserve('two',flash,'test',[])
            with self.assertRaises(ValidationStopped):ledger.reserve('pro',SimpleNamespace(model_name='deepseek-v4-pro',provider='deepseek'),'test',[])
            ledger.finish(first,raw='{}',usage={'prompt_tokens':1,'output_tokens':1})
            ledger.reserve('two',flash,'test',[])
            with ledger.connect() as db:
                with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO calls(call_key,model) VALUES('bypass','deepseek-flash')")

    def test_budget_stop_never_enters_provider_and_unknown_usage_keeps_reservation(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');ledger.enable_flash_budget(100000)
            provider=Mock(model_name='deepseek-flash',provider='deepseek')
            provider.generate.side_effect=ProviderError('HTTP_402')
            with self.assertRaises(ProviderError):RecordedModel(ledger,'one',provider,'answer').generate([])
            with self.assertRaises(ValidationStopped) as raised:RecordedModel(ledger,'two',provider,'answer').generate([])
            self.assertEqual(raised.exception.attempts,0)
            self.assertEqual(provider.generate.call_count,1)
            summary=ledger.summary()
            self.assertEqual(summary['calls_reserved'],1)
            self.assertGreater(summary['resumed_flash_cost_bound_cny'],.06)

    def test_concurrent_reservations_cannot_both_spend_the_same_balance(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');ledger.enable_flash_budget(100000)
            provider=SimpleNamespace(model_name='deepseek-flash',provider='deepseek')
            def reserve(key):
                try:return ledger.reserve(key,provider,'answer',[])
                except ValidationStopped:return None
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,['one','two']))
            self.assertEqual(sum(result is not None for result in results),1)
            self.assertEqual(ledger.summary()['calls_reserved'],1)

    def test_unlimited_ledger_keeps_failures_crash_reservations_and_unique_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=ExperimentLedger(Path(temp)/'ledger.sqlite3');model=SimpleNamespace(model_name='offline',provider='offline')
            first=ledger.reserve('failed',model,'test',[]);ledger.finish(first,error='offline_failure')
            ledger.reserve('crash',model,'test',[])
            with self.assertRaises(sqlite3.IntegrityError):ledger.reserve('crash',model,'test',[])
            with self.assertRaises(ValueError):ledger.finish(first,raw='{}')
            summary=ledger.summary();self.assertEqual((summary['failed'],summary['unresolved']),(1,1))
            self.assertIsNone(summary['call_limit']);self.assertIsNone(summary['token_limit'])
            ledger.freeze('source',{'hash':'one'})
            with self.assertRaises(ValueError):ledger.freeze('source',{'hash':'two'})


class ProviderApiTests(unittest.TestCase):
    register=fixtures.MultiuserTests.register
    chat=fixtures.MultiuserTests.chat

    def setUp(self):
        fixtures.MultiuserTests.setUp(self);self.a.close();self.b.close()
        self.model.model_name='deepseek-flash';self.qwen=fixtures.FakeModel();self.qwen.model_name='qwen3.8-flash'
        self.app=create_app(data_dir=self.data,store=self.store,model=self.model,model_options={self.model.model_name:self.model,self.qwen.model_name:self.qwen})
        self.a,self.b=TestClient(self.app),TestClient(self.app);self.addCleanup(self.a.close);self.addCleanup(self.b.close)

    def test_provider_catalog_routing_failure_and_request_identity(self):
        catalog=self.a.get('/api/library').json()
        self.assertEqual([m['provider'] for m in catalog['models']],['deepseek','bailian'])
        self.register(self.a,'provider-user');chat=self.chat(self.a);key=uuid4().hex
        body={'chat_id':chat,'request_key':key,'question':'RAG 与 Memory 的区别','model':'qwen3.8-flash'}
        self.qwen.unavailable=True
        result=self.a.post('/api/ask',json=body).json()
        self.assertEqual(result['status'],'MODEL_FAILED');self.assertEqual((self.qwen.calls,self.model.calls),(1,0))
        self.assertTrue(self.a.post('/api/ask',json=body).json()['reused'])
        self.assertEqual(self.a.post('/api/ask',json={**body,'model':'deepseek-flash'}).status_code,409)
        self.assertEqual(self.a.get('/api/me').json()['quota']['used'],1)


if __name__=='__main__':unittest.main()
