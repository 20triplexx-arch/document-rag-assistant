# 案例06 带推理的 Agentic RAG

推理工具与知识检索是两项能力

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合观察 Agent 在知识库上组织回答。上游将 Agno、LanceDB、OpenAI 嵌入、Gemini 生成与 ReasoningTools 组合，教学重点是信息流和证据检查。

## 架构

> 流程：URL资料 → Knowledge/LanceDB → 向量检索 → Agent与推理工具 → 流式答复与引用

## 关键代码与机制

rag_reasoning_agent.py 的 load_knowledge 建立 LanceDb，search_type 为 vector，嵌入器为 OpenAIEmbedder。load_agent 将该知识库与 Gemini 模型、ReasoningTools 组合。它不是关键词检索与向量融合的演示。

页面 state 保存 knowledge_urls 与 urls_loaded，避免同一页面状态反复导入。加载资料使用远程URL，新增URL后立即导入；若URL内容发生变化，仍要考虑索引如何更新，不能仅靠“已加载”集合判断版本。

流式界面收集答案与 citations；引用字段是否出现，取决于框架和模型响应。推理工具帮助组织过程，不会自动证明最终结论。阅读时把“有推理展示”与“证据支持了回答”分别检查。

## 环境依赖

Agno、Streamlit、LanceDB、Google模型与嵌入服务。需要 Google 和嵌入服务密钥。资料抓取与模型请求均可能联网，不能把此案例称为完全本地。

<!-- pagebreak -->

# 实验卡06 带推理的 Agentic RAG

## 复现步骤

在案例目录安装 requirements，启动：
```bash
python -m pip install -r requirements.txt
streamlit run rag_reasoning_agent.py
```
填入两类密钥，使用公开URL，确认导入成功后提问。所有模型名与数据库接口都需按实际依赖版本复核。

## 结果与故障核对

记录检索来源、最终断言与引用。测试一个跨段落问题和一个资料外问题。不要把模型展示的推理文本直接视作真实内部过程或正确性证明。

## 扩展练习

给一次回答分别评“是否有引用”“引用是否支持结论”“是否遗漏例外”三项。

## 参考答案

三项独立记录，不能用一项替代其余两项。例如有URL但原文没有相关条件，引用存在通过，支持性不通过。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/agentic_rag_with_reasoning/README.md)

- [rag_reasoning_agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/agentic_rag_with_reasoning/rag_reasoning_agent.py) | Git blob：336c7a4afce1131f82d443b0cf963d8ed2593eb6

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
