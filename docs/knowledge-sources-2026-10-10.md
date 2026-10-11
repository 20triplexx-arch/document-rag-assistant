# AI Agent 学习资料候选 · 2026-10-10

调研日期：2026-10-10（Asia/Shanghai）。用户希望扩展“学有据”的知识面，要求在 GitHub 寻找高星 AI Agent 学习项目。

本轮以约 1 万星以上为筛选基线，结合课程正文、实践案例和对原有两本教材的补充价值选择候选。星数是调研时访问 GitHub 仓库首页显示的约数，会随时间变化；这不是 GitHub 全站排名。用户随后确认首批仅接入 Microsoft 与 Hugging Face，RAG_Techniques 留待下一批。

状态更新（2026-10-10）：Microsoft 19 篇与 Hugging Face 60 篇教学正文已按固定提交导入；当前默认四套教材合计 204 篇、4082 个片段，新增篇目均有中文文件。版本、语言与许可审计及验证见 [首批扩库记录](course-expansion-2026-10-10.md)。以下主表保留调研时星数，不执行教材代码、不安装课程框架，扩库验证未调用真实模型；其他候选尚未导入。

后续案例更新（同日）：用户选择 GitHub 实战案例入库，awesome-llm-apps 已锁定 `4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2` 并导入 12 个英文案例 README、提供 17 个实现入口链接；当前四套课程加案例共 216 篇、4220 个片段。见 [首批案例记录](case-import-2026-10-10.md)。RAG_Techniques 与其他候选继续留待后续批次。

## 高星候选

| 项目与一手来源 | Stars（约） | 类型 | 可补充的学习内容 |
| --- | --- | --- | --- |
| [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) | 141.0k | 应用案例集合 | Agent、RAG、MCP、多 Agent 团队、语音与实际应用案例 |
| [dair-ai/Prompt-Engineering-Guide](https://github.com/dair-ai/Prompt-Engineering-Guide) | 79.0k | 方法指南 | 提示词、上下文工程、RAG 和 Agent 相关方法；有中文页面 |
| [microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners) | 76.8k | 系统课程 | 18 课覆盖工具使用、规划、多 Agent、Agentic RAG、记忆、生产与安全；提供简体中文翻译 |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 43.0k | 框架及官方文档 | 状态编排、持久执行、人工介入、短期与长期记忆 |
| [huggingface/agents-course](https://github.com/huggingface/agents-course) | 33.4k | 系统课程 | Agent 基础、smolagents/LangGraph/LlamaIndex、应用与带基准的最终实践；有中文目录 |
| [NirDiamant/RAG_Techniques](https://github.com/NirDiamant/RAG_Techniques) | 29.7k | 专题教程 | 分块、混合检索、重排、查询处理、Graph RAG 与 Agentic RAG |
| [NirDiamant/GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents) | 24.5k | Agent 实践教程 | 50 多项教程及实现，涵盖工具、反思、任务编排与多 Agent 系统 |
| [datawhalechina/llm-universe](https://github.com/datawhalechina/llm-universe) | 14.1k | 中文应用课程 | 知识库搭建、向量数据库、RAG 应用及评估优化；属于相邻基础内容 |

## 建议优先级与正文入口

1. **Microsoft AI Agents for Beginners**：适合作为第三套系统课程，先筛选工具使用、规划、多 Agent、上下文、记忆和安全等章节。以各课 Markdown 正文为主要入口；中文翻译与英文原文需按锁定版本核对对应关系，不同时导入多份语言镜像。代码练习主要围绕 Microsoft Agent Framework/Foundry，阅读课程不等于当前项目已接入这些服务。来源：[课程首页](https://github.com/microsoft/ai-agents-for-beginners)。
2. **Hugging Face Agents Course**：补充不同框架视角和课程实践。调研时查看了 [中文目录](https://github.com/huggingface/agents-course/tree/main/units/zh-CN) 与 [英文目录](https://github.com/huggingface/agents-course/tree/main/units/en)。首批已逐章核对固定版本的 60 篇教学正文，中文均存在，bonus-unit2 与 bonus_unit2 显式对应；后续上游变化需要重新审计。来源：[课程说明](https://github.com/huggingface/agents-course)。
3. **RAG_Techniques**：优先筛选混合检索、重排、分块和查询处理，能补充当前关键词检索基线的学习内容。正文大量位于 [教程 Notebook](https://github.com/NirDiamant/RAG_Techniques/tree/main/all_rag_techniques)，需提取 Markdown 单元并保留单元位置；案例中的技术效果不能直接当作“学有据”的验证结果。来源：[技术目录](https://github.com/NirDiamant/RAG_Techniques)。
4. **GenAI_Agents**：补充工具、反思和多 Agent 实践，以 [教程目录](https://github.com/NirDiamant/GenAI_Agents/tree/main/all_agents_tutorials) 为候选入口，优先选择有完整解释的案例，避免只索引仓库首页的简短介绍。来源：[项目说明](https://github.com/NirDiamant/GenAI_Agents)。

其余项目保留为第二批：awesome-llm-apps 提供应用广度，Prompt-Engineering-Guide 补充方法，LangGraph 官方文档补充工程细节，llm-universe 补充中文 RAG 基础。Prompt-Engineering-Guide 的 [pages](https://github.com/dair-ai/Prompt-Engineering-Guide/tree/main/pages) 包含 MDX 和中文页面，不能假定所有专题都已有完整中文版本。llm-universe 首页仍将进阶部分标为创作中，不能把目录中列出的规划内容算作已完成教材。

## 来源许可与筛选记录

本次查看的仓库首页声明：Microsoft、Prompt-Engineering-Guide、LangGraph 为 MIT；awesome-llm-apps、Hugging Face Agents Course 为 Apache-2.0。正式导入时仍须保存锁定提交的许可文件及所选内容的单独声明。

[GenAI_Agents 的 LICENSE](https://github.com/NirDiamant/GenAI_Agents/blob/main/LICENSE) 和 [RAG_Techniques 的 LICENSE](https://github.com/NirDiamant/RAG_Techniques/blob/main/LICENSE) 是自定义协议，写有非商业使用、署名及商业使用需事先书面许可等条款，不能按 MIT 记录。llm-universe 的许可本轮尚未确认，保留候选身份，正式入库前需查明所选正文的许可。

补充筛选事实：[anthropics/courses](https://github.com/anthropics/courses) 约 22.9k 星，但首页显示已于 2026-09-15 归档，本轮未列入首批；[langchain-academy](https://github.com/langchain-ai/langchain-academy) 约 2.9k 星、[agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch) 约 2.4k 星，作为专题补充保留，不列入本轮高星主表。

## 后续批次所需工作

- 从候选中确定实际来源，锁定提交 SHA、正文清单、语言、来源链接和许可，保留原文与哈希；新语料建立独立快照，不覆盖旧教材或用户库。
- 首批已加入 MDX 的等长遮罩和原文位置保留；Notebook 尚未支持，下一批需提取 Markdown 单元并保留单元位置。不执行代码、不把图片或视频链接标成已解析正文；本轮不调用模型翻译。
- Web 与 CLI 范围已改为当前语料驱动，目录与许可来自 v2 教材清单；未来新增来源仍需明确筛选与章节语言对应关系、许可原文、Git blob，并建立独立快照。
- 新课程已完成检索及原文位置抽查；语料扩大与答案质量提升分开验收，首批导入不改变答案支持尚未通过验收的结论。

回到 [项目 README](../README.md)。
