"""Offline source views, atomic retrieval and cost-policy regression. No live models."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from study_rag.core import Source, prepare_corpus, build_index, verified_corpus, CorpusError
from study_rag.source_views import source_view, locator, view_chunks


def fixture(path='lesson.ipynb', body=None):
    source = Source('notebook-fixture', 'course', 'Notebook lesson', 'owner/course', 'a'*40, path)
    raw = json.dumps(body or {'nbformat':4,'metadata':{'language_info':{'name':'python'}},'cells':[
        {'cell_type':'markdown','source':['# 工具教学\n','这是连续的中文原文，保留😀字符。']},
        {'cell_type':'code','source':['def local_tool(value):\n','    return value + 1\n'],
         'execution_count':99,'outputs':[{'text':'OUTPUT_MUST_NOT_BE_INDEXED'}]}]},ensure_ascii=False).encode()
    license_text='Offline test license\n';license_raw=license_text.encode()
    catalog={'version':4,'books':[{'book':'course','display_name':'课程','order':0,'repository':source.repository,
        'commit':source.commit,'license':'test','license_text':license_text,'license_path':'LICENSE',
        'license_git_blob':hashlib.sha1(f'blob {len(license_raw)}\0'.encode()+license_raw).hexdigest()}],
        'chapters':{source.source_id:{'language':'zh-CN','canonical_path':path,'order':0,
            'kind':'implementation','content_type':'notebook','git_blob':hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest(),
            'bytes':len(raw),'applicable_versions':['unknown']}}}
    return source,raw,catalog


class SourceViewTests(unittest.TestCase):
    def test_notebook_keeps_only_source_cells_and_real_cell_line_mapping(self):
        source,raw,_=fixture();text,cells=source_view(source.path,raw)
        self.assertNotIn('OUTPUT_MUST_NOT_BE_INDEXED',text);self.assertNotIn('execution_count',text)
        self.assertEqual(len(cells),2)
        start=text.index('return value');where=locator(source,raw,start,start+len('return value + 1'))
        self.assertEqual((where['cell_index'],where['start_line'],where['end_line']),(2,2,2))
        with self.assertRaises(CorpusError):locator(source,raw,0,len(text))
        self.assertIn('😀',text)

    def test_notebook_index_is_rebuilt_from_original_json_and_rejects_tampering(self):
        source,raw,catalog=fixture()
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);prepare_corpus([source],data,lambda _:raw,catalog=catalog);build_index(data,data/'index.sqlite3')
            manifest,chunks,_,_=verified_corpus(data,data/'index.sqlite3')
            self.assertEqual(manifest['schema_version'],4)
            self.assertTrue(any('local_tool' in c.text and '[code]' in c.section for c in chunks))
            self.assertTrue(all('OUTPUT_MUST_NOT_BE_INDEXED' not in c.text for c in chunks))
            with closing(sqlite3.connect(data/'index.sqlite3')) as db,db:db.execute("UPDATE chunks SET payload='{}' WHERE position=0")
            with self.assertRaises(CorpusError):verified_corpus(data,data/'index.sqlite3')

    def test_atomic_table_and_list_boundaries_preserve_original_characters(self):
        source=Source('markdown-fixture','course','Lesson','owner/course','a'*40,'lesson.md')
        text='# 标题\n\n定义段落保持完整。\n\n| 参数 | 规则 |\n| --- | --- |\n| config | 保留参数，不可自定义 |\n\n- 第一个完整要点\n- 第二个完整要点\n'
        chunks=view_chunks(source,text.encode())
        self.assertTrue(any(c.text.strip()=='| config | 保留参数，不可自定义 |' for c in chunks))
        self.assertTrue(any(c.text.strip()=='- 第一个完整要点' for c in chunks))

    def test_long_paragraph_and_table_row_are_not_cut_by_character_limit(self):
        source=Source('long-atoms','course','Lesson','owner/course','a'*40,'lesson.md')
        paragraph='连续定义。'*400
        row='| 参数 | '+'完整约束，'*400+' |'
        text='# 定义\n\n'+paragraph+'\n\n'+row+'\n'
        chunks=view_chunks(source,text.encode(),max_chars=500)
        self.assertTrue(any(c.text.strip()==paragraph for c in chunks))
        self.assertTrue(any(c.text.strip()==row for c in chunks))
        self.assertTrue(all(text[c.start_char:c.end_char]==c.text for c in chunks))

    def test_invalid_notebook_source_does_not_get_silently_coerced(self):
        for cells in [[{'cell_type':'code','source':[123]}],[{'cell_type':'markdown','source':{}}]]:
            with self.assertRaises(CorpusError):source_view('bad.ipynb',json.dumps({'nbformat':4,'cells':cells}).encode())

    def test_code_parent_expansion_does_not_bridge_separate_fences(self):
        from study_rag.qa_retrieval_v4 import materials,_expand
        from study_rag.core import json_text
        source=Source('fence-fixture','course','Lesson','owner/course','a'*40,'lesson.md')
        raw=b'# Example\n\n```python\nvalue = "first example"\n```\n\nThis is intervening prose.\n\n```python\nvalue = "second example"\n```\n'
        catalog={'books':[{'book':'course','display_name':'Course'}],
                 'chapters':{source.source_id:{'language':'en','kind':'lesson','content_type':'prose'}}}
        mat=materials(((source,raw),),tuple(view_chunks(source,raw)),json_text(catalog))
        entry=next(e for e in mat['entries'] if e['content_type']=='code' and 'first example' in e['body'])
        result=_expand(entry,mat,'show code')
        self.assertNotIn('intervening',result['context_text']);self.assertNotIn('second example',result['context_text'])


class StaticFactTests(unittest.TestCase):
    def test_notebook_bindings_and_fact_hydration_do_not_use_outputs_or_execute(self):
        from study_rag.static_facts import bindings,provenance,fact_pool
        from study_rag.citation_spans import spans_for_evidence,hydrate
        source,raw,_=fixture();text,cells=source_view(source.path,raw);cell=cells[1]
        graph=bindings(source.path,raw)
        self.assertEqual(graph['definitions'][0]['name'],'local_tool')
        self.assertEqual(graph['definitions'][0]['cell_index'],2)
        item={'evidence_id':'E1','source_id':source.source_id,'start_char':cell['start'],'end_char':cell['end'],
              'start_line':text.count('\n',0,cell['start'])+1,'text':text[cell['start']:cell['end']],
              'context_text':text[cell['start']:cell['end']],'content_type':'code',
              'source_locator':locator(source,raw,cell['start'],cell['end']),
              'provenance':provenance(source,raw,cell['start'],cell['end'])}
        spans=spans_for_evidence([item]);facts=fact_pool('local_tool 是导入的吗？',[item],spans)
        self.assertTrue(facts)
        result=hydrate({'blocks':[{'type':'source_facts','fact_ids':[next(iter(facts))]}]},spans,facts)
        self.assertIn('本地定义',result['blocks'][0]['text'])
        self.assertNotIn('OUTPUT_MUST_NOT_BE_INDEXED',json.dumps(result))
        from study_rag.answer_schema import verify_reference
        location=verify_reference(result['blocks'][0]['references'][0],item)
        self.assertEqual(location['source_locator']['cell_index'],2)
        with self.assertRaises(CorpusError):hydrate({'type':'source_facts','fact_ids':['F999']},spans,facts)
        with self.assertRaises(CorpusError):hydrate({'type':'source_facts','fact_ids':list(facts)[:1],'text':'forged'},spans,facts)

    def test_dependency_internal_claim_cannot_hide_behind_a_valid_fact(self):
        from study_rag.static_facts import validate_boundaries
        from study_rag.provenance import ProvenanceError
        evidence=[{'provenance':{'python':{'module_imported_names':['rag'],'module_local_names':[]}}}]
        fact={'text':'调用方显式传入 search=hybrid_search。'}
        for text in ['rag没有调用perform_search做重排。',fact['text']+' rag内部一定重新检索。']:
            with self.assertRaises(ProvenanceError):validate_boundaries({'claims':[{'text':text}]},evidence,{'F1':fact})
        validate_boundaries({'claims':[{'text':'不能断言rag内部是否重新检索。'}]},evidence,{'F1':fact})


class NotebookHttpTests(unittest.TestCase):
    def test_authenticated_stream_fact_selection_cell_location_and_request_replay(self):
        from fastapi.testclient import TestClient
        from study_rag.web import create_app
        from study_rag.store import Store
        class Fake:
            model_name='deepseek-flash';span_references=True;calls=0
            def generate_stream(self,messages,callback):
                self.calls+=1;payload=json.loads(messages[1]['content'])
                fact=next(k for k,v in payload['SOURCE_FACTS'].items() if v['kind']=='definition')
                group=next(iter(payload['FACT_GROUPS'].items()))
                raw=json.dumps({'blocks':[{'face_id':group[1]['face_id'],'type':'fact_group','group_id':group[0]}],'missing_face_ids':[]},ensure_ascii=False)
                for i in range(0,len(raw),3):callback(raw[i:i+3])
                return raw,{'model':self.model_name,'attempts':1}
        source,raw,catalog=fixture()
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'data';prepare_corpus([source],data,lambda _:raw,catalog=catalog);build_index(data,data/'index.sqlite3')
            model=Fake();store=Store(Path(temp)/'users.sqlite3')
            with patch('study_rag.qa_retrieval_v5.semantic_parent_ranks',return_value=[]),TestClient(create_app(data_dir=data,store=store,model=model)) as client:
                lib=client.get('/api/library').json()
                self.assertEqual((lib['raw_files'],lib['notebook_cells'],lib['answer_schema_version']),(1,2,2))
                auth=client.post('/api/register',json={'username':'notebook-user','password':'offline-password-123'}).json()
                client.headers['X-CSRF-Token']=auth['csrf']
                chat=client.post('/api/chats',json={'title':'Notebook'}).json()['id']
                body={'chat_id':chat,'request_key':uuid4().hex,'question':'只按源码解释 local_tool 的定义','model':'deepseek-flash'}
                response=client.post('/api/ask/stream',json=body)
                events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                self.assertTrue(any(e['type']=='block' for e in events))
                result=next(e['result'] for e in events if e['type']=='result')
                self.assertEqual(result['status'],'CITED_DRAFT')
                self.assertEqual(result['evidence'][0]['source_locator']['cell_index'],2)
                self.assertNotIn('#L',result['evidence'][0]['line_url'])
                self.assertTrue(client.post('/api/ask',json=body).json()['reused'])
                self.assertEqual(model.calls,1)
            # Output-only mutation still changes original bytes and must invalidate caches.
            original=data/(source.source_id+'.md')
            original.write_bytes(raw.replace(b'OUTPUT_MUST_NOT_BE_INDEXED',b'OUTPUT_CHANGED'))
            with self.assertRaises(CorpusError):verified_corpus(data,data/'index.sqlite3')


if __name__=='__main__':unittest.main()
