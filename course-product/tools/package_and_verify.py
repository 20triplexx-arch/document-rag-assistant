"""Build two allowlisted ZIPs and test the extracted buyer delivery."""
from pathlib import Path, PurePosixPath
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pypdf import PdfReader
from write_course import LESSONS, document
from write_cases import CASES, SOURCES

ROOT=Path(__file__).resolve().parents[1]
BUY=ROOT/'delivery'
SELL=ROOT/'marketing'
DIST=ROOT/'dist';DIST.mkdir(exist_ok=True)
QA=ROOT/'qa';QA.mkdir(exist_ok=True)
CLEAN=QA/'clean-venv'/'Scripts'/'python.exe'
assert CLEAN.is_file()
assert len(LESSONS)==24 and len(CASES)==len(SOURCES)==12

def include(path,root):
    rel=path.relative_to(root)
    if not path.is_file() or path.is_symlink():return False
    if any(part in {'__pycache__','runtime','.venv','node_modules'} for part in rel.parts):return False
    return path.suffix.lower() in {'.md','.txt','.py','.json','.pdf','.png','.zip'} or path.name=='.env.example'

def selected_files(root):return sorted(p for p in root.rglob('*') if include(p,root))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def archive(root,target,name):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for path in selected_files(root):
            output.write(path,name+'/'+path.relative_to(root).as_posix())
    with zipfile.ZipFile(target) as reader:
        assert reader.testzip() is None
        assert not any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in reader.namelist())
    return target

# Scope and manuscript checks.
lesson_files=[p for p in (BUY/'01-课程讲义').glob('*.md') if re.match(r'^\d{2}-',p.name)]
case_files=[p for p in (BUY/'02-案例手册').glob('*.md') if re.match(r'^\d{2}-',p.name)]
assert len(lesson_files)==24 and len(case_files)==12
for lesson in LESSONS:
    text=document(lesson)
    assert len(text)>700
    for heading in ['学习目标','中文讲解','示例与观察','动手任务','参考答案','常见问题']:
        assert '## '+heading in text
    for code in re.findall(r'```python\n(.*?)```',text,re.S):ast.parse(code)
assert len(list((SELL/'封面与详情图').glob('*.png')))==7
assert len(re.findall(r'^## 笔记\d：',(SELL/'小红书五篇笔记.md').read_text(encoding='utf-8'),re.M))==5

for root in [BUY,SELL]:
    for path in selected_files(root):
        if path.suffix in {'.md','.txt','.json','.py'}:
            text=path.read_text(encoding='utf-8')
            assert 'Users\\zxc' not in text and 'D:\\CodexWork' not in text
        if path.suffix=='.py':ast.parse(path.read_text(encoding='utf-8'))
    assert not any(p.suffix.lower() in {'.sqlite','.sqlite3','.db','.log','.key','.pem'} for p in selected_files(root))

# Every attached upstream implementation still matches its recorded public blob.
upstream=json.loads((BUY/'04-来源与许可/案例源码阅读/source-manifest.json').read_text(encoding='utf-8'))
assert len(upstream)==17
for item in upstream:
    path=BUY/'04-来源与许可/案例源码阅读'/item['path']
    raw=path.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==item['git_blob']
    assert item['license']=='Apache-2.0' and item['runtime_verified'] is False
assert not any('hello-agents' in p.name.lower() for p in selected_files(BUY))

preview=SELL/'免费试看包'
preview_zip=archive(preview,SELL/'AI-Agent免费试看-v1.0.zip','AI-Agent免费试看-v1.0')

manifest={'product':'AI Agent实战入门：Python、RAG与MCP','version':'1.0','release_date':'2026-10-12',
          'lessons':24,'walkthroughs':12,'independent_projects':3,'offline_only_verified':True,
          'files':[{'path':p.relative_to(BUY).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)}
                   for p in selected_files(BUY) if p.name!='交付清单.json']}
(BUY/'交付清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
buyer_zip=archive(BUY,DIST/'AI-Agent实战入门-v1.0-买家交付包.zip','AI-Agent实战入门-v1.0')
seller_zip=archive(SELL,DIST/'AI-Agent实战入门-v1.0-卖家素材包.zip','AI-Agent上架素材-v1.0')

def extract_checked(path,target):
    target.mkdir(parents=True,exist_ok=True)
    assert target.resolve().is_relative_to(QA.resolve())
    with zipfile.ZipFile(path) as z:
        for item in z.infolist():
            assert (target/item.filename).resolve().is_relative_to(target.resolve())
        z.extractall(target)

extracted=QA/'extracted-v1'
extract_checked(buyer_zip,extracted/'buyer')
extract_checked(seller_zip,extracted/'seller')
buyer_root=extracted/'buyer'/'AI-Agent实战入门-v1.0'
for item in manifest['files']:
    target=buyer_root/item['path']
    assert target.is_file() and target.stat().st_size==item['bytes'] and digest(target)==item['sha256']
assert len(selected_files(buyer_root))==len(selected_files(BUY))
seller_root=extracted/'seller'/'AI-Agent上架素材-v1.0'
for source in selected_files(SELL):
    assert digest(seller_root/source.relative_to(SELL))==digest(source)
assert len(selected_files(seller_root))==len(selected_files(SELL))

# Test the actual extracted package, not the authoring directory.
projects=buyer_root/'03-练习项目'
tests=subprocess.run([str(CLEAN),'-X','utf8','-m','unittest','-v','test_projects.py'],cwd=projects,
                     capture_output=True,text=True,encoding='utf-8',timeout=90)
(QA/'extracted-project-tests.txt').write_text(tests.stdout+tests.stderr,encoding='utf-8')
assert tests.returncode==0,tests.stderr
test_count=int(re.search(r'Ran (\d+) tests',tests.stderr)[1])
with tempfile.TemporaryDirectory(dir=QA,prefix='smoke-') as temp:
    assert Path(temp).resolve().is_relative_to(QA.resolve())
    db=Path(temp)/'memory.sqlite3'
    commands=[('tool',[str(CLEAN),'-X','utf8','tool_agent.py','--operation','multiply','--a','18','--b','7']),
              ('memory-first',[str(CLEAN),'-X','utf8','memory_chat.py','--db',str(db),'--session','alice','--message','我在学RAG']),
              ('memory-restore',[str(CLEAN),'-X','utf8','memory_chat.py','--db',str(db),'--session','alice','--message','上次是什么']),
              ('rag',[str(CLEAN),'-X','utf8','document_qa.py','报销材料有哪些？'])]
    smoke={}
    for label,cmd in commands:
        result=subprocess.run(cmd,cwd=projects,capture_output=True,text=True,encoding='utf-8',timeout=15)
        assert result.returncode==0,result.stderr
        smoke[label]=json.loads(result.stdout)
    assert smoke['tool']['observation']['result']==126
    assert '我在学RAG' in smoke['memory-restore']['answer']
    assert '电子发票' in smoke['rag']['answer'] and not smoke['rag']['model_called']

pdf_checks=json.loads((QA/'pdf-verification.json').read_text(encoding='utf-8'))['checks']
for label,path in [('course',BUY/'01-课程讲义/AI-Agent实战入门-24课.pdf'),
                   ('cases',BUY/'02-案例手册/12个案例中文拆解.pdf'),
                   ('preview',SELL/'免费试看包/AI-Agent免费试看.pdf')]:
    reader=PdfReader(path)
    assert len(reader.pages)==pdf_checks[label]['pages']
    assert len('\n'.join(p.extract_text() or '' for p in reader.pages))==pdf_checks[label]['characters']
report={'release_date':'2026-10-12','python':subprocess.check_output([str(CLEAN),'--version'],text=True).strip(),
        'scope':{'lessons':24,'cases':12,'projects':3,'cover':1,'detail_images':6,'social_notes':5},
        'pdfs':pdf_checks,'offline_tests':test_count,'real_model_calls':0,
        'archive_integrity':'passed','extracted_hashes':'passed','extracted_cli_smoke':'passed',
        'upstream_implementation_blobs':17,'upstream_cases_runtime_verified':False,
        'files':{'buyer':len(selected_files(BUY)),'seller':len(selected_files(SELL))},
        'archives':[{'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)} for p in [buyer_zip,seller_zip]],
        'preview_zip':str(preview_zip)}
(QA/'release-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
