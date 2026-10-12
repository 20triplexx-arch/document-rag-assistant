"""Check every PDF page and render all pages for a visual layout review."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import re
import pdfplumber
from pypdf import PdfReader
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
POPPLER=Path('C:/Users/zxc/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
pdfs=[('course',ROOT/'delivery/01-课程讲义/AI-Agent实战入门-24课.pdf'),
      ('cases',ROOT/'delivery/02-案例手册/12个案例中文拆解.pdf'),
      ('preview',ROOT/'marketing/免费试看包/AI-Agent免费试看.pdf')]
report={}
for label,path in pdfs:
    reader=PdfReader(path)
    text='\n'.join(page.extract_text() or '' for page in reader.pages)
    assert '\ufffd' not in text
    if label=='course':
        for i in range(1,25):assert f'第{i:02d}课' in text
        assert 'python tool_agent.py' in text and '电子发票' in text
    if label=='cases':
        for i in range(1,13):assert f'案例{i:02d}' in text
        assert '0.85' in text and '未运行' in text
    for destination in reader.outline:
        assert 0 <= reader.get_destination_page_number(destination) < len(reader.pages)
    blank=[];bounds=[];char_counts=[]
    with pdfplumber.open(path) as document:
        for number,page in enumerate(document.pages,1):
            char_counts.append(len(page.chars))
            body=[ch for ch in page.chars if ch['top']>45 and ch['bottom']<page.height-45]
            if number>1 and len(body)<15:blank.append(number)
            for ch in page.chars:
                if ch['x0'] < -1 or ch['x1']>page.width+1 or ch['top'] < -1 or ch['bottom']>page.height+1:
                    bounds.append({'page':number,'char':ch['text'],'bbox':[ch['x0'],ch['top'],ch['x1'],ch['bottom']]})
    assert not blank, f'{label}: blank pages {blank}'
    assert not bounds, f'{label}: out-of-page characters {bounds[:3]}'
    report[label]={'pages':len(reader.pages),'bookmarks':len(reader.outline),'characters':len(text),
                   'blank_pages':blank,'out_of_page_characters':bounds,'links':sum(len(p.get('/Annots',[])) for p in reader.pages)}

def render(job):
    label,path=job
    folder=ROOT/'qa'/'rendered'/label;folder.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(POPPLER),'-r','105','-png',str(path),str(folder/'page')],check=True,capture_output=True)
    files=sorted(folder.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
    files=[p for p in files if int(p.stem.split('-')[-1]) <= report[label]['pages']]
    assert len(files)==report[label]['pages']
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    sheets=ROOT/'qa'/'contact-sheets';sheets.mkdir(exist_ok=True)
    paths=[]
    for offset in range(0,len(files),6):
        group=files[offset:offset+6]
        sheet=Image.new('RGB',(1032,2214),'#d9dfe4')
        draw=ImageDraw.Draw(sheet)
        for n,file in enumerate(group):
            page=Image.open(file).convert('RGB');page.thumbnail((490,697))
            x=18+(n%2)*512;y=32+(n//2)*738
            draw.text((x,y-25),f'{label} / {offset+n+1:02d}',font=font,fill='#172f40')
            sheet.paste(page,(x,y))
        target=sheets/f'{label}-{offset//6+1:02d}.jpg'
        sheet.save(target,quality=91)
        paths.append(str(target))
    return {'label':label,'rendered_pages':len(files),'contact_sheets':paths}

with ThreadPoolExecutor(max_workers=3) as pool:
    images=list(pool.map(render,pdfs))
(ROOT/'qa'/'pdf-verification.json').write_text(json.dumps({'checks':report,'rendering':images},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
print(json.dumps(images,ensure_ascii=False))
