# 案例04 混合检索与重排（Hybrid RAG）

混合检索后重排，再决定回答依据

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合观察多路召回、重排和生成之间的接口。上游使用 RAGLite、Streamlit、嵌入服务、Cohere 重排与 Anthropic 生成，配置比基础练习多。

## 架构

> 流程：上传PDF → insert_document → hybrid_search → retrieve_chunks → rerank_chunks → rag生成

## 关键代码与机制

main.py 的 initialize_config 构建 RAGLiteConfig。固定实现写有嵌入模型 text-embedding-3-large 和 Cohere reranker，模型与服务名称属于该快照。perform_search 先 hybrid_search 取10个候选，再 retrieve_chunks，再 rerank_chunks。

主界面保存配置、导入文档，并在查询时调用 perform_search。若没有候选，handle_fallback 直接调用通用模型回答。这个回退会改变回答依据：用户若以为答案始终来自上传资料，就容易把常识答复当成有来源的结论。

数据库默认可使用本地 SQLite，README 同时介绍外部数据库选项。先用最小本地路径排除数据库连通问题，再检查嵌入、重排与生成三个服务。任何一层失败都应单独显示，不要统一写成模型错误。

## 环境依赖

固定 requirements 包含 raglite==0.2.1、Streamlit、rerankers、Cohere 与相关模型客户端。需要嵌入、生成与重排三类账户配置。上游依赖存在固定与范围混用，实际安装仍需验证。

<!-- pagebreak -->

# 实验卡04 混合检索与重排（Hybrid RAG）

## 复现步骤

安装固定目录的 requirements，并按 README 安装其指定的 spaCy 模型包。该外部包应自行检查官方来源后安装。启动：
```bash
python -m pip install -r requirements.txt
streamlit run main.py
```
在侧栏配置三类密钥与数据库路径，上传公开PDF，再先问一个明确写在文档中的事实。

## 结果与故障核对

保存候选与重排结果，观察正确片段是否进入最终上下文。另问一个文档没有答案的问题，确认回退答复是否被明确标注。课程未测量重排带来的效果或延迟。

## 扩展练习

为这个案例设计“仅依据文档”开关，说明无候选时应怎样返回。

## 参考答案

开启时，无候选或证据不足就返回说明，不调用通用知识回退；关闭时允许回退，但答案必须标明资料外信息，并与文档结论区分。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/hybrid_search_rag/README.md)

- [main.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/hybrid_search_rag/main.py) | Git blob：07af8a0cc47ce06e038ff99626c53ae7bd946620

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
