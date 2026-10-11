# 首批课程扩库与验证 · 2026-10-10

更新日期：2026-10-10（Asia/Shanghai）。用户已确认本轮只接入 Microsoft 与 Hugging Face，RAG_Techniques 留待下一批。

## 已发布的本机快照

默认来源为根目录 `sources-expanded.json`，默认语料为 `data/courses-20261010-v1/`；配置入口是 `study_rag/settings.py`。网页与 CLI 共用这套范围。

| 教材 ID（展示顺序） | 篇数 | 片段数 | 固定提交 | 仓库许可 |
| --- | ---: | ---: | --- | --- |
| `awesome-agentic-ai-zh` | 71 | 1253 | `50fc26d5decc1f3ee8a9e67b9f2c807e179e01d6` | MIT |
| `Hello-Agents` | 54 | 1942 | `6acdf9527f9c229b173f26d66bee2f6831d6c93a` | CC BY-NC-SA 4.0 |
| `microsoft-ai-agents` | 19 | 465 | `ff2ba665e088bf51d9959126c5893e089b50da30` | MIT |
| `huggingface-agents` | 60 | 422 | `3c469e773ec04e5f338b727ff20e3a6ea823ff81` | Apache-2.0 |
| 合计 | 204 | 4082 | 四个固定版本 | 各自保留许可 |

新快照语料版本：`317eae4a54ab58308f753eab459b2dd04539f475978d2093b4c0c307a41f1b43`。
旧两套快照版本：`d5c4e3b02f6c5a8864714d8a39975dc3dee075ae16c490dc689f0132c7ab02aa`。

原有 125 篇的来源 ID、章节声明、仓库、提交、路径、原文字节及 3195 个片段保持一致；旧 `sources-full.json`、`data/fulltext-20261009-v2/` 和账号库继续保留。

## 收录与语言规则

- [Microsoft 固定版本](https://github.com/microsoft/ai-agents-for-beginners/tree/ff2ba665e088bf51d9959126c5893e089b50da30)：只收 00～18 课的主线 `README.md`，优先对应 `translations/zh-CN/` 文件；没有中文时收英文主线文件。共 19 篇。
- [Hugging Face 固定版本](https://github.com/huggingface/agents-course/tree/3c469e773ec04e5f338b727ff20e3a6ea823ff81)：按英文 `_toctree.yml` 顺序收 unit0～4、bonus-unit1～3 的 60 篇 MDX 教学正文，包含框架子目录。排除 `quiz`、`discord101`、`get-your-certificate`、`additional-readings` 页面及导航 README。中文优先 `units/zh-CN/`，其中英文 `bonus-unit2` 显式对应中文 `bonus_unit2`；缺中文时收对应英文文件。
- 每个主线章节仅保留一个语言版本，来源 ID 由主线路径稳定生成。v2 的 `canonical_path` 保存章节关系，不把中文目录拼写差异当作新章节。
- 本轮新增 79 篇都有中文文件，英文补缺为 **0**。英文补缺与语言去重用离线合成缺口验证，不声称实际导入了英文补缺。没有调用模型翻译；上游中文文件中的英文术语和未翻译段落仍按原文保留。
- 不执行教材代码，不安装课程框架，不解析图片、附件、视频、外链正文。Hugging Face 的入门/结课教学说明保留；纯测验和社交操作页不收录。

许可原文、路径和 Git blob 保存在 v2 来源目录与快照契约中。新增许可一手文件为 [Microsoft LICENSE](https://github.com/microsoft/ai-agents-for-beginners/blob/ff2ba665e088bf51d9959126c5893e089b50da30/LICENSE) 和 [Hugging Face LICENSE](https://github.com/huggingface/agents-course/blob/3c469e773ec04e5f338b727ff20e3a6ea823ff81/LICENSE)；网页依照教材目录展示许可。

## 实现与引用

v2 将教材显示名、顺序、许可原文与章节语言、章节顺序、对应路径、Git blob、字节数纳入语料版本哈希与索引契约；v1 原快照仍可读取和复核。未知教材 ID 在网页返回 422，CLI 同样拒绝，不预留调用额度、不生成答案。

MDX 的 import/export、多行 JSX 标签、媒体与展示语法使用等长空白遮罩，保留换行和位置；保留容器中的教学正文、表格、代码块。切分时用遮罩识别标题，代码内伪标题不形成章节；片段仍保存原文件内容与字符/行范围，引用指向固定提交原文件的行号。概念检索进一步屏蔽代码、习题和纯资料链接区域，CLI 原文检索保留教学代码和参考链接文本。

网页卡片、下拉框、目录由 `/api/library` 生成，默认“全部教材”；保留选择联动、目录搜索、白色聊天布局和手机样式。每套最多两个概念证据，跨四套最多八个，允许引用 E1～E8；基础中英术语别名覆盖工具、规划、上下文、记忆等概念。讲解继续最多一次模型调用，调用额度、同源保护、账号讨论隔离和引文出处核对保留。

## 验证结果

2026-10-10：67 项后端测试、11 项前端测试通过，依赖检查、Python/JavaScript 语法检查通过。新测试覆盖四套筛选、未知教材 422、许可与顺序、英文补缺、语言去重、中文附加单元映射、MDX 多行组件与代码伪标题、教学正文和表格保留、原始行号回查、E8 引文和跨四套单次调用。

离线逐篇复核 204 篇的 SHA-256、字节数和 Git blob；重建期望片段并对照持久索引，字符范围并集覆盖全部非空白原文。原有 125 篇逐篇比较声明与字节。重复导入返回 `CORPUS_REUSED` 与 `INDEX_REUSED`，网络请求为 0。

两套新课均抽查工具、记忆、Agentic RAG、可观测性问题，检索片段可回查固定原文件行范围；Microsoft 命中工具第 04 课、记忆第 13 课、Agentic RAG 第 05 课和生产可观测性第 10 课，Hugging Face 命中对应框架/Agentic RAG/可观测性附加单元正文。抽查是关键词召回和引用位置核对，没有固定题集的召回率或答案质量结论；记忆匹配可能只讨论框架状态，不必然完整解释长期记忆。

所有生成测试使用离线替身，**真实模型调用为 0**。引文存在不代表结论得到支持；语义检索、固定题集、答案支持评测与公网部署仍未验收。

详细运行报告在忽略提交的 `data/courses-20261010-v1/coverage.json`、`output/expansion-retrieval-check.json`、`output/expansion-verification.log`。账号表只核对汇总与内容一致性，不把账号资料写入文档；本轮没有修改账号或讨论表结构。

切换后本机 `/api/library` 返回 200，确认四套顺序、204 篇、4082 个片段与正确许可；页面已实际加载四张教材卡片及“全部教材”默认范围。六张账号相关表的记录内容与切换前一致，原两套全部 3195 个片段的 ID 和文本也逐项相同。服务运行状态属于 2026-10-10 当时的检查结果，后续接手需重新确认。

## 复现、复用与回退

已有当前快照时，以下命令离线校验或复用；`search` 不调用模型：

```powershell
.\.venv\Scripts\python.exe starter.py verify
.\.venv\Scripts\python.exe starter.py import
.\.venv\Scripts\python.exe expanded_import.py
.\.venv\Scripts\python.exe starter.py search '工具调用' --book microsoft-ai-agents
.\.venv\Scripts\python.exe starter.py search '可观测性' --book huggingface-agents
```

没有当前快照的新环境可以直接 `starter.py import` 按已保存 v2 清单下载并核对公开原文，不需要重新审计目录。要完整重复审计：先运行 `fulltext_import.py --discover` 重建原两套快照，再运行 `expanded_import.py --discover` 审计固定 Git 树并导入扩库快照。审计需要访问 GitHub，但不请求模型。清单不匹配已有快照时拒绝覆盖；需要另建目录，不删除现有教材。

旧快照离线复核：

```powershell
.\.venv\Scripts\python.exe starter.py --data-dir data/fulltext-20261009-v2 verify
```

切换先完成快照与测试验证；`.\stop.ps1` 核对本目录监听进程和活跃讲解，拒绝中断进行中的生成。服务继续本机 `127.0.0.1:8765`，账号库仍是 `output/users.sqlite3`。需要回退时，先确认讲解结束并停止服务，将 `study_rag/settings.py` 的默认目录与来源改回 `data/fulltext-20261009-v2` 和 `sources-full.json`，核对旧快照后执行 `.\background.ps1`。代码支持旧 v1 契约，网页将自动恢复两套目录；不回滚或覆盖账号库。

回到 [README](../README.md)。
