# 八主题逐题复核 · 2026-10-14

复核者：本轮 AI 助手依据固定原文检查。不是人工审批或人类正确率。输出格式/引文通过不等于内容验收。

最终 8 题仅 4 题产生有效输出，其余被拦截；有效输出还存在偏题、具体内容不足等问题。保留旧默认，不增加模型调用。

冻结验收检索仅覆盖 10/23 个已标注必要要点，完整可答 1/6；不能以开发题 70/72 宣称已能解决新场景。未判定证据不自动算错。

| 阶段 | 题号 | 输出 | 本次检索已标注支持 | 复核发现 |
| --- | --- | --- | --- | --- |
| baseline | CTX-D1 | 已拦截：quote_source | 未统计 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| baseline | CTX-D2 | 有效结构/出处 | 未统计 | 指出窗口限制和摘要，trim/delete 未检索到；重复且有拼写错误 simmarize。 |
| baseline | MCP-D1 | 有效结构/出处 | 未统计 | 角色概念基本有依据，但未找到当前规范版本/能力处理正文。 |
| baseline | MCP-D2 | 有效结构/出处 | 未统计 | 把应用实例的外部状态持久化/水平扩展推成 MCP 协议机制，缺少两版规范正文。 |
| baseline | MEM-D1 | 有效结构/出处 | 未统计 | 错误断言短期记忆重启后不会保留，并把长期记忆概括为保留全部历史，与 thread/checkpointer 和 namespace 的来源对象混淆。 |
| baseline | MEM-D2 | 有效结构/出处 | 未统计 | 本轮没有源码证据，选择不足回答，未伪称运行。 |
| baseline | MULTI-D1 | 有效结构/出处 | 未统计 | 只有 subagent 依据时给出部分答案，handoff 缺口明确；未解决完整比较。 |
| baseline | MULTI-D2 | 有效结构/出处 | 未统计 | 说明隔离与回传结果；追加上下文中毒建议与当前问题关系弱。 |
| baseline | OBS-D1 | 有效结构/出处 | 未统计 | 用其他框架的 run 定义代替 LangSmith，最终虽指出资料缺口，但前面的对象混用已经影响教学。 |
| baseline | OBS-D2 | 有效结构/出处 | 未统计 | 观测与评测区分基本清楚；追加收据/schema 示例超过用户所问。 |
| baseline | PLAN-D1 | 已拦截：quote_source | 未统计 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| baseline | PLAN-D2 | 有效结构/出处 | 未统计 | 资料只列 harness 能力但仍作机制推演；最终缺口说明不能替代前面推演的明确标注。 |
| baseline | RAG-D1 | 有效结构/出处 | 未统计 | 把复杂 Agent 的数十/上百次串行调用泛化为 Agentic RAG 的定义性延迟条件，且未完整比较。 |
| baseline | RAG-D2 | 已拦截：quote_source | 未统计 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| baseline | TOOL-D1 | 有效结构/出处 | 未统计 | 工具调用工作单与宿主执行的核心链有依据；依赖代码式段落，原始概念过滤仍有局限。 |
| baseline | TOOL-D2 | 有效结构/出处 | 未统计 | 没有源码时拒绝推测 divide 的实现，缺口说明合理；不能因此断言整个仓库没有函数。 |
| candidate | CTX-D1 | 有效结构/出处 | 3/3 | 三种上下文及瞬态/持久边界有依据；展开较长，重复模型/工具/生命周期区分，可精简。 |
| candidate | CTX-D2 | 有效结构/出处 | 3/3 | 主要机制与信息损失取舍有依据；长段解释后又重复三条摘要，篇幅需精简。 |
| candidate | CTX-D3 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MCP-D1 | 有效结构/出处 | 3/3 | 采用 2026-07-28，每请求元数据有依据；额外错误码细节超过初学者所问范围。 |
| candidate | MCP-D2 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MCP-D3 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MEM-D1 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MEM-D2 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MEM-D3 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MULTI-D1 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | MULTI-D2 | 有效结构/出处 | 3/3 | 输入隔离与最终输出机制有依据；最后追加 handoff 规则，应限定其具体模式，避免泛化到所有返回。 |
| candidate | MULTI-D3 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | OBS-D1 | 有效结构/出处 | 3/3 | run/trace/thread 对象已正确区分，例子有依据；末段 LangChain 工具说明与本题关系弱。 |
| candidate | OBS-D2 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | OBS-D3 | 有效结构/出处 | 3/3 | 正确指出案例不是指标采集器；表格三阶段映射部分为综合解释，未清晰标注推演，仍不能当作案例自带分阶段实现。 |
| candidate | PLAN-D1 | 有效结构/出处 | 3/3 | ReAct 与静态计划的核心区别、适用条件和未提供动态重规划的缺口有依据。 |
| candidate | PLAN-D2 | 有效结构/出处 | 3/3 | 三种能力、todo 非完成证明有依据；实际完成校验细节缺失说明合理；可以进一步减少重复。 |
| candidate | PLAN-D3 | 已拦截：quote_source | 3/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | RAG-D1 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | RAG-D2 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | RAG-D3 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | TOOL-D1 | 已拦截：quote_source | 1/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| candidate | TOOL-D2 | 有效结构/出处 | 3/3 | 首句仍称 divide 内部处理，紧接着才说没有 divide，前提纠正前后矛盾；源码引用存在不代表解释正确。 |
| candidate | TOOL-D3 | 有效结构/出处 | 3/3 | 第二段把工具描述列入模型生成部分，混淆开发者定义 schema/描述与模型生成实参；存在关键对象混淆。 |
| oracle | CTX-D1 | 有效结构/出处 | 3/3 | 三种上下文与瞬态/持久范围由表格正文支持；适合基础解释。 |
| oracle | MCP-D1 | 有效结构/出处 | 3/3 | 明确 2026-07-28 和三个组件，能力按每请求处理，未混入旧初始化流程。 |
| oracle | MEM-D1 | 有效结构/出处 | 3/3 | thread/checkpointer 与 namespace 的跨讨论差异有依据；回答直接且具体。 |
| oracle | MULTI-D1 | 有效结构/出处 | 3/3 | 控制权、持久状态变量和选择条件有依据；仍有定义与列表重复。 |
| oracle | OBS-D1 | 有效结构/出处 | 3/3 | LangSmith run/trace/thread 关系有依据，示意没有声称已实际运行。 |
| oracle | PLAN-D1 | 有效结构/出处 | 3/3 | 反应式循环与静态计划区别有依据，工具结果变化与未提供重规划的缺口明确。 |
| oracle | RAG-D1 | 有效结构/出处 | 3/3 | 主流程、模型决策与延迟条件有依据；列表与开头略重复。 |
| oracle | TOOL-D1 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| retest | MCP-D2 | 有效结构/出处 | 3/3 | 版本区分改善，但把旧逻辑会话表述成连接边界，现有证据不能支持；细节明显过多。最终提示补了限制，未追加开发复测。 |
| retest | MEM-D2 | 有效结构/出处 | 3/3 | 已改用实际 Python 源码，纠正 README 的 initialize 示意；初始化、查找和创建有依据，代码摘录不是独立脚本，未执行。 |
| retest | RAG-D1 | 有效结构/出处 | 3/3 | 控制权、执行顺序、延迟预测及检索延迟限制有依据；开头与列表略重复。 |
| retest | TOOL-D1 | 有效结构/出处 | 1/3 | 工具完整循环和结果对应有依据；并行 return_direct、多模态及 MCP 输入请求是未问的扩展，表格再次重复正文，篇幅与聚焦尚未达标。 |
| acceptance | CTX-A1 | 有效结构/出处 | 0/3 | 把用户假设的学习情境解释成实验中的 DISCUSSION_CONTEXT 为空，泄露无关实现细节；主要展开 MCP 规范而非上下文选择，关键子问题未被充分解决。 |
| acceptance | MCP-A1 | 已拦截：quote_source | 0/2 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| acceptance | MEM-A1 | 已拦截：quote_source | 1/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| acceptance | MULTI-A1 | 有效结构/出处 | 2/3 | 模式选择和上下文边界有依据；直接套通用多领域示例，研究报告流程的具体输入/输出安排不足，handoff 消息建议不应泛化为绝对限制。 |
| acceptance | OBS-A1 | 已拦截：quote_source | 2/3 | 输出被 quote_source 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| acceptance | PLAN-A1 | 已拦截：response_schema | 3/3 | 输出被 response_schema 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。 |
| acceptance | RAG-A1 | 有效结构/出处 | 2/3 | 识别 yes/no、异常保留文档、改写/搜索路径，能解释主流程；但空检索后“不设 run_web_search”的表述不精确（grade_documents 默认返回 No），仍需修正说明。 |
| acceptance | TOOL-A1 | 有效结构/出处 | 0/3 | 输出有效但没有检索到工具规范的人在环/确认段落，未给出所需具体确认边界；泛化为先协商能力还可能混淆 2026 无状态模型，未通过质量验收。 |

实验边界：
- 旧/新端到端使用不同语料及提示，不能把差异归因于单独检索因素。
- 同语料 BM25/E5 RRF 对照仅为离线检索消融。
- 8 次充分支持上下文生成使用 v1.1 提示，24 次候选使用 v1 提示；提示同时变化，不是干净的检索因果对照。
- 4 次复测使用 v1.2，最终 8 题冻结为 v1.3。最终提示的开发题覆盖未全部重跑。
- 新标注来自 AI 原文复核，无人工审批；新题未额外标注干扰段落，未判定不能自动算错。
- 同主题的综合验收题仍复用基础概念，样本很小，不能据此给出人类正确率。
- 汇总修正部分可答题的完整题统计：完整覆盖已知支持不等于完整可回答；原始排名、位置及历史运行文件保留。
- 部分初版实现只保存代码哈希，输入、证据及原始输出可复核，不能用最终代码复现所有历史阶段。
