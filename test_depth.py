"""长输入、深入讲解、扩展正文与模型上限；不请求真实模型。"""
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from study_rag.core import Source, build_index, prepare_corpus, validate_text
from study_rag.limits import (MAX_EVIDENCE_CHARS, MAX_QUESTION_CHARS, MODEL_OUTPUT_TOKENS,
                              MODEL_TIMEOUT_SECONDS, MODEL_JOB_LEASE_SECONDS)
from study_rag.rag import DeepSeekModel, answer_from_pack, build_messages, retrieve, validate_draft
import test_multiuser as fixtures


class LongInputApiTests(TestCase):
    setUp = fixtures.MultiuserTests.setUp
    register = fixtures.MultiuserTests.register
    chat = fixtures.MultiuserTests.chat
    ask = fixtures.MultiuserTests.ask

    def test_10000_chinese_characters_cross_old_body_limit_and_persist_unchanged(self):
        self.register(self.a, 'long-input-user')
        chat = self.chat(self.a)
        question = 'RAG' + '背景说明' * 2499 + '。'
        self.assertEqual(len(question), MAX_QUESTION_CHARS)
        response = self.ask(self.a, chat, question=question, explain=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.a.get(f'/api/chats/{chat}').json()[0]['question'], question)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.ask(self.a, chat, question=question+'字', explain=False).status_code, 422)
        self.assertEqual(len(self.a.get(f'/api/chats/{chat}').json()), 1)

    def test_request_body_remains_bounded(self):
        self.register(self.a, 'bounded-body-user')
        response = self.a.post('/api/chats', content=b'x' * (128 * 1024 + 1),
                               headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_long_generation_lease_remains_exclusive_until_finished(self):
        import time
        user_id=self.store.register('long-generation-user',fixtures.PASSWORD)['id']
        job=self.store.reserve(user_id,'long-generation-request')
        with self.store.database() as db:
            remaining=db.execute('SELECT lease_until FROM jobs WHERE id=?',(job,)).fetchone()[0]-time.time()
        self.assertGreater(remaining,MODEL_TIMEOUT_SECONDS*2)
        self.assertLessEqual(remaining,MODEL_JOB_LEASE_SECONDS)
        from study_rag.store import LimitError
        with self.assertRaises(LimitError):self.store.reserve(user_id,'another-request')
        self.store.finish(job,{'status':'MODEL_FAILED','model_calls':1})
        self.store.reserve(user_id,'after-completion')


class DeepDraftTests(TestCase):
    def setUp(self):
        self.quote = '工具执行之后把观察结果放回上下文，再决定下一步动作。'
        self.evidence = [{'evidence_id':'E1','context_text':self.quote,'book':'test',
                          'section':'机制','display_name':'测试教材'}]
        self.raw = json.dumps({'status':'answered','claims':[
            {'heading':heading,'text':('机制说明与实践边界。\n' * 65),'evidence_id':'E1','quote':self.quote}
            for heading in ['核心结论','工作机制','状态变化','实现步骤','实践例子','风险边界']],
            'missing_information':''},ensure_ascii=False)

    def test_long_structured_answer_is_not_cut_to_four_short_points(self):
        draft = validate_draft(self.raw,self.evidence)
        self.assertEqual(len(draft.claims),6)
        self.assertTrue(all(len(p.text)>500 for p in draft.claims))
        model = SimpleNamespace(generate=MagicMock(return_value=(self.raw,{'attempts':1})))
        result = answer_from_pack({'question':'深入说明工具循环','evidence':self.evidence},model)
        self.assertEqual(result['status'],'CITED_DRAFT')
        self.assertEqual(len(result['answer']['claims']),6)
        self.assertFalse(result['support_verified'])
        self.assertEqual(result['model_calls'],1)
        model.generate.assert_called_once()

    def test_long_answer_still_rejects_a_single_fabricated_quote(self):
        raw = json.loads(self.raw)
        raw['claims'][-1]['quote']='这是一段不存在于原文中的伪造引文。'
        with self.assertRaises(ValueError):validate_draft(json.dumps(raw),self.evidence)

    def test_legacy_answer_without_headings_is_accepted(self):
        raw=json.loads(self.raw)
        raw['claims']=raw['claims'][:1]
        del raw['claims'][0]['heading']
        self.assertEqual(validate_draft(json.dumps(raw),self.evidence).claims[0].heading,'')

    def test_prompt_requests_mechanisms_examples_boundaries_without_filling_gaps(self):
        prompt=build_messages('深入说明',self.evidence)[0]['content']
        for word in ['因果关系','具体例子','适用边界','partial','不能据此断言','最多20条']:
            self.assertIn(word,prompt)
        self.assertNotIn('最多4条',prompt)


class ProviderLimitTests(TestCase):
    def response(self,finish='stop'):
        return SimpleNamespace(model='offline-model',usage=SimpleNamespace(prompt_tokens=100,completion_tokens=8000),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason=finish)])

    def test_larger_output_and_timeout_keep_one_call_and_no_retry(self):
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'offline-test-placeholder'}), \
             patch('study_rag.rag.OpenAI') as factory:
            client=factory.return_value
            client.chat.completions.create.return_value=self.response()
            DeepSeekModel().generate([{'role':'user','content':'JSON'}])
        self.assertEqual(factory.call_args.kwargs['timeout'],MODEL_TIMEOUT_SECONDS)
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'],MODEL_OUTPUT_TOKENS)
        client.chat.completions.create.assert_called_once()

    def test_output_limit_keeps_usage_and_does_not_retry_or_display_incomplete_json(self):
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'offline-test-placeholder'}), \
             patch('study_rag.rag.OpenAI') as factory:
            client=factory.return_value
            client.chat.completions.create.return_value=self.response('length')
            result=answer_from_pack({'question':'深入说明','evidence':[{'evidence_id':'E1','book':'test',
                                    'section':'正文','context_text':'工具调用保存上下文。'}]},DeepSeekModel())
        self.assertEqual(result['status'],'MODEL_FAILED')
        self.assertEqual(result['error_type'],'MODEL_OUTPUT_LIMIT')
        self.assertEqual(result['usage']['output_tokens'],8000)
        self.assertEqual(result['model_calls'],1)
        self.assertIsNone(result['answer'])
        client.chat.completions.create.assert_called_once()


class RichEvidenceTests(TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def corpus(self,text):
        source=Source('rich','collection','测试教材','example/repo','a'*40,'README.md')
        prepare_corpus([source],self.root,lambda _:text.encode('utf-8'))
        build_index(self.root,self.root/'index.sqlite3')
        return source

    def test_concept_excludes_objectives_contributions_and_setup_but_installation_positive_survives(self):
        self.corpus('# RAG\n\n## Learning Objectives\nRAG 学习目标，安装 RAG。\n\n'
                    '## Contributing\nRAG RAG RAG Contributions welcome.\n\n'
                    '## Getting Started\nInstall dependencies, install spaCy, run the application.\n\n'
                    '## Mechanism\nRAG 检索外部知识，再将证据提供给模型生成回答。\n')
        concept=retrieve(self.root,self.root/'index.sqlite3','RAG 工作机制')
        self.assertTrue(concept['evidence'])
        self.assertTrue(all('Mechanism' in e['section'] for e in concept['evidence']))
        install=retrieve(self.root,self.root/'index.sqlite3','RAG 案例安装启动步骤')
        self.assertTrue(any('Getting Started' in e['section'] for e in install['evidence']))
        self.assertLessEqual(len(install['evidence']),2)

    def test_neighbor_context_remains_in_heading_and_preserves_exact_positions_and_code_mask(self):
        text=('# 教材\n\n## 工作机制\n'+('RAG 检索知识，Memory 保存状态。\n'*100)+
              '\n```python\nprint("代码不能作为概念证据")\n```\n'+
              '\n## Another topic\n相邻标题下的额外事实不应混入工作机制。\n')
        self.corpus(text)
        result=retrieve(self.root,self.root/'index.sqlite3','RAG Memory 工作机制')
        original=validate_text(text.encode())
        self.assertTrue(result['evidence'])
        self.assertTrue(any(e['end_char']-e['start_char']>1400 for e in result['evidence']))
        for e in result['evidence']:
            self.assertEqual(e['text'],original[e['start_char']:e['end_char']])
            self.assertEqual(e['start_line'],original.count('\n',0,e['start_char'])+1)
            self.assertEqual(e['end_line'],original.count('\n',0,e['end_char']-1)+1)
            self.assertLessEqual(len(e['text']),MAX_EVIDENCE_CHARS)
            self.assertNotIn('代码不能作为概念证据',e['context_text'])
            if e['section'].endswith('工作机制'):
                self.assertNotIn('额外事实',e['context_text'])
