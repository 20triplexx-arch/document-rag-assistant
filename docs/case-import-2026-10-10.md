# 首批 GitHub 实战案例 · 2026-10-10

用户选择“GitHub 实战案例入库”。本批从 [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) 筛选 12 个案例；2026-10-10 GitHub API 记录为 141,024 stars，星数只表示该次查询。固定提交为 `4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2`，[根目录许可](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/LICENSE)为 Apache-2.0。

## 范围与快照

默认来源 `sources-cases.json`，默认快照 `data/courses-cases-20261010-v1/`。四套课程保持 204 篇、4082 个片段，新增 12 篇案例 README、138 个片段；合计 **216 篇、4220 个片段**。案例集合 ID：`awesome-llm-apps-cases`，排在四套课程之后。

快照版本：`14830ef070b791490d7b73b177d94101931ed372d3f0eb58f38907f15947bcb2`。
前一版本四套课程：`317eae4a54ab58308f753eab459b2dd04539f475978d2093b4c0c307a41f1b43`。

新增 12 篇均为英文；没有对应中文文件，采用英文原文并标注语言，不调用模型翻译。中文标题和主题是本地目录元数据，不冒称上游译文。每个案例只收一个语言版本；原有 204 篇的来源声明、字节、元数据与 4082 个片段 ID/文本保持一致，原快照保留。

收录案例说明、架构/学习目标、运行说明以及 README 内的代码块和表格。17 个 Python 实现入口按固定 Git 树核对路径、blob 和大小，作为目录链接提供；**这些独立实现文件没有入库为正文，也没有运行**。不安装案例框架，不启动 Ollama、Qdrant、Neo4j 或案例服务，不请求案例依赖的模型/API，不登录其第三方服务。

## 案例清单

| 中文目录标题 | 主题 | 固定版本原文 |
| --- | --- | --- |
| 自定义工具调用（Function Tools） | 函数参数、注册、错误处理 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/README.md) |
| 持久会话与记忆（SQLite） | 会话持久化、恢复 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/5_memory_agent/5_2_persistent_conversation_agent/README.md) |
| 本地文档问答（Local RAG） | 本地模型、向量检索 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/local_rag_agent/README.md) |
| 混合检索与重排（Hybrid RAG） | 关键词/语义检索、重排 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/hybrid_search_rag/README.md) |
| 检索纠错（Corrective RAG） | 相关性评估、查询改写 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/corrective_rag/README.md) |
| 带推理的 Agentic RAG | 推理、知识库 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/agentic_rag_with_reasoning/README.md) |
| 知识图谱与可核对引用 | 多跳检索、来源追踪 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/knowledge_graph_rag_citations/README.md) |
| RAG 故障诊断 | 失败模式、调试 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/rag_failure_diagnostics_clinic/README.md) |
| 浏览器 MCP Agent | 浏览器交互、工具调用 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/browser_mcp_agent/README.md) |
| 多 MCP 服务协作 | 多服务、工具协作 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/multi_mcp_agent/README.md) |
| 多 Agent 研究团队 | 信息研究、角色协作 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/multi_agent_researcher/README.md) |
| 多 Agent 旅行规划 | 任务分工、行程组织 | [README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/README.md) |

## 使用与接口

网页“教材与案例”新增案例卡片；点击直接打开案例目录并选择该集合提问，再次点击仍打开目录，可通过范围下拉框恢复全部教材。“浏览实战案例”快捷入口只打开目录，不改写问题或提问范围。案例目录按中文标题、主题或路径搜索，只展示案例；每个案例显示英文标记、主题、原文与固定版本实现入口。“完整目录”重置搜索与案例筛选，显示全部 216 篇。默认“全部教材”包含课程与案例，保持原聊天布局和手机样式。

`/api/library` 保留原字段，增加集合/章节 `kind`，案例章节包含 `topics` 和 `implementation_links`。相关元数据纳入 v2 快照哈希；实现路径须属于该案例目录、使用固定提交，未知集合返回 422。网页和 CLI 使用同一范围。

检索保持关键词基线，补充混合检索、重排、纠错、知识图谱、故障诊断等中英别名，使用中文章节标题辅助召回。概念取证过滤遮罩后只剩标题的片段，原文检索仍可访问；代码块不会进入概念讲解提示。每个集合最多两个证据、全范围最多八个，讲解仍最多调用一次模型。

## 2026-10-10 验证

78 项后端测试、12 项前端测试及依赖/语法检查通过。新增测试覆盖第五个案例集合、主题搜索、固定版本实现链接、英文标记、中文案例检索、未知集合拒绝、五集合总证据上限、模型替身只调用一次、元数据篡改拒绝、实现入口路径校验、代码保留不执行和仅标题片段过滤。

全部 216 篇核对 SHA-256、字节数、Git blob 与索引契约；位置范围覆盖全部非空白原文。对照前一快照确认原 204 篇、4082 个片段相同。再次运行 `case_import.py` 复用快照及索引，网络请求为 0。

12 个案例使用中文目录标题定向检索，前两个证据中均命中对应案例，并回查固定原文件行号。该抽查使用了已知标题，只验证定向召回与引用位置，**不是独立题集或答案质量评测**；例如知识图谱查询可能先命中准备条件，旅行规划可能先命中目标介绍，不能据此保证答案完整。所有生成测试使用离线替身，真实模型调用为 0；README 中的功能/效果属于上游说明，未经过本项目运行验收。

详细报告保存在忽略提交的 `data/courses-cases-20261010-v1/coverage.json`、`data/cases-inventory.json`、`output/case-retrieval-check.json` 与 `output/case-verification.log`。账号库继续使用 `output/users.sqlite3`；不修改账号和讨论表结构，不把私有数据写入文档。

切换后本机 `/api/library` 返回 200，确认五个集合、216 篇、4220 个片段，以及案例集合的 12 篇英文标记与 17 个实现链接；网页已实际加载案例卡片和范围选项。六张账号相关表的记录内容与切换前一致。服务运行状态是当日检查结果，后续接手需重新确认。

## 复现与回退

### 同日案例入口修复验证

用户反馈案例按钮点不开：原卡片仅切换提问范围，原快捷按钮仅填入示例问题，均未打开案例目录。本次调整两个入口后，`node --check static/app.js` 与 14 项前端测试通过；新增/更新覆盖匿名浏览、保留问题及范围、重复打开、案例限定搜索、完整目录恢复全部和旧课程语料禁用案例入口。实际本机浏览器确认 12 个案例与固定版本链接，搜索“重排”命中 1 个案例，完整目录显示 216 篇；390px 宽度的目录无横向溢出。账号、教材、后端和模型均未改动或调用，静态文件刷新即生效。Impeccable 检测器提示目录标题前的 44px 图标块；对照截图，该控件为现有关闭按钮，无新增图标卡片，故保留。

以下为原导入流程的复现与回退说明。

已有当前快照时校验/重复导入不会下载或请求模型：

```powershell
.\verify.ps1
.\.venv\Scripts\python.exe starter.py import
.\.venv\Scripts\python.exe case_import.py
.\.venv\Scripts\python.exe starter.py search '混合检索 RAG 案例' --book awesome-llm-apps-cases
.\.venv\Scripts\python.exe starter.py search '浏览器 MCP' --book awesome-llm-apps-cases
```

新环境没有快照时，默认 `starter.py import` 可直接按照已保存的 v2 清单下载并校验 216 篇，不需要执行案例项目。需要重新审计时先按 [四套课程复现说明](course-expansion-2026-10-10.md) 准备前一快照，再运行 `case_import.py --discover`。固定提交和首批案例清单在 `case_import.py`，变更清单必须另建快照。

回退到四套课程：确认无进行中的讲解，执行 `.\stop.ps1`；将 `study_rag/settings.py` 默认来源和目录改回 `sources-expanded.json` 与 `data/courses-20261010-v1`，离线核对后执行 `.\background.ps1`。旧快照保留，网页自动恢复四套；不要回滚或重置账号库。

回到 [README](../README.md)。
