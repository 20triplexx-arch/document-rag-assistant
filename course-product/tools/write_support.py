"""Learning guide, provenance, preview, market notes and complete sales copy."""
from pathlib import Path
import hashlib
import json
import shutil
from write_course import LESSONS, document

ROOT = Path(__file__).resolve().parents[1]
BUY = ROOT / 'delivery'
SELL = ROOT / 'marketing'
START = BUY / '00-开始学习'
REF = BUY / '04-来源与许可'
for path in [SELL, START, REF, SELL/'免费试看包']:
    path.mkdir(parents=True, exist_ok=True)

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip()+'\n', encoding='utf-8')

write(BUY/'先读我.md', '''
# AI Agent 实战入门：Python、RAG 与 MCP

版本 v1.0 | 2026-10-12 | 图文自学课程

从“00-开始学习/学习计划.md”开始，按顺序阅读讲义并完成三个基础练习。

## 你收到的内容

- 01-课程讲义：24节完整讲义、课程PDF与可编辑Markdown。
- 02-案例手册：12个案例中文拆解、手册PDF与可编辑Markdown。
- 03-练习项目：工具调用、SQLite会话记忆、文档问答三个独立Python项目及离线测试。
- 04-来源与许可：原文参考索引、案例源码阅读附件、固定版本记录与许可原文。
- 00-开始学习：四周计划、配置与排错、练习答案与验收说明。

## 先跑通，后联网

三个练习默认离线，不需要密钥，也不安装第三方Python包。你需要本机安装Python 3.12，并在练习目录打开终端。联网模式需自行设置DeepSeek密钥和可用模型，可能产生额外API费用。

文档问答基础版只读取UTF-8 Markdown和TXT，采用关键词检索。它不解析PDF、图片，也没有向量数据库。离线输出是原文摘录，联网模式才生成文本。

## 两类案例的验证状态

本包独立编写的三个基础练习经过Windows/Python 3.12独立环境离线测试；联网接口通过离线替身检查消息格式，未调用真实模型验证效果。

上游12个案例已读固定版本说明和源码，17个原有实现入口核对了Git blob；没有安装或运行上游服务。它们是阅读与复现指导，不是12个已经验收的可直接启动项目。源码阅读附件需配合完整上游仓库，不能当完整项目安装包。

## 使用约定

课程交付不含录播视频、真人答疑、软件账号或长期更新承诺。文件缺损与交付问题按购买平台订单规则处理。第三方开源原文和源码继续适用各自许可；课程的新编讲解、排版与素材没有获得第三方品牌背书。

PDF阅读器可使用目录书签跳转；所有Markdown均为UTF-8，建议用支持Markdown的编辑器阅读。源码、终端命令及资料链接均可复制。
''')

plan = '''# 四周学习计划

建议每次45到60分钟，阅读与实践交替。每周安排六次学习和一次回顾；用时是建议，不是学习效果保证。

| 周次 | 主线课程 | 实践与验收 |
| --- | --- | --- |
| 第1周 | 第01到06课 | 建环境、看消息、计算函数与参数错误 |
| 第2周 | 第07到12课 | 看工具循环、SQLite跨进程恢复、检查上下文 |
| 第3周 | 第13到18课 | 切分与来源、关键词问答、人工重排 |
| 第4周 | 第19到24课 | 检索纠错、故障记录、MCP分工、作品说明 |

## 每周回顾

第1周：能解释模型提出调用与程序执行的区别；运行乘法、除零和未知工具样本。

第2周：用两次独立命令恢复alice历史，bob不读取alice；解释数据库历史与模型输入的区别。

第3周：能回查文档问答的文件与行号；对无答案题说明资料不足，不编造到账日期。

第4周：写一个有证据的故障记录，任选一个上游案例画数据流；整理三项作品的成功与失败结果。

## 12个案例怎样选

先读案例01到03，对应三个基础练习。随后按兴趣选择：案例04到08学习检索与诊断；案例09到10学习MCP；案例11到12学习多Agent分工。每次先阅读机制和边界，再决定是否自行安装上游依赖。

## 学习记录模板

| 日期 | 课号或案例 | 我的输入 | 实际结果 | 失败原因或下一步 |
| --- | --- | --- | --- | --- |
| 2026-10-12 | 第05课示例 | 18乘7 | 126 | 下一次测试除零 |

记录中使用虚构或公开资料；截图不要包含密钥、账号、数据库中的私有对话。
'''
write(START/'学习计划.md', plan)

write(START/'配置与排错.md', r'''
# 三个基础练习：配置与排错

## 1. 安装与定位

从[Python官方站点](https://www.python.org/downloads/)获取Python 3.12。若终端没有python命令，使用实际解释器路径；Windows也可尝试py -3.12。

在“03-练习项目”目录打开终端，创建独立环境。直接调用环境解释器，无需修改执行策略：

```powershell
python --version
python -m venv .venv
..venvScriptspython.exe tool_agent.py
```

如果使用py启动器，前两条分别改为py -3.12 --version和py -3.12 -m venv .venv。无需pip安装第三方包。

macOS/Linux使用python3 -m venv .venv与./.venv/bin/python。本次只做Windows实机离线验收。

## 2. 计算工具

```powershell
..venvScriptspython.exe tool_agent.py --operation multiply --a 18 --b 7
..venvScriptspython.exe tool_agent.py --operation divide --a 9 --b 0
```

第一条observation.result为126；第二条observation.ok为false，退出码2，说明除数不能为零。离线参数由命令行给定，不自动理解自然语言。

## 3. 会话保存与恢复

```powershell
..venvScriptspython.exe memory_chat.py --session alice --message "我在学RAG"
..venvScriptspython.exe memory_chat.py --session alice --message "上次说了什么？"
..venvScriptspython.exe memory_chat.py --session bob --history
```

alice第二次能回放第一次输入；bob应返回空列表。默认数据库写入当前工作目录的runtime/learning.sqlite3；需要固定位置时显式传--db。session是本机分组标识，没有身份认证。

## 4. 文档问答

```powershell
..venvScriptspython.exe document_qa.py "报销材料有哪些？"
..venvScriptspython.exe document_qa.py "量子纠缠数学定义"
```

第一条输出材料原文与sources；第二条没有检索结果，不会调用模型。默认读取sample_docs，所有规则都是虚构教学资料。自定义目录用--docs，只接受UTF-8 .md/.txt，单篇大小不超过1 MB。

## 5. 可选联网

只有添加--online才会联网。PowerShell在当前终端设置两个变量；密钥值由你从自己的DeepSeek账户取得，不通过本课程出售：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host "输入你自己的DeepSeek密钥（仅当前终端）" -MaskInput
$env:DEEPSEEK_MODEL = "deepseek-flash"
..venvScriptspython.exe tool_agent.py --online --question "18乘7之后加9"
..venvScriptspython.exe memory_chat.py --online --session online-demo --message "请解释字典"
..venvScriptspython.exe document_qa.py "20日以后提交会怎样？" --online
```

Read-Host -MaskInput适用于PowerShell 7；Windows PowerShell 5.1使用下面的兼容方式：

```powershell
$courseSecret = Read-Host "输入你自己的DeepSeek密钥" -AsSecureString
$courseCredential = [System.Net.NetworkCredential]::new("", $courseSecret)
$env:DEEPSEEK_API_KEY = $courseCredential.Password
Remove-Variable courseCredential, courseSecret
```

程序不会自动加载.env.example，也不会把密钥打印出来。型号deepseek-flash来自制作时的官方接口文档；请使用你账户实际可用的名称。common.py固定请求DeepSeek官方chat/completions，关闭思考模式以简化教学消息，保留最大输出与60秒超时。

每个记忆或问答回合最多一次模型请求，工具循环最多四次请求、八次工具执行。程序不自动重试。请求可能传输本次问题、近期历史或检索片段；费用按账户与实际用量计算，19.9元课程价格不含API费用。

参考[DeepSeek官方文档](https://api-docs.deepseek.com/)。真实联网效果未在本次制作中测试；离线通过不代表线上模型行为通过。

## 6. 运行回归测试

```powershell
..venvScriptspython.exe -m unittest -v test_projects.py
```

测试不会请求模型。联网逻辑使用替身响应检查消息、调用上限与引用错误；跨进程测试使用临时数据库，结束后清理。

## 7. 排错表

| 现象 | 先检查 | 下一步 |
| --- | --- | --- |
| 找不到python | 安装和解释器路径 | 用py -3.12或完整路径 |
| 找不到脚本 | 当前目录 | 进入03-练习项目 |
| 中文乱码 | 文件与终端编码 | 使用UTF-8；必要时python -X utf8 |
| 记忆“消失” | db路径、session | 用相同路径和ID恢复 |
| 文档没命中 | 文件格式、真实关键词 | 先查原文，再改查询 |
| 缺少密钥或型号 | 当前终端变量 | 配置两项后再加--online |
| HTTP 400 | 模型与请求参数 | 查当前官方接口说明 |
| HTTP 401/402 | 凭据或余额 | 自行核对账户 |
| 超时/429 | 网络、限流 | 稍后手动重试，避免重复动作 |
| 引用检查失败 | 输出中的[S编号] | 核对来源，不把无引用答案当可靠结果 |

保存错误类别与命令，不保存密钥。除零退出码2是预期的教学失败，不是安装损坏。
''')

write(START/'验收与版本说明.md', '''
# v1.0 验收与版本说明

制作日期：2026-10-12。课程面向具备函数、字典和终端基础的入门者。

课程新增中文教学编排、24节讲义、12例源码拆解、3个独立标准库练习、四周计划和答案。涉及第三方代码的版权、作者和许可继续保留。

验证分层：离线基础练习包含工具输入校验、轮次上限、跨进程会话恢复、分组过滤、事务失败、上下文裁剪、原文行号、无结果、引用编号异常与配置失败。联网请求仅用替身，不调用真实模型。上游案例只进行固定来源与代码阅读检查。

本包不含语义向量检索实现、OCR、完整MCP服务、浏览器自动化成品或公网部署。相关能力在讲义中说明，在上游案例里提供学习路径。

文件可读、程序可运行、引用编号存在分别只能支持对应验证结论。模型输出的事实、外部服务的当前兼容性和真实业务效果需要另外验收。

如编辑讲义或项目，请同步更新示例、答案和验收记录；不要让售卖文案继续宣传旧版本的内容。
''')

write(BUY/'03-练习项目'/'README.md', r'''
# 3个独立Python练习

Python 3.12标准库，默认离线，零第三方Python依赖。

| 文件 | 功能 | 默认行为 |
| --- | --- | --- |
| tool_agent.py | 工具契约与有上限的模型循环 | 执行命令行给定的算术参数 |
| memory_chat.py | SQLite保存与恢复会话 | 回放上一条输入 |
| document_qa.py | 本地文档检索与来源 | 关键词检索后摘录原文 |
| common.py | DeepSeek请求与错误处理 | 仅在--online路径调用 |
| test_projects.py | 离线回归测试 | 临时数据，替身模型，不联网 |

快速运行：
```powershell
python tool_agent.py --operation multiply --a 18 --b 7
python memory_chat.py --session alice --message "我在学RAG"
python memory_chat.py --session alice --message "上一句是什么？"
python document_qa.py "报销材料有哪些？"
python -m unittest -v test_projects.py
```

完整环境、联网和排错步骤见../00-开始学习/配置与排错.md。

源码是独立教学实现；不调用eval、不自动重试、不读取课程外的账号数据库。运行后生成的runtime属于你的本机数据，交付他人时不要打包它。

关键词评分是词项重叠，不是语义向量或概率。来源检查只验证编号存在，联网结论仍需回查。默认示例规则是虚构资料。
''')

manifest = json.loads((ROOT.parent/'sources-cases.json').read_text(encoding='utf-8'))
allowed = {b['book'] for b in manifest['catalog']['books'] if b['license'] in {'MIT','Apache-2.0'}}
selected = [s for s in manifest['sources'] if s['book'] in allowed]
reference_text = '# 开源原文参考索引与许可\n\n'
reference_text += ('课程新编讲解使用自己的教学结构与示例。以下索引链接到公开原文，原文免费公开；付费内容价值在中文教学编排、案例指导与基础练习。\n\n'
                   '索引共162篇：三套可商用许可的课程150篇和12篇案例说明。这里只提供固定版本索引，不把第三方原文标为本课程独家原创。附件另含17个案例实现文件供阅读核对，不是完整项目安装包。\n\n'
                   '图片、视频、附件和外链文章没有复制到本包，链接访问需要网络。原文是固定快照，不代表当前最新版本。\n\n')
license_dir = REF/'licenses'
license_dir.mkdir(exist_ok=True)
for book in manifest['catalog']['books']:
    if book['book'] not in allowed: continue
    reference_text += f"## {book['display_name']}\n\n仓库：{book['repository']}\n\n固定提交：{book['commit']}\n\n许可：{book['license']}\n\n"
    write(license_dir/(book['book']+'-LICENSE.txt'), book['license_text'])
    for source in selected:
        if source['book'] != book['book']: continue
        url = f"https://github.com/{source['repository']}/blob/{source['commit']}/{source['path']}"
        reference_text += f"- [{source['chapter']}]({url})\n"
    reference_text += '\n'
reference_text += '''## 新增与修改说明

新增：24课中文教学文本、图示、练习答案；12案例中文结构、源码分析与复现指导；3个独立Python标准库练习；封面、详情图与售卖文案。

上游实现附件按固定版本逐字节复制，没有去掉原有作者或版权声明。许可原文单独保留。课程对上游限制与问题的分析是新增教学内容，不代表上游作者背书。

第三方MIT和Apache-2.0内容继续适用相应许可。购买课程不会缩减这些许可授予你的权利，也不代表获得第三方商标、图片、模型账户或服务权限。

课程新编图文、答案、版式与销售素材未额外授予转售许可；第三方开源部分按其原有许可处理。

## 协议与接口参考

- [MCP官方架构说明](https://modelcontextprotocol.io/docs/learn/architecture)：角色与能力概念，2026-10-12查阅。
- [DeepSeek官方接口文档](https://api-docs.deepseek.com/)：接口配置与模型名称，2026-10-12查阅。

较旧上游SDK与当前协议可能存在差异；本课程没有构造或验收一个完整MCP客户端。
'''
write(REF/'原文索引与许可说明.md', reference_text)

# Copy exactly the 17 audited implementation files. No app state or corpus is copied.
review = []
for source in selected:
    if source['book'] != 'awesome-llm-apps-cases': continue
    for item in manifest['catalog']['chapters'][source['source_id']]['implementation_files']:
        original = ROOT/'research'/'upstream'/item['path']
        raw = original.read_bytes()
        actual = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert actual == item['git_blob']
        target = REF/'案例源码阅读'/item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        review.append({'case':source['chapter'],'path':item['path'],'repository':source['repository'],
                       'commit':source['commit'],'git_blob':actual,'sha256':hashlib.sha256(raw).hexdigest(),
                       'license':'Apache-2.0','runtime_verified':False})
write(REF/'案例源码阅读'/'README.md', '''
# 17个固定版本实现入口：仅供源码阅读

这些文件从awesome-llm-apps的固定版本复制，Apache-2.0许可及上游版权保留。来源与Git blob见同目录source-manifest.json。

这不是12个完整项目的发行包：依赖、其他模块、配置、数据库和外部服务不在这里。复现应按案例手册克隆完整上游仓库并切到指定提交，不直接运行这个阅读附件。

本次没有安装或执行上游代码。模型名称、包版本、网页与外部服务可能变化，复现时自行核对。
''')
write(REF/'案例源码阅读'/'source-manifest.json', json.dumps(review,ensure_ascii=False,indent=2))

preview = SELL/'免费试看包'
toc = '# 课程目录与试看说明\n\nAI Agent 实战入门：Python、RAG与MCP | v1.0\n\n'
for lesson in LESSONS:
    toc += f'- 第{lesson[1]}课 {lesson[2]}\n'
toc += '\n完整版包含24节讲义、12个案例拆解、3个标准库基础练习、学习计划与答案。首版试卖19.9元；联网模型费用另计。\n\n试看内容只包含目录、第一课与工具练习节选，不包含完整联网工具循环。\n'
write(preview/'课程目录.md', toc)
write(preview/'第一课.md', document(LESSONS[0]))
write(preview/'工具练习节选.md', '''
# 工具调用练习节选

把模型提出的结构化输入交给一个明确的函数，是工具调用的基础。下面的独立代码不需要密钥，也不请求模型：

```python
def multiply(a, b):
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {"ok": False, "error": "必须是数字"}
    return {"ok": True, "result": a * b}

print(multiply(18, 7))
print(multiply("18", 7))
```

先运行，再回答：为什么第二次返回错误？为什么必须单独判断bool？

参考答案：字符串不是约定的数值类型；Python中bool属于int的子类，仅判断int会把True作为1。

这是单函数节选，省略了完整课程中的工具注册、数值边界、模型消息链和有上限的循环；完整版的3个项目具有独立运行说明与测试。
''')
write(preview/'先读我.md', '''
# 免费试看包

先读课程目录，再读第一课与工具练习节选。PDF包含同样的试看内容；Markdown可直接复制代码。

第一课的三个命令展示完整版项目入口，试看包不附完整项目；可以直接运行工具练习节选中的独立函数。

课程适合会一点Python的入门者。完整版是图文自学文件，不含真人答疑、录播视频或API密钥。
''')

write(SELL/'闲鱼标题与商品详情.md', '''
# 闲鱼上架文案

## 三版标题

1. AI Agent实战入门｜24课12案例3练习
2. Python智能体自学课｜RAG与MCP图文
3. Agent开发入门｜PDF讲义与源码练习

## 价格

首版试卖19.9元。只标实际售价，不虚构划线原价、销量或限时名额。

## 商品详情正文

会一点Python，想开始学Agent，但被工具调用、记忆、RAG和MCP这些词绕住了？这套图文课程把它们按学习顺序讲清，并用三个小项目让你边看边做。

你会收到：

- 24节中文图文课：环境与消息、工具调用、会话记忆、文档问答、检索优化、MCP与多Agent。
- 12个开源案例中文拆解：用途、架构、关键代码、环境、复现步骤、边界和练习答案。
- 3个独立Python基础练习：计算工具、SQLite会话、带来源的文档问答。
- PDF与可编辑Markdown、四周学习计划、练习答案、配置排错说明、来源与许可。

适合已经会运行Python脚本、能读函数和字典的入门者。建议先看免费目录、第一课和工具练习节选，再判断是否适合自己。

三个基础练习默认离线，使用Python3.12标准库，无需模型密钥或第三方Python包；Windows独立环境通过离线回归测试。可选联网需自行配置DeepSeek密钥，API费用另计。联网模型效果未实测。

文档问答基础版是关键词检索，只读取Markdown与TXT。上游12例是源码拆解与复现指导，未运行验收，不承诺12个完整项目一键启动。

这是图文自学课程文件，不含录播、真人答疑、软件账号或长期更新服务。第三方开源原文免费公开，课程付费价值在中文教学编排、案例指导与独立练习，来源和许可在附录保留。

交付方式按本账号支持的平台功能填写，交付完整版压缩包，不索要你的模型密钥。文件缺漏或损坏按订单规则处理；退款事项以平台适用规则为准。

## 发布前填写与核对

选择后台实际允许的课程或数字商品类目，确认本账号支持的交付方式。没有相关类目或经营权限时，先使用目录和试看介绍内容，不伪装成其他商品。

将上述交付方式一句替换为你实际采用的站内交付流程。上架素材是可编辑文案，不代替账户准入检查；本次没有发布商品。
''')

NOTES = [
('别先背框架名，先看懂一次工具调用', '''
学Agent时，最值得先跑通的任务可以很小：让模型把“18乘7”变成一个函数调用，程序算出126，再把结果交回模型。

关键不是模型会不会口算，而是你能不能看见这条链：问题、工具说明、参数、实际执行、观察结果、最终文本。模型说“计算完成”，不等于函数真的执行过。

先把calculate写成普通Python函数，测试正常输入、字符串、除零和未知工具。函数通过后，再接模型循环。这样出了问题，你能判断是参数、函数还是模型接口，不会一上来就盲改提示词。

我整理的《AI Agent实战入门》按这个顺序安排24节图文课，配12例源码拆解与3个基础练习。可先看目录、第一课和工具练习节选；适合会一点Python的人。首版19.9元，模型API费用另计。

#Python学习 #Agent开发 #智能体 #工具调用
'''),
('模型“忘了”：先查保存、恢复、发送这三步', '''
同一句“模型不记得”，可能是三种不同问题：对话只放在进程列表里，退出后没了；数据已经存进SQLite，但恢复时用了另一个session；历史恢复了，却没有加入本次模型请求。

把进程内列表、数据库历史和模型上下文画成三个盒子，问题会清楚很多。先用两个独立命令保存和回放，再切换session检查是否串组。测试跨进程恢复时，不需要先花钱调用模型。

保存全部历史也不等于每次全部发送。上下文有预算，裁剪时尽量保留完整轮次，并说明哪些早期条件可能不在当前输入里。session只是分组键，不能直接当登录权限。

课程的SQLite练习就用这个小流程，24课中另有上下文预算与记忆边界讲解。完整版为PDF、Markdown和代码，先看试看再选择；不含真人答疑。

#SQLite #AI记忆 #Python项目 #Agent学习
'''),
('RAG有引用，为什么还是可能答错？', '''
看到答案后面有[S1]，先别急着认定可靠。你要分别检查三件事：这个编号真的存在吗；文件和行号能回到原文吗；原文真的支持这句话吗。

举一个虚构教学例子：资料说“20日以后提交进入下月审核”。它能支持超期审核规则，却不能支持“下个月1日到账”。虽然话题一样，答案增加了原文没有的日期。

学习时先做关键词检索并显示原文，再接模型生成。无结果就说明缺资料，不强行补答案。记录一条有答案题、一条例外题和一条无答案题，比只展示成功截图更有用。

《AI Agent实战入门》的文档问答练习附虚构资料、来源行号和离线测试。基础版只读Markdown与TXT，关键词检索；向量、混合与重排在课程和案例手册中拆解。

#RAG #知识库 #AI应用开发 #Python
'''),
('MCP先搞懂三个角色，再去接一堆服务', '''
MCP可以先看三个角色：Host承载AI应用，Client管理连接，Server提供能力。服务端可提供工具、资源和提示模板；模型仍由应用调用，协议不负责替你判断任务目标。

把浏览器任务拆开：观察页面、找到控件、执行动作、再观察结果。浏览器打开了，不代表任务完成；服务连接了，也不代表写入操作都被授权。

连接多个服务前，先画一条小数据流。例如读仓库问题、生成待办草稿，到这里并不需要邮箱或日历写权限。真正创建事件时再检查时间、时区、授权和返回ID。

这套课程用主线讲清分工，再拆解浏览器MCP和多服务案例。上游12个案例是源码阅读与复现指导，未运行验收；课程附3个独立基础练习供你先离线学习。

#MCP #智能体开发 #AI工具 #Python入门
'''),
('会一点Python，怎样排一条Agent学习路线', '''
可以把路线拆成四周：第一周看环境、消息与函数工具；第二周看循环、SQLite和上下文；第三周看文档切分、检索、来源与重排；第四周看纠错、故障记录、MCP和角色分工。

每周留一份能检查的结果。计算项目要有正常值和错误输入；记忆项目要能跨进程恢复；文档问答要能回查原文，也能说明资料不足。

最后再读大案例。一个旅行规划应用可能包含前后端、数据库、模型路由和抓取服务，不适合作为第一次环境配置。先把小流程讲明白，再比较框架怎么封装它们。

《AI Agent实战入门》首版包括24课、12个案例拆解、3个标准库练习，提供PDF与可编辑Markdown，试卖19.9元。先看免费试看，确认自己能读函数、字典和终端命令；本课程是图文自学文件。

#Agent自学 #学习路线 #Python #RAG #MCP
'''),
]
notes_text='# 五篇小红书笔记\n\n发布时使用账号实际支持的站内商品或内容入口；本稿不包含站外联系方式、虚构成交或收益承诺。\n\n'
for i,(title,body) in enumerate(NOTES,1):
    notes_text+=f'## 笔记{i}：{title}\n\n{body.strip()}\n\n'
write(SELL/'小红书五篇笔记.md',notes_text)

write(SELL/'售前问答与交付说明.md', '''
# 售前问答

问：完全不会Python能学吗？答：建议先掌握函数、字典、JSON和运行脚本，本课程没有完整Python零基础教学。

问：买到的是视频吗？答：是PDF、可编辑Markdown与代码，不含录播视频。

问：三个练习能离线运行吗？答：默认离线，使用Python3.12标准库，不需要密钥。

问：有没有真实模型效果测试？答：没有。联网格式用替身检查，模型行为与账户可用性需买家自行验证。

问：12个案例全都能直接跑吗？答：12例提供中文源码拆解、复现步骤与边界，未运行验收；完整复现要克隆上游固定版本并自行配依赖与服务。

问：文档问答能读PDF或扫描件吗？答：本包基础练习只读UTF-8 Markdown/TXT，不含PDF解析和OCR。

问：包含向量数据库和MCP服务吗？答：基础练习没有；主线解释机制，案例手册介绍上游实现与复现条件。

问：还需要花多少钱？答：课程首版19.9元；联网模型、外部服务或硬件费用由买家按自己的账户与选择承担。

问：是不是开源资料改个名字卖？答：原文公开可查，课程新增完整学习路线、中文讲解、任务答案、源码分析与3个独立练习，附录保留来源许可，不宣传第三方原文为独家原创。

问：有没有一对一答疑和长期更新？答：首版没有。配置与常见故障提供在文件里，版本交付以v1.0为准。

问：可以先看看吗？答：提供目录、第一课和工具练习节选的免费试看包。

问：文件打不开、少文件怎么办？答：先重新下载和解压；核对交付清单，文件损坏或缺漏按订单处理，退款遵循适用的平台规则。

## 卖家交付步骤

1. 先确认账号可用类目与站内交付功能。
2. 使用封面与六张详情图，填写实际售价19.9元，选择准确的商品形式。
3. 售前提供免费试看ZIP；买家购买完整版后交付“买家交付包”ZIP。
4. 引导买家读“先读我.md”，再读学习计划与配置说明。
5. 不索要买家密钥；售后问题让买家提供脱敏错误类别和命令。

没有相关上架类目或权限时，不通过错误类目伪装发布。没有测试线上功能时，不把它宣传为已验证。上架、上传、收款与自动发货均未在本次执行。
''')

market = '''# 闲鱼挂牌价调研：2026-10-12

渠道：闲鱼网页。Agent课程搜索未提供有效搜索结果；样本来自其相关推荐区，并打开“手搓Agent”详情页核对。它是一个小规模便利样本，存在推荐偏差，不是完整市场抽样。

| 商品 | 挂牌价（元） | 页面可见交付描述 | 链接 |
| --- | --- | --- | --- |
| Agent学习12步完整路线 | 1.99 | 电子学习路线 | https://www.goofish.com/item?id=1077401506364 |
| AI Agent项目实战资料合集 | 2.00 | 电子资料合集 | https://www.goofish.com/item?id=1073272601408 |
| AI Agent自学资料合集 | 1.99 | 自学电子资料 | https://www.goofish.com/item?id=1079827372852 |
| AI Agent 20个实战项目资料包 | 1.00 | 项目资料包 | https://www.goofish.com/item?id=1074708376375 |
| AI Agent学习资料合集 | 1.03 | 电子资料合集 | https://www.goofish.com/item?id=1078761115405 |
| AI Agent智能体开发全套课程 | 6.88 | 课程，内容未进一步核查 | https://www.goofish.com/item?id=1082326775613 |
| 指挥AI做企业Agent，13讲 | 2.99 | 电子资料 | https://www.goofish.com/item?id=1070511589559 |
| 手搓Agent教程 | 16.00 | 卖家描述PDF、源码和配置说明；已打开详情 | https://www.goofish.com/item?id=1083156553339 |
| V8 AI测试课程 | 69.00 | 课程，与本产品受众和形式不同 | https://www.goofish.com/item?id=1064211783678 |

## 定价判断

上述价格仅为观察时的挂牌价，不是成交均价；“想要”不等于购买数量；卖家关于原创、运行和售后的描述未经验证。第三方课程合集的出售授权也未核查，不把它们当作内容来源。

16元的教程描述更接近图文+源码产品。本产品采用24课、12案例拆解与3个基础练习，选择19.9元作为首版试卖价，这是产品定位与有限样本结合后的判断，不保证成交或销量。

没有另行验证小红书成交价，不据此声称两个平台存在稳定价差。后续可以记录真实曝光、询问、试看和成交，自行决定是否调整价格；本次没有设置持续监控或自动调价。
'''
write(ROOT/'research'/'闲鱼价格调研-2026-10-12.md',market)
write(SELL/'闲鱼价格调研-2026-10-12.md',market)

write(ROOT/'README.md', '''
# 课程产品工作目录

delivery为买家文件，marketing为卖家素材，research为来源检查，tools为可复现制作脚本，qa为验收中间产物，dist为最终ZIP。

课程名称：AI Agent实战入门：Python、RAG与MCP。24课、12例拆解、3个基础练习；首版19.9元。现有学有据应用与账号数据不参与交付。

制作脚本只读原资料，并在本目录写入。不要把research、qa或项目根目录整个打包给买家；最终发布使用dist内两个指定ZIP。
''')
print('Wrote learning guide, provenance, source attachment, preview and complete seller copy.')
