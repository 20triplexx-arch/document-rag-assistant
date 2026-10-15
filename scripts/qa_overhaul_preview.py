"""Public Notebook position/UI fixture, temporary account, zero model calls."""
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import locator
from study_rag.store import Store
from study_rag.web import create_app
from study_rag.answer_schema import validate_v2
from study_rag.citation_spans import spans_for_evidence


class OfflineOnly:
    model_name='deepseek-flash'
    def generate(self,*args):raise AssertionError('Offline UI has no model transport')
    def generate_stream(self,*args):raise AssertionError('Offline UI has no model transport')


def main():
    import uvicorn
    data=ROOT/'data/qa-overhaul-20261015-v2'
    manifest,chunks,sources,contents=verified_corpus(data,data/'index.sqlite3')
    c=next(c for c in chunks if sources[c.source_id].path.endswith('.ipynb') and '[code]' in c.section and 100<len(c.text)<700)
    source=sources[c.source_id];raw=next(raw for s,raw in contents if s.source_id==c.source_id)
    e={**c.__dict__,'evidence_id':'E1','content_type':'code','context_text':c.text,'book':source.book,
       'path':source.path,'source_url':source.source_url,'line_url':source.source_url,
       'source_locator':locator(source,raw,c.start_char,c.end_char)}
    span=spans_for_evidence([e])['E1'][0]
    answer={'schema_version':2,'status':'answered','blocks':[{'type':'paragraph',
        'text':'这是 Notebook 教学单元中的原始源码片段。此样例只验证显示与引用位置。',
        'references':[{'evidence_id':'E1','quote':span['text']}]}],'missing_information':''}
    answer=validate_v2(json.dumps(answer),[e]).model_dump()
    result={'status':'CITED_DRAFT','question':'Notebook 单元位置 · 离线界面验证','answer':answer,'evidence':[e],
            'source_verified':True,'quote_verified':True,'support_verified':False,'model_calls':0,
            'corpus_version':manifest['corpus_version'],'qa_version':3}
    output=ROOT/'output/qa-overhaul-20261015-v2/ui-fixture.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='overhaul-ui-') as temp:
        store=Store(Path(temp)/'users.sqlite3');user=store.create_admin('overhaul-preview','overhaul-preview-pass')
        chat=store.create_chat(user['id'],'Notebook 位置验证')
        store.save_exchange(user['id'],chat['id'],str(uuid4()),result['question'],result)
        model=OfflineOnly()
        app=create_app(data_dir=data,store=store,model=model,model_options={'deepseek-flash':model},session_cookie_name='overhaul_preview')
        print('OFFLINE_UI_READY http://127.0.0.1:8872',flush=True)
        uvicorn.run(app,host='127.0.0.1',port=8872,log_level='error')


if __name__=='__main__':main()
