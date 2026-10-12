"""Offline regression tests. No test sends an API request."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import CourseError, completion
from tool_agent import calculate, execute_tool, run_online
from memory_chat import chat, history, recent_context
from document_qa import answer_question, chunks_from_directory

HERE = Path(__file__).resolve().parent


class ToolTests(unittest.TestCase):
    def test_arithmetic(self):
        for operation, expected in [('add', 9), ('subtract', 3), ('multiply', 18), ('divide', 2)]:
            self.assertEqual(calculate({'operation': operation, 'a': 6, 'b': 3})['result'], expected)

    def test_invalid_contract(self):
        inputs = [{}, {'operation': 'add', 'a': 1}, {'operation': 'add', 'a': 1, 'b': 2, 'extra': 3},
                  {'operation': 'sqrt', 'a': 1, 'b': 2}, {'operation': 'add', 'a': True, 'b': 2},
                  {'operation': 'add', 'a': '1', 'b': 2}, {'operation': 'add', 'a': 10**1000, 'b': 2},
                  {'operation': 'add', 'a': float('nan'), 'b': 2}, ['bad']]
        for arguments in inputs:
            with self.subTest(arguments=str(arguments)[:60]):
                self.assertFalse(calculate(arguments)['ok'])

    def test_divide_zero(self):
        self.assertFalse(calculate({'operation': 'divide', 'a': 1, 'b': 0})['ok'])

    def test_json_and_unknown_tool(self):
        for name, args in [('unknown', '{}'), ('calculate', 'not-json'), ('calculate', 'null')]:
            self.assertFalse(execute_tool(name, args)['ok'])

    def test_online_contract_with_fake_responses(self):
        calls = []
        def fake(messages, tools):
            calls.append(list(messages))
            if len(calls) == 1:
                return {'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': 'call_1', 'type': 'function', 'function': {
                        'name': 'calculate', 'arguments': '{"operation":"multiply","a":18,"b":7}'}}]}
            return {'role': 'assistant', 'content': '程序结果为126。'}
        result = run_online('18乘7', fake)
        self.assertEqual(result['trace'][0]['observation']['result'], 126)
        self.assertEqual(calls[1][-1]['tool_call_id'], 'call_1')
        self.assertEqual(result['model_calls'], 2)

    def test_loop_cap(self):
        def forever(messages, tools):
            return {'role': 'assistant', 'tool_calls': [{'id': 'call', 'function': {
                'name': 'calculate', 'arguments': '{"operation":"add","a":1,"b":2}'}}]}
        with self.assertRaisesRegex(CourseError, '上限'):
            run_online('repeat', forever, max_rounds=2)

    def test_malformed_tool_call(self):
        with self.assertRaises(CourseError):
            run_online('bad', lambda messages, tools: {'tool_calls': [{'function': {}}]})


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'memory.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_process_restart_and_session_isolation(self):
        base = [sys.executable, '-X', 'utf8', str(HERE / 'memory_chat.py'), '--db', self.db]
        subprocess.run(base + ['--session', 'alice', '--message', "Python's RAG"], check=True, capture_output=True)
        second = subprocess.run(base + ['--session', 'alice', '--message', '记得吗？'], check=True, capture_output=True, text=True, encoding='utf-8')
        self.assertIn("Python's RAG", json.loads(second.stdout)['answer'])
        self.assertEqual(history(self.db, 'bob'), [])
        self.assertEqual(len(history(self.db, 'alice')), 4)

    def test_failure_saves_no_half_turn(self):
        def fail(messages): raise CourseError('simulation')
        with self.assertRaises(CourseError): chat(self.db, 'a', 'first', True, fail)
        self.assertEqual(history(self.db, 'a'), [])

    def test_boundaries(self):
        with self.assertRaises(CourseError): chat(self.db, '', 'hi')
        with self.assertRaises(CourseError): chat(self.db, 'a', ' ')
        with self.assertRaises(CourseError): chat(self.db, 'a', 'x'*3001)

    def test_context_keeps_pairs(self):
        messages = [{'role': role, 'content': str(i)} for i in range(5) for role in ['user', 'assistant']]
        selected = recent_context(messages, limit=4)
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected[0]['role'], 'user')
        self.assertEqual(selected[0]['content'], '3')
        self.assertEqual(recent_context(messages, char_budget=1), [])


class RetrievalTests(unittest.TestCase):
    def test_citations_match_original_lines(self):
        docs = HERE / 'sample_docs'
        result = answer_question(docs, '报销材料有哪些？')
        self.assertFalse(result['model_called'])
        self.assertTrue(result['sources'])
        self.assertIn('电子发票', result['answer'])
        for source in result['sources']:
            lines = (docs / source['file']).read_text(encoding='utf-8').splitlines()
            self.assertEqual(source['text'], '\n'.join(lines[source['start_line']-1:source['end_line']]))

    def test_no_hits_never_calls_model(self):
        def forbidden(messages): raise AssertionError('must not call')
        result = answer_question(HERE / 'sample_docs', '量子纠缠数学定义', True, forbidden)
        self.assertEqual(result['sources'], [])
        self.assertFalse(result['model_called'])

    def test_online_unknown_or_missing_citation(self):
        for content in ['资料没有说明', '结论[S99]']:
            with self.assertRaises(CourseError):
                answer_question(HERE / 'sample_docs', '报销材料', True, lambda messages: {'content': content})

    def test_online_valid_id_does_not_claim_semantic_proof(self):
        result = answer_question(HERE / 'sample_docs', '报销材料', True, lambda messages: {'content': '需电子发票[S1]。'})
        self.assertIn('仍需人工', result['citation_check'])

    def test_format_and_missing_directory(self):
        with self.assertRaises(CourseError): chunks_from_directory(HERE / 'missing')
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'fake.pdf').write_bytes(b'not a pdf')
            self.assertEqual(chunks_from_directory(temp), [])


class ClientTests(unittest.TestCase):
    def test_missing_config_cannot_send_network_request(self):
        with patch.dict(os.environ, {}, clear=True), patch('urllib.request.urlopen') as opener:
            with self.assertRaises(CourseError): completion([{'role': 'user', 'content': 'hello'}])
            opener.assert_not_called()

    def test_payload_and_output_limit(self):
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return json.dumps({'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': 'cut'}}]}).encode()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'TEST_ONLY', 'DEEPSEEK_MODEL': 'test-model'}), patch('urllib.request.urlopen', return_value=Reply()) as opener:
            with self.assertRaisesRegex(CourseError, '长度'):
                completion([{'role': 'user', 'content': 'hello'}])
            request = opener.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.deepseek.com/chat/completions')
            self.assertEqual(json.loads(request.data)['max_tokens'], 1200)


if __name__ == '__main__':
    unittest.main()
