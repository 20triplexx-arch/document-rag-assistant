"""Object analysis coverage from verified source bytes; never imports collected code."""
from pathlib import Path
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.static_facts import python_units,bindings


def main():
    data=ROOT/'data/qa-overhaul-20261015-v2';manifest,_,_,contents=verified_corpus(data,data/'index.sqlite3')
    gaps=[];files=[];symbols=set()
    for source,raw in contents:
        text,units=python_units(source.path,raw);graph=bindings(source.path,raw)
        for row in graph['analysis_gaps']:
            unit=next(c for c in units if c['scope_id']==row['scope_id'])
            gaps.append({'source_id':source.source_id,'path':source.path,'source_url':source.source_url,**row,
                'start_char':unit['start'],'end_char':unit['end'],'start_line':text.count('\n',0,unit['start'])+1})
        for r in graph['definitions']+graph['assignments']:symbols.add((source.source_id,r['scope_id'],r['qualified_name']))
        files.append({'source_id':source.source_id,'path':source.path,'python_units':len(units),
            'definitions':len(graph['definitions']),'imports':len(graph['imports']),'calls':len(graph['calls']),
            'assignments':len(graph['assignments']),'returns':len(graph['returns']),'analysis_gaps':len(graph['analysis_gaps']),
            'notebook_magics_or_shell_lines':sum(len(re.findall(r'(?m)^[ \t]*[%!]',text[u['start']:u['end']])) for u in units)})
    report={'corpus_version':manifest['corpus_version'],'raw_files':len(contents),'scoped_symbols':len(symbols),
        'python_units':sum(f['python_units'] for f in files),'analysis_gap_units':len(gaps),'gaps':gaps,'files':files,
        'boundary':'Static parsing only. Incomplete teaching fragments and notebook magics are not runtime behavior proof.',
        'model_calls':0,'network_requests':0}
    (ROOT/'output/qa-repair-20261015-v5/object-index-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'files','gaps'}},ensure_ascii=False))


if __name__=='__main__':main()
