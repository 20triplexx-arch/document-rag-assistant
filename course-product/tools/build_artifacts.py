"""Reproducible books and typography-led sales artwork. No remote media."""
from pathlib import Path
import html
import re
import subprocess
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                PageBreak, Flowable, Table, TableStyle, KeepTogether,
                                XPreformatted)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BUY = ROOT / 'delivery'
SELL = ROOT / 'marketing'
QA = ROOT / 'qa'
QA.mkdir(exist_ok=True)
NAVY = '#112638'
BLUE = '#2155E8'
CREAM = '#F5F3ED'
INK = '#172F40'
MUTED = '#586A75'
POPPLER = Path('C:/Users/zxc/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')

pdfmetrics.registerFont(TTFont('CourseBody', 'C:/Windows/Fonts/msyh.ttc'))
pdfmetrics.registerFont(TTFont('CourseBold', 'C:/Windows/Fonts/msyhbd.ttc'))
pdfmetrics.registerFontFamily('CourseBody', normal='CourseBody', bold='CourseBold', italic='CourseBody', boldItalic='CourseBold')

STYLE = {
    'body': ParagraphStyle('body', fontName='CourseBody', fontSize=10, leading=15.3,
                           textColor=colors.HexColor(INK), spaceAfter=4, wordWrap='CJK',
                           splitLongWords=True, allowWidows=0, allowOrphans=0),
    'h1': ParagraphStyle('h1', fontName='CourseBold', fontSize=18, leading=25,
                         textColor=colors.HexColor(NAVY), spaceAfter=12, wordWrap='CJK', keepWithNext=True),
    'h2': ParagraphStyle('h2', fontName='CourseBold', fontSize=11.5, leading=16,
                         textColor=colors.HexColor(NAVY), spaceBefore=6, spaceAfter=4, keepWithNext=True, wordWrap='CJK'),
    'h3': ParagraphStyle('h3', fontName='CourseBold', fontSize=11, leading=18,
                         textColor=colors.HexColor(BLUE), spaceBefore=9, spaceAfter=6, keepWithNext=True, wordWrap='CJK'),
    'code': ParagraphStyle('code', fontName='CourseBody', fontSize=9.1, leading=12.5,
                           backColor=colors.HexColor('#EEF2F5'), textColor=colors.HexColor(INK),
                           borderPadding=6, spaceBefore=5, spaceAfter=10),
    'flow': ParagraphStyle('flow', fontName='CourseBody', fontSize=10, leading=15.5,
                           backColor=colors.HexColor(NAVY), textColor=colors.white,
                           borderPadding=8, spaceBefore=13, spaceAfter=17, wordWrap='CJK'),
    'cell': ParagraphStyle('cell', fontName='CourseBody', fontSize=9, leading=13.5,
                           wordWrap='CJK', textColor=colors.HexColor(INK), splitLongWords=True),
    'toc': ParagraphStyle('toc', fontName='CourseBody', fontSize=10.5, leading=15.5,
                          textColor=colors.HexColor(INK), spaceBefore=0, wordWrap='CJK'),
}

def inline(text):
    text = html.escape(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
                  lambda m: f'<link href="{m[2]}" color="{BLUE}">{m[1]}</link>', text)
    text = re.sub(r'`([^`]+)`', lambda m: f'<font color="{BLUE}">{m[1]}</font>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)

def wrap_code(line, max_width=452):
    # Never introduce line breaks into copyable code. Fix the manuscript instead.
    if pdfmetrics.stringWidth(line, 'CourseBody', 9.1) > max_width:
        raise ValueError('Code line too wide; format the manuscript: ' + line)
    return [line]

def markdown_story(text, label):
    lines, story, i, section = text.splitlines(), [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.strip() == '<!-- pagebreak -->':
            story.append(PageBreak());i+=1;continue
        if line.startswith('```'):
            i += 1; code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code += wrap_code(lines[i])
                i += 1
            story.append(XPreformatted(html.escape('\n'.join(code)), STYLE['code']))
            i += 1; continue
        if line.startswith('|') and i+1 < len(lines) and re.match(r'^\|[\s:|\-]+\|$', lines[i+1]):
            rows=[]
            while i < len(lines) and lines[i].startswith('|'):
                if not re.match(r'^\|[\s:|\-]+\|$', lines[i]):
                    rows.append([Paragraph(inline(cell.strip()), STYLE['cell']) for cell in lines[i].strip('|').split('|')])
                i += 1
            count=max(len(row) for row in rows)
            widths=([108, 374] if count==2 else [100,180,202] if count==3 else [95,120,140,127] if count==4 else [482/count]*count)
            table=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E6ECF2')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
                ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),
                ('BOTTOMPADDING',(0,0),(-1,-1),7),
                ('LINEBELOW',(0,0),(-1,0),0.7,colors.HexColor('#CDD7E0')),
                ('LINEBELOW',(0,1),(-1,-1),0.35,colors.HexColor('#DFE5EA'))]))
            story.extend([table,Spacer(1,12)]); continue
        if line.startswith('# '):
            title=line[2:].strip()
            if story and title.startswith(('第','案例')):
                story.append(PageBreak())
            paragraph=Paragraph(inline(title),STYLE['h1'])
            paragraph.bookmark_key=f'{label}-section-{section}'
            section+=1
            story.append(paragraph); i+=1; continue
        if line.startswith('## '):
            story.append(Paragraph(inline(line[3:]),STYLE['h2']));i+=1;continue
        if line.startswith('### '):
            story.append(Paragraph(inline(line[4:]),STYLE['h3']));i+=1;continue
        if line.startswith('> '):
            story.append(Paragraph(inline(line[2:]),STYLE['flow']));i+=1;continue
        if line.startswith('- '):
            story.append(Paragraph('• '+inline(line[2:]),STYLE['body']));i+=1;continue
        para=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','```','> ','|','- ')):
            para.append(lines[i]);i+=1
        story.append(Paragraph(inline(' '.join(para)),STYLE['body']))
    return story

class Cover(Flowable):
    def __init__(self, title, subtitle, count):
        super().__init__();self.width=482;self.height=690
        self.title=title;self.subtitle=subtitle;self.count=count
    def draw(self):
        c=self.canv
        c.setFillColor(colors.HexColor('#9EBDE6'))
        c.setFont('CourseBody',11);c.drawString(0,636,'学习 • 执行 • 核对')
        c.setFillColor(colors.white);c.setFont('CourseBold',36)
        for i,line in enumerate(self.title):c.drawString(0,545-i*57,line)
        c.setFont('CourseBody',13);c.setFillColor(colors.HexColor('#CFDBE7'))
        c.drawString(0,382,self.subtitle)
        c.setStrokeColor(colors.HexColor('#4A6579'));c.line(0,345,482,345)
        c.setFont('CourseBold',19);c.setFillColor(colors.white);c.drawString(0,295,self.count)
        c.setFont('CourseBody',11);c.setFillColor(colors.HexColor('#CFDBE7'))
        c.drawString(0,230,'面向会一点 Python 的入门者')
        c.drawString(0,202,'先运行基础练习，再阅读进阶案例')
        c.setFillColor(colors.HexColor('#7D9BAE'));c.setFont('CourseBody',10)
        c.drawString(0,70,'v1.0 / 2026.10.12 / 图文自学课程')

class Book(BaseDocTemplate):
    def __init__(self,path,label):
        super().__init__(str(path),pagesize=A4,leftMargin=56,rightMargin=57,
                         topMargin=58,bottomMargin=53,title=label,author='AI Agent 实战入门课程',
                         pageCompression=1)
        self.label=label
        self.addPageTemplates(PageTemplate(id='book',frames=[Frame(56,49,482,740,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.page))
    def page(self,c,doc):
        c.saveState()
        if doc.page==1:
            c.setFillColor(colors.HexColor(NAVY));c.rect(0,0,A4[0],A4[1],fill=1,stroke=0)
        else:
            c.setStrokeColor(colors.HexColor('#DCE3E8'));c.line(56,807,538,807)
            c.setFont('CourseBody',8);c.setFillColor(colors.HexColor(MUTED))
            c.drawString(56,817,self.label)
            c.drawString(56,30,'v1.0 / 教学资料 / 来源许可见附录')
            c.drawRightString(538,30,str(doc.page))
        c.restoreState()
    def afterFlowable(self,flowable):
        if getattr(flowable,'bookmark_key',None):
            text=flowable.getPlainText();key=flowable.bookmark_key
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text,key,0,False)
            self.notify('TOCEntry',(0,text,self.page,key))

def make_book(path,label,title,subtitle,count,body):
    toc=TableOfContents();toc.levelStyles=[STYLE['toc']]
    story=[Cover(title,subtitle,count),PageBreak(),Paragraph('目录',STYLE['h1']),toc,PageBreak()]
    story+=markdown_story(body,label)
    doc=Book(path,label);doc.multiBuild(story)
    reader=PdfReader(path)
    print(f'{path.name}: {len(reader.pages)} pages, {len(reader.outline)} bookmarks')
    return len(reader.pages)

def text_at(c,text,x,y,size=32,color=INK,bold=False,width=None,leading=None):
    font='CourseBold' if bold else 'CourseBody'
    c.setFillColor(colors.HexColor(color));c.setFont(font,size)
    if width is None:
        c.drawString(x,y,text);return y
    current='';rows=[]
    for char in text:
        if char=='\n':rows.append(current);current='';continue
        if current and pdfmetrics.stringWidth(current+char,font,size)>width:
            rows.append(current);current=char
        else:current+=char
    rows.append(current)
    for row in rows:c.drawString(x,y,row);y-=leading or size*1.45
    return y

def poster(c,index):
    W,H=1080,1440
    dark=index in [0,2,4,6]
    bg=NAVY if dark else CREAM
    fg='#FFFFFF' if dark else INK
    secondary='#B4C9DA' if dark else MUTED
    c.setFillColor(colors.HexColor(bg));c.rect(0,0,W,H,fill=1,stroke=0)
    c.setStrokeColor(colors.HexColor('#2A4459' if dark else '#D4DCD9'))
    c.line(72,1330,1008,1330);c.line(72,108,1008,108)
    text_at(c,'AI AGENT / 实战入门',72,1360,25,secondary)
    text_at(c,'图文自学课程 · v1.0',72,61,25,secondary)
    text_at(c,f'{index:02d}',947,61,25,secondary)
    if index==0:
        text_at(c,'会一点 Python，从这里开始',72,1261,34,secondary)
        text_at(c,'AI Agent',66,1099,112,fg,True)
        text_at(c,'实战入门',66,945,112,fg,True)
        text_at(c,'Python / RAG / MCP',72,837,40,'#9BBAFF')
        c.setStrokeColor(colors.HexColor('#456178'));c.line(72,770,1008,770)
        for x,value,label in [(72,'24','节中文图文课'),(391,'12','个案例拆解'),(710,'03','个基础练习')]:
            text_at(c,value,x,621,85,fg,True)
            text_at(c,label,x,567,29,secondary)
        text_at(c,'把工具、记忆和文档问答连起来',72,448,36,fg,True)
        text_at(c,'PDF + 可编辑讲义 + Python 代码',72,391,31,secondary)
        c.setFillColor(colors.HexColor(BLUE));c.rect(72,207,426,109,fill=1,stroke=0)
        text_at(c,'首版试卖  ¥19.9',102,244,38,'#FFFFFF',True)
        text_at(c,'先看目录与免费试看',543,248,30,secondary)
        text_at(c,'联网模型费用另计',72,145,24,secondary)
    elif index==1:
        text_at(c,'01 / 学什么',72,1267,32,BLUE,True)
        text_at(c,'一条清楚的学习路线',72,1155,64,fg,True)
        modules=[('01','认识 Agent','环境 · 消息 · 模型调用 · 工作流'),
                 ('02','工具调用','函数工具 · 参数 · 循环 · 错误'),
                 ('03','会话与记忆','历史 · SQLite · 上下文 · 边界'),
                 ('04','文档问答','切分 · 检索 · 生成 · 来源核对'),
                 ('05','RAG 优化','混合 · 重排 · 纠错 · 故障诊断'),
                 ('06','MCP 与协作','协议 · 浏览器 · 多服务 · 分工')]
        y=1000
        for num,title,detail in modules:
            text_at(c,num,72,y,35,BLUE,True)
            text_at(c,title,180,y,37,fg,True)
            text_at(c,detail,180,y-54,27,MUTED)
            c.setStrokeColor(colors.HexColor('#D4DCD9'));c.line(72,y-84,1008,y-84)
            y-=130
        text_at(c,'每课都有示例、任务、答案与常见问题',72,161,28,BLUE,True)
    elif index==2:
        text_at(c,'02 / 先跑通三个小项目',72,1267,32,'#9BBAFF',True)
        text_at(c,'从代码到可检查的结果',72,1155,64,fg,True)
        items=[('01','计算工具','18 × 7 = 126','测试参数、除零与未知工具'),
               ('02','会话记忆','关闭，再打开','用 SQLite 保存并恢复上一轮'),
               ('03','文档问答','回答之前先找资料','显示原文、文件名与行号')]
        y=988
        for num,title,result,detail in items:
            text_at(c,num,72,y,45,'#9BBAFF',True)
            text_at(c,title,191,y,42,fg,True)
            text_at(c,result,191,y-78,39,fg)
            text_at(c,detail,191,y-137,29,secondary)
            c.setStrokeColor(colors.HexColor('#345067'));c.line(72,y-181,1008,y-181)
            y-=257
        text_at(c,'默认离线 · Python 3.12 标准库',72,166,31,'#9BBAFF',True)
    elif index==3:
        text_at(c,'03 / 12 份源码拆解',72,1267,32,BLUE,True)
        text_at(c,'看懂案例怎么连接',72,1155,66,fg,True)
        titles=['函数工具','SQLite 会话','本地 RAG','混合检索与重排','检索纠错','Agentic RAG',
                '知识图谱与引用','RAG 故障诊断','浏览器 MCP','多 MCP 服务','多 Agent 研究','多 Agent 旅行']
        for i,title in enumerate(titles):
            x=72+(i%2)*484;y=991-(i//2)*127
            text_at(c,f'{i+1:02d}',x,y,29,BLUE,True)
            text_at(c,title,x+66,y,29,fg,True,width=382)
            c.setStrokeColor(colors.HexColor('#D4DCD9'));c.line(x,y-56,x+426,y-56)
        text_at(c,'用途 · 架构 · 代码 · 步骤 · 边界 · 练习',72,195,28,BLUE,True)
        text_at(c,'上游案例未运行验收，完整复现需自行配置',72,145,25,MUTED)
    elif index==4:
        text_at(c,'04 / 文档问答练习',72,1267,32,'#9BBAFF',True)
        text_at(c,'让答案有地方可查',72,1155,70,fg,True)
        text_at(c,'问：报销需要哪些材料？',72,1000,38,fg,True)
        c.setFillColor(colors.HexColor('#1D3A51'));c.rect(72,690,936,233,fill=1,stroke=0)
        text_at(c,'离线摘录 [S1]',102,864,30,'#9BBAFF',True)
        text_at(c,'需要电子发票、费用明细和审批记录。',102,797,32,fg,width=855)
        text_at(c,'来源：报销规则.md / 原文行范围',102,727,27,secondary)
        text_at(c,'01  找资料',72,588,35,fg,True)
        text_at(c,'02  核对文件与行号',72,508,35,fg,True)
        text_at(c,'03  检查原文是否支持结论',72,428,35,fg,True)
        text_at(c,'关键词检索 · Markdown / TXT',72,290,31,'#9BBAFF',True)
        text_at(c,'示例为虚构资料；联网生成需自行配置模型',72,202,25,secondary)
        text_at(c,'基础练习不含 PDF 解析与向量数据库',72,158,25,secondary)
    elif index==5:
        text_at(c,'05 / 四周学习建议',72,1267,32,BLUE,True)
        text_at(c,'每周留下一份成果',72,1155,70,fg,True)
        weeks=[('第1周','环境与工具','跑通计算，解释参数与错误'),('第2周','循环与记忆','重启后恢复，检查会话分组'),
               ('第3周','检索与来源','命中原文，核对答案的依据'),('第4周','诊断与协作','记录故障，整理三项作品')]
        y=988
        for week,title,detail in weeks:
            text_at(c,week,72,y,32,BLUE,True)
            text_at(c,title,271,y,41,fg,True)
            text_at(c,detail,271,y-66,29,MUTED)
            c.setStrokeColor(colors.HexColor('#D4DCD9'));c.line(72,y-106,1008,y-106)
            y-=194
        text_at(c,'每次45至60分钟，按自己的节奏学习',72,167,28,BLUE,True)
    else:
        text_at(c,'06 / 收到文件，怎样开始',72,1267,32,'#9BBAFF',True)
        text_at(c,'先读，再跑，再核对',72,1155,70,fg,True)
        items=[('01','打开「先读我」','确认学习入口与项目说明'),('02','按四周计划读讲义','PDF书签跳转，Markdown可编辑'),
               ('03','运行默认离线练习','不需要密钥，不安装第三方Python包'),('04','核对原文与参考答案','先理解结果，再尝试可选联网')]
        y=987
        for num,title,detail in items:
            text_at(c,num,72,y,40,'#9BBAFF',True)
            text_at(c,title,180,y,37,fg,True)
            text_at(c,detail,180,y-63,27,secondary)
            y-=189
        text_at(c,'图文文件交付 · 适合有 Python 基础的入门者',72,177,27,'#9BBAFF',True)
        text_at(c,'不含录播、真人答疑或软件账号',72,132,24,secondary)

def make_posters():
    target=SELL/'封面与详情图';target.mkdir(exist_ok=True)
    names=['00-课程封面','01-课程目录','02-三个练习','03-十二案例','04-来源核对','05-学习计划','06-交付入口']
    artwork=QA/'sales-artwork.pdf'
    c=canvas.Canvas(str(artwork),pagesize=(1080,1440),pageCompression=1)
    for i in range(7):poster(c,i);c.showPage()
    c.save()
    temp=QA/'poster-renders';temp.mkdir(exist_ok=True)
    subprocess.run([str(POPPLER),'-r','72','-png',str(artwork),str(temp/'image')],check=True,capture_output=True)
    for i,name in enumerate(names,1):
        image=Image.open(temp/f'image-{i}.png').convert('RGB')
        assert image.size==(1080,1440)
        image.save(target/(name+'.png'))
    print('Rendered 1 cover and 6 detail images at 1080 x 1440.')

def build():
    main=(BUY/'01-课程讲义'/'课程完整讲义.md').read_text(encoding='utf-8')
    # The cover carries the title; do not duplicate it in the body.
    main='\n'.join(main.splitlines()[4:])
    main=main.split('\n\n<!-- pagebreak -->\n\n# 继续学习与来源')[0]
    main+='\n\n<!-- pagebreak -->\n\n# 继续学习与来源\n\n24课练习参考答案和四周计划位于00-开始学习；12案例另有完整手册PDF。原文参考索引与许可位于04-来源与许可。\n\n'
    main+='三个基础练习默认离线，联网效果未实测；上游案例未运行验收。关键词与向量检索的实现边界在配置说明中列明。\n'
    main+='''
## 选择下一条练习路线

| 方向 | 对应案例 | 做出一项可检查的改进 |
| --- | --- | --- |
| 检索优化 | 案例04到08 | 为同义题和无答案题建回归表 |
| 工具集成 | 案例09到10 | 画清读取、草稿与写入边界 |
| 多Agent分工 | 案例11到12 | 定义交付字段与约束检查 |

先完成基础练习并写出局限，再自行决定是否安装上游框架。运行项目时用独立环境和公开或虚构资料，保存真实结果，不把尝试动作当作任务完成。

## 原文与许可

课程新增中文讲解、练习和教学结构。相关开源原文免费公开，以下名称仅用于附录来源识别，不代表课程获得第三方官方背书。

| 来源 | 许可 | 阅读位置 |
| --- | --- | --- |
| Agentic AI学习路线 | MIT | 04-来源与许可中的固定版本索引 |
| Microsoft AI Agents | MIT | 同一索引中的Microsoft目录 |
| Hugging Face Agents | Apache-2.0 | 同一索引中的Hugging Face目录 |
| awesome-llm-apps案例 | Apache-2.0 | 案例手册链接与17个实现阅读附件 |

许可原文保存在04-来源与许可/licenses。源码附件保留上游内容，供回查，不是12个完整安装包。第三方开源部分继续按原有许可使用。

## 复习时问自己

工具真的执行了吗？历史真的传给模型了吗？资料真的回答了问题吗？引用真的支持了结论吗？把这四个问题与执行记录放在一起，才能说明你掌握了数据流。
'''
    closing=main.split('\n\n<!-- pagebreak -->\n\n',1)[1]
    (BUY/'01-课程讲义'/'继续学习与来源.md').write_text(closing,encoding='utf-8')
    (BUY/'01-课程讲义'/'课程完整讲义.md').write_text(
        '# AI Agent 实战入门\n\nPython、RAG 与 MCP | v1.0 | 2026-10-12\n\n'+main,encoding='utf-8')
    cases=(BUY/'02-案例手册'/'案例完整手册.md').read_text(encoding='utf-8')
    preview_dir=SELL/'免费试看包'
    preview='\n\n'.join((preview_dir/name).read_text(encoding='utf-8') for name in ['课程目录.md','第一课.md','工具练习节选.md'])
    results={}
    results['course_pages']=make_book(BUY/'01-课程讲义'/'AI-Agent实战入门-24课.pdf','AI Agent 实战入门',
                                     ['AI Agent','实战入门'],'Python / RAG / MCP','24节图文课 · 3个基础练习',main)
    results['case_pages']=make_book(BUY/'02-案例手册'/'12个案例中文拆解.pdf','12个案例中文拆解',
                                   ['12个实战案例','中文拆解'],'固定版本源码阅读与复现指导','用途 · 架构 · 代码 · 边界 · 练习',cases)
    results['preview_pages']=make_book(preview_dir/'AI-Agent免费试看.pdf','AI Agent 免费试看',
                                      ['AI Agent','免费试看'],'先看目录，再判断是否适合','课程目录 · 第一课 · 工具练习节选',preview)
    make_posters()
    import json
    (QA/'artifact-counts.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results

if __name__=='__main__':
    print(build())
